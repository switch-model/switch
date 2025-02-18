# Copyright (c) 2015-2024 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
import os, shutil, argparse, glob
import pandas as pd

# have to import the module rather than the functions themselves because
# the module is probably still loading (this was called from it)
import switch_model.upgrade as up
from pyomo.environ import DataPortal

upgrades_from = "2.0.9"
upgrades_to = "2.0.10"

replace_modules = {
    # modules to be replaced in the module list
    # old_module: [new_module1, new_module2, ...],
    "switch_model.balancing.demand_response.iterative": [
        "switch_model.balancing.demand_response.iterative",
        "switch_model.balancing.unserved_load",
    ]
}

module_messages = {
    # description of significant changes to particular modules other than
    # moving/renaming
    # old_module: message
    "switch_model.hawaii.ev": """
        The `switch_model.hawaii.ev` module has a new flag
        `--report-vehicle-costs` that can be used to export info on the cost of
        electric and internal combustion engine vehicles to vehicle_costs.csv.
        You should use this flag instead of `--save-expressions
        ev_extra_annual_cost ice_annual_fuel_cost` if you want this information.
        This module also no longer assumes internal combustion engine vehicles
        use "Motor_Gasoline" as their fuel. Instead, it reads the name from the
        `ice_fuel` column in inputs/ev_fleet_info.csv. This should be set to
        "Motor_Gasoline" in your input files to continue the previous behavior.
        Also note: `ev_extra_cost_per_vehicle_year`, `ice_fuel` and
        `ice_miles_per_gallon` columns in ev.csv are now semi-optional. They
        must be provided if you use the `--report-vehicle-costs` flag but they
        can be omitted if you don't set this flag. When using this flag, 
        `ice_fuel` must match the name of a fuel in your `fuel_costs.csv` or
        `fuel_supply_curves.csv` input file.
        """,
    "switch_model.balancing.demand_response.iterative": """
        There are two important changes to the `demand_response.iterative`
        module in Switch 2.0.10: (1) The bidding function in the demand module
        must now accept duration_of_tp as an additional argument and must report
        the benefit of each bid (WTP) in dollars per hour instead of total
        dollars for the timeseries. Note that prices are given in $/MWh for each
        timepoint in the timeseries and quantities are reported back in MW for
        each timepoint (of indeterminate duration). WTP is typically calculated
        from p • q, which has units of $/hour * n_timepoints, which was the
        previous return value. Dividing this value by len(p) gives $/hour, which
        will be more robust across different timeseries definitions. (2) This
        module no longer defines its own unserved load components. Instead, you
        should use the `switch_model.balancing.unserved_load` module to ensure
        the model is feasible, even with large demand-side bids. Your modules
        list has been updated to reflect this change.
    """,
    "switch_model.balancing.demand_response.iterative.constant_elasticity_demand_system": """
    The built-in `constant_elasticity_demand_system` now reports bid benefit
    (wtp) in $/hour instead of $/timeseries, to be compatible with the updated
    `demand_response.iterative` module.
    """,
}


def create_unserved_load_penalty(inputs_dir):
    with open(modules_file(inputs_dir)) as f:
        old_module_list = [line.strip() for line in f.read().splitlines()]

    lost_load_file = os.path.join(inputs_dir, "lost_load_cost.csv")

    up.print_verbose()
    if os.path.exists(lost_load_file):
        cur_penalty = pd.read_csv(lost_load_file)["unserved_load_penalty"].item()

        if cur_penalty > 10000:
            up.print_verbose(
                f"""
                WARNING: switch_model.balancing.demand_response.iterative
                previously applied an unserved load penalty of $10,000/MWh. That
                module will no longer apply a lost-load penalty; instead the
                balancing.unserved_load module will use the penalty specified in
                your {lost_load_file} file, which is currently higher:
                ${cur_penalty}/MWh. You should change this unserved_load_penalty
                to 10000 if you want to replicate the previous behavior.
                """
            )
        elif cur_penalty == 10000:
            up.print_verbose(
                f"""
                NOTE: switch_model.balancing.demand_response.iterative module
                previously applied an unserved load penalty of $10,000/MWh in
                addition to the identical one specified in your {lost_load_file}
                file. The demand_response.iterative module will no longer apply
                a lost-load penalty; instead the balancing.unserved_load module
                will use the penalty specified in {lost_load_file}. This should
                not change your model results.
                """
            )
        else:
            if "switch_model.balancing.unserved_load" in old_module_list:
                up.print_verbose(
                    f"""
                    NOTE: switch_model.balancing.demand_response.iterative
                    previously applied an unserved load penalty of $10,000/MWh
                    in addition to the lower one specified by the
                    switch_model.balancing.unserved_load module. The
                    demand_response.iterative module will no longer apply a
                    lost-load penalty; instead the balancing.unserved_load
                    module will continue to use the penalty specified in your
                    {lost_load_file} file, which is currently
                    ${cur_penalty}/MWh. This should not change your model
                    results.
                    """
                )
            else:
                # lower penalty already specified, not previously using
                # unserved_load module, but may have had the unserved load file
                # for side cases?
                up.print_verbose(
                    f"""
                    WARNING: switch_model.balancing.demand_response.iterative
                    previously applied an unserved load penalty of $10,000/MWh.
                    Your {lost_load_file} file specifies a lower one for use by
                    switch_model.balancing.unserved_load, but you do not appear
                    to be using the unserved_load module. The
                    demand_response.iterative module will no longer apply a
                    lost-load penalty; instead the unserved_load module will
                    apply the penalty specified by unserved_load_penalty in your
                    {lost_load_file} file, which is currently
                    ${cur_penalty}/MWh. You may need to raise this to 10000 to
                    avoid changing your model results.
                    """
                )

    elif "switch_model.balancing.unserved_load" in old_module_list:
        up.print_verbose(
            f"""
            NOTE: It appears that you were previously using the
            switch_model.balancing.unserved_load with the default penalty of
            $5,000/MWh. This will be left unchanged, and the
            switch_model.balancing.demand_response.iterative will no longer
            apply an independent, higher (and therefore unused) penalty of
            $10,000/MWh.
            """
        )
    else:
        with open(lost_load_file, "w") as f:
            f.write("unserved_load_penalty\n")
            f.write("10000\n")
        up.print_verbose(
            f"""
            The upgrade script has created {lost_load_file} to apply the same
            lost-load penalty as previously used by
            switch_model.balancing.demand_response.iterative ($10000/MWh).
            """
        )


module_actions = {
    # functions to run if they previously were using a particular module
    # old_module: function      # function must accept inputs_dir as its only argument
    "switch_model.balancing.demand_response.iterative": create_unserved_load_penalty
}


def upgrade_input_dir(inputs_dir):
    """
    Upgrade the input directory.
    """
    # Write a new version text file. We do this early so that if the update
    # fails and then the user tries again it won't try to upgrade a second time,
    # overwriting their backup.
    up._write_input_version(inputs_dir, upgrades_to)

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
        up.print_verbose(f"Input file {old_name} was already renamed to {new_name}.")
    else:
        shutil.move(old_path, new_path)
        up.print_verbose(f"Input file {old_name} has been renamed to {new_name}.")


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
        up.print_verbose(
            f"Column {old_col_name} has been renamed to {new_col_name} in {file_name}."
        )
    elif new_col_name in df.columns:
        up.print_verbose(
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
        up.print_verbose(
            f"Column {old_file_name} > {old_col_name} has been moved to {new_file_name} > {new_col_name}."
        )
    elif new_col_name in new_df.columns:
        up.print_verbose(
            f"Column {old_file_name} > {old_col_name} was already moved to {new_file_name} > {new_col_name}."
        )
    elif not optional_col:
        # column wasn't found and isn't optional
        raise ValueError(f"Mandatory column {old_col_name} not found in {old_path}.")


def item_list(items):
    """Generate normal-text version of list of items, with commas and "and" as needed."""
    return " and ".join(", ".join(items).rsplit(", ", 1))


def update_modules(inputs_dir):
    """
    Report relevant messages, perform actions and rename/replace modules in the
    module list if needed. Modules list is sought in standard locations.
    """

    modules_path = modules_file(inputs_dir)
    with open(modules_path) as f:
        old_module_list = [line.strip() for line in f.read().splitlines()]

    # perform any required actions and report any messages for the previously
    # active modules
    for module in old_module_list:
        if module in module_messages:
            up.print_verbose()
            up.print_verbose(f"ATTENTION: {up.rewrap(module_messages[module])}")
        if module in module_actions:
            module_actions[module](inputs_dir)

    replace_module_entries(modules_path)


def modules_file(inputs_dir):
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
    return modules_path


def replace_module_entries(modules_path):
    # Upgrade module listings
    # Each line of the original file is either a module identifier or a comment
    with open(modules_path) as f:
        old_module_list = [line.strip() for line in f.read().splitlines()]

    # rename modules as needed
    new_module_list = []
    for module in old_module_list:
        try:
            # identify replacements if specified
            new_modules = replace_modules[module]
            up.print_verbose()
            up.print_verbose(
                f"The upgrade script has replaced {module} with {item_list(new_modules)} "
                f"in your {modules_path} file."
            )
        except KeyError:
            # not in replace_module dict; use original module
            new_modules = [module]
        new_module_list.extend(new_modules)

    if new_module_list != old_module_list:
        # write new modules list
        # TODO: make a backup of this file and preserve comments
        # drop any duplicates (e.g., if a replacement includes a module already
        # in the list)
        new_module_list = list(dict.fromkeys(new_module_list))
        with open(modules_path, "w") as f:
            for module in new_module_list:
                f.write(module + "\n")


def set_ice_fuel(inputs_dir):
    ev_file = os.path.join(inputs_dir, "ev_fleet_info.csv")
    if os.path.exists(ev_file):
        ev = pd.read_csv(ev_file, na_values=".")
        # add the previous default ICE fuel ("Motor_Gasoline")
        ev["ice_fuel"] = "Motor_Gasoline"
        ev.to_csv(ev_file, index=False, na_rep=".")
        up.print_verbose()
        up.print_verbose(
            f"""
            The upgrade script has added the default ice_fuel ("Motor_Gasoline")
            to {ev_file}. You can remove this if you are not using the
            --report-vehicle-costs flag with the switch_model.hawaii.ev module.
            """
        )
