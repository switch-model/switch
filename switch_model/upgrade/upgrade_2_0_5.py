# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.1 to 2.0.4. (There were no changes for 2.0.2
or 2.0.3.) This doesn't actually do anything except update the data version
number and show the module-change messages.
"""

import os, shutil, argparse, glob
import pandas
import switch_model.upgrade
from pyomo.environ import DataPortal


upgrades_from = "2.0.4"
upgrades_to = "2.0.5"

replace_modules = {
    # no renames in this version
}

module_messages = {
    # description of significant changes to particular modules (other than moving)
    # old_module: message
    "switch_model": "Beginning with Switch 2.0.5, all inputs must be in .csv files and all "
    "outputs will be written to .csv files."
}


def upgrade_input_dir(inputs_dir):
    """
    Upgrade the input directory.
    """
    # rename modules and report changes
    update_modules(inputs_dir)

    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)

    # Convert all .tab input files to .csv (maybe it should
    # work with a list of specific files instead?)
    for old_path in glob.glob(os.path.join(inputs_dir, "*.tab")):
        new_path = old_path[:-4] + ".csv"
        convert_tab_to_csv(old_path, new_path)
    # Convert certain .tab input files to .csv
    # These are all simple ampl/pyomo files with only un-indexed parameters
    for f in [
        "financials.dat",
        "trans_params.dat",
        "spillage_penalty.dat",
        "spinning_reserve_params.dat",
        "lost_load_cost.dat",
        "hydrogen.dat",
    ]:
        old_path = os.path.join(inputs_dir, f)
        new_path = old_path[:-4] + ".csv"
        if os.path.exists(old_path):
            convert_dat_to_csv(old_path, new_path)


def convert_tab_to_csv(old_path, new_path):
    # Note: we assume the old file is a simple ampl/pyomo dat file, with only
    # non-indexed parameters (that is the case for all the ones listed above)
    try:
        # Allow any whitespace as a delimiter because that is how ampl/pyomo .tab
        # files work, and some of our older examples use spaces instead of tabs
        # (e.g., tests/upgrade_dat/copperplate1/inputs/variable_capacity_factors.tab).
        df = pandas.read_csv(old_path, na_values=["."], sep=r"\s+")
        df.to_csv(new_path, sep=",", na_rep=".", index=False)
        os.remove(old_path)
    except Exception as e:
        print("\nERROR converting {} to {}:\n{}".format(old_path, new_path, e.message))
        raise


def convert_dat_to_csv(old_path, new_path):
    # define a dummy "model" where every "parameter" reports a dimension of 0.
    # otherwise Pyomo assumes they have dim=1 and looks for index values.
    class DummyModel:
        def __getattr__(self, pname):
            return DummyParam()

    class DummyParam:
        def dim(self):
            return 0

    try:
        data = DataPortal(model=DummyModel())
        data.load(filename=old_path)
        # this happens to be in a pandas-friendly format
        df = pandas.DataFrame(data.data())
        df.to_csv(new_path, sep=",", na_rep=".", index=False)
        os.remove(old_path)
    except Exception as e:
        print("\nERROR converting {} to {}:\n{}".format(old_path, new_path, e.message))
        raise


# These functions are not used in the 2.0.5 upgrade, but kept here for the future
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
    df = pandas.read_csv(path, na_values=["."], sep=",")  # for 2.0.5+
    df.rename(columns={old_col_name: new_col_name}, inplace=True)
    df.to_csv(path, sep=",", na_rep=".", index=False)


def item_list(items):
    """Generate normal-text version of list of items, with commas and "and" as needed."""
    return " and ".join(", ".join(items).rsplit(", ", 1))


def update_modules(inputs_dir):
    """Rename modules in the module list if needed (list is sought in
    standard locations) and return list of alerts for user."""

    modules_path = os.path.join(inputs_dir, "modules.txt")
    if not os.path.isfile(modules_path):
        modules_path = os.path.join(inputs_dir, "..", "modules.txt")
    if not os.path.isfile(modules_path):
        modules_path = "modules.txt"
    if not os.path.isfile(modules_path):
        raise RuntimeError(
            "Unable to find modules or modules.txt file for input directory '{}'. "
            "This file should be located in the input directory, its parent, or "
            "the current working directory.".format(inputs_dir)
        )
    modules_path = os.path.normpath(modules_path)  # tidy up for display later

    # Upgrade module listings
    # Each line of the original file is either a module identifier or a comment
    with open(modules_path) as f:
        old_module_list = [line.strip() for line in f.read().splitlines()]

    # rename modules as needed
    new_module_list = []
    for module in old_module_list:
        try:
            new_modules = replace_modules[module]
            switch_model.upgrade.print_verbose(
                "Module {old} has been replaced by {new} in {file}.".format(
                    old=module, new=item_list(new_modules), file=modules_path
                )
            )
        except KeyError:
            new_modules = [module]
        new_module_list.extend(new_modules)

    if new_module_list != old_module_list:
        # write new modules list
        with open(modules_path, "w") as f:
            for module in new_module_list:
                f.write(module + "\n")

    # report any significant changes in the previously active modules
    for module in old_module_list:
        try:
            switch_model.upgrade.print_verbose(
                "ATTENTION: {}".format(module_messages[module])
            )
        except KeyError:
            pass
