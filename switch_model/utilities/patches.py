import inspect
import textwrap
import types

import pyomo.version
from pyomo.core.base.misc import _robust_sort_keyfcn


def fixed_robust_sort_keyfcn(self, val, use_key=True):
    """Generate a tuple ( str(type_name), val ) for sorting the value.

    `key=` expects a function.  We are generating a functor so we
    have a convenient place to store the _typemap, which converts
    the type-specific functions for converting a value to the second
    argument of the sort key.

    """
    if use_key and self._key is not None:
        val = self._key(val)

    try:
        i, _typename = self._typemap[val.__class__]
    except KeyError:
        # If this is not a type we have seen before, determine what
        # to use for the second value in the tuple.
        _type = val.__class__
        _typename = _type.__name__
        try:
            # 1: Check if the type is comparable.  In Python 3, sorted()
            #    uses "<" to compare objects.
            val < val
            i = 1
        except:
            try:
                # 2: try converting the value to string
                str(val)
                i = 2
            except:
                # 3: fallback on id().  Not deterministic
                #    (run-to-run), but at least is consistent within
                #    this run.
                i = 3
        self._typemap[_type] = i, _typename
    if i == 1:
        return _typename, val
    elif i == 3:
        return _typename, tuple(self(v, use_key=False) for v in val)
    elif i == 2:
        return _typename, str(val)
    else:
        return _typename, id(val)

def patch_pyomo():
    # fix Pyomo issue #2019. Once PR #2020 gets released this will no longer be needed
    from pyomo.core.base.misc import _robust_sort_keyfcn
    setattr(_robust_sort_keyfcn, "__call__", fixed_robust_sort_keyfcn)

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