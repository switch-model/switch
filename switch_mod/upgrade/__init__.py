"""
Upgrade input directories between versions. 
See version-specific upgrade scripts for change details.

The main entry point is the switch console tool. See:
    switch upgrade --help

API Synopsis:
    import switch_mod.upgrade

    print switch_mod.upgrade.get_input_version(inputs_dir)

    if switch_mod.upgrade.inputs_need_upgrade(inputs_dir):
        switch_mod.upgrade.upgrade_inputs(inputs_dir)

    print switch_mod.upgrade.get_input_version(inputs_dir)
    
    switch_mod.upgrade.scan_and_upgrade(examples_dir)

"""

import argparse
import os
import shutil

from switch_mod import __version__
import upgrade_2_0_0b1

code_version = __version__
version_file = 'switch_inputs_version.txt'

def scan_and_upgrade(top_dir, input_dir_name = 'inputs'):
    for dirpath, dirnames, filenames in os.walk(top_dir):
        for dirname in dirnames:
            path = os.path.join(dirpath, dirname)
            if os.path.exists(os.path.join(path, input_dir_name, 'modules.txt')):
                upgrade_inputs(os.path.join(path, input_dir_name))


def get_input_version(inputs_dir):
    """
    Scan the inputs directory and take a best-guess at version number.
    In the simple case, this will be in the stored in switch_inputs_version.txt
    Args: 
        inputs_dir (str) path to inputs folder
    Returns:
        version (str) of inputs folder or None for unknown/invalid folders
    """
    version = None
    version_path = os.path.join(inputs_dir, version_file)
    if os.path.isfile(version_path):
        with open(version_path, 'r') as f:
            version = f.readline().strip()
    elif os.path.isfile(os.path.join(inputs_dir, 'generator_info.tab')):
        version = '2.0.0b0'
    return version


def write_input_version(inputs_dir, new_version):
    version_path = os.path.join(inputs_dir, version_file)
    with open(version_path, 'w') as f:
        f.write(new_version + "\n")
    

def inputs_need_upgrade(inputs_dir):
    """
    Determine if input directory can be upgraded with this script.
    Args: 
        inputs_dir (str) path to inputs folder
    Returns:
        (boolean)
    """
    inputs_version = get_input_version(inputs_dir)
    if inputs_version is None:
        return False
    return inputs_version < code_version


def backup(inputs_dir):
    # Make a backup of the inputs_dir into a zip file, unless that already exists
    inputs_version = get_input_version(inputs_dir)
    if inputs_version is None:
        inputs_version = 'Unknown'
    inputs_backup = inputs_dir + '_v' + inputs_version
    inputs_backup_path = inputs_backup + ".zip"
    if not os.path.isfile(inputs_backup_path):
        shutil.make_archive(inputs_backup, 'zip', inputs_dir)

def upgrade_inputs(inputs_dir):
    if inputs_need_upgrade(inputs_dir):
        upgrade_2_0_0b1.upgrade_input_dir(inputs_dir)


def main(args=None):
    if args is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--path", type=str, default="inputs", 
            help='Input directory path (default is "inputs")')
        parser.add_argument("--recursive", dest="recusive", 
            default=False, action='store_true',
            help=('Recursively scan the provided path for inputs directories '
                  'named "inputs", and upgrade each dirctory found.'))
        args = parser.parse_args()
    if args.recusive:
        scan_and_upgrade(args.path)
    else:
        if not os.path.isdir(args.path):
            print "Error: Input directory {} does not exist.".format(args.path)
            return -1    
        upgrade_inputs(args.path)
