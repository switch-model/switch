# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds unit commitment decisions and impacts.

The core modules in the package are commit and fuel_use. The discrete
module is optional and enforces discrete unit commitment.

I wrote some magic sauce so that you can treat this package as a module
that includes all of the core modules instead of having to refer to them
individually. This means you can either specify your module list as:

switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',
                  'gen_tech', 'project.build', 'project.dispatch',
                  'project.unitcommit')

or as

switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',
                  'gen_tech', 'project.build', 'project.dispatch',
                  'project.unitcommit.commit', 'project.unitcommit.fuel_use')

You will get an error if you include both the package and the core modules,
because they are redundant.

"""

core_modules = [
    'switch_mod.project.unitcommit.commit',
    'switch_mod.project.unitcommit.fuel_use']
