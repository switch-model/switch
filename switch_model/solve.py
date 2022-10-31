#!/usr/bin/env python
# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
from __future__ import print_function

import logging
import sys, os, time, shlex, re, inspect, textwrap, types, threading, json, traceback

try:
    import IPython

    has_ipython = True
except ImportError:
    has_ipython = False

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

from pyomo.environ import *
from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition
import pyomo.version

import switch_model
from switch_model.utilities import (
    create_model,
    _ArgumentParser,
    StepTimer,
    make_iterable,
    LogOutput,
    warn,
    wrap,
    unwrap,
    rewrap,
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
    # Otherwise, report the traceback, possibly in a cleaner format.
    global old_excepthook
    old_excepthook = sys.excepthook
    if pre_module_options.debug:
        sys.excepthook = debug
    else:
        global full_traceback
        full_traceback = pre_module_options.full_traceback
        sys.excepthook = report_error

    # Write output to a log file if logging option is specified
    # TODO: change all our non-interactive output to report via the logger, then
    # use logger.addHandler(logging.FileHandler(log_file_path)) in make_logger()
    # and drop the LogOutput context manager. (That will also enable logging of
    # messages from solve_scenarios.py to the default log file.) This may
    # require context code anyway to copy all stdout and stderr to the logger
    # while also emitting it on stdout and stderr, e.g., to correctly log
    # tracebacks or messages from Pyomo code or tracebacks from our code.
    if pre_module_options.log_run_to_file:
        logs_dir = pre_module_options.logs_dir
    else:
        logs_dir = None  # disables logging

    # set root logger to an appropriate level
    # we never use pyomo's DEBUG level, because it produces an overwhelming
    # amount of output
    pyomo_levels = {
        "DEBUG": "INFO",
        "INFO": "WARNING",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
    }
    pyomo_log_level = pyomo_levels[pre_module_options.log_level.upper()]
    logging.getLogger("root").setLevel(pyomo_log_level)

    with LogOutput(logs_dir):
        # Create a unique logger for this model (other models may have different
        # logging settings and may exist at the same time as this one). This has
        # to be done after we start LogOutput, because the logger gets a
        # reference to the current sys.stdout, which should be the tee to the
        # log file.
        logger = make_logger(pre_module_options)

        logger.info(
            textwrap.dedent(
                f"""
                {'=' * 80}
                Switch {switch_model.__version__}, https://switch-model.org
                {'=' * 80}"""
            )
        )

        # Warn users about deprecated flags; we know this earlier but don't have
        # a working logger to report it until here.
        # if '--verbose' in args or '--quiet' in args:
        #     logger.warn(unwrap("""
        #         The --verbose and --quiet flags will be removed in a future
        #         version of Switch. Please use --log-level instead.
        #     """))

        # Check for outdated inputs. This has to happen before modules.txt is
        # parsed to avoid errors from incompatible files.
        parser = _ArgumentParser(allow_abbrev=False, add_help=False)
        add_module_args(parser)
        module_options = parser.parse_known_args(args=args)[0]

        if os.path.exists(module_options.inputs_dir) and do_inputs_need_upgrade(
            module_options.inputs_dir
        ):
            if "--help" in args or "-h" in args:
                # don't prompt to upgrade if they're looking for help
                print(
                    rewrap(
                        """
                        Limited help is available because the inputs directory
                        needs to be upgraded. Module-specific help will be
                        available after upgrading the inputs directory via
                        "switch solve" or "switch upgrade".
                        """
                    )
                )
                parser.print_help()
                return 0

            do_upgrade = query_yes_no(
                rewrap(
                    """
                    Warning! Your inputs directory needs to be upgraded. Do you
                    want to auto-upgrade now? We'll keep a backup of this
                    current version.
                    """
                )
            )
            if do_upgrade:
                upgrade_inputs(module_options.inputs_dir)
            else:
                print(
                    rewrap(
                        """
                        Inputs need to be upgraded. Consider using "switch upgrade
                        --help". Exiting.
                        """
                    )
                )
                return -1

        # build a module list based on configuration options, and add
        # the current module (to register define_arguments callback)
        modules = get_module_list(args)

        # Patch pyomo if needed, to allow reconstruction of expressions.
        # This must be done before the model is constructed.
        patch_pyomo()

        # Define the model
        model = create_model(modules, args=args, logger=logger)
        # Add any suffixes specified on the command line (usually only iis)
        add_extra_suffixes(model)

        logger.info("Model defined in {:.2f} s.".format(timer.step_time()))

        # return the model as-is if requested
        if return_model and not return_instance:
            return model

        if model.options.reload_prior_solution:
            # Fail quickly if the prior solution file is not available.
            # TODO: allow a directory to be specified after --reload-prior-solution,
            # otherwise use outputs_dir.
            prior_solution_file = os.path.join(
                model.options.outputs_dir, "results.pickle"
            )
            if not os.path.exists(prior_solution_file):
                raise IOError(
                    "Prior solution {} does not exist.".format(prior_solution_file)
                )

        # create an instance (also reports time spent reading data and loading into model)
        logger.info("\nLoading inputs...")
        instance = model.load_inputs()

        #### Below here, we refer to instance instead of model ####

        logger.info("Executing pre-solve functions...")
        instance.pre_solve()
        logger.info(f"Completed pre-solve processing in {timer.step_time():.2f} s.")

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
            logger.info("Loading prior solution...")
            reload_prior_solution_from_pickle(instance, prior_solution_file)
            logger.info(
                f"Loaded previous results into model instance in {timer.step_time():.2f} s."
            )
        else:
            # solve the model (reports time for each step as it goes)
            if instance.iterate_modules:
                logger.info("Iterating model...")
                iterate(instance)
            else:
                results = solve(instance)
                logger.info("")
                logger.info(
                    f"Optimization termination condition was "
                    f"{results.solver.termination_condition}."
                )
                if str(results.solver.message) != "<undefined>":
                    logger.info(f"Solver message: {results.solver.message}")
                timer.step_time()  # restart counter for next step

            # save model configuration for future reference
            file = os.path.join(instance.options.outputs_dir, "model_config.json")
            with open(file, "w") as f:
                json.dump(
                    {
                        "options": vars(instance.options),
                        "modules": modules,
                        "iterate_modules": instance.iterate_modules,
                    },
                    f,
                    indent=4,
                )

            if not instance.options.no_save_solution:
                logger.info(f"\nSaving solution file...")
                save_results(instance, instance.options.outputs_dir)
                logger.info(f"Saved solution file in {timer.step_time():.2f} s.")

        # report results
        # (repeated if model is reloaded, to automatically run any new export code)
        if not instance.options.no_post_solve:
            logger.info("\nExecuting post-solve functions...")
            instance.post_solve()
            logger.info(
                f"Completed post-solve processing in {timer.step_time():.2f} s."
            )

        logger.info(f"\nSwitch completed successfully in {timer.total_time():0.2f} s.")
        logger.info("=" * 80 + "\n")

    # end of LogOutput block

    if instance.options.interact:
        m = instance  # present the solved model as 'm' for convenience
        banner = "\n".join(
            [
                "",
                "=" * 60,
                "Entering interactive {} shell.".format(
                    "IPython" if has_ipython else "Python"
                ),
                "Abstract model is in 'model' variable;",
                "Solved instance is in 'instance' and 'm' variables.",
                "Type ctrl-d or exit() to exit shell.",
                "=" * 60,
                "",
            ]
        )
        # IPython support is disabled until they fix
        # https://github.com/ipython/ipython/issues/12199
        if has_ipython and False:
            banner += "\nUse tab to auto-complete"
            IPython.embed(
                banner1=banner,
                exit_msg="Leaving interactive interpreter, returning to program.",
                colors=instance.options.interact_color,
            )
        else:
            import code

            code.interact(
                banner=banner,
                local=dict(list(globals().items()) + list(locals().items())),
            )

    # return solved model for users who want to do other things with it
    return instance


# should we show a full traceback when there is an error?
full_traceback = False


def report_error(exc_type, exc_value, exc_traceback):
    msg = f"{exc_type.__name__}: {exc_value}"
    if not "\n" in msg:  # not pre-wrapped by Pyomo
        msg = wrap(msg, indent=4)
    print(f"{'=' * 80}\nTerminating early due to error:\n{msg}\n{'-' * 80}")
    if exc_type is SyntaxError or full_traceback:
        print("Error details:")
        # error in a custom module or user requested normal tracebacks; pass it along
        old_excepthook(exc_type, exc_value, exc_traceback)
    else:
        # provide a tidier error message
        error_locs = []
        for frame, line in traceback.walk_tb(exc_traceback):
            # https://stackoverflow.com/q/2000861/3830997
            # error_locs.append(inspect.getmodule(frame).__spec__.name, line)
            error_locs.append((frame.f_globals["__name__"], frame.f_code.co_name, line))

        # TODO: only show the traceback if --log-level info?

        print(
            "The error occurred at\n"
            + "".join(
                f"    > {module}.{func}:{line}\n" for module, func, line in error_locs
            )
            + "Run with --full-traceback to see more details or --debug to debug interactively.\n"
            + "=" * 80
            + "\n"
        )
        exit(1)


def debug(exc_type, exc_value, exc_traceback):
    """
    Launch interactive debugger to handle the exception.
    """
    import traceback

    try:
        from ipdb import post_mortem
    except ImportError:
        from pdb import post_mortem
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    report_model_in_traceback(exc_traceback)
    # explicitly use _this_ traceback, so debug can be called from an
    # exception handler if needed (see https://stackoverflow.com/a/242514)
    post_mortem(exc_traceback)


def reload_prior_solution_from_pickle(instance, pickle_file):
    with open(pickle_file, "rb") as fh:
        results = pickle.load(fh)
    instance.solutions.load_from(results)
    return instance


patched_pyomo = False


def patch_pyomo():
    # patch Pyomo if needed
    global patched_pyomo
    if patched_pyomo:
        return
    patched_pyomo = True

    # Pyomo 5.1.1 (and maybe others) is very slow to load prior solutions
    # because it does a full-component search for each component name as it
    # assigns the data. This ends up taking longer than solving the model. So we
    # micro- patch pyomo.core.base.PyomoModel.ModelSolutions.add_solution to use
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
        # We don't allow later versions of Pyomo than we've tested with, so
        # this should only show up during testing when preparing to release a
        # new version.
        print(
            "NOTE: The patch to pyomo.core.base.PyomoModel.ModelSolutions.add_solution "
            "has been deactivated because the Pyomo source code has changed. "
            f"Check whether this patch is still needed and edit {__file__} "
            "accordingly."
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
        instance.logger.info(f"Loaded variable {var.name} values into instance.")


def iterate(m, depth=0):
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

    if depth == len(m.iterate_modules):
        # asked to converge at the deepest level
        # just preprocess to reflect all changes and then solve
        m.preprocess()
        solve(m)
    else:
        # iterate until converged at the current level

        # note: the modules in m.iterate_modules were also specified in the model's
        # module list, and have already been loaded, so they are accessible via sys.modules
        current_modules = []
        for module_name in m.iterate_modules[depth]:
            try:
                current_modules.append(sys.modules[module_name])
            except KeyError:
                raise ValueError(
                    "Module {} specified in iterate.txt has not been loaded. "
                    "It should be added to modules.txt as well.".format(module_name)
                )

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
            iterate(m, depth=depth + 1)

            # post-iterate modules at this level
            m.iteration_number = j  # may have been changed during iterate()
            m.iteration_node = m.iteration_node[:depth] + (j,)
            for module in current_modules:
                converged = iterate_module_func(m, module, "post_iterate", converged)

            j += 1
        if converged:
            m.logger.info(
                "Iteration of {ms} was completed after {j} rounds.".format(
                    ms=m.iterate_modules[depth], j=j
                )
            )
        else:
            m.logger.info(
                "Iteration of {ms} was stopped after {j} iterations without convergence.".format(
                    ms=m.iterate_modules[depth], j=j
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
        dest="iterate_list",
        default=None,
        help="""
            Text file with a list of modules to iterate until converged
            (default is iterate.txt). Each row is one level of iteration, and
            there can be multiple modules on each row.
        """,
    )
    argparser.add_argument(
        "--max-iter",
        dest="max_iter",
        type=int,
        default=None,
        help="""
            Maximum number of iterations to complete at each level for iterated
            models
        """,
    )

    # scenario information
    argparser.add_argument(
        "--scenario-name",
        dest="scenario_name",
        default="",
        help="Name of research scenario represented by this model",
    )

    # flag for output; used by many modules so we define it here
    argparser.add_argument(
        "--sorted-output",
        default=False,
        action="store_true",
        dest="sorted_output",
        help=(
            "Sort result files lexicographically. Otherwise results are "
            "written in the same order as the input data (with Pyomo 5.7+) or "
            "in random order (with earlier versions of Pyomo)."
        ),
    )

    # note: pyomo has a --solver-suffix option but it is not clear
    # whether that does the same thing as --suffix defined here,
    # so we don't reuse the same name.
    argparser.add_argument(
        "--suffixes",
        "--suffix",
        dest="suffixes",
        nargs="+",
        action="extend",
        default=[],
        help="""
            Extra suffixes to add to the model and exchange with the solver
            (e.g., iis, rc, dual, or slack)
        """,
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
        dest="solver_manager",
        default="serial",
        help="""
            Name of Pyomo solver manager to use for the model ("neos" to use
            remote NEOS server)
        """,
    )
    argparser.add_argument(
        "--solver-io",
        dest="solver_io",
        default=None,
        help="Method for Pyomo to use to communicate with solver",
    )
    # note: pyomo has a --solver-options option but it is not clear
    # whether that does the same thing as --solver-options-string so we don't reuse the same name.
    argparser.add_argument(
        "--solver-options-string",
        dest="solver_options_string",
        default=None,
        help="""
            A quoted string of options to pass to the model solver. Each option
            must be of the form option=value. (e.g., --solver-options-string
            "mipgap=0.001 primalopt='' advance=2 threads=1")
        """,
    )
    argparser.add_argument(
        "--keepfiles",
        action="store_true",
        default=None,
        help="""
            Keep temporary files produced by the solver (may be useful with
            --symbolic-solver-labels)
        """,
    )
    argparser.add_argument(
        "--stream-output",
        "--stream-solver",
        action="store_true",
        dest="tee",
        default=None,
        help="""
            Display information from the solver about its progress (usually
            combined with a suitable --solver-options-string)
        """,
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
        dest="symbolic_solver_labels",
        default=None,
        help="""
            Use symbol names derived from the model when interfacing with the
            solver. See "pyomo solve --solver=x --help" for more details.
        """,
    )
    argparser.add_argument(
        "--tempdir",
        default=None,
        help="""
            The name of a directory to hold temporary files produced by the
            solver. This is usually paired with --keepfiles and
            --symbolic-solver-labels.
        """,
    )
    argparser.add_argument(
        "--retrieve-cplex-mip-duals",
        dest="retrieve_cplex_mip_duals",
        default=False,
        action="store_true",
        help="""
            Patch Pyomo's solver script for cplex to re-solve and retrieve dual
            values for mixed-integer programs.
        """,
    )

    # General purpose arguments
    # NOTE: the following could potentially be made into standard arguments for all models,
    # e.g. by defining them in a define_standard_arguments() function in switch.utilities.py

    # Define input/output options
    # note: --inputs-dir is defined in add_module_args, because it may specify the
    # location of the module list (deprecated)
    argparser.add_argument(
        "--input-alias",
        "--input-aliases",
        dest="input_aliases",
        nargs="+",
        default=[],
        action="extend",
        help="""
            List of input file substitutions, in form of
            standard_file.csv=alternative_file.csv, useful for sensitivity
            studies with alternative inputs.
        """,
    )
    argparser.add_argument(
        "--outputs-dir",
        default="outputs",
        help='Directory to write output files (default is "outputs")',
    )
    argparser.add_argument(
        "--no-post-solve",
        default=False,
        action="store_true",
        help="""
            Don't run post-solve code on the completed model (i.e., reporting
            functions).
        """,
    )
    argparser.add_argument(
        "--reload-prior-solution",
        default=False,
        action="store_true",
        help="""
            Load a previously saved solution; useful for re-running
            post-solve code or interactively exploring the model (with
            --interact).
        """,
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
        help="""
            Enter interactive shell after solving the instance to enable
            inspection of the solved model.
        """,
    )
    if has_ipython:
        argparser.add_argument(
            "--interact-color",
            dest="interact_color",
            default="NoColor",
            choices=["NoColor", "LightBG", "Linux"],
            help="Color scheme to use with the IPython interactive shell.",
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
        help="Module(s) to remove from the model after processing "
        "--module-list file and prior --include-modules arguments",
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

    # Standard logging levels from
    # https://docs.python.org/3/library/logging.html#levels
    # Code should use logger.warn() for errors that can be recovered from,
    # logger.info() for high-level sequence-of-events reporting and
    # logger.debug() for detailed diagnostic information.
    # logger.error() should be used to explain an error in more detail if
    # needed at the same time as the code raises an exception.
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="warning",
        choices=["error", "warning", "info", "debug"],
        help="Amount of detail to include in on-screen logging and log files. "
        'Default is "warning".',
    )
    # Older logging flags are retained for now to avoid disruption. They may be
    # deprecated later.
    parser.add_argument(
        "--verbose",
        dest="log_level",
        action="store_const",
        const="info",
        help="Equivalent to --log-level info",
    )
    parser.add_argument(
        "--quiet",
        dest="log_level",
        action="store_const",
        const="warning",
        help="Equivalent to --log-level warning",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Automatically start pdb debugger when an error occurs",
    )

    parser.add_argument(
        "--full-traceback",
        action="store_true",
        default=False,
        help=(
            "Show full Python traceback when an error occurs; can help to "
            "pinpoint the cause of errors."
        ),
    )


def parse_pre_module_options(args):
    """
    Parse and return options needed before modules are loaded.
    """
    parser = _ArgumentParser(allow_abbrev=False, add_help=False)
    add_pre_module_args(parser)
    pre_module_args = parser.parse_known_args(args=args)[0]

    return pre_module_args


def parse_list_file(file):
    """Read all items from `file` into a list, removing white space at either
    end of line, blank lines and anything after "#" """
    with open(file) as f:
        items = [r.split("#", 1)[0].strip() for r in f.read().splitlines()]
    items = [i for i in items if i]
    return items


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
        # We also omit blank lines and anything after "#".
        # Otherwise take the module names as given.
        modules = parse_list_file(module_list_file)

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

    # add this module, since it has callbacks, e.g. define_arguments for
    # iteration and suffixes
    modules.append(__name__)

    return modules


def get_iteration_list(m):
    # Identify modules to iterate until convergence (if any)
    try:
        iterate_list_file = m.options.iterate_list
    except AttributeError as e:
        # the --iterate-list option is defined in this module, but sometimes
        # this module will not be in the module list (e.g., for small test
        # models) so it will not be defined. In those cases, we assume no
        # iteration should be done, rather than trying to read the default
        # iteration file. (We could change this to use the default file later
        # if needed.)
        return []
    if iterate_list_file is None and os.path.exists("iterate.txt"):
        iterate_list_file = "iterate.txt"
    if iterate_list_file is None:
        iterate_modules = []
    else:
        iterate_rows = parse_list_file(iterate_list_file)
        # delimit modules at the same level with space(s), tab(s) or comma(s)
        iterate_modules = [re.sub("[ \t,]+", " ", r).split(" ") for r in iterate_rows]
    return iterate_modules


def get_option_file_args(dir=".", extra_args=[]):
    """
    Retrieve base arguments from options.txt (if present). These can be on
    multiple lines to ease editing, and comments starting with "#" (possibly
    mid-line) will be ignored.
    """
    args = []
    options_path = os.path.join(dir, "options.txt")
    if os.path.exists(options_path):
        with open(options_path) as f:
            base_options = f.read().splitlines()
        for r in base_options:
            args.extend(shlex.split(r, comments=True))

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
        retrieve_cplex_mip_duals(model)

    # solve the model
    timer = StepTimer()
    model.logger.info("\nSolving model...")

    if model.options.tempdir is not None:
        # from https://software.sandia.gov/downloads/pub/pyomo/PyomoOnlineDocs.html#_changing_the_temporary_directory
        from pyutilib.services import TempfileManager

        TempfileManager.tempdir = model.options.tempdir

    if model.options.tee:
        # bar above solver output
        model.logger.info("-" * 33 + " solver output " + "-" * 32)

    try:
        results = model.solver_manager.solve(model, opt=model.solver, **solver_args)
    except ValueError as err:
        # show the solver status for obscure errors if possible
        model.logger.error("\n" + "=" * 80 + "\nError during solve:\n")
        try:
            model.logger.error(err.__traceback__.tb_frame.f_locals["results"])
        except:
            pass
        raise

    if model.options.tee:
        # bar below solver output
        model.logger.info("-" * 28 + " end of solver output " + "-" * 28 + "\n")

    model.logger.info(
        f"Solved model. Total time spent in solver: {timer.step_time():0.2f} s."
    )

    # Treat infeasibility as an error, rather than trying to load and save the results
    # (note: in this case, results.solver.status may be SolverStatus.warning instead of
    # SolverStatus.error)
    infeasibility_message = (
        "You can identify infeasible constraints by adding "
        "switch_model.balancing.diagnose_infeasibility to the module list and "
        "solving again."
        "\n\nAlternatively, if the solver can generate an irreducibly "
        "inconsistent set (IIS), more information may be available by setting "
        "the appropriate flags in the --solver-options-string and then calling "
        'this script with "--suffixes iis".\n'
    )

    if results.solver.termination_condition == TerminationCondition.infeasible:
        if hasattr(model, "iis"):
            model.logger.error(
                "Model was infeasible; irreducibly inconsistent set (IIS) returned by solver:"
            )
            model.logger.error("\n".join(sorted(c.name for c in model.iis)))
        else:
            model.logger.error("Model was infeasible. " + infeasibility_message)

        # This infeasibility logging module could be nice, but it doesn't work
        # for my solvers and produces extraneous messages.
        # import pyomo.util.infeasible
        # pyomo.util.infeasible.log_infeasible_constraints(model)
        raise RuntimeError("Infeasible model")

    # Raise an error if the solver failed to produce a solution
    # Note that checking for results.solver.status in {SolverStatus.ok,
    # SolverStatus.warning} is not enough because with a warning there will
    # sometimes be a solution and sometimes not.

    try:
        # pyomo 5.2, maybe earlier or later
        no_solution = len(model.solutions.solutions) == 0
        solution_status = "unavailable"
    except AttributeError:
        # other pyomo version (4.4 or 5.6.8?)
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
        no_solution = len(model.solutions[-1]._entry["variable"]) == 0
        solution_status = model.solutions[-1].status

    if no_solution:
        # no solution returned
        model.logger.error("Solver terminated without a solution.")
        model.logger.error("  Solver Status: ", results.solver.status)
        model.logger.error("  Solution Status: ", solution_status)
        model.logger.error(
            "  Termination Condition: ", results.solver.termination_condition
        )
        if (
            model.options.solver == "glpk"
            and results.solver.termination_condition == TerminationCondition.other
        ):
            model.logger.error(
                "Hint: glpk has been known to classify infeasible problems as 'other'."
            )
            model.logger.error(infeasibility_message)
        raise RuntimeError("Solver failed to find an optimal solution.")

    # Report any warnings; these are written to stderr so users can find them in
    # error logs (e.g. on HPC systems). These can occur, e.g., if solver reaches
    # time limit or iteration limit but still returns a valid solution
    if results.solver.status == SolverStatus.warning:
        model.logger.warning(
            "Solver terminated with warning.\n"
            f"  Solver Status: {results.solver.status}\n"
            f"  Solution Status: {model.solutions[-1].status}\n"
            f"  Termination Condition: {results.solver.termination_condition}"
        )

    ### process and return solution ###

    # Cache a copy of the results object, to allow saving and restoring model
    # solutions later.
    model.last_results = results
    return results


instance_number = 0
instance_number_lock = threading.Lock()


def make_logger(parsed_args):
    """
    Create a unique logger to attach to a model instance.

    This module may be kept in memory and used to create multiple instances with
    different logging settings (e.g., via switch solve-scenarios), so we need to
    create a unique logger for each model. This is also used by solve_scenarios
    to create a logger for its own output.
    """
    global instance_number
    # Create a unique name to avoid reloading a logger created in a previous
    # call to logging.getLogger. This name only needs to be unique within this
    # process because if users call this function in separate processes they
    # will not see the loggers each other have created (logging module is not
    # multiprocessing-aware). So process-level locking is adequate.
    with instance_number_lock:
        instance_number += 1
        if instance_number == 1:
            # typical case, solving one model and quitting
            instance_name = "Switch"
        else:
            instance_name = "Switch instance {}".format(instance_number)
    logger = logging.getLogger(instance_name)
    # Follow user-specified logging level (converted to standard key)
    logger.setLevel(parsed_args.log_level.upper())
    # Always log to stdout (not stderr)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    return logger


def retrieve_cplex_mip_duals(model):
    """patch Pyomo's solver to retrieve duals and reduced costs for MIPs
    from cplex lp solver. (This could be made permanent in
    pyomo.solvers.plugins.solvers.CPLEX.create_command_line)."""
    from pyomo.solvers.plugins.solvers.CPLEX import CPLEXSHELL

    old_create_command_line = CPLEXSHELL.create_command_line
    logger = model.logger

    def new_create_command_line(*args, **kwargs):
        # call original command
        command = old_create_command_line(*args, **kwargs)
        # alter script
        if (
            hasattr(command, "script")
            and "optimize\n" in command.script
            and not "change problem fix\n" in command.script
        ):
            command.script = command.script.replace(
                "optimize\n",
                "optimize\nchange problem fix\noptimize\n"
                # see http://www-01.ibm.com/support/docview.wss?uid=swg21399941
                # and http://www-01.ibm.com/support/docview.wss?uid=swg21400009
            )
            logger.info("changed CPLEX solve script to the following:")
            logger.info(command.script)
        else:
            logger.warning(
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


def report_model_in_traceback(tb):
    """
    Report on location of model in current traceback, if one can be found easily.
    """
    import traceback

    for level, (frame, line) in enumerate(reversed(list(traceback.walk_tb(tb)))):
        file_loc = "{}, line {}".format(frame.f_code.co_filename, line)
        if level == 0:
            location = "in the current frame"
        elif level == 1:
            location = "in\n{}\n(1 level up)".format(file_loc)
        else:
            location = "in\n{}\n({} levels up)".format(file_loc, level)
        vars = frame.f_locals
        for name, v in vars.items():
            if isinstance(v, Model):
                print(
                    "\nA model can be found in variable '{}' {}".format(name, location)
                )
                return
        for name, v in vars.items():
            if isinstance(v, Component) and hasattr(v, "model"):
                print(
                    "\nA model can be found in '{}.model()' {}".format(name, location)
                )
                return
    print("\nNo Pyomo model was found in the current stack trace.")


###############

if __name__ == "__main__":
    main()
