# Copyright 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds operational decisions and constraints both on projects and
on transmission lines.

The core module in the package is proj_dispatch. The no_commit module can be 
included to define simple operational bounds. Alternatively, a unit commitment 
formulation can be considered by including the unitcommit package. The 
no_commit module and the unitcommit package are mutually exclusive.

If transmission wants to be included in the model, then the 
operations.trans_dispatch module should be loaded. If this is the case,
investment.trans_build must also be included.

This package can be treated as a module that includes all of the mentioned 
core modules instead of having to refer to them individually. This means that
the module list can be specified as:

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
    'operations')

or as

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
    'operations.proj_dispatch')

You will get an error if you include both the package and the core modules,
because they are redundant.

"""

core_modules = [
    'switch_mod.operations.proj_dispatch']
