# Copyright (c) 2015-2024 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
import os, shutil, argparse, glob
import pandas as pd
import switch_model.upgrade
from pyomo.environ import DataPortal

upgrades_from = "2.0.9"
upgrades_to = "2.0.10"

replace_modules = {
    # modules to be replaced in the module list
    # old_module: [new_module1, new_module2, ...],
}

module_messages = {
    # description of significant changes to particular modules other than
    # moving/renaming
    # old_module: message
    "switch_model.hawaii.ev": (
        """
        The `switch_model.hawaii.ev` module no longer assumes internal combustion engine
        vehicles use "Motor_Gasoline" as their fuel. The new default is "none", which will
        cause the cost of ICE fuel to be reported as zero. Set `ice_fuel` to
        "Motor_Gasoline" in inputs/ev.csv to continue the previous behavior. Also note: the
        `ev_extra_cost_per_vehicle_year`, `ice_fuel` and `ice_miles_per_gallon` columns in
        ev.csv are now optional. They can be omitted if you are not reporting or using EV
        incremental costs or ICE fuel costs via `--save-expressions ev_extra_annual_cost
        ice_annual_fuel_cost`.
        """
    )
}


def upgrade_input_dir(inputs_dir):
    """
    Upgrade the input directory.
    """
    # Write a new version text file. We do this early so that if the update
    # fails and then the user tries again it won't try to upgrade a second time,
    # overwriting their backup.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)

    # rename modules and report changes
    update_modules(inputs_dir)

    # use the ICE fuel previously assumed by switch_model.hawaii.ev
    set_ice_fuel(inputs_dir)


def rename_file(inputs_dir, old_name, new_name, optional_file=True):
    old_path = os.path.join(inputs_dir, old_name)
    new_path = os.path.join(inputs_dir, new_name)
    if optional_file and not os.path.isfile(old_path):
        pass
    elif os.path.isfile(new_path) and not os.path.isfile(old_path):
        switch_model.upgrade.print_verbose(
            f"Input file {old_name} was already renamed to {new_name}."
        )
    else:
        shutil.move(old_path, new_path)
        switch_model.upgrade.print_verbose(
            f"Input file {old_name} has been renamed to {new_name}."
        )


def rename_column(
    inputs_dir, file_name, old_col_name, new_col_name, optional_file=True
):
    path = os.path.join(inputs_dir, file_name)
    if optional_file and not os.path.isfile(path):
        return
    df = pd.read_csv(path, na_values=["."], sep=",")  # for 2.0.5+
    if old_col_name in df.columns:
        df.rename(columns={old_col_name: new_col_name}, inplace=True)
        df.to_csv(path, sep=",", na_rep=".", index=False)
        switch_model.upgrade.print_verbose(
            f"Column {old_col_name} has been renamed to {new_col_name} in {file_name}."
        )
    elif new_col_name in df.columns:
        switch_model.upgrade.print_verbose(
            f"Column {old_col_name} was already renamed to {new_col_name} in {file_name}."
        )


def move_column(
    inputs_dir,
    old_file_name,
    old_col_name,
    new_file_name,
    new_col_name,
    join_cols,
    optional_col=True,
):
    old_path = os.path.join(inputs_dir, old_file_name)
    new_path = os.path.join(inputs_dir, new_file_name)
    if optional_col and not os.path.isfile(old_path):
        return
    # add dummy key to allow cross-joins
    fixed_join_cols = list(join_cols) + ["dummy_join_key"]
    old_df = pd.read_csv(old_path, na_values=["."], sep=",").assign(dummy_join_key=0)
    # TODO: create new_path if it doesn't exist
    new_df = pd.read_csv(new_path, na_values=["."], sep=",").assign(dummy_join_key=0)
    if old_col_name in old_df.columns:
        new_col = old_df.loc[:, fixed_join_cols + [old_col_name]].merge(
            new_df.loc[:, fixed_join_cols], on=fixed_join_cols
        )
        new_df[new_col_name] = new_col[old_col_name]
        new_df.drop("dummy_join_key", axis=1, inplace=True)
        new_df.to_csv(new_path, sep=",", na_rep=".", index=False)
        old_df.drop([old_col_name, "dummy_join_key"], axis=1, inplace=True)
        old_df.to_csv(old_path, sep=",", na_rep=".", index=False)
        switch_model.upgrade.print_verbose(
            f"Column {old_file_name} > {old_col_name} has been moved to {new_file_name} > {new_col_name}."
        )
    elif new_col_name in new_df.columns:
        switch_model.upgrade.print_verbose(
            f"Column {old_file_name} > {old_col_name} was already moved to {new_file_name} > {new_col_name}."
        )
    elif not optional_col:
        # column wasn't found and isn't optional
        raise ValueError(f"Mandatory column {old_col_name} not found in {old_path}.")


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
        if module in module_messages:
            switch_model.upgrade.print_verbose()
            switch_model.upgrade.print_verbose(
                f"ATTENTION: {switch_model.upgrade.rewrap(module_messages[module])}"
            )


def set_ice_fuel(inputs_dir):
    ev_file = os.path.join(inputs_dir, "ev.csv")
    if os.path.exists(ev_file):
        ev = pd.read_csv(ev_file, na_values=".")
        # add the previous default ICE fuel ("Motor_Gasoline")
        ev["ice_fuel"] = "Motor_Gasoline"
        ev.to_csv(ev_file, index=False, na_rep=".")
        switch_model.upgrade.print_verbose()
        switch_model.upgrade.print_verbose(
            """
            Added default ice_fuel ("Motor_Gasoline") to ev.csv. This can be removed 
            if you are not using ICE fuel costs from the `switch_model.hawaii.ev` module.
            """
        )
