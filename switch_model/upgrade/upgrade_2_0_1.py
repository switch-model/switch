# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.0b4 (final beta) to 2.0.1. (There were no changes for 2.0.0.)
This just moves some modules, as listed in the rename_modules variable.
"""

import os, shutil, argparse
import pandas
import switch_model.upgrade

upgrades_from = '2.0.0b4'
upgrades_to = '2.0.1'

# note: we could keep switch_model.hawaii.reserves active, but then we would need special code to switch
# the model to the main reserves module if and only if they are using the iterative demand response system
# which seems unnecessarily complicated
replace_modules = {
    'switch_model.hawaii.demand_response':
        ['switch_model.balancing.demand_response.iterative'],
    'switch_model.hawaii.r_demand_system':
        ['switch_model.balancing.demand_response.iterative.r_demand_system'],
    'switch_model.hawaii.reserves': [
        'switch_model.balancing.operating_reserves.areas',
        'switch_model.balancing.operating_reserves.spinning_reserves',
    ]
}
module_messages = {
    # description of significant changes to particular modules (other than moving)
    # old_module: message
    'switch_model.hawaii.r_demand_system':
        'The switch_model.hawaii.r_demand_system module has been moved. Please update '
        'the --dr-demand-module flag to point to the new location.',
    'switch_model.hawaii.demand_response':
        'The switch_model.hawaii.demand_response module has been moved. Please update '
        'iterate.txt to refer to the new location.',
    'switch_model.hawaii.switch_patch':
        'The switch_model.hawaii.switch_patch module no longer patches '
        'the cplex solver to generate dual values for mixed-integer programs. '
        'Use the new --retrieve-cplex-mip-duals flag if you need this behavior.'
}

def upgrade_input_dir(inputs_dir):
    """
    Upgrade the input directory.
    """
    # rename modules and report changes
    update_modules(inputs_dir)

    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)


def rename_file(old_name, new_name, optional_file=True):
    old_path = os.path.join(inputs_dir, old_name)
    new_path = os.path.join(inputs_dir, new_name)
    if optional_file and not os.path.isfile(old_path):
        return
    shutil.move(old_path, new_path)

def rename_column(file_name, old_col_name, new_col_name, optional_file=True):
    path = os.path.join(inputs_dir, file_name)
    if optional_file and not os.path.isfile(path):
        return
    df = pandas.read_csv(path, na_values=['.'], sep='\t')
    df.rename(columns={old_col_name: new_col_name}, inplace=True)
    df.to_csv(path, sep='\t', na_rep='.', index=False)

def item_list(items):
    """Generate normal-text version of list of items, with commas and "and" as needed."""
    return ' and '.join(', '.join(items).rsplit(', ', 1))

def update_modules(inputs_dir):
    """Rename modules in the module list if needed (list is sought in
    standard locations) and return list of alerts for user."""

    modules_path = os.path.join(inputs_dir, 'modules.txt')
    if not os.path.isfile(modules_path):
        modules_path = os.path.join(inputs_dir, '..', 'modules.txt')
    if not os.path.isfile(modules_path):
        raise RuntimeError(
            "Unable to find modules or modules.txt file for input directory '{}'. "
            "This file should be located in the input directory or its parent."
            .format(inputs_dir)
        )
    modules_path = os.path.normpath(modules_path) # tidy up for display later

    # Upgrade module listings
    # Each line of the original file is either a module identifier or a comment
    with open(modules_path) as f:
        old_module_list = [line.strip() for line in f.read().splitlines()]

    # rename modules as needed
    new_module_list=[]
    for module in old_module_list:
        try:
            new_modules = replace_modules[module]
            print (
                "Module {old} has been replaced by {new} in {file}."
                .format(old=module, new=item_list(new_modules), file=modules_path)
            )
        except KeyError:
            new_modules = [module]
        new_module_list.extend(new_modules)

    # load reserve balancing areas module early, to support modules that
    # define reserve products.

    # switch_model.hawaii.reserves loaded late and then found reserve
    # components defined by other modules, but
    # switch_model.balancing.operating_reserves.spinning_reserves should
    # load early so other modules can register reserves with it.
    if 'switch_model.hawaii.reserves' in old_module_list:
        new_spin = 'switch_model.balancing.operating_reserves.areas'
        try:
            insert_pos = new_module_list.index('switch_model.balancing.load_zones') + 1
            if insert_pos < new_module_list.index(new_spin):
                new_module_list.remove(new_spin)
                new_module_list.insert(insert_pos, new_spin)
                # print (
                #     '{} has been moved up to row {} in {}, '
                #     'to allow other modules to register reserves with it.'
                #     .format(new_spin, insert_pos + 1, modules_path)
                # )
        except ValueError:
            # couldn't find the location to insert spinning reserves module
            print (
                '{} module should be moved early in the module list, '
                'before any modules that define reserve elements.'
                .format(new_spin)
            )

    #import pdb; pdb.set_trace()

    # write new modules list
    with open(modules_path, 'w') as f:
       for module in new_module_list:
            f.write(module + "\n")

    # report any significant changes in the previously active modules
    for module in old_module_list:
        try:
            print "ATTENTION: {}".format(module_messages[module])
        except KeyError:
            pass
