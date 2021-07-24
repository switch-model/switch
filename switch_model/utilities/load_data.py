import os
from typing import Type

from pyomo.core.base.set import UnknownSetDimen
from pyomo.environ import *

# Mapping of file names to components to load from that file.
# Ordered dict to ensure we are creating our components in the right order
_registered_components = {}

def patch_to_allow_loading(cls: Type):
    def new_init(self, *args, input_file=None, input_column=None, input_optional=None, **kwargs):
        self.__old_init__(*args, **kwargs)
        if input_file is None:
            return

        if input_optional is None:
            input_optional = "default" in kwargs

        self.input_column = input_column
        self.input_optional = input_optional

        if input_file not in _registered_components:
            _registered_components[input_file] = [self]
        else:
            _registered_components[input_file].append(self)

    cls.__old_init__ = cls.__init__
    cls.__init__ = new_init


def load_registered_inputs(switch_data, inputs_dir):
    for file, components in _registered_components.items():
        # We use lists since load_aug is going to convert to a list in any case
        params = [c for c in components if isinstance(c, Param)]
        optional_params = [p for p in params if p.input_optional]
        index = [c for c in components if isinstance(c, Set)]

        if len(index) + len(params) != len(components):
            raise Exception(
                "This should not happen. Did you specify an input file for an element that is not a Set or Param?")

        kwargs = dict(filename=os.path.join(inputs_dir, file))

        if len(index) > 1:
            raise Exception(f"Can't define multiple sets from the same file. {str(index)}")
        elif len(index) == 1:
            index = index[0]
            optional = index.input_optional
        else:
            index = None
            optional = all(c.input_optional for c in components)

        if len(params) == 0:
            kwargs["set"] = index
        else:
            kwargs["param"] = params
            if index is not None:
                kwargs["index"] = index

        load_data(switch_data, optional=optional, auto_select=True, optional_params=optional_params, **kwargs)

    # Remove all the elements to reset the dictionary
    _registered_components.clear()


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

def load_data(switch_data, optional, auto_select, optional_params, **kwds):
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
        if not isinstance(p, str):
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

        def get_column_name(p):
            if hasattr(p, "input_column") and p.input_column is not None:
                return p.input_column
            else:
                return p.name

        kwds['select'] = headers[0:num_indexes] + [get_column_name(p) for p in params]
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