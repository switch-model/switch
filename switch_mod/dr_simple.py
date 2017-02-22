# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines a simple DR scheme for the SWITCH-Pyomo model. Load in a certain
load zone may be shifted between timepoints belonging to the same 
timeseries at no cost, which allows assessing the potential value of
demand shifting.

"""

import os
from pyomo.environ import *


def define_components(mod):
    
    """
    Adds components to a Pyomo abstract model object to describe a demand
    response scheme on load zones.

    dr_max_curtail_in_MW[(lz in LOAD_ZONES, t in TIMEPOINTS)] is a parameter
    that describe the maximum demand curtailment in MW allowed in a load
    zone at a specific timepoint. Its default value is 0.

    dr_max_increase_in_MW[lz, t] is a parameter that describes the maximum
    demand increase in MW allowed in a load zone at a specific timepoint.
    Its default value is infinity.

    DemandResponse[lz,t] is a decision variable describing how much load
    in MW is reduced (if its value is negative) or increased (if
    its value is positive).
    
    DR_Max_Curtailment[lz,t] is a constraint that describes the maximum
    curtailment allowed in MW for a load zone at a specific timepoint.

    DR_Curtail_Allowed[lz,t] is a constraint that prevents curtailment
    to be more than the local demand at each timepoint.

    DR_Max_Increase[lz,t] is a constraint that describes the maximum increase
    of demand allowed in MW for a load zone at a specific timepoint.

    DR_Net_Zero[lz,ts in TIMESERIES] is a constraint that forces all the
    changes in the demand to balance out over the course of each timeseries.

    Notes:

    DR_Max_Curtailment and DR_Curtail_Allowed can be merged in only one
    equation, picking the minimum value between min(dr_max_curtail_in_MW,
    lz_demand_mw).
    
    """
    
    mod.dr_max_curtail_in_MW = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default= 0.0,
        within=NonNegativeReals)
    mod.dr_max_increase_in_MW = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default= float('inf'),
        within=NonNegativeReals)
    mod.DemandResponse = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=Reals)

    mod.DR_Max_Curtailment = Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t:
        m.DemandResponse[z, t] >= (-1.0) * m.dr_max_curtail_in_MW[z,t])

    mod.DR_Curtail_Allowed = Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t:
        m.DemandResponse[z, t] >= (-1.0) * m.lz_demand_mw[z,t])

    mod.DR_Max_Increase = Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t:
        m.DemandResponse[z, t] <= m.dr_max_increase_in_MW[z,t])

    mod.DR_Net_Zero = Constraint(
        mod.LOAD_ZONES, mod.TIMESERIES,
        rule=lambda m, z, ts:
        sum(m.DemandResponse[z, t] for t in m.TS_TPS[ts]) == 0.0)

    mod.LZ_Energy_Components_Consume.append('DemandResponse')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import demand response-specific data from an input directory.

    dr_data.tab
        LOAD_ZONE, TIMEPOINT, dr_max_curtail_in_MW, dr_max_increase_in_MW

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'dr_data.tab'),
        autoselect=True,
        param=(mod.dr_max_curtail_in_MW, mod.dr_max_increase_in_MW))
