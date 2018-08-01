from pyomo.environ import *
import switch_model.utilities as utilities

# patch Pyomo's solver to retrieve duals and reduced costs for MIPs from cplex lp solver
# (This could be made permanent in pyomo.solvers.plugins.solvers.CPLEX.create_command_line)
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
    print "changed CPLEX solve script to the following:"
    print command.script
    return command
from pyomo.solvers.plugins.solvers.CPLEX import CPLEXSHELL
old_create_command_line = CPLEXSHELL.create_command_line
CPLEXSHELL.create_command_line = new_create_command_line

# # TODO: combine the following changes into a pull request for Pyomo
# # patch Pyomo's table-reading function to allow .tab files with headers but no data
# import os, re
# def new_tab_read(self):
#     if not os.path.exists(self.filename):
#         raise IOError("Cannot find file '%s'" % self.filename)
#     self.FILE = open(self.filename, 'r')
#     try:
#         tmp=[]
#         for line in self.FILE:
#             line=line.strip()
#             tokens = re.split("[\t ]+",line)
#             if tokens != ['']:
#                 tmp.append(tokens)
#         if len(tmp) == 0:
#             raise IOError("Empty *.tab file")
#         else:  # removed strange special handling for one-row files
#             self._set_data(tmp[0], tmp[1:])
#     except:
#         raise
#     finally:
#         self.FILE.close()
#         self.FILE = None
# from pyomo.core.plugins.data.text import TextTable
# TextTable.read = new_tab_read
#
# try:
#     import inspect
#     import pyomo.core.data.process_data
#     pp_code = inspect.getsource(pyomo.core.data.process_data._process_param)
#     start = pp_code.find('if singledef:', 0, 2000)
#     if start < 0:
#         raise RuntimeError('unable to find singledef statement')
#     # patch to allow command to have no more arguments at this point (i.e., no data)
#     srch, repl = 'if cmd[0] == "(tr)":', 'if cmd and cmd[0] == "(tr)":'
#     start = pp_code.find(srch, start, start + 500)
#     if start < 0:
#         raise RuntimeError('unable to find (tr) statement')
#     pp_code = pp_code[:start] + repl + pp_code[start+len(srch):]
#     # patch next line for the same reason
#     srch, repl = 'if cmd[0] != ":":', 'if not cmd or cmd[0] != ":":'
#     start = pp_code.find(srch, start, start + 500)
#     if start < 0:
#         raise RuntimeError('unable to find ":" statement')
#     pp_code = pp_code[:start] + repl + pp_code[start+len(srch):]
#     # compile code to a function in the process_data module
#     exec(pp_code, vars(pyomo.core.data.process_data))
# except Exception as e:
#     print "Unable to patch current version of pyomo.core.data.process_data:"
#     print '{}({})'.format(type(e).__name__, ','.join(repr(a) for a in e.args))
#     print "Switch will not be able to read empty data files."


def define_components(m):
    """Make various changes to the model to facilitate reporting and avoid unwanted behavior"""
    
    # define an indexed set of all periods before or including the current one.
    # this is useful for calculations that must index over previous and current periods
    # e.g., amount of capacity of some resource that has been built
    m.CURRENT_AND_PRIOR_PERIODS = Set(m.PERIODS, ordered=True, initialize=lambda m, p:
        # note: this is a fast way to refer to all previous periods, which also respects 
        # the built-in ordering of the set, but you have to be careful because 
        # (a) pyomo sets are indexed from 1, not 0, and
        # (b) python's range() function is not inclusive on the top end.
        [m.PERIODS[i] for i in range(1, m.PERIODS.ord(p)+1)]
    )
    
    # create lists of projects by energy source
    # we sort these to help with display, but that may not actually have any effect
    m.GENERATION_PROJECTS_BY_FUEL = Set(m.FUELS, initialize=lambda m, f:
        sorted([p for p in m.FUEL_BASED_GENS if f in m.FUELS_FOR_GEN[p]])
    )
    m.GENERATION_PROJECTS_BY_NON_FUEL_ENERGY_SOURCE = Set(m.NON_FUEL_ENERGY_SOURCES, initialize=lambda m, s:
        sorted([p for p in m.NON_FUEL_BASED_GENS if m.gen_energy_source[p] == s])
    )

