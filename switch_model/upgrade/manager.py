# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

from __future__ import print_function

import argparse
import os
import shutil
from distutils.version import StrictVersion

import switch_model

import upgrade_2_0_0b1
import upgrade_2_0_0b2
import upgrade_2_0_0b4
import upgrade_2_0_1

# Available upgrade code. This needs to be in consecutive order so
# upgrade_inputs can incrementally apply the upgrades.
upgrade_plugins = [
    (upgrade_2_0_0b1,
     upgrade_2_0_0b1.upgrades_from,
     upgrade_2_0_0b1.upgrades_to),
    (upgrade_2_0_0b2,
     upgrade_2_0_0b2.upgrades_from,
     upgrade_2_0_0b2.upgrades_to),
    (upgrade_2_0_0b4,
     upgrade_2_0_0b4.upgrades_from,
     upgrade_2_0_0b4.upgrades_to),
    (upgrade_2_0_1,
     upgrade_2_0_1.upgrades_from,
     upgrade_2_0_1.upgrades_to),
]

# Not every code revision requires an update; this is the last revision that did.
last_required_update = upgrade_plugins[-1][-1]

code_version = StrictVersion(switch_model.__version__)
version_file = 'switch_inputs_version.txt'
#verbose = False
verbose = True

def scan_and_upgrade(top_dir, inputs_dir_name='inputs', backup=True, assign_current_version=False):
    for dirpath, dirnames, filenames in os.walk(top_dir):
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.exists(os.path.join(path, inputs_dir_name, 'modules.txt')):
                # print_verbose('upgrading {}'.format(os.path.join(path, inputs_dir_name)))
                upgrade_inputs(os.path.join(path, inputs_dir_name), backup, assign_current_version)


def get_input_version(inputs_dir):
    """
    Scan the inputs directory and take a best-guess at version number.
    In the simple case, this will be in the stored in switch_inputs_version.txt
    Args:
        inputs_dir (str) path to inputs folder
    Returns:
        version (str) of inputs folder
    Note: Raises an ValueError if the inputs directory has an unrecognized format.
    """
    version_path = os.path.join(inputs_dir, version_file)
    if os.path.isfile(version_path):
        with open(version_path, 'r') as f:
            version = f.readline().strip()
    # Before we started storing version numbers in the inputs directory, we
    # had an input file named generator_info.tab. If that file exists, we are
    # dealing with version 2.0.0b0.
    elif os.path.isfile(os.path.join(inputs_dir, 'generator_info.tab')):
        version = '2.0.0b0'
    else:
        raise ValueError((
            "Input directory {} is not recognized as a valid Switch input folder. "
            "An input directory needs to contain a file named '{}' that stores the "
            "version number of Switch that it was intended for. ").format(
                inputs_dir, version_file))
    return version


def _write_input_version(inputs_dir, new_version):
    version_path = os.path.join(inputs_dir, version_file)
    with open(version_path, 'w') as f:
        f.write(new_version + "\n")

def do_inputs_need_upgrade(inputs_dir):
    """
    Determine if input directory can be upgraded with this script.
    Args:
        inputs_dir (str) path to inputs folder
    Returns:
        (boolean)
    """
    # Not every code revision requires an update, so just hard-code the last
    # revision that required an update.
    inputs_version = get_input_version(inputs_dir)
    return StrictVersion(inputs_version) < StrictVersion(last_required_update)


def _backup(inputs_dir):
    """
    Make a backup of the inputs_dir into a zip file, unless it already exists
    """
    inputs_backup = inputs_dir + '_v' + get_input_version(inputs_dir)
    inputs_backup_path = inputs_backup + ".zip"
    if not os.path.isfile(inputs_backup_path):
        shutil.make_archive(inputs_backup, 'zip', inputs_dir)


def print_verbose(*args):
    global verbose
    if verbose:
        print(*args)


def upgrade_inputs(inputs_dir, backup=True, assign_current_version=False):
    # This logic will grow over time as complexity evolves.. Don't overengineer
    upgraded = False
    if do_inputs_need_upgrade(inputs_dir):
        print_verbose('Upgrading ' + inputs_dir)
        if backup:
            print_verbose('\tBacked up original inputs')
            _backup(inputs_dir)
        # Successively apply the upgrade scripts as needed.
        for (upgrader, v_from, v_to) in upgrade_plugins:
            inputs_v = StrictVersion(get_input_version(inputs_dir))
            # note: the next line catches datasets created by/for versions of Switch that
            # didn't require input directory upgrades
            if StrictVersion(v_from) <= inputs_v < StrictVersion(v_to):
                print_verbose('\tUpgrading from ' + v_from + ' to ' + v_to)
                upgrader.upgrade_input_dir(inputs_dir)
        upgraded = True

    if (StrictVersion(last_required_update) < StrictVersion(switch_model.__version__)
            and assign_current_version):
        # user requested writing of current version number, even if no upgrade is needed
        # (useful for updating examples to track with new release of Switch)
        _write_input_version(inputs_dir, switch_model.__version__)
        upgraded = True

    if upgraded:
        print_verbose('\tFinished upgrading ' + inputs_dir + '\n')
    else:
        print_verbose('Skipped ' + inputs_dir + '; it does not need upgrade.')


def main(args=None):
    if args is None:
        # note: we don't pass the args object directly to scan_and_upgrade or upgrade_inputs
        # because those may be called from elsewhere with custom arguments
        parser = argparse.ArgumentParser()
        add_parser_args(parser)
        args = parser.parse_args()
    set_verbose(args.verbose)
    if args.recursive:
        scan_and_upgrade('.', args.inputs_dir_name, args.backup, args.assign_current_version)
    else:
        if not os.path.isdir(args.inputs_dir_name):
            print("Error: Input directory {} does not exist.".format(args.inputs_dir_name))
            return -1
        upgrade_inputs(os.path.normpath(args.inputs_dir_name), args.backup, args.assign_current_version)

def set_verbose(verbosity):
    global verbose
    verbose = verbosity

def add_parser_args(parser):
    parser.add_argument("--inputs-dir-name", type=str, default="inputs",
        help='Input directory name (default is "inputs")')
    parser.add_argument("--backup", action='store_true', default=True,
        help='Make backup of inputs directory before upgrading (set true by default)')
    parser.add_argument("--no-backup", action='store_false', dest='backup',
        help='Do not make backup of inputs directory before upgrading')
    parser.add_argument("--assign-current-version", dest='assign_current_version',
        action='store_true', default=False,
        help=('Update version number in inputs directory to match current version'
              'of Switch, even if data does not require an upgrade.'))
    parser.add_argument("--recursive", dest="recursive",
        default=False, action='store_true',
        help=('Recursively scan the provided path for inputs directories '
              'named "inputs", and upgrade each directory found. Note, this '
              'requires each inputs directory to include modules.txt. This '
              'will not work if modules.txt is in the parent directory.'))
    parser.add_argument("--verbose", action='store_true', default=verbose)
    parser.add_argument("--quiet", dest="verbose", action='store_false')
