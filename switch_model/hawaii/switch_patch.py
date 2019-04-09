from pyomo.environ import *

def define_components(m):
    """Make various changes to the model to support hawaii-specific modules."""

    # define an indexed set of all periods before or including the current one.
    # this is useful for calculations that must index over previous and current periods
    # e.g., amount of capacity of some resource that has been built
    # This isn't very good form (generally every asset should have a lifetime and we
    # should refer to that), so it's not included in the core model.
    m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD = Set(
        m.PERIODS, ordered=True,
        initialize=lambda m, p:
            [p2 for p2 in m.PERIODS if m.PERIODS.ord(p2) <= m.PERIODS.ord(p)]
    )

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
