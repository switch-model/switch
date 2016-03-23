#!/usr/bin/env python

import sys, os, time, traceback, shlex, re

from pyomo.environ import *
from pyomo.opt import SolverFactory, SolverStatus, TerminationCondition

from utilities import create_model, _ArgumentParser

def main(args=sys.argv[1:]):
        
    # build a module list based on configuration options passed in,
    # and add the current module (to register define_arguments callback)
    modules = get_module_list(args)
    
    # Define the model
    model = create_model(modules, args=args)

    # Add any suffixes specified on the command line (usually only iis)
    add_extra_suffixes(model)
    
    # get a list of modules to iterate through
    iterate_modules = get_iteration_list(model)
    
    print "\n\n======================================================================="
    print "arguments:"
    print " ".join(k+"="+repr(v) for k, v in model.options.__dict__.items() if v)
    print "modules:", modules
    if iterate_modules:
        print "iterate_modules", iterate_modules
    print "======================================================================="

    # create an instance
    instance = model.load_inputs()

    # make sure the outputs_dir exists (used by some modules during iterate)
    if not os.path.exists(instance.options.outputs_dir):
        os.makedirs(instance.options.outputs_dir)

    # solve the model
    if iterate_modules:
        print "iterating model..."
        iterate(instance, iterate_modules)
    else:
        print "solving model..."
        solve(instance)
        print "finished solving"
    
    # report/save results
    instance.post_solve()

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
        m.iteration_node = []

    if depth == len(iterate_modules):
        # asked to converge at the deepest level
        # just preprocess to reflect all changes and then solve
        m.preprocess()
        solve(m)
    else:
        # iterate until converged at the current level

        # note: the modules in iterate_modules were also specified in the model's 
        # module list, and have already been loaded, so they are accessible via sys.modules
        current_modules = [sys.modules[module_name] for module_name in iterate_modules[depth]]
        # truncate the iteration tree at the current level
        m.iteration_node = m.iteration_node[:depth] + [0]

        j = 0
        converged = False
        while not converged:
            # take one step at the current level
            if m.options.max_iter is not None and j >= m.options.max_iter:
                break

            # record the current iteration number and node for use by modules 
            # (e.g., to name files or reset/index params)
            m.iteration_number = j
            m.iteration_node[-1] = j

            converged = True
            # pre-iterate modules at this level
            for module in current_modules:
                if hasattr(module, 'pre_iterate'): 
                    converged = module.pre_iterate(m) and converged

            # converge the deeper-level modules, if any (inner loop)
            iterate(m, iterate_modules, depth=depth+1)
            
            # post-iterate modules at this level
            for module in current_modules:
                if hasattr(module, 'post_iterate'):
                    converged = module.post_iterate(m) and converged

            j += 1
        if converged:
            print "Iteration of {ms} was completed after {j} rounds.".format(ms=iterate_modules[depth], j=j)
        else:
            print "Iteration of {ms} was stopped after {j} iterations without convergence.".format(ms=iterate_modules[depth], j=j)
    return

def define_arguments(argparser):
    # callback function to define model configuration arguments while the model is built

    # add standard module arguments (not used later, but this adds them to the help)
    add_module_args(argparser)

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
    argparser.add_argument("--suffixes", "--suffix", nargs="+", default=[],
        help="Extra suffixes to add to the model and exchange with the solver (e.g., iis, rc, dual, or slack)")

    # Define solver-related arguments
    # These are a subset of the arguments offered by "pyomo solve --solver=cplex --help"
    argparser.add_argument("--solver", default="glpk", 
        help='Name of Pyomo solver to use for the model (default is "glpk")')
    argparser.add_argument("--solver-io", default=None, help="Method for Pyomo to use to communicate with solver")
    # note: pyomo has a --solver-options option but it is not clear
    # whether that does the same thing as --solver-options-string so we don't reuse the same name.
    argparser.add_argument("--solver-options-string", default=None, 
        help='A quoted string of options to pass to the model solver. Each option must be of the form option=value. '
            '(e.g., --solver-options-string "mipgap=0.001 primalopt advance=2 threads=1")')
    argparser.add_argument("--keepfiles", action='store_true', default=None,
        help="Keep temporary files produced by the solver (may be useful with --symbolic-solver-labels)")
    argparser.add_argument(
        "--stream-output", "--stream-solver", action='store_true', dest="tee", default=None,
        help="Display information from the solver about its progress (usually combined with a suitable --solver-options string)")
    argparser.add_argument(
        "--symbolic-solver-labels", action='store_true', default=None, 
        help='Use symbol names derived from the model when interfacing with the solver. '
            'See "pyomo solve --solver=x --help" for more details.')
    argparser.add_argument("--tempdir", default=None,
        help='The name of a directory to hold temporary files produced by the solver. '
             'This is usually paired with --keepfiles and --symbolic-solver-labels.')

    # NOTE: the following could potentially be made into standard arguments for all models,
    # e.g. by defining them in a define_standard_arguments() function in switch.utilities.py

    # Define input/output options
    argparser.add_argument("--inputs-dir", default="inputs", 
        help='Directory containing input files (default is "inputs")')
    argparser.add_argument("--outputs-dir", default="outputs",
        help='Directory to write output files (default is "outputs")')

    # General purpose arguments
    argparser.add_argument(
        '--verbose', '-v', default=False, action='store_true',
        help='Show information about model preparation and solution')


def add_module_args(parser):
    parser.add_argument(
        "--module-list", default=None, 
        help='Text file with a list of modules to include in the model (default is "modules.txt")'
    )
    parser.add_argument(
        "--include-modules", "--include-module", dest="include_modules", nargs='+', default=[],
        help="Module(s) to add to the model in addition to any specified with --module-list"
    )
    parser.add_argument(
        "--exclude-modules", "--exclude-module", dest="exclude_modules", nargs='+', default=[],
        help="Module(s) to remove from the model after processing --module-list and --include-modules"
    )

def get_module_list(args):
    # parse module options
    parser = _ArgumentParser(allow_abbrev=False, add_help=False)
    add_module_args(parser)
    module_options = parser.parse_known_args(args=args)[0]

    # identify modules to load
    module_list_file = module_options.module_list
    if module_list_file is None and os.path.exists("modules.txt"):
        module_list_file = "modules.txt"
    if module_list_file is None:
        modules = []
    else:
        # if it exists, the module list contains one module name per row (no .py extension)
        # we strip whitespace from either end (because those errors can be annoyingly hard to debug).
        # We also omit blank lines and lines that start with "#"
        # Otherwise take the module names as given.
        with open(module_list_file) as f:
            modules = [r.strip() for r in f.read().splitlines()]
        modules = [m for m in modules if m and not m.startswith("#")]

    modules.extend(module_options.include_modules)
    for module_name in module_options.exclude_modules:
        modules.remove(module_name)
    
    # add the current module, since it has callbacks, e.g. define_arguments for iteration and suffixes
    modules.append(__name__)

    print "module list:", modules

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
        iterate_modules = [re.sub("[ \t,]+", " ", r).split(" ") for r in iterate_rows]
    return iterate_modules

def get_option_file_args():
    args = []
    # retrieve base arguments from options.txt (if present)
    # note: these can be on multiple lines to ease editing,
    # and lines can be commented out with #
    if os.path.exists("options.txt"):
        with open("options.txt") as f:
            base_options = f.read().splitlines()
        for r in base_options:
            if not r.lstrip().startswith("#"):
                args.extend(shlex.split(r))
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
        setattr(model, suffix, Suffix(direction=Suffix.IMPORT_EXPORT))


def solve(model):
    if not hasattr(model, "solver"):
        # Create a solver object the first time in. We don't do this until a solve is
        # requested, because sometimes a different solve function may be used,
        # with its own solver object (e.g., with runph or a parallel solver server).
        # In those cases, we don't want to go through the expense of creating an
        # unused solver object, or get errors if the solver options are invalid.
        model.solver = SolverFactory(model.options.solver, solver_io=model.options.solver_io)

        # patch for Pyomo < 4.2
        # note: Pyomo added an options_string argument to solver.solve() in Pyomo 4.2 rev 10587. 
        # (See https://software.sandia.gov/trac/pyomo/browser/pyomo/trunk/pyomo/opt/base/solvers.py?rev=10587 )
        # This is misreported in the documentation as options=, but options= actually accepts a dictionary.
        if model.options.solver_options_string and not hasattr(model.solver, "_options_string_to_dict"):
            for k, v in _options_string_to_dict(model.options.solver_options_string).items():
                model.solver.options[k] = v
    
    # get solver arguments (if any)
    if hasattr(model, "options"):
        solver_args = dict(
            options_string=model.options.solver_options_string,
            keepfiles=model.options.keepfiles,
            tee=model.options.tee,
            symbolic_solver_labels=model.options.symbolic_solver_labels
        )
        # drop all the unspecified options
        solver_args = {k: v for (k, v) in solver_args.items() if v is not None}
    else:
        solver_args={}

    # Automatically send all defined suffixes to the solver
    solver_args["suffixes"] = [c.cname() for c in model.component_objects() if isinstance(c, Suffix)]
    # note: the next few lines are faster than the line above, but seem risky:
    # i = m._ctypes.get(Suffix, [None])[0]
    # solver_args["suffixes"] = []
    # while i is not None:
    #     c, i = m._decl_order[i]
    #     solver_args[suffixes].append(c.cname())
    
    # patch for Pyomo < 4.2
    if not hasattr(model.solver, "_options_string_to_dict"):
        solver_args.pop("options_string", "")

    # solve the model
    if model.options.verbose:
        print "solving model..."
    start = time.time()
    
    if model.options.tempdir is not None:
        # from https://software.sandia.gov/downloads/pub/pyomo/PyomoOnlineDocs.html#_changing_the_temporary_directory
        from pyutilib.services import TempfileManager
        TempfileManager.tempdir = model.options.tempdir

    results = model.solver.solve(model, **solver_args)

    if model.options.verbose:
        print "Total time in solver: {t}s".format(t=time.time()-start)
    
    # check for errors
    model.solutions.load_from(results)
    if results.solver.termination_condition == pyomo.opt.TerminationCondition.infeasible:
        if hasattr(model, "iis"):
            print "Model was infeasible; irreducible infeasible set (IIS) returned by solver:"
            print "\n".join(c.cname() for c in m.iis)
        else:
            print "Model was infeasible; if the solver can generate an irreducible infeasible set,"
            print "more information may be available by calling this script with --suffixes iis ..."
        raise RuntimeError("Infeasible model")
    
    return results

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
    tokens = pyutilib.misc.quote_split('[ ]+',istr)
    for token in tokens:
        index = token.find('=')
        if index is -1:
            raise ValueError(
                "Solver options must have the form option=value: '%s'" % istr)
        try:
            val = eval(token[(index+1):])
        except:
            val = token[(index+1):]
        ans[token[:index]] = val
    return ans



        
###############

if __name__ == "__main__":
    # combine default arguments read from options.txt file with 
    # additional arguments specified on the command line
    args = get_option_file_args()
    # add any command-line arguments
    args.extend(sys.argv[1:])
    main(args)
    
