# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories between versions. 
See version-specific upgrade scripts for change details.

The main entry point is the switch console tool. See:
    switch upgrade --help

API Synopsis:
    import switch_model.upgrade

    print switch_model.upgrade.get_input_version(inputs_dir)

    if switch_model.upgrade.inputs_need_upgrade(inputs_dir):
        switch_model.upgrade.upgrade_inputs(inputs_dir)

    print switch_model.upgrade.get_input_version(inputs_dir)
    
    switch_model.upgrade.scan_and_upgrade(examples_dir)

"""
# Public interface
from .manager import main, upgrade_inputs, scan_and_upgrade, get_input_version, do_inputs_need_upgrade
# Private utility functions for this upgrade sub-package
from .manager import _backup, _write_input_version

