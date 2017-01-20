# Copyright 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds generation project and transmission line construction.

The core module in the package is proj_build. The proj_discrete_build module 
is optional and enforces discrete unit builds (see that module for 
documentation).

If transmission wants to be included in the model, then the 
investment.trans_build module should be loaded. If this is the case,
operations.trans_dispatch must also be included.

This package can be treated as a module that includes all of the mentioned 
core modules instead of having to refer to them individually. This means that
the module list can be specified as:

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'investment')

or as

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'investment.proj_build')

You will get an error if you include both the package and the core modules,
because they are redundant.

"""

core_modules = [
    'switch_mod.investment.proj_build']
