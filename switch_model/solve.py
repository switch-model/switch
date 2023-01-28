#!/usr/bin/env python
# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
from __future__ import print_function

from pyomo.environ import *
from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition
import pyomo.version

import sys, os, time, shlex, re, inspect, textwrap, types

try:
    # Python 2
    import cPickle as pickle
except ImportError:
    import pickle

try:
    # Python 2
    input = raw_input
except NameError:
    pass

import switch_model
from switch_model.utilities import (
    create_model,
    _ArgumentParser,
    StepTimer,
    make_iterable,
    LogOutput,
    warn,
)
from switch_model.upgrade import do_inputs_need_upgrade, upgrade_inputs


def main(args=None, return_model=False, return_instance=False):

    timer = StepTimer()
    if args is None:
        # combine default arguments read from options.txt file with
        # additional arguments specified on the command line
        args = get_option_file_args(extra_args=sys.argv[1:])

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
        logs_dir = None  # disables logging

    with LogOutput(logs_dir):

        # Look out for outdated inputs. This has to happen before modules.txt is
        # parsed to avoid errors from incompatible files.
        parser = _ArgumentParser(allow_abbrev=False, add_help=False)
        add_module_args(parser)
        module_options = parser.parse_known_args(args=args)[0]
        if os.path.exists(module_options.inputs_dir) and do_inputs_need_upgrade(
            module_options.inputs_dir
        ):
            do_upgrade = query_yes_no(
                "Warning! Your inputs directory needs to be upgraded. "
                "Do you want to auto-upgrade now? We'll keep a backup of "
                "this current version."
            )
            if do_upgrade:
                upgrade_inputs(module_options.inputs_dir)
            else:
                print("Inputs need upgrade. Consider `switch upgrade --help`. Exiting.")
                stop_logging_output()
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

        # get a list of modules to iterate through
        iterate_modules = get_iteration_list(model)

        if model.options.verbose:
            print(
                "\n======================================================================="
            )
            print("Switch {}, http://switch-model.org".format(switch_model.__version__))
            print(
                "======================================================================="
            )
            print("Arguments:")
            print(
                ", ".join(
                    k + "=" + repr(v) for k, v in model.options.__dict__.items() if v
                )
            )
            print("Modules:\n" + ", ".join(m for m in modules))
            if iterate_modules:
                print("Iteration modules:", iterate_modules)
            print(
                "=======================================================================\n"
            )
            print("Model created in {:.2f} s.".format(timer.step_time()))
            print("Loading inputs...")

        # create an instance (also reports time spent reading data and loading into model)
        instance = model.load_inputs()

        #### Below here, we refer to instance instead of model ####

        instance.pre_solve()
        if instance.options.verbose:
            print(
                "Total time spent constructing model: {:.2f} s.\n".format(
                    timer.step_time()
                )
            )

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

        if instance.options.reload_prior_solution:
            print("Loading prior solution...")
            reload_prior_solution_from_pickle(instance, instance.options.outputs_dir)
            if instance.options.verbose:
                print(
                    "Loaded previous results into model instance in {:.2f} s.".format(
                        timer.step_time()
                    )
                )
        else:
            # solve the model (reports time for each step as it goes)
            if iterate_modules:
                if instance.options.verbose:
                    print("Iterating model...")
                iterate(instance, iterate_modules)
            else:
                results = solve(instance)
                if instance.options.verbose:
                    print("")
                    print(
                        "Optimization termination condition was {}.".format(
                            results.solver.termination_condition
                        )
                    )
                    if str(results.solver.message) != "<undefined>":
                        print("Solver message: {}".format(results.solver.message))
                    print("")

                if instance.options.verbose:
                    timer.step_time()  # restart counter for next step

                if not instance.options.no_save_solution:
                    save_results(instance, instance.options.outputs_dir)
                    if instance.options.verbose:
                        print("Saved results in {:.2f} s.".format(timer.step_time()))

        # report results
        # (repeated if model is reloaded, to automatically run any new export code)
        if not instance.options.no_post_solve:
            if instance.options.verbose:
                print("Executing post solve functions...")
            instance.post_solve()
            if instance.options.verbose:
                print(
                    "Post solve processing completed in {:.2f} s.".format(
                        timer.step_time()
                    )
                )

    # end of LogOutput block

    if instance.options.interact:
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

        code.interact(
            banner=banner, local=dict(list(globals().items()) + list(locals().items()))
        )


def reload_prior_solution_from_pickle(instance, outdir):
    with open(os.path.join(outdir, "results.pickle"), "rb") as fh:
        results = pickle.load(fh)
    instance.solutions.load_from(results)
    return instance


patched_pyomo = False


def patch_pyomo():
    global patched_pyomo
    if not patched_pyomo:
        patched_pyomo = True
        # patch Pyomo if needed

        # Pyomo 4.2 and 4.3 mistakenly discard the original rule during
        # Expression.construct. This makes it impossible to reconstruct
        # expressions (e.g., for iterated models). So we patch it.
        if (4, 2) <= pyomo.version.version_info[:2] <= (4, 3):
            # test whether patch is needed:
            m = ConcreteModel()
            m.e = Expression(rule=lambda m: 0)
            if hasattr(m.e, "_init_rule") and m.e._init_rule is None:
                # add a deprecation warning here when we stop supporting Pyomo 4.2 or 4.3
                old_construct = pyomo.environ.Expression.construct

                def new_construct(self, *args, **kwargs):
                    # save rule, call the function, then restore it
                    _init_rule = self._init_rule
                    old_construct(self, *args, **kwargs)
                    self._init_rule = _init_rule

                pyomo.environ.Expression.construct = new_construct
            del m

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
            replace_method(ModelSolutions, "add_solution", add_solution_code)
        elif pyomo.version.version_info[:2] >= (5, 0):
            print(
                "NOTE: The patch to pyomo.core.base.PyomoModel.ModelSolutions.add_solution "
                "has been deactivated because the Pyomo source code has changed. "
                "Check whether this patch is still needed and edit {} accordingly.".format(
                    __file__
                )
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
        orig_method.__closure__,
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
        var_file = os.path.join(instance.options.outputs_dir, "{}.csv".format(var.name))
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
        with open(var_file, "r") as f:
            reader = csv.reader(f, delimiter=",")
            next(reader)  # skip headers
            for row in reader:
                index = tuple(t(k) for t, k in zip(key_types, row[:-1]))
                try:
                    v = var[index]
                except KeyError:
                    raise KeyError(
                        "Unable to set value for {}[{}]; index is invalid.".format(
                            var.name, keys
                        )
                    )
                if row[-1] == "":
                    # Variables that are not used in the model end up with no
                    # value after the solve and get saved as blanks; we skip those.
                    continue
                val = float(row[-1])
                if v.is_integer() or v.is_binary():
                    val = int(val)
                v.value = val
        if instance.options.verbose:
            print("Loaded variable {} values into instance.".format(var.name))


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
            sys.modules[
                module_name
                if module_name in sys.modules
                else "switch_model." + module_name
            ]
            for module_name in iterate_modules[depth]
        ]

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
                converged = iterate_module_func(m, module, "pre_iterate", converged)

            # converge the deeper-level modules, if any (inner loop)
            iterate(m, iterate_modules, depth=depth + 1)

            # post-iterate modules at this level
            m.iteration_number = j  # may have been changed during iterate()
            m.iteration_node = m.iteration_node[:depth] + (j,)
            for module in current_modules:
                converged = iterate_module_func(m, module, "post_iterate", converged)

            j += 1
        if converged:
            print(
                "Iteration of {ms} was completed after {j} rounds.".format(
                    ms=iterate_modules[depth], j=j
                )
            )
        else:
            print(
                "Iteration of {ms} was stopped after {j} iterations without convergence.".format(
                    ms=iterate_modules[depth], j=j
                )
            )
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
    # callback function to define model configuration arguments while the model is built

    # add arguments needed before modules are loaded
    # here to add them to the solve.py help
    add_pre_module_args(argparser)

    # add standard module arguments (not used later, but this adds them to the help)
    add_module_args(argparser)

    # iteration options
    argparser.add_argument(
        "--iterate-list",
        default=None,
        help="Text file with a list of modules to iterate until converged (default is iterate.txt); "
        "each row is one level of iteration, and there can be multiple modules on each row",
    )
    argparser.add_argument(
        "--max-iter",
        type=int,
        default=None,
        help="Maximum number of iterations to complete at each level for iterated models",
    )

    # scenario information
    argparser.add_argument(
        "--scenario-name",
        default="",
        help="Name of research scenario represented by this model",
    )

    # note: pyomo has a --solver-suffix option but it is not clear
    # whether that does the same thing as --suffix defined here,
    # so we don't reuse the same name.
    argparser.add_argument(
        "--suffixes",
        "--suffix",
        nargs="+",
        action="extend",
        default=[],
        help="Extra suffixes to add to the model and exchange with the solver (e.g., iis, rc, dual, or slack)",
    )

    # Define solver-related arguments
    # These are a subset of the arguments offered by "pyomo solve --solver=cplex --help"
    argparser.add_argument(
        "--solver",
        default="glpk",
        help='Name of Pyomo solver to use for the model (default is "glpk")',
    )
    argparser.add_argument(
        "--solver-manager",
        default="serial",
        help='Name of Pyomo solver manager to use for the model ("neos" to use remote NEOS server)',
    )
    argparser.add_argument(
        "--solver-io",
        default=None,
        help="Method for Pyomo to use to communicate with solver",
    )
    # note: pyomo has a --solver-options option but it is not clear
    # whether that does the same thing as --solver-options-string so we don't reuse the same name.
    argparser.add_argument(
        "--solver-options-string",
        default=None,
        help="A quoted string of options to pass to the model solver. Each option must be of the form option=value. "
        "(e.g., --solver-options-string \"mipgap=0.001 primalopt='' advance=2 threads=1\")",
    )
    argparser.add_argument(
        "--keepfiles",
        action="store_true",
        default=None,
        help="Keep temporary files produced by the solver (may be useful with --symbolic-solver-labels)",
    )
    argparser.add_argument(
        "--stream-output",
        "--stream-solver",
        action="store_true",
        dest="tee",
        default=None,
        help="Display information from the solver about its progress (usually combined with a suitable --solver-options-string)",
    )
    argparser.add_argument(
        "--no-stream-output",
        "--no-stream-solver",
        action="store_false",
        dest="tee",
        default=None,
        help="Don't display information from the solver about its progress",
    )
    argparser.add_argument(
        "--symbolic-solver-labels",
        action="store_true",
        default=None,
        help="Use symbol names derived from the model when interfacing with the solver. "
        'See "pyomo solve --solver=x --help" for more details.',
    )
    argparser.add_argument(
        "--tempdir",
        default=None,
        help="The name of a directory to hold temporary files produced by the solver. "
        "This is usually paired with --keepfiles and --symbolic-solver-labels.",
    )
    argparser.add_argument(
        "--retrieve-cplex-mip-duals",
        default=False,
        action="store_true",
        help=(
            "Patch Pyomo's solver script for cplex to re-solve and retrieve "
            "dual values for mixed-integer programs."
        ),
    )

    # NOTE: the following could potentially be made into standard arguments for all models,
    # e.g. by defining them in a define_standard_arguments() function in switch.utilities.py

    # Define input/output options
    # note: --inputs-dir is defined in add_module_args, because it may specify the
    # location of the module list (deprecated)
    # argparser.add_argument("--inputs-dir", default="inputs",
    #     help='Directory containing input files (default is "inputs")')
    argparser.add_argument(
        "--input-alias",
        "--input-aliases",
        dest="input_aliases",
        nargs="+",
        default=[],
        help="List of input file substitutions, in form of standard_file.csv=alternative_file.csv, "
        "useful for sensitivity studies with different inputs.",
    )
    argparser.add_argument(
        "--outputs-dir",
        default="outputs",
        help='Directory to write output files (default is "outputs")',
    )

    # General purpose arguments
    argparser.add_argument(
        "--verbose",
        "-v",
        dest="verbose",
        default=False,
        action="store_true",
        help="Show information about model preparation and solution",
    )
    argparser.add_argument(
        "--quiet",
        "-q",
        dest="verbose",
        action="store_false",
        help="Don't show information about model preparation and solution (cancels --verbose setting)",
    )
    argparser.add_argument(
        "--no-post-solve",
        default=False,
        action="store_true",
        help="Don't run post-solve code on the completed model (i.e., reporting functions).",
    )
    argparser.add_argument(
        "--reload-prior-solution",
        default=False,
        action="store_true",
        help="Load a previously saved solution; useful for re-running post-solve code or interactively exploring the model (via --interact).",
    )
    argparser.add_argument(
        "--no-save-solution",
        default=False,
        action="store_true",
        help="Don't save solution after model is solved.",
    )
    argparser.add_argument(
        "--interact",
        default=False,
        action="store_true",
        help="Enter interactive shell after solving the instance to enable inspection of the solved model.",
    )


def add_module_args(parser):
    parser.add_argument(
        "--module-list",
        default=None,
        help='Text file with a list of modules to include in the model (default is "modules.txt")',
    )
    parser.add_argument(
        "--include-modules",
        "--include-module",
        dest="include_exclude_modules",
        nargs="+",
        action="include",
        default=[],
        help="Module(s) to add to the model in addition to any specified with --module-list file",
    )
    parser.add_argument(
        "--exclude-modules",
        "--exclude-module",
        dest="include_exclude_modules",
        nargs="+",
        action="exclude",
        default=[],
        help="Module(s) to remove from the model after processing --module-list file and prior --include-modules arguments",
    )
    # note: we define --inputs-dir here because it may be used to specify the location of
    # the module list, which is needed before it is loaded.
    parser.add_argument(
        "--inputs-dir",
        default="inputs",
        help='Directory containing input files (default is "inputs")',
    )


def add_pre_module_args(parser):
    """
    Add arguments needed before any modules are loaded.
    """
    parser.add_argument(
        "--log-run",
        dest="log_run_to_file",
        default=False,
        action="store_true",
        help="Log output to a file.",
    )
    parser.add_argument(
        "--logs-dir",
        dest="logs_dir",
        default="logs",
        help='Directory containing log files (default is "logs"',
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Automatically start pdb debugger on exceptions",
    )


def parse_pre_module_options(args):
    """
    Parse and return options needed before modules are loaded.
    """
    parser = _ArgumentParser(allow_abbrev=False, add_help=False)
    add_pre_module_args(parser)
    pre_module_args = parser.parse_known_args(args=args)[0]

    return pre_module_args


def get_module_list(args):
    # parse module options
    parser = _ArgumentParser(allow_abbrev=False, add_help=False)
    add_module_args(parser)
    module_options = parser.parse_known_args(args=args)[0]

    # identify modules to load
    module_list_file = module_options.module_list

    # search first in the current directory
    if module_list_file is None and os.path.exists("modules.txt"):
        module_list_file = "modules.txt"
    # search next in the inputs directory ('inputs' by default)
    if module_list_file is None:
        test_path = os.path.join(module_options.inputs_dir, "modules.txt")
        if os.path.exists(test_path):
            module_list_file = test_path
    if module_list_file is None:
        # note: this could be a RuntimeError, but then users can't do "switch solve --help" in a random directory
        # (alternatively, we could provide no warning at all, since the user can specify --include-modules in the arguments)
        print(
            "WARNING: No module list found. Please create a modules.txt file with a list of modules to use for the model."
        )
        modules = []
    else:
        # if it exists, the module list contains one module name per row (no .py extension)
        # we strip whitespace from either end (because those errors can be annoyingly hard to debug).
        # We also omit blank lines and lines that start with "#"
        # Otherwise take the module names as given.
        with open(module_list_file) as f:
            modules = [r.strip() for r in f.read().splitlines()]
        modules = [m for m in modules if m and not m.startswith("#")]

    # adjust modules as requested by the user
    # include_exclude_modules format: [('include', [mod1, mod2]), ('exclude', [mod3])]
    for action, mods in module_options.include_exclude_modules:
        if action == "include":
            for module_name in mods:
                if (
                    module_name not in modules
                ):  # maybe we should raise an error if already present?
                    modules.append(module_name)
        if action == "exclude":
            for module_name in mods:
                try:
                    modules.remove(module_name)
                except ValueError:
                    raise ValueError(  # maybe we should just pass?
                        "Unable to exclude module {} because it was not "
                        "previously included.".format(module_name)
                    )

    # add this module, since it has callbacks, e.g. define_arguments for iteration and suffixes
    modules.append("switch_model.solve")

    return modules


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


def get_option_file_args(dir=".", extra_args=[]):

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
    if not hasattr(model, "solver"):
        # Create a solver object the first time in. We don't do this until a solve is
        # requested, because sometimes a different solve function may be used,
        # with its own solver object (e.g., with runph or a parallel solver server).
        # In those cases, we don't want to go through the expense of creating an
        # unused solver object, or get errors if the solver options are invalid.
        model.solver = SolverFactory(
            model.options.solver, solver_io=model.options.solver_io
        )

        # patch for Pyomo < 4.2
        # note: Pyomo added an options_string argument to solver.solve() in Pyomo 4.2 rev 10587.
        # (See https://software.sandia.gov/trac/pyomo/browser/pyomo/trunk/pyomo/opt/base/solvers.py?rev=10587 )
        # This is misreported in the documentation as options=, but options= actually accepts a dictionary.
        if model.options.solver_options_string and not hasattr(
            model.solver, "_options_string_to_dict"
        ):
            for k, v in _options_string_to_dict(
                model.options.solver_options_string
            ).items():
                model.solver.options[k] = v

        # import pdb; pdb.set_trace()
        model.solver_manager = SolverManagerFactory(model.options.solver_manager)

    # get solver arguments
    solver_args = dict(
        options_string=model.options.solver_options_string,
        keepfiles=model.options.keepfiles,
        tee=model.options.tee,
        symbolic_solver_labels=model.options.symbolic_solver_labels,
    )
    # drop all the unspecified options
    solver_args = {k: v for (k, v) in solver_args.items() if v is not None}

    # Automatically send all defined suffixes to the solver
    solver_args["suffixes"] = [c.name for c in model.component_objects(ctype=Suffix)]

    # note: the next few lines are faster than the line above, but seem risky:
    # i = m._ctypes.get(Suffix, [None])[0]
    # solver_args["suffixes"] = []
    # while i is not None:
    #     c, i = m._decl_order[i]
    #     solver_args[suffixes].append(c.name)

    # patch for Pyomo < 4.2
    if not hasattr(model.solver, "_options_string_to_dict"):
        solver_args.pop("options_string", "")

    # patch Pyomo to retrieve MIP duals from cplex if needed
    if model.options.retrieve_cplex_mip_duals:
        retrieve_cplex_mip_duals()

    # solve the model
    if model.options.verbose:
        timer = StepTimer()
        print("Solving model...")

    if model.options.tempdir is not None:
        # from https://software.sandia.gov/downloads/pub/pyomo/PyomoOnlineDocs.html#_changing_the_temporary_directory
        from pyutilib.services import TempfileManager

        TempfileManager.tempdir = model.options.tempdir

    results = model.solver_manager.solve(model, opt=model.solver, **solver_args)
    # import pdb; pdb.set_trace()

    if model.options.verbose:
        print(
            "Solved model. Total time spent in solver: {:2f} s.".format(
                timer.step_time()
            )
        )

    # Treat infeasibility as an error, rather than trying to load and save the results
    # (note: in this case, results.solver.status may be SolverStatus.warning instead of
    # SolverStatus.error)
    if results.solver.termination_condition == TerminationCondition.infeasible:
        if hasattr(model, "iis"):
            print(
                "Model was infeasible; irreducibly inconsistent set (IIS) returned by solver:"
            )
            print("\n".join(sorted(c.name for c in model.iis)))
        else:
            print(
                "Model was infeasible; if the solver can generate an irreducibly inconsistent set (IIS),"
            )
            print(
                "more information may be available by setting the appropriate flags in the "
            )
            print(
                'solver_options_string and calling this script with "--suffixes iis".'
            )
        raise RuntimeError("Infeasible model")

    # Raise an error if the solver failed to produce a solution
    # Note that checking for results.solver.status in {SolverStatus.ok,
    # SolverStatus.warning} is not enough because with a warning there will
    # sometimes be a solution and sometimes not.
    # Note: the results object originally contains values for model components
    # in results.solution.variable, etc., but pyomo.solvers.solve erases it via
    # result.solution.clear() after calling model.solutions.load_from() with it.
    # load_from() loads values into the model.solutions._entry, so we check there.
    # (See pyomo.PyomoModel.ModelSolutions.add_solution() for the code that
    # actually creates _entry).
    # Another option might be to check that model.solutions[-1].status (previously
    # result.solution.status, but also cleared) is in
    # pyomo.opt.SolutionStatus.['optimal', 'bestSoFar', 'feasible', 'globallyOptimal', 'locallyOptimal'],
    # but this seems pretty foolproof (if undocumented).
    if len(model.solutions[-1]._entry["variable"]) == 0:
        # no solution returned
        print("Solver terminated without a solution.")
        print("  Solver Status: ", results.solver.status)
        print("  Solution Status: ", model.solutions[-1].status)
        print("  Termination Condition: ", results.solver.termination_condition)
        if (
            model.options.solver == "glpk"
            and results.solver.termination_condition == TerminationCondition.other
        ):
            print(
                "Hint: glpk has been known to classify infeasible problems as 'other'."
            )
        raise RuntimeError("Solver failed to find an optimal solution.")

    # Report any warnings; these are written to stderr so users can find them in
    # error logs (e.g. on HPC systems). These can occur, e.g., if solver reaches
    # time limit or iteration limit but still returns a valid solution
    if results.solver.status == SolverStatus.warning:
        warn(
            "Solver terminated with warning.\n"
            + "  Solution Status: {}\n".format(model.solutions[-1].status)
            + "  Termination Condition: {}".format(results.solver.termination_condition)
        )

    ### process and return solution ###

    # Cache a copy of the results object, to allow saving and restoring model
    # solutions later.
    model.last_results = results
    return results


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
        if hasattr(command, "script") and "optimize\n" in command.script:
            command.script = command.script.replace(
                "optimize\n",
                "optimize\nchange problem fix\noptimize\n"
                # see http://www-01.ibm.com/support/docview.wss?uid=swg21399941
                # and http://www-01.ibm.com/support/docview.wss?uid=swg21400009
            )
            print("changed CPLEX solve script to the following:")
            print(command.script)
        else:
            print(
                "Unable to patch CPLEX solver script to retrieve duals "
                "for MIP problems"
            )
        return command

    new_create_command_line.is_patched = True
    if not getattr(CPLEXSHELL.create_command_line, "is_patched", False):
        CPLEXSHELL.create_command_line = new_create_command_line


# taken from https://software.sandia.gov/trac/pyomo/browser/pyomo/trunk/pyomo/opt/base/solvers.py?rev=10784
# This can be removed when all users are on Pyomo 4.2
import pyutilib


def _options_string_to_dict(istr):
    ans = {}
    istr = istr.strip()
    if not istr:
        return ans
    if istr[0] == "'" or istr[0] == '"':
        istr = eval(istr)
    tokens = pyutilib.misc.quote_split("[ ]+", istr)
    for token in tokens:
        index = token.find("=")
        if index == -1:
            raise ValueError(
                "Solver options must have the form option=value: '{}'".format(istr)
            )
        try:
            val = eval(token[(index + 1) :])
        except:
            val = token[(index + 1) :]
        ans[token[:index]] = val
    return ans


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
    with open(os.path.join(outdir, "results.pickle"), "wb") as fh:
        pickle.dump(instance.last_results, fh, protocol=-1)
    # remove the solution from the results object, to minimize long-term memory use
    instance.last_results.solution.clear()


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


###############

if __name__ == "__main__":
    main()
