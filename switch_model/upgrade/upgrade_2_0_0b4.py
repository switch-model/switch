# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.0b2 to 2.0.0b4. (There were no changes for 2.0.0b3)
Changes are:
* rename 'project' column to 'GENERATION_PROJECT' in 'gen_inc_heat_rates.tab' file.
"""

import os, shutil, argparse
import pandas
import switch_model.upgrade

upgrades_from = '2.0.0b2'
upgrades_to = '2.0.0b4'

def upgrade_input_dir(inputs_dir):
    """
    Upgrade an input directory.
    """

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
        
    old_new_column_names_in_file = {
        'gen_inc_heat_rates.tab': [('project', 'GENERATION_PROJECT')]
    }
    
    for fname, old_new_pairs in old_new_column_names_in_file.iteritems():
        for old_new_pair in old_new_pairs:
            old = old_new_pair[0]
            new = old_new_pair[1]
            rename_column(fname, old_col_name=old, new_col_name=new)

    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)
