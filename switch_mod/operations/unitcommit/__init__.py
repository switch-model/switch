# Copyright 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds unit commitment decisions and impacts.

The core modules in the package are commit and fuel_use. The discrete
module is optional and enforces discrete unit commitment.

"""
core_modules = [
    'switch_mod.operations.unitcommit.commit',
    'switch_mod.operations.unitcommit.fuel_use']
