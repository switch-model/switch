# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Utility functions for SWITCH-pyomo.
"""

import csv
import os
import types
import importlib
import sys
import argparse
import __main__ as main
from pyomo.environ import *
import pyomo.opt
import switch_mod.export # For ampl-tab dialect
import datetime

# This stores full names of modules that are dynamically loaded to
# define a Switch model.
_full_module_names = {}

# Check whether this is an interactive session (determined by whether
# __main__ has a __file__ attribute). Scripts can check this value to
# determine what level of output to display.
interactive_session = not hasattr(main, '__file__')

def define_AbstractModel(*module_list, **kwargs):
    # stub to provide old functionality as we move to a simpler calling convention
    args = kwargs.get("args", sys.argv[1:])
    return create_model(module_list, args)

def create_model(module_list, args=sys.argv[1:]):
    """

    Construct a Pyomo AbstractModel using the Switch modules or packages
    in the given list and return the model. The following utility methods
    are attached to the model as class methods to simplify their use:
    min_data_check(), load_inputs(), save_results().

    This is implemented as calling define_components() for each module
    that has that function defined, then calling
    define_dynamic_components() for each module that has that function
    defined. This division into two stages give some modules an
    opportunity to have dynamic constraints or objective functions. For
    example, financials.define_components() defines empty lists that
    will be used to calculate overall system costs. Other modules such
    as transmission.build and project.build that have components that
    contribute to system costs insert the names of those components into
    these lists. The total system costs equation is defined in
    financials.define_dynamic_components() as the sum of elements in
    those lists. This division into multiple stages allows a user of
    Switch to include additional modules such as demand response or
    storage without rewriting the core equations for system costs. The
    two primary use cases for dynamic components so far are load-zone
    level energy balancing and overall system costs.
    
    All modules can request access to command line parameters and set their
    default values for those options. If this codebase is being used more like a
    library than a stand-alone executable, this behavior can cause problems. For
    example, running this model with PySP's runph tool will cause errors where a
    runph argument such as --instance-directory is unknown to the switch
    modules, so parse_args() generates an error. This behavior can be avoided
    calling this function with an empty list for args: 
        create_model(module_list, args=[])

    SYNOPSIS:
    >>> from switch_mod.utilities import define_AbstractModel
    >>> model = define_AbstractModel(
    ...     'switch_mod', 'project.no_commit', 'fuel_cost')

    """
    # Load modules
    module_list_full_names = _load_modules(module_list)
    model = AbstractModel()
    # Add the list of modules to the model
    model.module_list = module_list_full_names

    # Define and parse model configuration options
    argparser = _ArgumentParser(allow_abbrev=False)
    _define_arguments(model, argparser)
    model.options = argparser.parse_args(args)
    
    # Bind some utility functions to the model as class objects
    _add_min_data_check(model)
    model.load_inputs = types.MethodType(load_inputs, model)
    model.pre_solve = types.MethodType(pre_solve, model)
    model.post_solve = types.MethodType(post_solve, model)
    # note: the next function is redundant with solve and post_solve
    # it is here (temporarily) for backward compatibility
    model.save_results = types.MethodType(save_results, model)

    # Define the model components
    _define_components(model, model.module_list)
    _define_dynamic_components(model, model.module_list)

    return model


def load_inputs(model, inputs_dir=None, attachDataPortal=True):
    """

    Load input data for an AbstractModel using the modules in the given
    list and return a model instance. This is implemented as calling the
    load_inputs() function of each module, if the module has that function.

    SYNOPSIS:
    >>> from switch_mod.utilities import define_AbstractModel
    >>> model = define_AbstractModel(
    ...     'switch_mod', 'project.no_commit', 'fuel_cost')
    >>> instance = model.load_inputs(inputs_dir='test_dat')

    """
    if inputs_dir is None:
        inputs_dir = getattr(model.options, "inputs_dir", "inputs")
    data = DataPortal(model=model)
    # Attach an augmented load data function to the data portal object
    data.load_aug = types.MethodType(load_aug, data)
    _load_inputs(model, inputs_dir, model.module_list, data)

    # At some point, pyomo deprecated 'create' in favor of
    # 'create_instance'. Determine which option is available
    # and use that.
    if hasattr(model, 'create_instance'):
        instance = model.create_instance(data)
    else:
        instance = model.create(data)

    if attachDataPortal:
        instance.DataPortal = data
    return instance


def save_inputs_as_dat(model, instance, save_path="inputs/complete_inputs.dat",
                       exclude=[], deterministic_order=False):
    """
    Save input data to a .dat file for use with PySP or other command line
    tools that have not been fully integrated with DataPortal.

    I wrote a test for this in tests.utilites_test.test_save_inputs_as_dat()
    that calls this function, imports the dat file, and verifies it matches
    the original data.

    SYNOPSIS:
    >>> from switch_mod.utilities import define_AbstractModel
    >>> model = define_AbstractModel(
    ...     'switch_mod', 'project.no_commit', 'fuel_cost')
    >>> instance = model.load_inputs(inputs_dir='test_dat')
    >>> save_inputs_as_dat(model, instance, save_path="test_dat/complete_inputs.dat")
    

    """
    # helper function to convert values to strings,
    # putting quotes around values that start as strings
    quote_str = lambda v: '"{}"'.format(v) if isinstance(v, basestring) else '{}'.format(str(v))
    
    with open(save_path, "w") as f:
        for component_name in instance.DataPortal.data():
            if component_name in exclude:
                continue    # don't write data for components in exclude list 
                            # (they're in scenario-specific files)
            component = getattr(model, component_name)
            comp_class = type(component).__name__
            component_data = instance.DataPortal.data(name=component_name)
            if comp_class == 'SimpleSet' or comp_class == 'OrderedSimpleSet':
                f.write("set " + component_name + " := ")
                f.write(' '.join(map(str, component_data))) # space-separated list
                f.write(";\n")
            elif comp_class == 'IndexedParam':
                if len(component_data) > 0:  # omit components for which no data were provided
                    f.write("param " + component_name + " := ")
                    if component.index_set().dimen == 1:
                        f.write(' '.join(str(key) + " " + quote_str(value)
                                for key,value in component_data.iteritems()))
                    else:
                        f.write("\n")
                        for key,value in (sorted(component_data.iteritems()) 
                                          if deterministic_order 
                                          else component_data.iteritems()):
                            f.write(" " + 
                                    ' '.join(map(str, key)) + " " +
                                    quote_str(value) + "\n")
                    f.write(";\n")
            elif comp_class == 'SimpleParam':
                f.write("param " + component_name + " := " + str(component_data) + ";\n")
            elif comp_class == 'IndexedSet':
                # raise RuntimeError(
                #     "Error with IndexedSet {}. Support for .dat export is not tested.".
                #     format(component_name))
                # print "Warning: exporting IndexedSet {}, but code has not been tested.".format(
                #     component_name)
                for key in component_data:  # note: key is always a tuple
                    f.write("set " + component_name + "[" + ",".join(map(str, key)) + "] := ")
                    f.write(' '.join(map(str, component_data[key]))) # space-separated list
                    f.write(";\n")
            else:
                raise ValueError(
                    "Error! Component type {} not recognized for model element '{}'.".
                    format(comp_class, component_name))

def pre_solve(model, outputs_dir=None):
    """
    Call pre-solve function (if present) in all modules used to compose this model.
    This function can be used to adjust the instance after it is created and before it is solved.
    """
    for module in get_module_list(model):
        if hasattr(module, 'pre_solve'):
            module.pre_solve(model)

def post_solve(model, outputs_dir=None):
    """
    Call post-solve function (if present) in all modules used to compose this model.
    This function can be used to report or save results from the solved model.
    """
    if outputs_dir is None:
        outputs_dir = getattr(model.options, "outputs_dir", "outputs")
    if not os.path.exists(outputs_dir):
        os.makedirs(outputs_dir)
    for module in get_module_list(model):
        if hasattr(module, 'post_solve'):
            module.post_solve(model, outputs_dir)
    _save_generic_results(model, outputs_dir)


def save_results(model, results, instance, outdir):
    """

    Export results in a modular fashion.

    """
    # Ensure the output directory exists. Don't worry about race
    # conditions.
    if not os.path.exists(outdir):
        os.makedirs(outdir)
    
    # Try to load the results and export.
    success = True
    
    if results.solver.termination_condition == pyomo.opt.TerminationCondition.infeasible:
        success = False
        if interactive_session:
            print ("ERROR: Problem is infeasible.") # this could be turned into an exception
    
    if hasattr(instance, 'solutions'):
        instance.solutions.load_from(results)
    else:
        # support for old versions of Pyomo (with undocumented True/False behavior)
        # (we should drop this and require everyone to use a suitably up-to-date pyomo)
        if not instance.load(results):
            success = False
            if interactive_session:
                print ("ERROR: unable to load solver results (may be caused by infeasibililty).")

    if success:
        if interactive_session:
            print "Model solved successfully."
        _save_results(model, instance, outdir, model.module_list)
        _save_generic_results(instance, outdir)
        _save_total_cost_value(instance, outdir)

    return success

def min_data_check(model, *mandatory_model_components):
    """

    This function checks that an instance of Pyomo abstract model has
    mandatory components defined. If a user attempts to create an
    instance without defining all of the necessary data, this will
    produce fatal errors with clear messages stating specifically what
    components have missing data. This function is attached to an
    abstract model by the _add_min_data_check() function. See
    _add_min_data_check() documentation for usage examples.

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
        rule=lambda m: check_mandatory_components(
            m, *mandatory_model_components)))


def _add_min_data_check(model):
    """

    Bind the min_data_check() method to an instance of a Pyomo AbstractModel
    object if it has not already been added. Also add a counter to keep
    track of what to name the next check that is added.

    >>> from switch_mod.utilities import _add_min_data_check
    >>> mod = AbstractModel()
    >>> _add_min_data_check(mod)
    >>> mod.set_A = Set(initialize=[1,2])
    >>> mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'})
    >>> mod.paramA_empty = Param(mod.set_A)
    >>> mod.min_data_check('set_A', 'paramA_full')
    >>> if hasattr(mod, 'create_instance'):
    ...     instance_pass = mod.create_instance()
    ... else:
    ...     instance_pass = mod.create()
    >>> mod.min_data_check('set_A', 'paramA_empty')
    >>> try:
    ...     if hasattr(mod, 'create_instance'):
    ...         instance_fail = mod.create_instance()
    ...     else:
    ...         instance_fail = mod.create()
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
    >>> from pyomo.environ import *
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
    True
    >>> utilities.check_mandatory_components(mod, 'paramB_empty')
    True
    >>> utilities.check_mandatory_components(mod, 'paramC')
    True
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
    return True


def _load_modules(module_list):
    """

    An internal function to recursively load switch modules that define
    components of an abstract model.

    SYNOPSIS:
    >>> from switch_mod.utilities import _load_modules
    >>> full_module_names = _load_modules([
    ...     'switch_mod', 'project.no_commit', 'fuel_cost'])

    This will first attempt to load each listed module from the
    switch_mod package, and will look for them in the broader system
    path if the first attempt fails. If any listed module is a package
    that includes a list named core_modules in __init__.py that contains
    full formed module names, those modules will be loaded recursively
    by this function.

    This function returns the full names of each loaded modules,
    including the "switch_mod." package prefix. After this function
    is called, each loaded module will be accessible via sys.modules

    """
    # Traverse the list of switch modules and load each one.
    full_names = []
    for m in module_list:
        # Skip loading if it was already loaded
        if m in _full_module_names:
            full_names.append(_full_module_names[m])
            continue
        if m in sys.modules:
            # If the module is already loaded, use that.
            # (this is helpful if the model is created by a custom module
            # named "solve" which wants to register its own callbacks or 
            # reporting [and not be replaced by switch_mod.solve])
            module = sys.modules[m]
        else:
            try:
                # First try to load this module from the switch package
                module = importlib.import_module('.' + m, package='switch_mod')
            except ImportError:
                # If that doesn't work, try from the general python path
                module = importlib.import_module(m)
        full_names.append(module.__name__)
        # If this has a list of core_modules, load them.
        if hasattr(module, 'core_modules'):
            _load_modules(module.core_modules)
        # Add this to the list of known loaded modules
        _full_module_names[m] = module.__name__
    return full_names


def get_module_list(model, module_list=None):
    """
    Generator function to yield every module in the module_list (or model.module_list),
    also recursing through the core_modules attribute specified within any of these.
    """
    # TODO: modify _load_modules to return a flattened list (like this does),
    # possibly of modules instead of module names.
    # Then just iterate directly through that in all the later functions.
    if module_list is None:
        module_list = model.module_list
    for module_name in module_list:
        module = sys.modules[module_name]
        yield module
        if hasattr(module, 'core_modules'):
            for cm in get_module_list(model, module.core_modules):
                yield cm

def _define_arguments(model, argparser):
    """
    Call define_arguments() (if present) in all modules that make up the model.
    These functions usually call argparser.add_argument() to define a 
    command-line option used to configure that module. The value of that argument
    will be placed in model.options.xxxx before define_components() is called
    """
    for module in get_module_list(model):
        if hasattr(module, 'define_arguments'):
            module.define_arguments(argparser)


def _define_components(model, module_list):
    """
    A private function to allow recurve calling of defining standard
    components from modules or packages.
    """
    for m in module_list:
        module = sys.modules[m]
        if hasattr(module, 'define_components'):
            module.define_components(model)
        if hasattr(module, 'core_modules'):
            _define_components(model, module.core_modules)


def _define_dynamic_components(model, module_list):
    """
    A private function to allow recurve calling of defining dynamic
    components from modules or packages.
    """
    for m in module_list:
        module = sys.modules[m]
        if hasattr(module, 'define_dynamic_components'):
            module.define_dynamic_components(model)
        if hasattr(module, 'core_modules'):
            _define_dynamic_components(model, module.core_modules)


def _load_inputs(model, inputs_dir, module_list, data):
    """
    A private function to allow recurve calling of loading data from
    modules or packages.
    """
    for m in module_list:
        module = sys.modules[m]
        if hasattr(module, 'load_inputs'):
            module.load_inputs(model, data, inputs_dir)
        if hasattr(module, 'core_modules'):
            _load_inputs(model, inputs_dir, module.core_modules, data)


def _save_results(model, instance, outdir, module_list):
    """
    A private function to allow recurve calling of saving results from
    modules or packages.
    """
    for m in module_list:
        module = sys.modules[m]
        if hasattr(module, 'save_results'):
            module.save_results(model, instance, outdir)
        if hasattr(module, 'core_modules'):
            _save_results(model, instance, outdir, module.core_modules)


def _save_generic_results(instance, outdir, deterministic_order=False):
    for var in instance.component_objects():
        if not isinstance(var, Var):
            continue

        index_name = var.index_set().name
        output_file = os.path.join(outdir, '%s.tab' % var.name)
        with open(output_file, 'wb') as fh:
            writer = csv.writer(fh, dialect='ampl-tab')
            # Write column headings
            writer.writerow(['%s_%d' % (index_name, i + 1)
                             for i in xrange(var.index_set().dimen)] +
                            [var.name])
            # Results are saved in a random order by default for
            # increased speed. Sorting is available if wanted.
            for key, obj in (sorted(var.items())
                            if deterministic_order
                            else var.items()):
                writer.writerow(tuple(make_iterable(key)) + (obj.value,))


def _save_total_cost_value(instance, outdir):
    values = instance.Minimize_System_Cost.values()
    assert len(values) == 1
    total_cost = values[0].expr()
    with open(os.path.join(outdir, 'total_cost.txt'), 'w') as fh:
        fh.write('%s\n' % total_cost)


class InputError(Exception):
    """Exception raised for errors in the input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def load_aug(switch_data, optional=False, auto_select=False,
             optional_params=[], **kwds):
    """

    This is a wrapper for the DataPortal object that accepts additional
    keywords. This currently supports a flag for the file being optional.
    The name load_aug() is not great and may be changed.

    """
    path = kwds['filename']
    # Skip if the file is missing
    if optional and not os.path.isfile(path):
        return
    # copy the optional_params to avoid side-effects when the list is altered below
    optional_params=list(optional_params)
    # Parse header and first row
    with open(path) as infile:
        headers = infile.readline().strip().split('\t')
        dat1 = infile.readline().strip().split('\t')
    # Skip if the file is empty or has no data in the first row.
    if optional and (headers == [''] or dat1 == ['']):
        return
    # Try to get a list of parameters. If param was given as a
    # singleton or a tuple, make it into a list that can be edited.
    params = []
    if 'param' in kwds:
        # Tuple -> list
        if isinstance(kwds['param'], tuple):
            kwds['param'] = list(kwds['param'])
        # Singleton -> list
        elif not isinstance(kwds['param'], list):
            kwds['param'] = [kwds['param']]
        params = kwds['param']
    # optional_params may include Param objects instead of names. In
    # those cases, convert objects to names.
    for (i, p) in enumerate(optional_params):
        if not isinstance(p, basestring):
            optional_params[i] = p.name
    # Expand the list optional parameters to include any parameter that
    # has default() defined. I need to allow an explicit list of default
    # parameters to support optional parameters like g_unit_size which
    # don't have default value because it is undefined for generators
    # for which it does not apply.
    for p in params:
        if p.default() is not None:
            optional_params.append(p.name)
    # How many index columns do we expect?
    # Grab the dimensionality of the index param if it was provided.
    if 'index' in kwds:
        num_indexes = kwds['index'].dimen
    # Next try the first parameter's index.
    elif len(params) > 0:
        try:
            num_indexes = params[0].index_set().dimen
        except ValueError:
            num_indexes = 0
    # Default to 0 if both methods failed.
    else:
        num_indexes = 0
    # Make a select list if requested. Assume the left-most columns are
    # indexes and that other columns are named after their parameters.
    # Maybe this could be extended to use a standard prefix for each data file?
    # e.g., things related to regional fuel market supply tiers (indexed by RFM_SUPPLY_TIER)
    # could all get the prefix "rfm_supply_tier_". Then they could get shorter names
    # within the file (e.g., "cost" and "limit"). We could also require the data file
    # to be called "rfm_supply_tier.tab" for greater consistency/predictability.
    if auto_select:
        if 'select' in kwds:
            raise InputError('You may not specify a select parameter if ' +
                             'auto_select is set to True.')
        kwds['select'] = headers[0:num_indexes]
        kwds['select'].extend([p.name for p in params])
    # Check to see if expected column names are in the file. If a column
    # name is missing and its parameter is optional, then drop it from
    # the select & param lists.
    if 'select' in kwds:
        if isinstance(kwds['select'], tuple):
            kwds['select'] = list(kwds['select'])
        del_items = []
        for (i, col) in enumerate(kwds['select']):
            p_i = i - num_indexes
            if col not in headers:
                if(len(params) > p_i >= 0 and
                   params[p_i].name in optional_params):
                    del_items.append((i, p_i))
                else:
                    raise InputError(
                        'Column {} not found in file {}.'
                        .format(col, path))
        # When deleting entries from select & param lists, go from last
        # to first so that the indexes won't get messed up as we go.
        del_items.sort(reverse=True)
        for (i, p_i) in del_items:
            del kwds['select'][i]
            del kwds['param'][p_i]
    # All done with cleaning optional bits. Pass the updated arguments
    # into the DataPortal.load() function.
    switch_data.load(**kwds)


# Define an argument parser that accepts the allow_abbrev flag to 
# prevent partial matches, even on versions of Python before 3.5.
# See https://bugs.python.org/issue14910
# This is needed because the parser may sometimes be called with only a subset 
# of the eventual argument list (e.g., to parse module-related arguments before
# loading the modules and adding their arguments to the list), and without this
# flag, the parser could match arguments that are meant to be used later
# (It's not likely, but for example if the user specifies a flag "--exclude",
# which will be consumed by one of their modules, the default parser would
# match that to "--exclude-modules" during the early, partial parse.)
if sys.version_info >= (3, 5):
    _ArgumentParser = argparse.ArgumentParser
else:
    # patch ArgumentParser to accept the allow_abbrev flag 
    # (works on Python 2.7 and maybe others)
    class _ArgumentParser(argparse.ArgumentParser):
        def __init__(self, *args, **kwargs):
            if not kwargs.get("allow_abbrev", True):
                if hasattr(self, "_get_option_tuples"):
                    # force self._get_option_tuples to return an empty list (of partial matches)
                    # see https://bugs.python.org/issue14910#msg204678
                    def new_get_option_tuples(self, option_string):
                        return []
                    self._get_option_tuples = types.MethodType(new_get_option_tuples, self)
                else:
                    raise RuntimeError(
                        "Incompatible argparse module detected. This software requires "
                        "Python 3.5 or later, or an earlier version of argparse that defines "
                        "ArgumentParser._get_option_tuples()"
                    )
            # consume the allow_abbrev argument if present
            kwargs.pop("allow_abbrev", None)
            return argparse.ArgumentParser.__init__(self, *args, **kwargs)


def approx_equal(a, b, tolerance=0.01):
    return abs(a-b) <= (abs(a) + abs(b)) / 2.0 * tolerance


def default_solver():
    return pyomo.opt.SolverFactory('glpk')

def make_iterable(item):
    """Return an iterable for the one or more items passed."""
    if isinstance(item, basestring):
        i = iter([item])
    else:
        try:
            # check if it's iterable
            i = iter(item)
        except TypeError:
            i = iter([item])
    return i


class Logging:
    """
    Assign standard output and a log file as output destinations. This is accomplished by assigning this class
    to sys.stdout.
    """
    def __init__(self, logs_dir):
        # Make logs directory if class is initialized
        if not os.path.exists(logs_dir):
            os.mkdir(logs_dir)

        # Assign sys.stdout and a log file as locations to write to
        self.terminal = sys.stdout
        self.log_file_path = os.path.join(logs_dir, datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + ".log")
        self.log_file = open(self.log_file_path, "w", buffering=1)

    def __getattr__(self, attr):
        """
        Default to sys.stdout attributes when calling attributes for this class.
        This is here to prevent unintended consequences for code that assumes sys.stdout is an object with its own
        methods, etc.
        """
        return getattr(self.terminal, attr)

    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)

    def flush(self):
        self.terminal.flush()
        self.log_file.flush()

