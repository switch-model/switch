import os
from typing import Type

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
        path = os.path.join(inputs_dir, file)
        # We use lists since load_aug is going to convert to a list in any case
        params = [c for c in components if isinstance(c, Param)]
        optional_params = [p for p in params if p.input_optional]
        index = [c for c in components if isinstance(c, Set)]

        if len(index) + len(params) != len(components):
            raise Exception(
                "This should not happen. Did you specify an input file for an element that is not a Set or Param?")

        kwargs = dict(
            filename=path,
            auto_select=True,
            optional_params=optional_params
        )

        if len(index) > 1:
            raise Exception(f"Can't define multiple sets from the same file. {str(index)}")
        elif len(index) == 1:
            index = index[0]
            kwargs["optional"] = index.input_optional
        else:
            index = None
            kwargs["optional"] = all(c.input_optional for c in components)

        if len(params) == 0:
            kwargs["set"] = index
        else:
            kwargs["param"] = params
            if index is not None:
                kwargs["index"] = index

        switch_data.load_aug(**kwargs)

    # Remove all the elements to reset the dictionary
    _registered_components.clear()
