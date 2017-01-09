# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""

This package adds project-level build and dispatch decisions.

The core modules in the package are build and dispatch. The
discrete_build module is optional and enforces discrete unit builds (see
that module for documentation).

I wrote some magic sauce so that you can treat this package as a module
that includes all of the core modules instead of having to refer to them
individually. This means you can either specify your module list as:

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
    'project')

or as

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
    'project.build', 'project.dispatch')

You will get an error if you include both the package and the core modules,
because they are redundant.

"""

core_modules = [
    'switch_mod.project.build',
    'switch_mod.project.dispatch']
