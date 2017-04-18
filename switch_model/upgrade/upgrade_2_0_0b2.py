# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.0b1 to 2.0.0b2.
Changes are:
* switch_mod package is renamed to switch_model
* Update the version number of the inputs directory.
"""

import os
import switch_model.upgrade

upgrades_from = '2.0.0b1'
upgrades_to = '2.0.0b2'

def upgrade_input_dir(inputs_dir):
    """
    Upgrade an input directory to rename the main package from 'switch_mod' 
    to 'switch_model' in the modules.txt file.
    """
    # Find modules.txt; it should be either in the inputs directory or in its 
    # parent directory. 
    modules_path = os.path.join(inputs_dir, 'modules.txt')
    if not os.path.isfile(modules_path):
        modules_path = os.path.join(inputs_dir, '..', 'modules.txt')
    if not os.path.isfile(modules_path):
        raise RuntimeError(
            "Unable to find modules or modules.txt file for input directory '{}'. "
            "This file should be located in the input directory or its parent."
            .format(inputs_dir)
        )

    # Replace switch_mod with switch_model in modules.txt
    with open(modules_path) as f:
        module_list = [line.strip() for line in f.read().splitlines()]
        final_module_list = [line.replace('switch_mod', 'switch_model')
                             for line in module_list]

    with open(modules_path, 'w') as f:
       for module in final_module_list:
            f.write(module + "\n")

    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)
