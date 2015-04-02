"""
Utility functions for SWITCH-pyomo.

Currently, this implements functions to check that an instance of Pyomo
abstract model has mandatory components defined. If a user attempts to
create an instance without defining all of the necessary data, this will
produce fatal errors with clear messages stating specifically what
components have missing data.

Without this check, I would get fatal errors if I forgot to specify data
for a component that didn't have a default value, but the error message
was obscure and gave me a line number with the first snippet of code
that tried to reference the component with missing data. It took me a
little bit of time to figure out what was causing that failure, and I'm
a skilled programmer. I would like this model to be accessible to non-
programmers as well, so I felt it was important to use the BuildCheck
Pyomo function to validate data during construction of a model instance.

I found that BuildCheck's message listed the name of the check that
failed, but did not provide mechanisms for printing a specific error
message. I tried printing to the screen, but that output tended to be
obscured or hidden. I've settled on raising a ValueError for now with a
clear and specific message. I could also use logging.error() or related
logger methods, and rely on BuildCheck to throw an error, but I've
already implemented this, and those other methods don't offer any clear
advantages that I can see.

This code can be tested with `python -m doctest -v utilities.py`

"""

import types
from coopr.pyomo import *


def min_data_check(model, *mandatory_model_components):
    model.__num_min_data_checks += 1
    new_data_check_name = "min_data_check_" + str(model.__num_min_data_checks)
    setattr(model, new_data_check_name, BuildCheck(
        rule=lambda mod: check_mandatory_components(
            mod, *mandatory_model_components)))


def add_min_data_check(model):
    """

    Bind the min_data_check() method to an instance of a Pyomo AbstractModel
    object if it has not already been added. Also add a counter to keep
    track of what to name the next check that is added.

    >>> from coopr.pyomo import *
    >>> import utilities
    >>> mod = AbstractModel()
    >>> utilities.add_min_data_check(mod)
    >>> mod.set_A = Set(initialize=[1,2])
    >>> mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'})
    >>> mod.paramA_empty = Param(mod.set_A)
    >>> mod.min_data_check('set_A', 'paramA_full')
    >>> instance_pass = mod.create()
    >>> mod.min_data_check('set_A', 'paramA_empty')
    >>> try:
    ...     instance_fail = mod.create()
    ... except ValueError as e:
    ...     print e  # doctest: +NORMALIZE_WHITESPACE
    ERROR: Constructing component 'min_data_check_2' from data=None failed:
        ValueError: Values are not provided for every element of the
        mandatory parameter 'paramA_empty'
    Values are not provided for every element of the mandatory parameter
    'paramA_empty'


    """
    if getattr(model, 'min_data_check', None) is None:
        model.__num_min_data_checks = 0
        model.min_data_check = types.MethodType(min_data_check, model)


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
    >>> utilities.check_mandatory_components(\
        mod, 'set_A', 'paramA_empty') # doctest: +NORMALIZE_WHITESPACE
    Traceback (most recent call last):
        ...
    ValueError: Values are not provided for every element of the
    mandatory parameter 'paramA_empty'
    >>> utilities.check_mandatory_components(mod, 'set_A', 'set_B')
    Traceback (most recent call last):
        ...
    ValueError: No data is defined for the mandatory set 'set_B'.
    >>> utilities.check_mandatory_components(mod, 'paramC', 'paramD')
    Traceback (most recent call last):
        ...
    ValueError: Value not provided for mandatory parameter 'paramD'

    # Demonstration of incorporating this funciton into Pyomo's BuildCheck()
    >>> mod.min_dat_pass = BuildCheck(\
            rule=lambda m: utilities.check_mandatory_components(\
                m, 'set_A', 'paramA_full','paramB_empty', 'paramC'))
    """

    for component_name in mandatory_model_components:
        obj = getattr(model, component_name)
        o_class = type(obj).__name__
        if o_class == 'SimpleSet' or o_class == 'OrderedSimpleSet':
            if len(obj) == 0:
                raise ValueError(
                    "No data is defined for the mandatory set '{}'.".
                    format(component_name))
        elif o_class == 'IndexedParam':
            if len(obj) != len(obj._index):
                raise ValueError(
                    ("Values are not provided for every element of " +
                     "the mandatory parameter '{}'").format(component_name))
        elif o_class == 'IndexedSet':
            if len(obj) != len(obj._index):
                raise ValueError(
                    ("Sets are not defined for every index of " +
                     "the mandatory indexed set '{}'").format(component_name))
        elif o_class == 'SimpleParam':
            if obj.value is None:
                raise ValueError(
                    "Value not provided for mandatory parameter '{}'".
                    format(component_name))
        else:
            raise ValueError(
                "Error! Object type {} not recognized for model element '{}'.".
                format(o_class, component_name))
    return 1
