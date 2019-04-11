# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Utility functions for SWITCH-pyomo.
"""

import os, types, importlib, re, sys, argparse, time, datetime
import __main__ as main
from pyomo.environ import *
import pyomo.opt

# Check whether this is an interactive session (determined by whether
# __main__ has a __file__ attribute). Scripts can check this value to
# determine what level of output to display.
interactive_session = not hasattr(main, '__file__')

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
    model = AbstractModel()

    # Load modules
    if module_list is None:
        import switch_model.solve
        module_list = switch_model.solve.get_module_list(args)
    model.module_list = module_list
    for m in module_list:
        importlib.import_module(m)

    # Bind utility functions to the model as class objects
    # Should we be formally extending their class instead?
    _add_min_data_check(model)
    model.has_discrete_variables = types.MethodType(has_discrete_variables, model)
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
    if isinstance(item, basestring):
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

def load_inputs(model, inputs_dir=None, attach_data_portal=True):
    """
    Load input data for an AbstractModel using the modules in the given
    list and return a model instance. This is implemented as calling the
    load_inputs() function of each module, if the module has that function.
    """
    if inputs_dir is None:
        inputs_dir = getattr(model.options, "inputs_dir", "inputs")

    # Load data; add a fancier load function to the data portal
    timer = StepTimer()
    data = DataPortal(model=model)
    data.load_aug = types.MethodType(load_aug, data)
    for module in model.get_modules():
        if hasattr(module, 'load_inputs'):
            module.load_inputs(model, data, inputs_dir)
    if model.options.verbose:
        print "Data read in {:.2f} s.\n".format(timer.step_time())

    # At some point, pyomo deprecated 'create' in favor of 'create_instance'.
    # Determine which option is available and use that.
    if hasattr(model, 'create_instance'):
        instance = model.create_instance(data)
    else:
        instance = model.create(data)
    if model.options.verbose:
        print "Instance created from data in {:.2f} s.\n".format(timer.step_time())

    if attach_data_portal:
        instance.DataPortal = data
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
    quote_str = lambda v: '"{}"'.format(v) if isinstance(v, basestring) else '{}'.format(str(v))
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
            if comp_class == 'SimpleSet' or comp_class == 'OrderedSimpleSet':
                f.write(
                    "set {} := {};\n"
                    .format(component_name, join_space(component_data))
                )
            elif comp_class == 'IndexedParam':
                if component_data:  # omit components for which no data were provided
                    f.write("param {} := \n".format(component_name))
                    for key, value in (
                        sorted(iteritems(component_data))
                        if sorted_output
                        else iteritems(component_data)
                    ):
                        f.write(" {} {}\n".format(join_space(key), quote_str(value)))
                    f.write(";\n")
            elif comp_class == 'SimpleParam':
                f.write("param {} := {};\n".format(component_name, component_data))
            elif comp_class == 'IndexedSet':
                for key, vals in iteritems(component_data):
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
            module.post_solve(instance, outputs_dir)


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
    """
    if getattr(model, 'min_data_check', None) is None:
        model.__num_min_data_checks = 0
        model.min_data_check = types.MethodType(min_data_check, model)


def has_discrete_variables(model):
    all_elements = lambda v: v.itervalues() if v.is_indexed() else [v]
    return any(
        v.is_binary() or v.is_integer()
        for variable in model.component_objects(Var, active=True)
        for v in all_elements(variable)
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
            	missing_index_elements = [v for v in set(obj._index) - set( obj.sparse_keys())]
                raise ValueError(
                    ("Values are not provided for every element of the "
                     "mandatory parameter '{}'. "
                     "Missing data for {} values, including: {}"
                    ).format(component_name, len(missing_index_elements), missing_index_elements[:10]))
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
    # only check if the file is missing and optional for .tab files.
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
    if suffix == 'tab':
        separator = '\t'
    elif suffix == 'csv':
        separator = ','
    else:
        raise switch_model.utilities.InputError('Unrecognized file type for input file {}'.format(path))
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
        if not isinstance(p, basestring):
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

    if optional and file_has_no_data_rows:
        # Skip the file.  Note that we are only doing this after having
        # validated the file's column headings.
        return
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
    _ArgumentParserAllowAbbrev = argparse.ArgumentParser
else:
    # patch ArgumentParser to accept the allow_abbrev flag
    # (works on Python 2.7 and maybe others)
    class _ArgumentParserAllowAbbrev(argparse.ArgumentParser):
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

# TODO: merge the _ArgumentParserAllowAbbrev code into this class
class _ArgumentParser(_ArgumentParserAllowAbbrev):
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
        # See https://bugs.python.org/issue34390.
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

class TeeStream:
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
            print "logging output to " + str(log_file_path)
    def __exit__(self, type, value, traceback):
        """ restore original output streams and close log file """
        if self.logs_dir is not None:
            sys.stdout = self.stdout
            sys.stderr = self.stderr
            self.log_file.close()

def iteritems(obj):
    """ Iterator of key, value pairs for obj;
    equivalent to obj.items() on Python 3+ and obj.iteritems() on Python 2 """
    try:
        return obj.iteritems()
    except AttributeError: # Python 3+
        return obj.items()
