"""
Utility functions for SWITCH-pyomo.

This code can be tested with `python -m doctest utilities.py`

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org

"""

import types
from pyomo.environ import *

# This stores modules that are dynamically loaded to define a Switch
# model.
_loaded_switch_modules = {}


def min_data_check(model, *mandatory_model_components):
    """

    This function checks that an instance of Pyomo abstract model has
    mandatory components defined. If a user attempts to create an
    instance without defining all of the necessary data, this will
    produce fatal errors with clear messages stating specifically what
    components have missing data. This function is attached to an
    abstract model by the add_min_data_check() function. See
    add_min_data_check() documentation for usage examples.

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

    """
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

    >>> import switch_mod.utilities as utilities
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
    and returns a clear error message if they don't exist.

    Typically, this method is not used directly. Instead, the
    min_data_check() method will set up a BuildCheck that uses this
    function.

    If an argument is a set, it must have non-zero length.

    If an argument is an indexed parameter, it must have a value for
    every index in the indexed set. Do not use this for indexed params
    that have default values. If the set indexing a param is not
    mandatory and is empty, then the indexed parameter may be empty as
    well.

    If an argument is a simple parameter, it must have a value.

    This does not work with indexed sets.

    EXAMPLE:
    >>> import switch_mod.utilities as utilities
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


def load_modules(module_list):
    """

    Load switch modules that define components of an abstract model.

    SYNOPSIS:
    >>> import switch_mod.utilities as utilities
    >>> switch_modules = ('timescales', 'financials', 'load_zones')
    >>> utilities.load_modules(switch_modules)

    load_modules() is effectively the same as a series of import
    statements except the module names are assumed to skip the
    "switch_mod." prefix, and the loaded modules are stored in a private
    list called _loaded_switch_modules.

    """
    # Go through each entry in the list and load it as a module.
    import importlib
    for m in module_list:
        # Load module if we haven't already
        if m not in _loaded_switch_modules:
            if 'switch_mod' not in m:
                full_name = 'switch_mod.' + m
            else:
                full_name = m
            _loaded_switch_modules[m] = importlib.import_module(full_name)
            if hasattr(_loaded_switch_modules[m], 'core_modules'):
                load_modules(_loaded_switch_modules[m].core_modules)


def define_AbstractModel(module_list):
    """

    Construct an AbstractModel object using the modules in the given
    list and return the model. This is implemented as calling
    define_components() for each module that has that function defined,
    then calling define_dynamic_components() for each module that has
    that function defined.

    This division into two stages give some modules an opportunity to
    have dynamic constraints or objective functions. For example,
    financials.define_components() defines empty lists that will be used
    to calculate overall system costs. Other modules such as
    transmission.build and project.build that have components that
    contribute to system costs insert the names of those components into
    these lists. The total system costs equation is defined in
    financials.define_dynamic_components() as the sum of elements in
    those lists. This division into multiple stages allows a user of
    Switch to include additional modules such as demand response or
    storage without rewriting the core equations for system costs. The
    two primary use cases for dynamic components so far are load-zone
    level energy balancing and overall system costs.

    SYNOPSIS:
    >>> import switch_mod.utilities as utilities
    >>> switch_modules = ('timescales', 'financials', 'load_zones')
    >>> utilities.load_modules(switch_modules)
    >>> switch_model = utilities.define_AbstractModel(switch_modules)

    """
    model = AbstractModel()
    _define_components(module_list, model)
    _define_dynamic_components(module_list, model)
    return model


def _define_components(module_list, model):
    """
    A private function to allow recurve calling of defining standard
    components from modules or packages.
    """
    for m in module_list:
        if hasattr(_loaded_switch_modules[m], 'define_components'):
            _loaded_switch_modules[m].define_components(model)
        if hasattr(_loaded_switch_modules[m], 'core_modules'):
            _define_components(_loaded_switch_modules[m].core_modules, model)


def _define_dynamic_components(module_list, model):
    """
    A private function to allow recurve calling of defining dynamic
    components from modules or packages.
    """
    for m in module_list:
        if hasattr(_loaded_switch_modules[m], 'define_dynamic_components'):
            _loaded_switch_modules[m].define_dynamic_components(model)
        if hasattr(_loaded_switch_modules[m], 'core_modules'):
            _define_dynamic_components(
                _loaded_switch_modules[m].core_modules, model)


def load_data(model, inputs_dir, module_list):
    """

    Load data for an AbstractModel using the modules in the given list
    and return a DataPortal object suitable for creating a model
    instance. This is implemented as calling the load_data() function of
    each module, if the module has that function.

    SYNOPSIS:
    >>> import switch_mod.utilities as utilities
    >>> switch_modules = ('timescales', 'financials', 'load_zones')
    >>> utilities.load_modules(switch_modules)
    >>> switch_model = utilities.define_AbstractModel(switch_modules)
    >>> inputs_dir = 'test_dat'
    >>> data = utilities.load_data(switch_model, inputs_dir, switch_modules)
    >>> switch_instance = switch_model.create(data)

    """
    data = DataPortal(model=model)
    _load_data(model, inputs_dir, module_list, data)
    return data


def _load_data(model, inputs_dir, module_list, data):
    """
    A private function to allow recurve calling of loading data from
    modules or packages.
    """
    for m in module_list:
        if hasattr(_loaded_switch_modules[m], 'load_data'):
            _loaded_switch_modules[m].load_data(model, data, inputs_dir)
        if hasattr(_loaded_switch_modules[m], 'core_modules'):
            _load_data(model, inputs_dir,
                       _loaded_switch_modules[m].core_modules, data)
