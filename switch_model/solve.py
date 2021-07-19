#!/usr/bin/env python
# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
from __future__ import print_function

from pyomo.environ import *
from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition, SolutionStatus
import pyomo.version
import pandas as pd

import sys, os, shlex, re, inspect, textwrap, types, pickle, traceback, gc
import warnings
import datetime
import platform

from pyomo.solvers.plugins.solvers.direct_or_persistent_solver import DirectOrPersistentSolver

import switch_model
from switch_model.utilities import (
    create_model, _ArgumentParser, StepTimer, make_iterable, LogOutput, warn, query_yes_no,
    get_module_list, add_module_args, _ScaledVariable, add_git_info
)
from switch_model.upgrade import do_inputs_need_upgrade, upgrade_inputs
from switch_model.tools.graph.cli_graph import main as graph_main
from switch_model.utilities.results_info import save_info, add_info, ResultsInfoSection


def main(args=None, return_model=False, return_instance=False, attach_data_portal=False):
    start_to_end_timer = StepTimer()
    timer = StepTimer()
    if args is None:
        # combine default arguments read from options.txt file with
        # additional arguments specified on the command line
        args = get_option_file_args(extra_args=sys.argv[1:])

    # Parse the --recommended and --recommended-debug flags to replace them with their placeholder
    args = parse_recommended_args(args)

    # Get options needed before any modules are loaded
    pre_module_options = parse_pre_module_options(args)

    # turn on post-mortem debugging mode if requested
    # (from http://stackoverflow.com/a/1237407 ; more options available there)
    if pre_module_options.debug:
        def debug(type, value, tb):
            import traceback
            try:
                from ipdb import pm
            except ImportError:
                from pdb import pm
            traceback.print_exception(type, value, tb)
            pm()
        sys.excepthook = debug

    # Write output to a log file if logging option is specified
    if pre_module_options.log_run_to_file:
        logs_dir = pre_module_options.logs_dir
    else:
        logs_dir = None # disables logging

    with LogOutput(logs_dir):

        # Look out for outdated inputs. This has to happen before modules.txt is
        # parsed to avoid errors from incompatible files.
        parser = _ArgumentParser(allow_abbrev=False, add_help=False)
        add_module_args(parser)
        module_options = parser.parse_known_args(args=args)[0]

        if not os.path.exists(module_options.inputs_dir):
            raise NotADirectoryError(
                "Inputs directory '{}' does not exist".format(module_options.inputs_dir))

        if do_inputs_need_upgrade(module_options.inputs_dir):
            do_upgrade = query_yes_no(
                "Warning! Your inputs directory needs to be upgraded. "
                "Do you want to auto-upgrade now? We'll keep a backup of "
                "this current version."
            )
            if do_upgrade:
                upgrade_inputs(module_options.inputs_dir)
            else:
                print("Inputs need upgrade. Consider `switch upgrade --help`. Exiting.")
                return -1

        # build a module list based on configuration options, and add
        # the current module (to register define_arguments callback)
        modules = get_module_list(args)

        # Patch pyomo if needed, to allow reconstruction of expressions.
        # This must be done before the model is constructed.
        patch_pyomo()

        # Define the model
        model = create_model(modules, args=args)

        # Add any suffixes specified on the command line (usually only iis)
        add_extra_suffixes(model)

        # return the model as-is if requested
        if return_model and not return_instance:
            return model

        if model.options.reload_prior_solution:
            # TODO: allow a directory to be specified after --reload-prior-solution,
            # otherwise use outputs_dir.
            if not os.path.isdir(model.options.outputs_dir):
                raise IOError("Directory specified for prior solution does not exist.")

        add_info("Host name", platform.node(), section=ResultsInfoSection.GENERAL)
        add_git_info()

        # get a list of modules to iterate through
        iterate_modules = get_iteration_list(model)

        if model.options.verbose:
            print("\n=======================================================================")
            print("Switch {}, http://switch-model.org".format(switch_model.__version__))
            print("=======================================================================")
            print("Arguments:")
            print(", ".join(k + "=" + repr(v) for k, v in model.options.__dict__.items() if v))
            print("Modules:\n"+", ".join(m for m in modules))
            if iterate_modules:
                print("Iteration modules:", iterate_modules)
            print("=======================================================================\n")
            print(f"Model created in {timer.step_time_as_str()}.")

        # create an instance (also reports time spent reading data and loading into model)
        instance = model.load_inputs(attach_data_portal=attach_data_portal)

        #### Below here, we refer to instance instead of model ####

        instance.pre_solve()
        if instance.options.verbose:
            print(f"Total time spent constructing model: {timer.step_time_as_str()}.\n")

        if instance.options.enable_breakpoints:
            print("Breaking after constructing model.  See "
                  "https://docs.python.org/3/library/pdb.html for instructions on using pdb.")
            breakpoint()

        # return the instance as-is if requested
        if return_instance:
            if return_model:
                return (model, instance)
            else:
                return instance

        # make sure the outputs_dir exists (used by some modules during iterate)
        # use a race-safe approach in case this code is run in parallel
        try:
            os.makedirs(instance.options.outputs_dir)
        except OSError:
            # directory probably exists already, but double-check
            if not os.path.isdir(instance.options.outputs_dir):
                raise

        # We no longer need model (only using instance) so we can garbage collect it to optimize our memory usage
        del model

        if instance.options.warm_start:
            if instance.options.verbose:
                timer.step_time()
            warm_start(instance)
            if instance.options.verbose:
                print(f"Loaded warm start inputs in {timer.step_time_as_str()}.")

        if instance.options.reload_prior_solution:
            print('Loading prior solution...')
            reload_prior_solution_from_pickle(instance, instance.options.outputs_dir)
            if instance.options.verbose:
                print(f'Loaded previous results into model instance in {timer.step_time_as_str()}.')
        else:
            # solve the model (reports time for each step as it goes)
            if iterate_modules:
                if instance.options.verbose:
                    print("Iterating model...")
                iterate(instance, iterate_modules)
            else:
                # Cleanup iterate_modules since unused
                del iterate_modules
                # Garbage collect to reduce memory use during solving
                gc.collect()
                # Note we've refactored to avoid using the results variable in this scope
                # to reduce the memory use during post-solve
                solve(instance)
                gc.collect()

        if instance.options.enable_breakpoints:
            print("Breaking before post_solve. See "
                  "https://docs.python.org/3/library/pdb.html for instructions on using pdb.")
            breakpoint()

        # report results
        # (repeated if model is reloaded, to automatically run any new export code)
        if not instance.options.no_post_solve:
            if instance.options.verbose:
                timer.step_time()
                print("Executing post solve functions...")
            instance.post_solve()
            if instance.options.verbose:
                print(f"Post solve processing completed in {timer.step_time_as_str()}.")

        if instance.options.graph:
            graph_main(args=["--overwrite"])

        total_time = start_to_end_timer.step_time_as_str()
        add_info("Total run time", total_time, section=ResultsInfoSection.GENERAL)

        add_info("End date", datetime.datetime.now().strftime('%Y-%m-%d'), section=ResultsInfoSection.GENERAL)
        add_info("End time", datetime.datetime.now().strftime('%H:%M:%S'), section=ResultsInfoSection.GENERAL)

        save_info(
            os.path.join(getattr(instance.options, "outputs_dir", "outputs"),
                         "info.txt")
        )

        if instance.options.verbose:
            print(f"Total time spent running SWITCH: {total_time}.")

    # end of LogOutput block

    if instance.options.interact or instance.options.reload_prior_solution:
        m = instance  # present the solved model as 'm' for convenience
        banner = (
            "\n"
            "=======================================================================\n"
            "Entering interactive Python shell.\n"
            "Abstract model is in 'model' variable; \n"
            "Solved instance is in 'instance' and 'm' variables.\n"
            "Type ctrl-d or exit() to exit shell.\n"
            "=======================================================================\n"
        )
        import code
        code.interact(banner=banner, local=dict(list(globals().items()) + list(locals().items())))


def warm_start(instance):
    """
    This function loads in the variables from a previous run
    and starts out our model at these variables to make it reach
    a solution faster.
    """
    warm_start_dir = os.path.join(instance.options.warm_start, "outputs")
    if not os.path.isdir(warm_start_dir):
        warnings.warn(
            f"Path {warm_start_dir} does not exist and cannot be used to warm start solver. Warm start skipped.")
        return

    # Loop through every variable in our model
    for variable in instance.component_objects(Var):
        scaled = isinstance(variable, _ScaledVariable)
        varname = variable.unscaled_name if scaled else variable.name
        scaling = variable.scaling_factor if scaled else 1

        filepath = os.path.join(warm_start_dir, varname + ".csv")
        if not os.path.exists(filepath):
            warnings.warn(f"Skipping warm start for set {varname} since {filepath} does not exist.")
            continue
        df = pd.read_csv(filepath, index_col=list(range(variable._index.dimen)))
        for index, val in df.iterrows():
            try:
                variable[index] = val[0] * scaling
            except (KeyError, ValueError):
                # If the index isn't valid that's ok, just don't warm start that variable
                pass


def reload_prior_solution_from_pickle(instance, outdir):
    with open(os.path.join(outdir, 'results.pickle'), 'rb') as fh:
        results = pickle.load(fh)
    instance.solutions.load_from(results)
    return instance


patched_pyomo = False
def patch_pyomo():
    global patched_pyomo
    if not patched_pyomo:
        patched_pyomo = True
        # patch Pyomo if needed

        # Pyomo 5.1.1 (and maybe others) is very slow to load prior solutions because
        # it does a full-component search for each component name as it assigns the
        # data. This ends up taking longer than solving the model. So we micro-
        # patch pyomo.core.base.PyomoModel.ModelSolutions.add_solution to use
        # Pyomo's built-in caching system for component names.
        # TODO: create a pull request for Pyomo to do this
        # NOTE: space inside the long quotes is significant; must match the Pyomo code
        old_code = """
                    for obj in instance.component_data_objects(Var):
                        cache[obj.name] = obj
                    for obj in instance.component_data_objects(Objective, active=True):
                        cache[obj.name] = obj
                    for obj in instance.component_data_objects(Constraint, active=True):
                        cache[obj.name] = obj"""
        new_code = """
                    # use buffer to avoid full search of component for data object
                    # which introduces a delay that is quadratic in model size
                    buf=dict()
                    for obj in instance.component_data_objects(Var):
                        cache[obj.getname(fully_qualified=True, name_buffer=buf)] = obj
                    for obj in instance.component_data_objects(Objective, active=True):
                        cache[obj.getname(fully_qualified=True, name_buffer=buf)] = obj
                    for obj in instance.component_data_objects(Constraint, active=True):
                        cache[obj.getname(fully_qualified=True, name_buffer=buf)] = obj"""

        from pyomo.core.base.PyomoModel import ModelSolutions
        add_solution_code = inspect.getsource(ModelSolutions.add_solution)
        if old_code in add_solution_code:
            # create and inject a new version of the method
            add_solution_code = add_solution_code.replace(old_code, new_code)
            replace_method(ModelSolutions, 'add_solution', add_solution_code)
        elif pyomo.version.version_info[:2] >= (5, 0):
            print(
                "NOTE: The patch to pyomo.core.base.PyomoModel.ModelSolutions.add_solution "
                "has been deactivated because the Pyomo source code has changed. "
                "Check whether this patch is still needed and edit {} accordingly."
                .format(__file__)
            )

def replace_method(class_ref, method_name, new_source_code):
    """
    Replace specified class method with a compiled version of new_source_code.
    """
    orig_method = getattr(class_ref, method_name)
    # compile code into a function
    workspace = dict()
    exec(textwrap.dedent(new_source_code), workspace)
    new_method = workspace[method_name]
    # create a new function with the same body, but using the old method's namespace
    new_func = types.FunctionType(
        new_method.__code__,
        orig_method.__globals__,
        orig_method.__name__,
        orig_method.__defaults__,
        orig_method.__closure__
    )
    # note: this normal function will be automatically converted to an unbound
    # method when it is assigned as an attribute of a class
    setattr(class_ref, method_name, new_func)


def reload_prior_solution_from_csvs(instance):
    """
    Assign values to all model variables from <variable>.csv files saved after
    previous solution. (Not currently used.)
    """
    import csv
    var_objects = instance.component_objects(Var)
    for var in var_objects:
        var_file = os.path.join(instance.options.outputs_dir, '{}.csv'.format(var.name))
        if not os.path.isfile(var_file):
            raise RuntimeError(
                "Tab output file for variable {} cannot be found in outputs "
                "directory. Exiting.".format(var.name)
            )
        try:
            # check types of the first tuple of keys for this variable
            key_types = [type(i) for i in make_iterable(next(var.iterkeys()))]
        except StopIteration:
            key_types = []  # no keys
        with open(var_file,'r') as f:
            reader = csv.reader(f, delimiter=',')
            next(reader) # skip headers
            for row in reader:
                index = tuple(t(k) for t, k in zip(key_types, row[:-1]))
                try:
                    v = var[index]
                except KeyError:
                    raise KeyError(
                        "Unable to set value for {}[{}]; index is invalid."
                        .format(var.name, index)
                    )
                if row[-1] == '':
                    # Variables that are not used in the model end up with no
                    # value after the solve and get saved as blanks; we skip those.
                    continue
                val = float(row[-1])
                if v.is_integer() or v.is_binary():
                    val = int(val)
                v.value = val
        if instance.options.verbose:
            print('Loaded variable {} values into instance.'.format(var.name))


def iterate(m, iterate_modules, depth=0):
    """Iterate through all modules listed in the iterate_list (usually iterate.txt),
    if any. If there is no iterate_list, then this will just solve the model once.

    If it exists, the iterate_list contains one row per level of iteration,
    and each row contains a list of modules to test for iteration at that level
    (these can be separated with commas, spaces or tabs).
    The model will run through the levels like nested loops, running the lowest level
    till it converges, then advancing the next higher level by one step, then running the
    lowest level to convergence/completion again, repeating until all levels are complete.
    During each iteration, the pre_iterate() and post_iterate() functions of each specified
    module (if they exist) will be called before and after solving. When a module is
    converged or completed, its post_iterate() function should return True.
    All modules specified in the iterate_list should also be loaded via the module_list
    or include_module(s) arguments.
    """

    # create or truncate the iteration tree
    if depth == 0:
        m.iteration_node = tuple()

    if depth == len(iterate_modules):
        # asked to converge at the deepest level
        # just preprocess to reflect all changes and then solve
        m.preprocess()
        solve(m)
    else:
        # iterate until converged at the current level

        # note: the modules in iterate_modules were also specified in the model's
        # module list, and have already been loaded, so they are accessible via sys.modules
        # This prepends 'switch_model.' if needed, to be consistent with modules.txt.
        current_modules = [
            sys.modules[module_name if module_name in sys.modules else 'switch_model.' + module_name]
            for module_name in iterate_modules[depth]]

        j = 0
        converged = False
        while not converged:
            # take one step at the current level
            if m.options.max_iter is not None and j >= m.options.max_iter:
                break

            converged = True

            # pre-iterate modules at this level
            m.iteration_number = j
            m.iteration_node = m.iteration_node[:depth] + (j,)
            for module in current_modules:
                converged = iterate_module_func(m, module, 'pre_iterate', converged)

            # converge the deeper-level modules, if any (inner loop)
            iterate(m, iterate_modules, depth=depth+1)

            # post-iterate modules at this level
            m.iteration_number = j      # may have been changed during iterate()
            m.iteration_node = m.iteration_node[:depth] + (j,)
            for module in current_modules:
                converged = iterate_module_func(m, module, 'post_iterate', converged)

            j += 1
        if converged:
            print("Iteration of {ms} was completed after {j} rounds.".format(ms=iterate_modules[depth], j=j))
        else:
            print("Iteration of {ms} was stopped after {j} iterations without convergence.".format(ms=iterate_modules[depth], j=j))
    return

def iterate_module_func(m, module, func, converged):
    """Call function func() in specified module (if available) and use the result to
    adjust model convergence status. If func doesn't exist or returns None, convergence
    status will not be changed."""
    module_converged = None
    iter_func = getattr(module, func, None)
    if iter_func is not None:
        module_converged = iter_func(m)
    if module_converged is None:
        # module is not taking a stand on whether the model has converged
        return converged
    else:
        return converged and module_converged


def define_arguments(argparser):
    """callback function to define model configuration arguments while the model is built"""

    # These flags were already processed, we only re-add them here
    # so that they appear in the help text (switch solve --help)
    add_pre_module_args(argparser)
    add_module_args(argparser)
    add_recommended_args(argparser)

    # iteration options
    argparser.add_argument(
        "--iterate-list", default=None,
        help="Text file with a list of modules to iterate until converged (default is iterate.txt); "
             "each row is one level of iteration, and there can be multiple modules on each row"
    )
    argparser.add_argument(
        "--max-iter", type=int, default=None,
        help="Maximum number of iterations to complete at each level for iterated models"
    )

    # scenario information
    argparser.add_argument(
        "--scenario-name", default="", help="Name of research scenario represented by this model"
    )

    # note: pyomo has a --solver-suffix option but it is not clear
    # whether that does the same thing as --suffix defined here,
    # so we don't reuse the same name.
    argparser.add_argument("--suffixes", "--suffix", nargs="+", action='extend', default=['rc','dual','slack'],
        help="Extra suffixes to add to the model and exchange with the solver (e.g., iis, rc, dual, or slack)")

    # Define solver-related arguments
    # These are a subset of the arguments offered by "pyomo solve --solver=cplex --help"
    argparser.add_argument("--solver", default="glpk",
        help='Name of Pyomo solver to use for the model (default is "glpk")')
    argparser.add_argument("--solver-manager", default="serial",
        help='Name of Pyomo solver manager to use for the model ("neos" to use remote NEOS server)')
    argparser.add_argument("--solver-io", default=None, help="Method for Pyomo to use to communicate with solver")
    # note: pyomo has a --solver-options option but it is not clear
    # whether that does the same thing as --solver-options-string so we don't reuse the same name.
    argparser.add_argument("--solver-options-string", default=None,
        help='A quoted string of options to pass to the model solver. Each option must be of the form option=value. '
            '(e.g., --solver-options-string "mipgap=0.001 primalopt=\'\' advance=2 threads=1")')
    argparser.add_argument("--keepfiles", action='store_true', default=None,
        help="Keep temporary files produced by the solver (may be useful with --symbolic-solver-labels)")
    argparser.add_argument(
        "--stream-output", "--stream-solver", action='store_true', dest="tee", default=None,
        help="Display information from the solver about its progress (usually combined with a suitable --solver-options-string)")
    argparser.add_argument(
        "--no-stream-output", "--no-stream-solver", action='store_false', dest="tee", default=None,
        help="Don't display information from the solver about its progress")
    argparser.add_argument(
        "--symbolic-solver-labels", action='store_true', default=None,
        help='Use symbol names derived from the model when interfacing with the solver. '
            'See "pyomo solve --solver=x --help" for more details.')
    argparser.add_argument("--tempdir", default=None,
        help='The name of a directory to hold temporary files produced by the solver. '
             'This is usually paired with --keepfiles and --symbolic-solver-labels.')
    argparser.add_argument(
        '--retrieve-cplex-mip-duals', default=False, action='store_true',
        help=(
            "Patch Pyomo's solver script for cplex to re-solve and retrieve "
            "dual values for mixed-integer programs."
        )
    )
    argparser.add_argument(
        '--gurobi-find-iis', default=False, action='store_true',
        help='Make Gurobi compute an irreducible inconsistent subsystem (IIS) if the model is found to be infeasible. '
             'The IIS will be writen to outputs\\iis.ilp. Note this flag enables --symbolic-solver-labels since '
             'otherwise debugging would be impossible. To learn more about IIS read: '
             'https://www.gurobi.com/documentation/9.1/refman/py_model_computeiis.html.'
    )

    # NOTE: the following could potentially be made into standard arguments for all models,
    # e.g. by defining them in a define_standard_arguments() function in switch.utilities.py

    # Define input/output options
    # note: --inputs-dir is defined in add_module_args, because it may specify the
    # location of the module list (deprecated)
    # argparser.add_argument("--inputs-dir", default="inputs",
    #     help='Directory containing input files (default is "inputs")')
    argparser.add_argument(
        "--input-alias", "--input-aliases", dest="input_aliases", nargs='+', default=[],
        help='List of input file substitutions, in form of standard_file.csv=alternative_file.csv, '
        'useful for sensitivity studies with different inputs.')
    argparser.add_argument("--outputs-dir", default="outputs",
        help='Directory to write output files (default is "outputs")')

    # General purpose arguments
    argparser.add_argument(
        '--verbose', '-v', dest='verbose', default=False, action='store_true',
        help='Show information about model preparation and solution')
    argparser.add_argument(
        '--quiet', '-q', dest='verbose', action='store_false',
        help="Don't show information about model preparation and solution (cancels --verbose setting)")
    argparser.add_argument(
        '--no-post-solve', default=False, action='store_true',
        help="Don't run post-solve code on the completed model (i.e., reporting functions).")
    argparser.add_argument(
        '--reload-prior-solution', default=False, action='store_true',
        help='Load a previously saved solution; useful for re-running post-solve code or interactively exploring the model (via --interact).')
    argparser.add_argument(
        '--save-solution', default=False, action='store_true',
        help="Save the solution to a pickle file after model is solved to allow for later inspection via --reload-prior-solution.")
    argparser.add_argument(
        '--interact', default=False, action='store_true',
        help='Enter interactive shell after solving the instance to enable inspection of the solved model.')
    argparser.add_argument(
        '--enable-breakpoints', default=False, action='store_true',
        help='Break and enter the Python Debugger at key points during the solving process.'
    )
    argparser.add_argument(
        "--sig-figs-output", default=5, type=int,
        help='The number of significant digits to include in the output by default'
    )
    argparser.add_argument(
        "--zero-cutoff-output", default=1e-5, type=float,
        help="If the magnitude of an output value is less than this value, it is rounded to 0."
    )

    argparser.add_argument(
        "--sorted-output", default=False, action='store_true',
        dest='sorted_output',
        help='Write generic variable result values in sorted order')
    argparser.add_argument(
        "--graph", default=False, action='store_true',
        help="Automatically run switch graph after post solve"
    )

    argparser.add_argument(
        "--threads", type=int, default=None,
        help="Number of threads to be used while solving. Currently only supported for Gurobi"
    )

    argparser.add_argument(
        "--warm-start", default=None,
        help="Path to folder of directory to use for warm start"
    )


def add_recommended_args(argparser):
    """
    Adds the --recommended and --recommended-debug flags.
    These flags are aliases for a bunch of other existing flags that
    are recommended.
    """
    argparser.add_argument(
        "--recommended", default=False, action='store_true',
        help='Includes several flags that are recommended including --solver gurobi --verbose --stream-output and more. '
             'See parse_recommended_args() in solve.py for the full list of recommended flags.'
    )

    argparser.add_argument(
        "--recommended-fast", default=False, action='store_true',
        help='Equivalent to --recommended however disables crossover during solving. This reduces'
             ' the solve time greatly however may result in less accurate values and may fail to find an optimal'
             ' solution. If you find that the solver returns a suboptimal solution use --recommended.'
    )

    argparser.add_argument(
        "--recommended-debug", default=False, action='store_true',
        help='Equivalent to running with all of the following options: --solver gurobi -v --sorted-output --keepfiles --tempdir temp --stream-output --symbolic-solver-labels --log-run --debug --solver-options-string "method=2 BarHomogeneous=1 FeasibilityTol=1e-5"'
    )


def parse_recommended_args(args):
    argparser = _ArgumentParser(add_help=False, allow_abbrev=False)
    add_recommended_args(argparser)
    options = argparser.parse_known_args(args)[0]

    flags_used = options.recommended + options.recommended_fast + options.recommended_debug
    if flags_used > 1:
        raise Exception("Must pick between --recommended-debug, --recommended-fast or --recommended.")
    if flags_used == 0:
        return args

    # Note we don't append but rather prepend so that flags can override the --recommend flags.
    args = [
               '--solver', 'gurobi',
               '-v',
               '--sorted-output',
               '--stream-output',
               '--log-run',
               '--debug',
               '--graph',
           ] + args
    solver_options_string = "BarHomogeneous=1 FeasibilityTol=1e-5 method=2"
    if options.recommended_fast:
        solver_options_string += " crossover=0"
    args = ['--solver-options-string', solver_options_string] + args
    if options.recommended_debug:
        args = ['--keepfiles', '--tempdir', 'temp', '--symbolic-solver-labels'] + args

    return args


def add_pre_module_args(parser):
    """
    Add arguments needed before any modules are loaded.
    """
    parser.add_argument("--log-run", dest="log_run_to_file", default=False, action="store_true",
                        help="Log output to a file.")
    parser.add_argument("--logs-dir", dest="logs_dir", default="logs",
                        help='Directory containing log files (default is "logs"')
    parser.add_argument("--debug", action="store_true", default=False,
                        help='Automatically start pdb debugger on exceptions')


def parse_pre_module_options(args):
    """
    Parse and return options needed before modules are loaded.
    """
    parser = _ArgumentParser(allow_abbrev=False, add_help=False)
    add_pre_module_args(parser)
    pre_module_args = parser.parse_known_args(args=args)[0]

    return pre_module_args


def get_iteration_list(m):
    # Identify modules to iterate until convergence (if any)
    iterate_list_file = m.options.iterate_list
    if iterate_list_file is None and os.path.exists("iterate.txt"):
        iterate_list_file = "iterate.txt"
    if iterate_list_file is None:
        iterate_modules = []
    else:
        with open(iterate_list_file) as f:
            iterate_rows = f.read().splitlines()
            iterate_rows = [r.strip() for r in iterate_rows]
            iterate_rows = [r for r in iterate_rows if r and not r.startswith("#")]
        # delimit modules at the same level with space(s), tab(s) or comma(s)
        iterate_modules = [re.sub("[ \t,]+", " ", r).split(" ") for r in iterate_rows]
    return iterate_modules

def get_option_file_args(dir='.', extra_args=[]):

    args = []
    # retrieve base arguments from options.txt (if present)
    # note: these can be on multiple lines to ease editing,
    # and lines can be commented out with #
    options_path = os.path.join(dir, "options.txt")
    if os.path.exists(options_path):
        with open(options_path) as f:
            base_options = f.read().splitlines()
        for r in base_options:
            if not r.lstrip().startswith("#"):
                args.extend(shlex.split(r))
    args.extend(extra_args)
    return args

# Generic argument-related code; could potentially be moved to utilities.py
# if we want to make these standard parts of Switch.

def add_extra_suffixes(model):
    """
    Add any suffix objects requested in the configuration options.
    We assume they will be used for import or export of floating-point values
    note: modules that need suffixes should normally just create them (possibly
    checking whether they already exist first). Then solve() will automatically
    pass them to the solver.
    """
    for suffix in model.options.suffixes:
        if not hasattr(model, suffix):
            setattr(model, suffix, Suffix(direction=Suffix.IMPORT_EXPORT))


def solve(model):
    if hasattr(model, "solver"):
        solver = model.solver
        solver_manager = model.solver_manager
    else:
        # Create a solver object the first time in. We don't do this until a solve is
        # requested, because sometimes a different solve function may be used,
        # with its own solver object (e.g., with runph or a parallel solver server).
        # In those cases, we don't want to go through the expense of creating an
        # unused solver object, or get errors if the solver options are invalid.
        #
        # Note previously solver was saved in model however this is very memory inefficient.
        solver = SolverFactory(model.options.solver, solver_io=model.options.solver_io)

        # If this option is enabled, gurobi will output an IIS to outputs\iis.ilp.
        if model.options.gurobi_find_iis:
            # Enable symbolic labels since otherwise we can't debug the .ilp file.
            model.options.symbolic_solver_labels = True

            # If no string is passed make the string empty so we can add to it
            if model.options.solver_options_string is None:
                model.options.solver_options_string = ""

            # Add to the solver options 'ResultFile=iis.ilp'
            # https://stackoverflow.com/a/51994135/5864903
            iis_file_path = os.path.join(model.options.outputs_dir, "iis.ilp")
            model.options.solver_options_string += " ResultFile={}".format(iis_file_path)

        if model.options.threads:
            # If no string is passed make the string empty so we can add to it
            if model.options.solver_options_string is None:
                model.options.solver_options_string = ""

            model.options.solver_options_string += f" Threads={model.options.threads}"

        solver_manager = SolverManagerFactory(model.options.solver_manager)

    # get solver arguments
    solver_args = dict(
        options_string=model.options.solver_options_string,
        keepfiles=model.options.keepfiles,
        tee=model.options.tee,
        symbolic_solver_labels=model.options.symbolic_solver_labels,
        save_results=model.options.save_solution if isinstance(solver, DirectOrPersistentSolver) else None,
    )

    if model.options.warm_start is not None:
        solver_args["warmstart"] = True

    # drop all the unspecified options
    solver_args = {k: v for (k, v) in solver_args.items() if v is not None}

    # Automatically send all defined suffixes to the solver
    solver_args["suffixes"] = [
        c.name for c in model.component_objects(ctype=Suffix)
    ]

    # note: the next few lines are faster than the line above, but seem risky:
    # i = m._ctypes.get(Suffix, [None])[0]
    # solver_args["suffixes"] = []
    # while i is not None:
    #     c, i = m._decl_order[i]
    #     solver_args[suffixes].append(c.name)

    # patch Pyomo to retrieve MIP duals from cplex if needed
    if model.options.retrieve_cplex_mip_duals:
        retrieve_cplex_mip_duals()

    # solve the model
    if model.options.verbose:
        timer = StepTimer()
        print("Solving model...")

    if model.options.tempdir is not None:
        if not os.path.exists(model.options.tempdir):
            os.makedirs(model.options.tempdir)

        # from https://pyomo.readthedocs.io/en/stable/working_models.html#changing-the-temporary-directory
        from pyomo.common.tempfiles import TempfileManager
        TempfileManager.tempdir = model.options.tempdir

    # Cleanup memory before entering solver to use up as little memory as possible.
    gc.collect()
    results = solver_manager.solve(model, opt=solver, **solver_args)

    if model.options.verbose:
        print(f"Solved model. Total time spent in solver: {timer.step_time_as_str()}.")

    if model.options.enable_breakpoints:
        print("Breaking after solving model. See "
              "https://docs.python.org/3/library/pdb.html for instructions on using pdb.")
        breakpoint()

    solver_status = results.solver.status
    solver_message = results.solver.message
    termination_condition = results.solver.termination_condition
    solution_status = model.solutions[-1].status if len(model.solutions) != 0 else None

    if solver_status != SolverStatus.ok or termination_condition != TerminationCondition.optimal:
        warn(
            f"Solver termination status is not 'ok' or not 'optimal':\n"
            f"\t- Termination condition: {termination_condition}\n"
            f"\t- Solver status: {solver_status}\n"
            f"\t- Solver message: {solver_message}\n"
            f"\t- Solution status: {solution_status}"
        )

        if solution_status == SolutionStatus.feasible and solver_status == SolverStatus.warning:
            print("If you used --recommended-fast, you might want to try using just --recommended.")

        if query_yes_no("Do you want to abort and exit?", default=None):
            raise SystemExit()

    if model.options.verbose:
        print(f"\nOptimization termination condition was {termination_condition}.")
        if str(solver_message) != '<undefined>':
            print(f'Solver message: {solver_message}')
        print("")

    if model.options.save_solution:
        if model.options.verbose:
            timer.step_time()  # restart counter for next step
        save_results(model, model.options.outputs_dir)
        if model.options.verbose:
            print(f'Saved results in {timer.step_time_as_str()}.')

    # Save memory by not storing the solutions
    del model.solutions
    del results

def retrieve_cplex_mip_duals():
    """patch Pyomo's solver to retrieve duals and reduced costs for MIPs
    from cplex lp solver. (This could be made permanent in
    pyomo.solvers.plugins.solvers.CPLEX.create_command_line)."""
    from pyomo.solvers.plugins.solvers.CPLEX import CPLEXSHELL
    old_create_command_line = CPLEXSHELL.create_command_line
    def new_create_command_line(*args, **kwargs):
        # call original command
        command = old_create_command_line(*args, **kwargs)
        # alter script
        if hasattr(command, 'script') and 'optimize\n' in command.script:
            command.script = command.script.replace(
                'optimize\n',
                'optimize\nchange problem fix\noptimize\n'
                # see http://www-01.ibm.com/support/docview.wss?uid=swg21399941
                # and http://www-01.ibm.com/support/docview.wss?uid=swg21400009
            )
            print("changed CPLEX solve script to the following:")
            print(command.script)
        else:
            print (
                "Unable to patch CPLEX solver script to retrieve duals "
                "for MIP problems"
            )
        return command
    new_create_command_line.is_patched = True
    if not getattr(CPLEXSHELL.create_command_line, 'is_patched', False):
        CPLEXSHELL.create_command_line = new_create_command_line

def save_results(instance, outdir):
    """
    Save model solution for later reuse.

    Note that this pickles a solver results object because the instance itself
    cannot be pickled -- see
    https://stackoverflow.com/questions/39941520/pyomo-ipopt-does-not-return-solution
    """
    # First, save the full solution data to the results object, because recent
    # versions of Pyomo only store execution metadata there by default.
    instance.solutions.store_to(instance.last_results)
    with open(os.path.join(outdir, 'results.pickle'), 'wb') as fh:
        pickle.dump(instance.last_results, fh, protocol=-1)
    # remove the solution from the results object, to minimize long-term memory use
    instance.last_results.solution.clear()


###############

if __name__ == "__main__":
    main()
