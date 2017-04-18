# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

from __future__ import print_function

import argparse
import os
import shutil
from distutils.version import StrictVersion

import switch_model

import upgrade_2_0_0b1
import upgrade_2_0_0b2

# Available upgrade code. This needs to be in consecutive order so 
# upgrade_inputs can incrementally apply the upgrades.
upgrade_plugins = [
    (upgrade_2_0_0b1, 
     upgrade_2_0_0b1.upgrades_from, 
     upgrade_2_0_0b1.upgrades_to),
    (upgrade_2_0_0b2, 
     upgrade_2_0_0b2.upgrades_from,
     upgrade_2_0_0b2.upgrades_to),
]
    

code_version = StrictVersion(switch_model.__version__)
version_file = 'switch_inputs_version.txt'
#verbose = False
verbose = True

def scan_and_upgrade(top_dir, input_dir_name = 'inputs'):
    for dirpath, dirnames, filenames in os.walk(top_dir):
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.exists(os.path.join(path, input_dir_name, 'modules.txt')):
                upgrade_inputs(os.path.join(path, input_dir_name), verbose)


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
    last_required_update = '2.0.0b2'
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


def upgrade_inputs(inputs_dir, backup=True):
    # This logic will grow over time as complexity evolves.. Don't overengineer
    if do_inputs_need_upgrade(inputs_dir):
        print_verbose('Upgrading ' + inputs_dir)
        if backup:
            print_verbose('\tBacked up original inputs')
            _backup(inputs_dir)
        # Successively apply the upgrade scripts as needed.
        for (upgrader, v_from, v_to) in upgrade_plugins:
            inputs_v = StrictVersion(get_input_version(inputs_dir))
            if inputs_v == StrictVersion(v_from):
                print_verbose('\tUpgrading from ' + v_from + ' to ' + v_to)
                upgrader.upgrade_input_dir(inputs_dir)
        print_verbose('\tFinished upgrading ' + inputs_dir + '\n')
    else:
        print_verbose('Skipped ' + inputs_dir + ' it does not need upgrade.')


def main(args=None):
    if args is None:
        parser = argparse.ArgumentParser()
        add_parser_args(parser)
        args = parser.parse_args()
    set_verbose(args.verbose)
    if args.recusive:
        scan_and_upgrade(args.path)
    else:
        if not os.path.isdir(args.path):
            print("Error: Input directory {} does not exist.".format(args.path))
            return -1    
        upgrade_inputs(os.path.normpath(args.path))

def set_verbose(verbosity):
    global verbose
    verbose = verbosity

def add_parser_args(parser):
    parser.add_argument("--path", type=str, default="inputs", 
        help='Input directory path (default is "inputs")')
    parser.add_argument("--recursive", dest="recusive", 
        default=False, action='store_true',
        help=('Recursively scan the provided path for inputs directories '
              'named "inputs", and upgrade each directory found. Note, this '
              'requires each inputs directory to include modules.txt. This '
              'will not work if modules.txt is in the parent directory.'))
    parser.add_argument("--verbose", action='store_true', default=verbose)
    parser.add_argument("--quiet", dest="verbose", action='store_false')
