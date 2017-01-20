# Copyright 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds unit commitment decisions and impacts.

The core modules in the package are commit and fuel_use. The discrete
module is optional and enforces discrete unit commitment.

This package can be treated as a module that includes all of the mentioned 
core modules instead of having to refer to them individually. This means that
the module list can be specified as:

switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',
                  'operations.proj_dispatch', 
                  'investment.proj_build', 'operations.unitcommit')

or as

switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',
                  'operations.proj_dispatch', 
                  'investment.proj_build', 'operations.unitcommit.commit', 
                  'operations.unitcommit.fuel_use')

You will get an error if you include both the package and the core modules,
because they are redundant.

"""

core_modules = [
    'switch_mod.operations.unitcommit.commit',
    'switch_mod.operations.unitcommit.fuel_use']
