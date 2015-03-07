"""
Utility functions for switch-pyomo.
This code can be tested with `python -m doctest -v utilities.py`
"""

from coopr.pyomo import *


def check_mandatory_components(model, *mandatory_model_components):
    """
    Checks whether mandatory elements of a Pyomo model are populated,
    and reports an error message if they don't exist.

    If an argument is a set, it must have non-zero length.

    If an argument is an indexed parameter, it must have a value for
    every index in the indexed set. Do not use this for indexed params
    that have default values. If the set indexing a param is not
    mandatory and is empty, then the indexed parameter may be empty as
    well.

    If an argument is a simple parameter, it must have a value.

    This does not work with indexed sets.

    EXAMPLE:
    >>> from coopr.pyomo import *
    >>> import utilities
    >>> mod = ConcreteModel()
    >>> mod.set_A = Set(initialize=[1,2])
    >>> mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'})
    >>> mod.paramA_empty = Param(mod.set_A)
    >>> mod.set_B = Set()
    >>> mod.paramB_empty = Param(mod.set_B)
    >>> mod.paramC = Param(initialize=1)
    >>> mod.paramD = Param()
    >>> utilities.check_mandatory_components(mod, 'set_A', 'paramA_full')
    1
    >>> utilities.check_mandatory_components(mod, 'paramB_empty')
    1
    >>> utilities.check_mandatory_components(mod, 'paramC')
    1
    >>> try:
    ...     utilities.check_mandatory_components(mod, 'set_A', 'paramA_empty')
    ... except ValueError as e:
    ...     print e
    ERROR! Values are not provided for every element of indexed parameter 'paramA_empty'
    >>> try:
    ...     utilities.check_mandatory_components(mod, 'set_A', 'set_B')
    ... except ValueError as e:
    ...     print e
    ERROR! No data is defined for the set 'set_B'.
    >>> try:
    ...     utilities.check_mandatory_components(mod, 'paramC', 'paramD')
    ... except ValueError as e:
    ...     print e
    ERROR! Value not provided for parameter 'paramD'

    # Demonstration of incorporating this funciton into Pyomo's BuildCheck()
    >>> mod.min_dat_pass = BuildCheck(rule=lambda m: \
            utilities.check_mandatory_components(m, 'set_A', 'paramA_full', \
                                               'paramB_empty', 'paramC'))
    """

    for e in mandatory_model_components:
        obj = getattr(model, e)
        o_class = type(obj).__name__
        if o_class == 'SimpleSet' or o_class == 'OrderedSimpleSet':
            if len(obj) == 0:
                raise ValueError(
                    "ERROR! No data is defined for the set '{}'.".format(e))
        elif o_class == 'IndexedParam':
            if len(obj) != len(obj._index):
                raise ValueError(
                    ("ERROR! Values are not provided for every element of " +
                     "indexed parameter '{}'").format(e))
        elif o_class == 'SimpleParam':
            if obj.value is None:
                raise ValueError(
                    "ERROR! Value not provided for parameter '{}'".format(e))
        else:
            raise ValueError(
                "Error! Object type not recognized for model element '{}'.".
                format(e))
    return 1
