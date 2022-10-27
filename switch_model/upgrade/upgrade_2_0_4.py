# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.1 to 2.0.4. (There were no changes for 2.0.2
or 2.0.3.) This doesn't actually do anything except update the data version
number and show the module-change messages.
"""

import os, shutil, argparse
import pandas
import switch_model.upgrade

upgrades_from = "2.0.1"
upgrades_to = "2.0.4"

replace_modules = {
    # no renames in this version
}

module_messages = {
    # description of significant changes to particular modules (other than moving)
    # old_module: message
    "switch_model.transmission.local_td": "Switch 2.0.4 makes two changes to the local_td module. "
    "1. The carrying cost of pre-existing local transmission and "
    "distribution is now included in the total system costs. "
    "2. The legacy transmission is no longer reported in the "
    "BuildLocalTD.tab output file.",
    "switch_model.reporting": "Output files (*.tab) now use native line endings instead of "
    "always using Unix-style line endings. On Windows systems, these "
    'files will now use "\\r\\n" instead of "\\n".',
    "switch_model.reporting.basic_exports": "Output files (*.csv) now use native line endings instead of "
    "always using Unix-style line endings. On Windows systems, these "
    'files will now use "\\r\\n" instead of "\\n".',
    "switch_model.hawaii.save_results": "Output files (*.tsv) now use native line endings instead of "
    "always using Unix-style line endings. On Windows systems, these "
    'files will now use "\\r\\n" instead of "\\n".',
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
    df = pandas.read_csv(path, na_values=["."], sep=r"\s+", index_col=False)
    df.rename(columns={old_col_name: new_col_name}, inplace=True)
    df.to_csv(path, sep="\t", na_rep=".", index=False)


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
