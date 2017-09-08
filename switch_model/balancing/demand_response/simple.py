# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines a simple Demand Response Shift Service for the SWITCH-Pyomo model.
Load in a certain load zone may be shifted between timepoints belonging to the
same timeseries at no cost, which allows assessing the potential value of
demand shifting. This does not include a Shed Service (curtailment of load), 
nor a Shimmy Service (fast dispatch for load following or regulation).

"""

import os
from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones'
optional_dependencies = 'switch_model.transmission.local_td'


def define_components(mod):
    
    """
    Adds components to a Pyomo abstract model object to describe a demand
    response shift service.

    dr_shift_down_limit[(z,t in ZONE_TIMEPOINTS)] is a parameter
    that describes the maximum reduction in demand for load-shifting demand
    response (in MW) that is allowed in a load zone at a specific timepoint.
    Its default value is 0, and it may not exceed the load.

    dr_shift_up_limit[z,t] is a parameter that describes the maximum
    increase in demand for load-shifting demand response (in MW) that is
    allowed in a load zone at a specific timepoint. Its default value is
    infinity.

    ShiftDemand[z,t] is a decision variable describing how much load
    in MW is reduced (if its value is negative) or increased (if
    its value is positive). This variable is bounded by dr_shift_down_limit
    and dr_shift_up_limit.
    
    If the local_td module is included, ShiftDemand[z,t] will be registered
    with local_td's distributed node for energy balancing purposes. If
    local_td is not included, it will be registered with load zone's central
    node and will not reflect efficiency losses in the distribution network.
    
    DR_Shift_Net_Zero[z,ts in TIMESERIES] is a constraint that forces all the
    changes in the demand to balance out over the course of each timeseries.
    
    """
    
    mod.dr_shift_down_limit = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default= 0.0,
        within=NonNegativeReals,
        validate=lambda m, value, z, t: value <= m.zone_demand_mw[z, t])
    mod.dr_shift_up_limit = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default= float('inf'),
        within=NonNegativeReals)
    mod.ShiftDemand = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=Reals,
        bounds=lambda m, z, t: 
        (
            (-1.0) * m.dr_shift_down_limit[z,t],
            m.dr_shift_up_limit[z,t]
        ))

    mod.DR_Shift_Net_Zero = Constraint(
        mod.LOAD_ZONES, mod.TIMESERIES,
        rule=lambda m, z, ts:
        sum(m.ShiftDemand[z, t] for t in m.TPS_IN_TS[ts]) == 0.0)
    
    if 'Distributed_Power_Withdrawals' in dir(mod):
        mod.Distributed_Power_Withdrawals.append('ShiftDemand')
    else:
        mod.Zone_Power_Withdrawals.append('ShiftDemand')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import demand response-specific data from an input directory.

    dr_data.tab
        LOAD_ZONE, TIMEPOINT, dr_shift_down_limit, dr_shift_up_limit

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'dr_data.tab'),
        autoselect=True,
        param=(mod.dr_shift_down_limit, mod.dr_shift_up_limit))
