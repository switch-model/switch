# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Utility functions for Switch.
"""
from __future__ import print_function

import functools
import os, types, sys, argparse, time, datetime, traceback, subprocess, platform
import warnings

import switch_model.__main__ as main
from pyomo.environ import *
from pyomo.core.base.set import UnknownSetDimen
from pyomo.dataportal import DataManagerFactory
from pyomo.dataportal.plugins.csv_table import CSVTable

from switch_model.utilities.results_info import add_info, ResultsInfoSection
from switch_model.utilities.scaling import _ScaledVariable, _get_unscaled_expression
import pyomo.opt

# Define string_types (same as six.string_types). This is useful for
# distinguishing between strings and other iterables.
string_types = (str,)

# Check whether this is an interactive session (determined by whether
# __main__ has a __file__ attribute). Scripts can check this value to
# determine what level of output to display.
interactive_session = not hasattr(main, '__file__')


class CustomModel(AbstractModel):
    """
    Class that wraps pyomo's AbstractModel and adds custom features.

    Currently the only difference between this class and pyomo's AbstractModel
    is that this class supports variable scaling. See utilities/scaling.py for
    more details.
    """

    def __init__(self, *args, **kwargs):
        super(CustomModel, self).__init__(*args, **kwargs)
        self.can_use_duals = None
        # We use a scaling factor for our objective function
        # to improve the numerical properties
        # of the model. The scaling factor was determined using trial
        # and error and this tool https://github.com/staadecker/lp-analyzer.
        # Learn more by reading the documentation on Numerical Issues.
        self.objective_scaling_factor = 1e-3

    def __setattr__(self, key, val):
        # __setattr__ is called whenever we set an attribute
        # to the model (e.g. model.some_key = some_value)
        # We want to do as normal unless we try assigning a _ScaledVariable to the model.
        if isinstance(val, _ScaledVariable):
            # If we are assigning a _ScaledVariable to the model then we actually
            # want to assign both a scaled variable and an unscaled expression to the model
            # We want to assign the scaled variable to a key with a prefix '_scaled_'
            # and the unscaled expression to the key without the prefix.
            # This way throughout the SWITCH code the unscaled expression will be used however
            # pyomo will be using the scaled variable when solving.

            # Set the unscaled_name of the variable
            val.unscaled_name = key
            # Set the name of the scaled variable
            val.scaled_name = "_scaled_" + key
            # Add the scaled variable to the model with the name we just found
            super().__setattr__(val.scaled_name, val)
            # Add the unscaled expression to the model with the original value provided by 'key'
            super().__setattr__(key, _get_unscaled_expression(val))
        else:
            super().__setattr__(key, val)

    def get_dual(self, component_name: str, *args, divider=None, invalid_return="."):
        """
        Returns the dual value for the given component.

        @param component_name: Name of the constraint to return the dual value for
        @param *args: Indexes of the component. For example, if the component is the energy
                        balance constraint, *args would be z, t for load_zone and timepoint
        @param divider: How much to divide the dual by. This is useful since the undivided dual
                        represents the increase in cost after scaling costs to the base year.
                        Often however, we wish to know the increase in cost prior to scaling,
                        for example the increase in cost of just one timepoint. As such
                        divider is often m.bring_timepoint_costs_to_base_year[t] or
                        m.bring_annual_costs_to_base_year[p].
        @param invalid_return: is what to return when the dual value doesn't exist. Defaults to "."
                                since normally duals are being outputed to a file and "." is used for
                                missing values.
        """
        # Get the component
        component = getattr(self, component_name)

        # If can_use_duals has not been set, set it with by checking has_discrete_variables
        if self.can_use_duals is None:
            # If the model has discrete variables dual values aren't meaningful and therefore we don't produce them
            self.can_use_duals = not has_discrete_variables(self)

        # Get the dual value if available
        if self.can_use_duals and args in component and component[args] in self.dual:
            # We divide by the scaling factor to undo the effects of it on the dual values
            dual = self.dual[component[args]] / self.objective_scaling_factor
            if divider:
                dual /= divider
            return dual
        else:
            return invalid_return

    def enable_duals(self):
        """
        Enables duals if not already enabled
        """
        if not hasattr(self, "dual"):
            self.dual = Suffix(direction=Suffix.IMPORT)


def define_AbstractModel(*module_list, **kwargs):
    # stub to provide old functionality as we move to a simpler calling convention
    args = kwargs.get("args", sys.argv[1:])
    return create_model(module_list, args)

def create_model(module_list=None, args=sys.argv[1:]):
    """

    Construct a Pyomo AbstractModel using the Switch modules or packages
    in the given list and return the model. The following utility methods
    are attached to the model as class methods to simplify their use:
    min_data_check(), load_inputs(), pre_solve(), post_solve().

    This is implemented as calling the following functions for each module
    that has them defined:

    define_dynamic_lists(model): Add lists to the model that other modules can
    register with. Used for power balance equations, cost components of the
    objective function, etc.

    define_components(model): Add components to the model object (parameters,
    sets, decisions variables, expressions, and/or constraints). Also register
    with relevant dynamic_lists.

    define_dynamic_components(model): Add dynamic components to the model that
    depend on the contents of dyanmics lists. Power balance constraints and
    the objective function are defined in this manner.

    See financials and balancing.load_zones for examples of dynamic definitions.

    All modules can request access to command line parameters and set their
    default values for those options. If this codebase is being used more like
    a library than a stand-alone executable, this behavior can cause problems.
    For example, running this model with PySP's runph tool will cause errors
    where a runph argument such as --instance-directory is unknown to the
    switch modules, so parse_args() generates an error. This behavior can be
    avoided calling this function with an empty list for args:
    create_model(module_list, args=[])

    """
    model = CustomModel()

    # Load modules
    if module_list is None:
        module_list = get_module_list(args)
    model.module_list = module_list
    for m in module_list:
        importlib.import_module(m)

    # Bind utility functions to the model as class objects
    # Should we be formally extending their class instead?
    _add_min_data_check(model)
    model.get_modules = types.MethodType(get_modules, model)
    model.load_inputs = types.MethodType(load_inputs, model)
    model.pre_solve = types.MethodType(pre_solve, model)
    model.post_solve = types.MethodType(post_solve, model)

    # Define and parse model configuration options
    argparser = _ArgumentParser(allow_abbrev=False)
    for module in model.get_modules():
        if hasattr(module, 'define_arguments'):
            module.define_arguments(argparser)
    model.options = argparser.parse_args(args)

    # Define model components
    for module in model.get_modules():
        if hasattr(module, 'define_dynamic_lists'):
            module.define_dynamic_lists(model)
    for module in model.get_modules():
        if hasattr(module, 'define_components'):
            module.define_components(model)
    for module in model.get_modules():
        if hasattr(module, 'define_dynamic_components'):
            module.define_dynamic_components(model)

    return model


def get_modules(model):
    """ Return a list of loaded module objects for this model. """
    for m in model.module_list:
        yield sys.modules[m]


def make_iterable(item):
    """Return an iterable for the one or more items passed."""
    if isinstance(item, string_types):
        i = iter([item])
    else:
        try:
            # check if it's iterable
            i = iter(item)
        except TypeError:
            i = iter([item])
    return i

class StepTimer(object):
    """
    Keep track of elapsed time for steps of a process.
    Use timer = StepTimer() to create a timer, then retrieve elapsed time and/or
    reset the timer at each step by calling timer.step_time()
    """

    def __init__(self):
        self.start_time = time.time()

    def step_time(self):
        """
        Reset timer to current time and return time elapsed since last step.
        """
        last_start = self.start_time
        self.start_time = now = time.time()
        return now - last_start

    def step_time_as_str(self):
        """
        Reset timer to current time and return time elapsed since last step as a formatted string.
        """
        return format_seconds(self.step_time())

def format_seconds(seconds):
    """
    Takes in a number of seconds and returns a string
    representing the seconds broken into hours, minutes and seconds.

    For example, format_seconds(3750.4) returns '1 h 2 min 30.40 s'.
    """
    minutes = int(seconds // 60)
    hours = int(minutes // 60)
    remainder_sec = seconds % 60
    remainder_min = minutes % 60

    output_str = ""

    if hours != 0:
        output_str += f"{hours} h "
    if minutes != 0:
        output_str += f"{remainder_min} min "
    output_str += f"{remainder_sec:.2f} s"

    return output_str


def load_inputs(model, inputs_dir=None, attach_data_portal=False):
    """
    Load input data for an AbstractModel using the modules in the given
    list and return a model instance. This is implemented as calling the
    load_inputs() function of each module, if the module has that function.
    """
    if inputs_dir is None:
        inputs_dir = getattr(model.options, "inputs_dir", "inputs")

    # Load data; add a fancier load function to the data portal
    if model.options.verbose:
        print("Reading data...")
    timer = StepTimer()
    data = DataPortal(model=model)
    data.load_aug = types.MethodType(load_aug, data)
    for module in model.get_modules():
        if hasattr(module, 'load_inputs'):
            module.load_inputs(model, data, inputs_dir)
    if model.options.verbose:
        print(f"Data read in {timer.step_time_as_str()}.\n")

    # At some point, pyomo deprecated 'create' in favor of 'create_instance'.
    # Determine which option is available and use that.
    if model.options.verbose:
        print("Creating instance...")
    if hasattr(model, 'create_instance'):
        instance = model.create_instance(data)
        # We want our functions from CustomModel to be accessible
        # Somehow simply setting the class to CustomModel allows us to do this
        # This is the same thing that happens in the Pyomo library at the end of
        # model.create_instance(). Note that Pyomo's ConcreteModel is basically the same as
        # our CustomModel so we're not causing any issues by changing from ConcreteModel
        # to CustomModel
        instance.__class__ = CustomModel
    else:
        instance = model.create(data)
    if model.options.verbose:
        print(f"Instance created from data in {timer.step_time_as_str()}.\n")

    if attach_data_portal:
        instance.DataPortal = data
    else:
        del data
    return instance


def save_inputs_as_dat(model, instance, save_path="inputs/complete_inputs.dat",
    exclude=[], sorted_output=False):
    """
    Save input data to a .dat file for use with PySP or other command line
    tools that have not been fully integrated with DataPortal.
    SYNOPSIS:
        save_inputs_as_dat(model, instance, save_path)
    """
    # helper function to convert values to strings,
    # putting quotes around values that start as strings
    quote_str = lambda v: '"{}"'.format(v) if isinstance(v, string_types) else '{}'.format(str(v))
    # helper function to create delimited lists from single items or iterables of any data type
    from switch_model.reporting import make_iterable
    join_space = lambda items: ' '.join(map(str, make_iterable(items)))  # space-separated list
    join_comma = lambda items: ','.join(map(str, make_iterable(items)))  # comma-separated list

    with open(save_path, "w") as f:
        for component_name in instance.DataPortal.data():
            if component_name in exclude:
                continue    # don't write data for components in exclude list
                            # (they're in scenario-specific files)
            component = getattr(model, component_name)
            comp_class = type(component).__name__
            component_data = instance.DataPortal.data(name=component_name)
            if comp_class in ('ScalarSet', 'OrderedScalarSet', 'AbstractOrderedScalarSet'):
                f.write(
                    "set {} := {};\n"
                    .format(component_name, join_space(component_data))
                )
            elif comp_class == 'IndexedParam':
                if component_data:  # omit components for which no data were provided
                    f.write("param {} := \n".format(component_name))
                    for key, value in (
                        sorted(component_data.items())
                        if sorted_output
                        else component_data.items()
                    ):
                        f.write(" {} {}\n".format(join_space(key), quote_str(value)))
                    f.write(";\n")
            elif comp_class == 'ScalarParam':
                f.write("param {} := {};\n".format(component_name, component_data))
            elif comp_class == 'IndexedSet':
                for key, vals in component_data.items():
                    f.write(
                        "set {}[{}] := {};\n"
                        .format(component_name, join_comma(key), join_space(vals))
                    )
            else:
                raise ValueError(
                    "Error! Component type {} not recognized for model element '{}'.".
                    format(comp_class, component_name))

def pre_solve(instance, outputs_dir=None):
    """
    Call pre-solve function (if present) in all modules used to compose this model.
    This function can be used to adjust the instance after it is created and before it is solved.
    """
    for module in instance.get_modules():
        if hasattr(module, 'pre_solve'):
            module.pre_solve(instance)

def post_solve(instance, outputs_dir=None):
    """
    Call post-solve function (if present) in all modules used to compose this model.
    This function can be used to report or save results from the solved model.
    """
    if outputs_dir is None:
        outputs_dir = getattr(instance.options, "outputs_dir", "outputs")
    if not os.path.exists(outputs_dir):
        os.makedirs(outputs_dir)

    # TODO: implement a check to call post solve functions only if
    # solver termination condition is not 'infeasible' or 'unknown'
    # (the latter may occur when there are problems with licenses, etc)

    for module in instance.get_modules():
        if hasattr(module, 'post_solve'):
            # Try-catch is so that if one module fails on post-solve
            # the other modules still run
            try:
                module.post_solve(instance, outputs_dir)
            except Exception:
                # Print the error that would normally be thrown with the
                # full stack trace and an explanatory message
                print(f"ERROR: Module {module.__name__} threw an Exception while running post_solve(). "
                      f"Moving on to the next module.\n{traceback.format_exc()}")

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

    >>> from switch_model.utilities import _add_min_data_check
    >>> mod = AbstractModel()
    >>> _add_min_data_check(mod)
    >>> mod.set_A = Set(initialize=[1,2])
    >>> mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'}, within=Any)
    >>> mod.paramA_empty = Param(mod.set_A)
    >>> mod.min_data_check('set_A', 'paramA_full')
    >>> if hasattr(mod, 'create_instance'):
    ...     instance_pass = mod.create_instance()
    ... else:
    ...     instance_pass = mod.create()
    >>> mod.min_data_check('set_A', 'paramA_empty')
    """
    if getattr(model, 'min_data_check', None) is None:
        model.__num_min_data_checks = 0
        model.min_data_check = types.MethodType(min_data_check, model)


def has_discrete_variables(model):
    return any(
        v.is_binary() or v.is_integer()
        for variable in model.component_objects(Var, active=True)
        for v in (variable.values() if variable.is_indexed() else [variable])
    )

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
    >>> import switch_model.utilities as utilities
    >>> mod = ConcreteModel()
    >>> mod.set_A = Set(initialize=[1,2])
    >>> mod.paramA_full = Param(mod.set_A, initialize={1:'a',2:'b'}, within=Any)
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
    ValueError: Values are not provided for every element of the mandatory parameter 'paramA_empty'. Missing data for 2 values, including: [1, 2]
    >>> utilities.check_mandatory_components(mod, 'set_A', 'set_B')
    Traceback (most recent call last):
        ...
    ValueError: No data is defined for the mandatory set 'set_B'.

    # Demonstration of incorporating this function into Pyomo's BuildCheck()
    >>> mod.min_dat_pass = BuildCheck(\
            rule=lambda m: utilities.check_mandatory_components(\
                m, 'set_A', 'paramA_full','paramB_empty', 'paramC'))
    """

    for component_name in mandatory_model_components:
        obj = getattr(model, component_name)
        o_class = type(obj).__name__
        if o_class == 'ScalarSet' or o_class == 'OrderedScalarSet':
            if len(obj) == 0:
                raise ValueError(
                    "No data is defined for the mandatory set '{}'.".
                    format(component_name))
        elif o_class == 'IndexedParam':
            if len(obj) != len(obj._index):
                missing_index_elements = [v for v in set(obj._index) - set( obj.sparse_keys())]
                raise ValueError(
                    "Values are not provided for every element of the "
                    "mandatory parameter '{}'. "
                    "Missing data for {} values, including: {}"
                    .format(component_name, len(missing_index_elements), missing_index_elements[:10])
                )
        elif o_class == 'IndexedSet':
            if len(obj) != len(obj._index):
                raise ValueError(
                    ("Sets are not defined for every index of " +
                     "the mandatory indexed set '{}'").format(component_name))
        elif o_class == 'ScalarParam':
            if obj.value is None:
                raise ValueError(
                    "Value not provided for mandatory parameter '{}'".
                    format(component_name))
        else:
            raise ValueError(
                "Error! Object type {} not recognized for model element '{}'.".
                format(o_class, component_name))
    return True


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
    # TODO:
    # Allow user to specify filename when defining parameters and sets.
    # Also allow user to specify the name(s) of the column(s) in each set.
    # Then use those automatically to pull data from the right file (and to
    # write correct index column names in the generic output files).
    # This will simplify code and ease comprehension (user can see
    # immediately where the data come from for each component). This can
    # also support auto-documenting of parameters and input files.

    path = kwds['filename']
    # Skip if the file is missing
    if optional and not os.path.isfile(path):
        return
    # If this is a .dat file, then skip the rest of this fancy business; we'll
    # only check if the file is missing and optional for .csv files.
    filename, extension = os.path.splitext(path)
    if extension == '.dat':
        switch_data.load(**kwds)
        return

    # copy the optional_params to avoid side-effects when the list is altered below
    optional_params=list(optional_params)
    # Parse header and first row
    with open(path) as infile:
        headers_line = infile.readline()
        second_line = infile.readline()
    file_is_empty = (headers_line == '')
    file_has_no_data_rows = (second_line == '')
    suffix = path.split('.')[-1]
    if suffix in {'tab', 'tsv'}:
        separator = '\t'
    elif suffix == 'csv':
        separator = ','
    else:
        raise InputError(f'Unrecognized file type for input file {path}')
    # TODO: parse this more formally, e.g. using csv module
    headers = headers_line.strip().split(separator)
    # Skip if the file is empty.
    if optional and file_is_empty:
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
        if not isinstance(p, string_types):
            optional_params[i] = p.name
    # Expand the list optional parameters to include any parameter that
    # has default() defined. I need to allow an explicit list of default
    # parameters to support optional parameters like gen_unit_size which
    # don't have default value because it is undefined for generators
    # for which it does not apply.
    for p in params:
        if p.default() is not None:
            optional_params.append(p.name)
    # How many index columns do we expect?
    # Grab the dimensionality of the index param if it was provided.
    if 'index' in kwds:
        num_indexes = kwds['index'].dimen
        if num_indexes == UnknownSetDimen:
            raise Exception(f"Index {kwds['index'].name} has unknown dimension. Specify dimen= during its creation.")
    # Next try the first parameter's index.
    elif len(params) > 0:
        try:
            indexed_set = params[0].index_set()
            num_indexes = indexed_set.dimen
            if num_indexes == UnknownSetDimen:
                raise Exception(f"{indexed_set.name} has unknown dimension. Specify dimen= during its creation.")
        except (ValueError, AttributeError):
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
    # to be called "rfm_supply_tier.csv" for greater consistency/predictability.
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

    if optional and file_has_no_data_rows:
        # Skip the file.  Note that we are only doing this after having
        # validated the file's column headings.
        return

    # Use our custom DataManager to allow 'inf' in csvs.
    if kwds["filename"][-4:] == ".csv":
        kwds['using'] = "switch_csv"
    # All done with cleaning optional bits. Pass the updated arguments
    # into the DataPortal.load() function.
    switch_data.load(**kwds)

# Register a custom data manager that wraps the default CSVTable DataManager
# This data manager does the same as CSVTable but converts 'inf' to float("inf")
# This is necessary since Pyomo no longer converts inf to float('inf') and is
# now throwing errors when we it expects a number but we input inf.
@DataManagerFactory.register('switch_csv')
class SwitchCSVDataManger(CSVTable):
    def process(self, model, data, default):
        status = super().process(model, data, default)
        self.convert_inf_to_float(data[self.options.namespace])
        return status

    @staticmethod
    def convert_inf_to_float(data):
        for values in data.values():
            for index, val in values.items():
                if val == "inf":
                    values[index] = float("inf")


class ExtendAction(argparse.Action):
    """Create or extend list with the provided items"""
    # from https://stackoverflow.com/a/41153081/3830997
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest) or []
        items.extend(values)
        setattr(namespace, self.dest, items)

class IncludeAction(argparse.Action):
    """Flag the specified items for inclusion in the model"""
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest) or []
        items.append(('include', values))
        setattr(namespace, self.dest, items)
class ExcludeAction(argparse.Action):
    """Flag the specified items for exclusion from the model"""
    def __call__(self, parser, namespace, values, option_string=None):
        items = getattr(namespace, self.dest) or []
        items.append(('exclude', values))
        setattr(namespace, self.dest, items)

# Test whether we need to issue warnings about the Python parsing bug.
# (applies to at least Python 2.7.11 and 3.6.2)
# This bug messes up solve-scenarios if the user specifies
# --scenario x --solver-options-string="a=b c=d"
test_parser = argparse.ArgumentParser()
test_parser.add_argument('--arg1', nargs='+', default=[])
bad_equal_parser = (
    len(test_parser.parse_known_args(['--arg1', 'a', '--arg2=a=1 b=2'])[1])
    == 0
)

class _ArgumentParser(argparse.ArgumentParser):
    """
    Custom version of ArgumentParser:
    - warns about a bug in standard Python ArgumentParser for --arg="some words"
    - allows use of 'extend', 'include' and 'exclude' actions to accumulate lists
      with multiple calls
    """
    def __init__(self, *args, **kwargs):
        super(_ArgumentParser, self).__init__(*args, **kwargs)
        self.register('action', 'extend', ExtendAction)
        self.register('action', 'include', IncludeAction)
        self.register('action', 'exclude', ExcludeAction)

    def parse_known_args(self, args=None, namespace=None):
        # parse_known_args parses arguments like --list-arg a b --other-arg="something with space"
        # as list_arg=['a', 'b', '--other-arg="something with space"'].
        # See https://bugs.python.org/issue22433.
        # We issue a warning to avoid this.
        if bad_equal_parser and args is not None:
            for a in args:
                if a.startswith('--') and '=' in a:
                    print(
                        "Warning: argument '{}' may be parsed incorrectly. It is "
                        "safer to use ' ' instead of '=' as a separator."
                        .format(a)
                    )
                    time.sleep(2)  # give users a chance to see it
        return super(_ArgumentParser, self).parse_known_args(args, namespace)


def approx_equal(a, b, tolerance=0.01):
    return abs(a-b) <= (abs(a) + abs(b)) / 2.0 * tolerance


def default_solver():
    return pyomo.opt.SolverFactory('glpk')

def warn(message):
    """
    Send warning message to sys.stderr.
    Unlike warnings.warn, this does not add the current line of code to the message.
    """
    sys.stderr.write("WARNING: " + message + '\n')

class TeeStream(object):
    """
    Virtual stream that writes output to both stream1 and stream2. Attributes
    of stream1 will be reported to callers if needed. For example, specifying
    `sys.stdout=TeeStream(sys.stdout, log_file_handle)` will copy
    output destined for sys.stdout to log_file_handle as well.
    """
    def __init__(self, stream1, stream2):
        self.stream1 = stream1
        self.stream2 = stream2
    def __getattr__(self, *args, **kwargs):
        """
        Provide stream1 attributes when attributes are requested for this class.
        This supports code that assumes sys.stdout is an object with its own
        methods, etc.
        """
        return getattr(self.stream1, *args, **kwargs)
    def write(self, *args, **kwargs):
        self.stream1.write(*args, **kwargs)
        self.stream2.write(*args, **kwargs)
    def flush(self, *args, **kwargs):
        self.stream1.flush(*args, **kwargs)
        self.stream2.flush(*args, **kwargs)

class LogOutput(object):
    """
    Copy output sent to stdout or stderr to a log file in the specified directory.
    Takes no action if directory is None. Log file is named based on the current
    date and time. Directory will be created if needed, and file will be overwritten
    if it already exists (unlikely).
    """
    def __init__(self, logs_dir):
        self.logs_dir = logs_dir
    def __enter__(self):
        """ start copying output to log file """
        if self.logs_dir is not None:
            if not os.path.exists(self.logs_dir):
                os.makedirs(self.logs_dir)
            log_file_path = os.path.join(
                self.logs_dir,
                datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S') + ".log"
            )
            self.log_file = open(log_file_path, "w", buffering=1)
            self.stdout = sys.stdout
            self.stderr = sys.stderr
            sys.stdout = TeeStream(sys.stdout, self.log_file)
            sys.stderr = TeeStream(sys.stderr, self.log_file)
            print("logging output to " + str(log_file_path))
    def __exit__(self, type, value, traceback):
        """ restore original output streams and close log file """
        if self.logs_dir is not None:
            sys.stdout = self.stdout
            sys.stderr = self.stderr
            self.log_file.close()


def query_yes_no(question, default="yes"):
    """Ask a yes/no question via input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


def catch_exceptions(warning_msg=None, should_catch=True):
    """Decorator that catches exceptions."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not should_catch:
                return func(*args, **kwargs)

            try:
                return func(*args, **kwargs)
            except:
                if warning_msg is not None:
                    warnings.warn(warning_msg)

        return wrapper

    return decorator


def run_command(command):
    return subprocess.check_output(command.split(" "), cwd=os.path.dirname(__file__)).strip().decode("UTF-8")


@catch_exceptions("Failed to get Git Branch.")
def get_git_branch():
    return run_command("git rev-parse --abbrev-ref HEAD")


@catch_exceptions("Failed to get Git Commit Hash.")
def get_git_commit():
    return run_command("git rev-parse HEAD")


def add_git_info():
    commit_num = get_git_commit()
    branch = get_git_branch()
    if commit_num is not None:
        add_info("Git Commit", commit_num, section=ResultsInfoSection.GENERAL)
    if branch is not None:
        add_info("Git Branch", branch, section=ResultsInfoSection.GENERAL)

def get_module_list(args=None, include_solve_module=True):
    # parse module options
    parser = _ArgumentParser(allow_abbrev=False, add_help=False)
    add_module_args(parser)
    module_options = parser.parse_known_args(args=args)[0]

    # identify modules to load
    module_list_file = module_options.module_list

    # search first in the current directory
    if module_list_file is None and os.path.exists("modules.txt"):
        module_list_file = "modules.txt"
    # search next in the inputs directory ('inputs' by default)
    if module_list_file is None:
        test_path = os.path.join(module_options.inputs_dir, "modules.txt")
        if os.path.exists(test_path):
            module_list_file = test_path
    if module_list_file is None:
        # note: this could be a RuntimeError, but then users can't do "switch solve --help" in a random directory
        # (alternatively, we could provide no warning at all, since the user can specify --include-modules in the arguments)
        print("WARNING: No module list found. Please create a modules.txt file with a list of modules to use for the model.")
        modules = []
    else:
        # if it exists, the module list contains one module name per row (no .py extension)
        # we strip whitespace from either end (because those errors can be annoyingly hard to debug).
        # We also omit blank lines and lines that start with "#"
        # Otherwise take the module names as given.
        with open(module_list_file) as f:
            modules = [r.strip() for r in f.read().splitlines()]
        modules = [m for m in modules if m and not m.startswith("#")]

    # adjust modules as requested by the user
    # include_exclude_modules format: [('include', [mod1, mod2]), ('exclude', [mod3])]
    for action, mods in module_options.include_exclude_modules:
        if action == 'include':
            for module_name in mods:
                if module_name not in modules:  # maybe we should raise an error if already present?
                    modules.append(module_name)
        if action == 'exclude':
            for module_name in mods:
                try:
                    modules.remove(module_name)
                except ValueError:
                    raise ValueError(            # maybe we should just pass?
                        'Unable to exclude module {} because it was not '
                        'previously included.'.format(module_name)
                    )

    # add this module, since it has callbacks, e.g. define_arguments for iteration and suffixes
    if include_solve_module:
        modules.append("switch_model.solve")

    return modules


def add_module_args(parser):
    parser.add_argument(
        "--module-list", default=None,
        help='Text file with a list of modules to include in the model (default is "modules.txt")'
    )
    parser.add_argument(
        "--include-modules", "--include-module", dest="include_exclude_modules", nargs='+',
        action='include', default=[],
        help="Module(s) to add to the model in addition to any specified with --module-list file"
    )
    parser.add_argument(
        "--exclude-modules", "--exclude-module", dest="include_exclude_modules", nargs='+',
        action='exclude', default=[],
        help="Module(s) to remove from the model after processing --module-list file and prior --include-modules arguments"
    )
    # note: we define --inputs-dir here because it may be used to specify the location of
    # the module list, which is needed before it is loaded.
    parser.add_argument("--inputs-dir", default="inputs",
        help='Directory containing input files (default is "inputs")')