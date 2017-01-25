# Copyright 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

This package adds generation project and transmission line construction.

The core module in the package is proj_build. The proj_discrete_build module 
is optional and enforces discrete unit builds (see that module for 
documentation).

To include transmission in the model, load the investment.trans_build and 
operations.trans_dispatch modules.

"""
core_modules = ['switch_mod.investment.proj_build']
