# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.5 to 2.0.6dev1: 
transmission lines now require bi-directional specifications.
"""

import argparse
import glob
import os
import shutil

import pandas
from pyomo.environ import DataPortal

import switch_model.upgrade

upgrades_from = '2.0.5'
upgrades_to = '2.0.6dev1'

replace_modules = {
    # no renames in this version
}

module_messages = {
    # description of significant changes to particular modules (other than moving)
    # module: message
    'switch_model.transmission.transport.build':
        'Transmission lines now must be specified in each direction.',
}

def upgrade_input_dir(inputs_dir):
    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)

    path = os.path.join(inputs_dir, 'transmission_lines.csv')
    try:
        df = pandas.read_csv(path)
    except FileNotFoundError:
        return
    
    df.rename(
        inplace=True,
        columns={
            'trans_lz1': 'trans_lz_send', 
            'trans_lz2': 'trans_lz_receive',
        })
    # Database key is not the same for non-directional vs directional lines.
    # Safest to drop it.
    if 'trans_dbid' in df:
        df.drop(columns='trans_dbid', inplace=True)
    df2 = df.copy()
    df2.rename(
        inplace=True,
        columns={
            'trans_lz_send': 'trans_lz_receive', 
            'trans_lz_receive': 'trans_lz_send'
        })
    df2['TRANSMISSION_LINE'] = (
        df2['trans_lz_send'] + '-' + df2['trans_lz_receive']
    )
    df_merged = pandas.concat([df, df2], ignore_index=True, sort=False)
    df_merged.to_csv(path, index=False)
