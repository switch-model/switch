# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
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
        for old, new in old_new_pairs:
            rename_column(fname, old_col_name=old, new_col_name=new)

    # merge trans_optional_params.tab with transmission_lines.tab
    trans_lines_path = os.path.join(inputs_dir, 'transmission_lines.tab')
    trans_opt_path = os.path.join(inputs_dir, 'trans_optional_params.tab')
    if os.path.isfile(trans_lines_path) and os.path.isfile(trans_lines_path):
        trans_lines = pandas.read_csv(trans_lines_path, na_values=['.'], sep='\t')
        if os.path.isfile(trans_opt_path):
            trans_opt = pandas.read_csv(trans_opt_path, na_values=['.'], sep='\t')
            trans_lines = trans_lines.merge(trans_opt, on='TRANSMISSION_LINE', how='left')
        trans_lines.to_csv(trans_lines_path, sep='\t', na_rep='.', index=False)
        if os.path.isfile(trans_opt_path):
            os.remove(trans_opt_path)

    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)
