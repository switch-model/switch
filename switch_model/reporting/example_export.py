# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
An example module for customized data export that draws from
multiple modules.

This module has prerequisites of timescales and load_zones.

After we write some more useful examples of custom export code, we should
remove this file.
"""
import os
from switch_model.reporting import write_table

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones'

def post_solve(instance, outdir):
    """
    This rudimentary example copies the export code from load_zones, but uses
    a different file name (load_balance2.txt).
    """
    write_table(
        instance, instance.LOAD_ZONES, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "load_balance2.txt"),
        headings=("load_zone", "timestamp",) + tuple(
            instance.Zone_Power_Injections +
            instance.Zone_Power_Withdrawals),
        values=lambda m, z, t: (z, m.tp_timestamp[t],) + tuple(
            getattr(m, component)[z, t]
            for component in (
                m.Zone_Power_Injections +
                m.Zone_Power_Withdrawals)))
