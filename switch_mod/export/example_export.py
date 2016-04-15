# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
An example module for customized data export that draws from
multiple modules.

This module has prerequisites of timescales and load_zones.

"""
import os

def save_results(model, instance, outdir):
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
        values=lambda m, lz, t: (lz, m.tp_timestamp[t],) + tuple(
            getattr(m, component)[lz, t]
            for component in (
                m.LZ_Energy_Components_Produce +
                m.LZ_Energy_Components_Consume)))
