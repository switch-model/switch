# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds unit commitment decisions and impacts.

The core modules in the package are commit and fuel_use. The discrete
module is optional and enforces discrete unit commitment.

"""
core_modules = [
    "switch_model.generators.core.commit.operate",
    "switch_model.generators.core.commit.fuel_use",
]
