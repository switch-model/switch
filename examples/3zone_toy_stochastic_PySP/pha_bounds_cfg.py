# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

# Use this by adding terms like the following to the runph command:
# --linearize-nonbinary-penalty-terms=5 --bounds-cfgfile=pha_bounds_cfg.py


def pysp_boundsetter_callback(self, scenario_tree, scenario):
    m = scenario._instance  # see pyomo/pysp/scenariotree/tree_structure.py

    # BuildLocalTD
    for p in m.PERIODS:
        for lz in m.LOAD_ZONES:
            m.BuildLocalTD[lz, p].setub(
                2 * m.zone_expected_coincident_peak_demand[lz, p]
            )

    # Estimate an upper bound of system peak demand for limiting generation unit
    # & transmission line builds
    system_wide_peak = {}
    for p in m.PERIODS:
        system_wide_peak[p] = sum(
            m.zone_expected_coincident_peak_demand[lz, p] for lz in m.LOAD_ZONES
        )

    # BuildGen
    for g, bld_yr in m.NEW_GEN_BLD_YRS:
        m.BuildGen[g, bld_yr].setub(5 * system_wide_peak[bld_yr])

    # BuildTx
    for tx, bld_yr in m.TRANS_BLD_YRS:
        m.BuildTx[tx, bld_yr].setub(5 * system_wide_peak[bld_yr])


# For some reason runph looks for pysp_boundsetter_callback when run in
# single-thread mode and ph_boundsetter_callback when called from mpirun with
# remote execution via pyro. so we map both names to the same function.
ph_boundsetter_callback = pysp_boundsetter_callback
