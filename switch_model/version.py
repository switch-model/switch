# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
This file should not contain anything that is not part of a minimal python
distribution because it needs to be executed before Switch (and its
dependencies) are installed.
"""
import os

base_version = '2.0.6-dev'

try:
    DATA_ROOT = os.path.join(os.path.dirname(__file__), 'data')
    with open(os.path.join(DATA_ROOT, 'installed_version.txt'), 'r') as f:
        __version__ = f.read().strip()
except (IOError, NameError):
    __version__ = base_version
