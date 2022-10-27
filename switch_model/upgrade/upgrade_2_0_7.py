# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
import os, shutil, argparse, glob
import pandas as pd
import switch_model.upgrade
from pyomo.environ import DataPortal

upgrades_from = "2.0.6"
upgrades_to = "2.0.7"

replace_modules = {
    # modules to be replaced in the module list
    # old_module: [new_module1, new_module2, ...],
}

module_messages = {
    # description of significant changes to particular modules other than
    # moving/renaming
    # old_module: message
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
    # update_modules(inputs_dir)

    rename_file(inputs_dir, "generation_projects_info.csv", "gen_info.csv", False)

    rename_column(
        inputs_dir,
        "gen_build_predetermined.csv",
        "gen_predetermined_cap",
        "build_gen_predetermined",
    )

    rename_column(
        inputs_dir,
        "gen_build_predetermined.csv",
        "gen_predetermined_storage_energy_mwh",  # briefly used pre-release
        "build_gen_energy_predetermined",
    )

    move_column(
        inputs_dir,
        old_file_name="trans_params.csv",
        old_col_name="distribution_loss_rate",
        new_file_name="load_zones.csv",
        new_col_name="local_td_loss_rate",
        join_cols=tuple(),
        optional_col=True,
    )


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
        try:
            switch_model.upgrade.print_verbose(
                "ATTENTION: {}".format(module_messages[module])
            )
        except KeyError:
            pass

