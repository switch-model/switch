import textwrap
import types
from typing import Type

from pyomo.environ import Set, Param

from switch_model.utilities.load_data import register_component_for_loading

_patched_pyomo = False

def patch_pyomo():
    global _patched_pyomo

    if _patched_pyomo:
        return

    # Patch Set and Param to allow specifying input file location (via input_file="...")
    extend_to_allow_loading(Set)
    extend_to_allow_loading(Param)

    _patched_pyomo = True

def extend_to_allow_loading(cls: Type):
    def new_init(self, *args, input_file=None, input_column=None, input_optional=None, **kwargs):
        self.__old_init__(*args, **kwargs)
        if input_file is not None:
            register_component_for_loading(self, input_file, input_column, input_optional, **kwargs)

    cls.__old_init__ = cls.__init__
    cls.__init__ = new_init


def replace_method(class_ref, method_name, new_source_code):
    """
    Replace specified class method with a compiled version of new_source_code.
    This isn't be used at the moment but we are leaving it for reference
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