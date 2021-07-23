import os
from typing import Type

from pyomo.environ import *
from collections import OrderedDict

_load_inputs_by_file = OrderedDict()
_required_files = set()


def patch_to_allow_loading(cls: Type):
    def new_init(
        self, *args, input_file=None, input_column=None, input_optional=False, **kwargs
    ):
        self.__old_init__(*args, **kwargs)
        if input_file is None:
            return

        self.input_column = input_column
        self.input_optional = input_optional

        if input_file not in _load_inputs_by_file:
            _load_inputs_by_file[input_file] = [self]
        else:
            _load_inputs_by_file[input_file].append(self)

    cls.__old_init__ = cls.__init__
    cls.__init__ = new_init


def load_registered_inputs(switch_data, inputs_dir):
    global _load_inputs_by_file

    for file, components in _load_inputs_by_file.items():
        path = os.path.join(inputs_dir, file)
        # We use lists since load_aug is going to convert to a list in any case
        params = [c for c in components if isinstance(c, Param)]
        optional_params = [p for p in params if p.input_optional]
        index = [c for c in components if isinstance(c, Set)]

        if len(index) + len(params) != len(components):
            raise Exception(
                "This should not happen. Did you specify an input file for an element that is not a Set or Param?"
            )

        kwargs = dict(
            filename=path,
            auto_select=True,
            optional_params=optional_params,
            optional=all(c.input_optional for c in components),
        )

        if len(index) > 1:
            raise Exception(
                f"Can't define multiple sets from the same file. {str(index)}"
            )
        elif len(index) == 1:
            index = index[0]
        else:
            index = None

        if len(params) == 0:
            kwargs["set"] = index
        else:
            kwargs["param"] = params
            if index is not None:
                kwargs["index"] = index

        switch_data.load_aug(**kwargs)

    _load_inputs_by_file = OrderedDict()


def require_input_file(filename):
    _required_files.add(filename)


patch_to_allow_loading(Set)
patch_to_allow_loading(Param)
