# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

# Use this by adding terms like the following to the runph command:
# --linearize-nonbinary-penalty-terms=5 --bounds-cfgfile=pha_bounds_cfg.py

def pysp_boundsetter_callback(self, scenario_tree, scenario):
    m = scenario._instance 	# see pyomo/pysp/scenariotree/tree_structure.py
 
    # BuildLocalTD
    for lz, bld_yr in m.LOCAL_TD_BUILD_YEARS - m.EXISTING_LOCAL_TD_BLD_YRS:
        m.BuildLocalTD[lz, bld_yr].setub(2 * m.lz_peak_demand_mw[lz, bld_yr])

    # Estimate an upper bound of system peak demand for limiting project
    # & transmission builds
    system_wide_peak = {}
    for p in m.PERIODS:
        system_wide_peak[p] = sum(
            m.lz_peak_demand_mw[lz, p] for lz in m.LOAD_ZONES)

    # BuildProj
    for proj, bld_yr in m.PROJECT_BUILDYEARS - m.EXISTING_PROJ_BUILDYEARS:
        if proj not in m.PROJECTS_CAP_LIMITED:
            m.BuildProj[proj, bld_yr].setub(5 * system_wide_peak[bld_yr])

    # BuildTrans
    for tx, bld_yr in m.NEW_TRANS_BLD_YRS:
        m.BuildTrans[tx, bld_yr].setub(5 * system_wide_peak[bld_yr])

# For some reason runph looks for pysp_boundsetter_callback when run in
# single-thread mode and ph_boundsetter_callback when called from mpirun with
# remote execution via pyro. so we map both names to the same function.
ph_boundsetter_callback = pysp_boundsetter_callback