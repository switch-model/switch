# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
An example module for customized data export that draws from
multiple modules.

This module has prerequisites of timescales and load_zones.

"""
import os

dependencies = 'switch_mod.timescales', 'switch_mod.balancing.load_zones'

def post_solve(instance, outdir):
    """
    Export results to standard files.

    """
    import switch_mod.export as export
    export.write_table(
        instance, instance.LOAD_ZONES, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "load_balance2.txt"),
        headings=("load_zone", "timestamp",) + tuple(
            instance.LZ_Energy_Components_Produce +
            instance.LZ_Energy_Components_Consume),
        values=lambda m, z, t: (z, m.tp_timestamp[t],) + tuple(
            getattr(m, component)[z, t]
            for component in (
                m.LZ_Energy_Components_Produce +
                m.LZ_Energy_Components_Consume)))
