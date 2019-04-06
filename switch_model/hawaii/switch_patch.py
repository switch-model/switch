from pyomo.environ import *
import switch_model.utilities as utilities

# Code below is in switch_model.solve now
# # micro-patch pyomo.core.base.PyomoModel.ModelSolutions.add_solution
# # to use a cache for component names; otherwise reloading a solution
# # takes longer than solving the model from scratch.
# # TODO: create a pull request for Pyomo to do this
# import inspect, textwrap, types
#
# def replace_method(class_ref, method_name, new_source_code):
#     """
#     Replace specified class method with a compiled version of new_source_code.
#     """
#     orig_method = getattr(class_ref, method_name)
#     # compile code into a function
#     workspace = dict()
#     exec(textwrap.dedent(new_source_code), workspace)
#     new_method = workspace[method_name]
#     # create a new function with the same body, but using the old method's namespace
#     new_func = types.FunctionType(
#         new_method.__code__,
#         orig_method.__globals__,
#         orig_method.__name__,
#         orig_method.__defaults__,
#         orig_method.__closure__
#     )
#     # note: this normal function will be automatically converted to an unbound
#     # method when it is assigned as an attribute of a class
#     setattr(class_ref, method_name, new_func)
#
# old_code = """
#                     for obj in instance.component_data_objects(Var):
#                         cache[obj.name] = obj
#                     for obj in instance.component_data_objects(Objective, active=True):
#                         cache[obj.name] = obj
#                     for obj in instance.component_data_objects(Constraint, active=True):
#                         cache[obj.name] = obj
# """
# new_code = """
#                     # use buffer to avoid full search of component for data object
#                     # which introduces a delay that is quadratic in model size
#                     buf=dict()
#                     for obj in instance.component_data_objects(Var):
#                         cache[obj.getname(fully_qualified=True, name_buffer=buf)] = obj
#                     for obj in instance.component_data_objects(Objective, active=True):
#                         cache[obj.getname(fully_qualified=True, name_buffer=buf)] = obj
#                     for obj in instance.component_data_objects(Constraint, active=True):
#                         cache[obj.getname(fully_qualified=True, name_buffer=buf)] = obj
# """
#
# from pyomo.core.base.PyomoModel import ModelSolutions
# add_solution_code = inspect.getsource(ModelSolutions.add_solution)
# if old_code in add_solution_code:
#     # create and inject a new version of the method code
#     add_solution_code = add_solution_code.replace(old_code, new_code)
#     replace_method(ModelSolutions, 'add_solution', add_solution_code)
# else:
#     print(
#         "NOTE: The patch to pyomo.core.base.PyomoModel.ModelSolutions.add_solution "
#         "has been deactivated because the Pyomo source code has changed. "
#         "Check whether this patch is still needed and edit {} accordingly."
#         .format(__file__)
#     )
#
# x = 7
# def prx(arg=81):
#     print x, arg
# prx()
# # both of these fail, readonly attribute
# # prx.__globals__ = {'prx': prx, 'x': 99}
# # prx.func_globals = {'prx': prx, 'x': 99}
#
# f = prx
# prx2 = types.FunctionType(f.__code__, {'prx': prx, 'x': 99}, f.__name__, f.__defaults__, f.__closure__)
# prx2(22)
#
# f = ModelSolutions.add_solution
# new_f = types.FunctionType(f.__code__, f.__globals__, f.__name__, f.__defaults__, f.__closure__)
#
# type(prx)
#
# def func(test='no argument'):
#     print test
# func(3)
#
# func.func_globals
#
# new_func = types.FunctionType(
#     func.func_code,
#     func.func_globals,
#     'new_func'
# )
# new_func()
#
# from pyomo.environ import *
# ms = ModelSolutions(AbstractModel())
# ms.add_solution(1, 2, 3, 4, 5, 6, 7)
#
# from pyomo.environ import *
# from pyomo.core.base.PyomoModel import ModelSolutions
# new_code = """
#     def add_symbol_map(self, symbol_map=None):
#         print logging
# """
# replace_method(ModelSolutions, 'add_symbol_map', new_code)
# ms = ModelSolutions(AbstractModel())
# ms.add_symbol_map()
#
# ms.add_solution.func_code.co_names
#
#     new_bytecode = types.CodeType(
#         fc.co_argcount,
#         fc.co_nlocals,
#         fc.co_stacksize,
#         fc.co_flags,
#         new_method.func_code.co_code,
#         fc.co_consts,
#         fc.co_names,
#         fc.co_varnames,
#         fc.co_filename,
#         fc.co_name,
#         fc.co_firstlineno,
#         fc.co_lnotab
#     )
#
#
# ModelSolutions.add_symbol_map
#
# import types
# class C(object):
#     def __init__(self):
#         self.val = 3
#
# def get_val(self):
#     return self.val
#
# C.get_val = types.MethodType(get_val, None, C)
# C.get_val
# C.__init__
# o = C()
# o.get_val()
#
# o.get_val = types.MethodType(get_val, o)
# o.get_val()


# (class_ref, name, new_source_code) = (ModelSolutions, 'add_solution', add_solution_code)
#
# space = dict()
# exec("class Dummy(object):\n" + add_solution_code, space)
# type(space['Dummy'].add_solution)

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


# def define_components(m):
#     """Make various changes to the model to facilitate reporting and avoid unwanted behavior"""
#
#     # define an indexed set of all periods before or including the current one.
#     # this is useful for calculations that must index over previous and current periods
#     # e.g., amount of capacity of some resource that has been built
#     m.CURRENT_AND_PRIOR_PERIODS = Set(m.PERIODS, ordered=True, initialize=lambda m, p:
#         # note: this is a fast way to refer to all previous periods, which also respects
#         # the built-in ordering of the set, but you have to be careful because
#         # (a) pyomo sets are indexed from 1, not 0, and
#         # (b) python's range() function is not inclusive on the top end.
#         [m.PERIODS[i] for i in range(1, m.PERIODS.ord(p)+1)]
#     )
