# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
This module defines Virtual Batteries of Electric Vehicles in each Load Zone for
defining Charging Profiles for the SWITCH-Pyomo model. Virtual Batteries 
represents the aggregation of several batteries from electric vehicles. The 
charging of a virtual battery can be delayed according to a limit on the 
cummulative charge that depends on mobility patterns and users availability.
Virtual Batteries are not allowed to inject energy to the grid and at the end
of each timeseries they must be charged at some specific level according
to users necessity.

"""

import os
from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones'
optional_dependencies = 'switch_model.transmission.local_td'


def define_components(mod):
    
    """
    Adds components to a Pyomo abstract model object to describe a virtual
    battery charging pattern.

    ev_charge_limit[z,t] is a parameter that describes the maximum 
    instantaneous charge (power limit) in MW for a virtual battery in load
    zone z at timepoint t.

    ev_cumulative_charge_upper_mwh[z,t] is a parameter that describes the
    upper limit to the cumulative charge state in MWh for the virtual
    battery in load zone z at a timepoint t. 

    ev_cumulative_charge_lower_mwh[z,t] is a parameter that describes the
    lower limit to the cumulative charge state in MWh for the virtual battery
    in load zone z at a a timepoint t.

    EVCharge[z,t] is a decision variable that describes how much MW
    (in average) are being injected to the virtual battery in load zone z
    at a timepoint t. This parameter models the power requirements from the
    grid and not the state of charge of the battery (i.e. no efficiency is
    considered).

    EVCumulativeCharge[z,t] is an expression that calculates the cumulative
    charge of the virtual battery in load zone z at timepoint t in MWh. It is calculated by
    summing all the charges at previous timepoints of t within its timeseries
    and multiplying them by their duration in hours.
    
    EV_Cumulative_Charge_Upper_Limit[z,t] is a constraint that limits the
    cumulative charge of the virtual battery to its upper limit defined on
    ev_cumulative_charge_upper.

    EV_Cumulative_Charge_Upper_Limit[z,t] is a constraint that limits the
    cumulative charge of the virtual battery to its lower limit defined on
    ev_cumulative_charge_lower.

    If the local_td module is included, EVCharge[z,t] will be registered
    with local_td's distributed node for energy balancing purposes. If
    local_td is not included, it will be registered with load zone's central
    node and will not reflect efficiency losses in the distribution network.
    
        
    """
    
    mod.ev_charge_limit_mw = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default = float('inf'),
        within=NonNegativeReals)

    mod.ev_cumulative_charge_upper_mwh = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default = 0.0,
        within=NonNegativeReals)

    mod.ev_cumulative_charge_lower_mwh = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        default = 0.0,
        within=NonNegativeReals)

    mod.EVCharge = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonNegativeReals,
        bounds=lambda m, z, t:
        (
           0.0,
           m.ev_charge_limit_mw[z,t]
           )
        )

    mod.EVCumulativeCharge = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t: \
            sum(m.EVCharge[z,tau]*m.tp_duration_hrs[tau]
                for tau in m.TPS_IN_TS[m.tp_ts[t]]
                if tau <= t)
        )

    mod.EV_Cumulative_Charge_Upper_Limit =  Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t:
        m.EVCumulativeCharge[z,t] <= m.ev_cumulative_charge_upper_mwh[z,t]) 

    mod.Vbat_Cumulative_Charge_Lower_Limit =  Constraint(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, z, t:
        m.EVCumulativeCharge[z,t] >= m.ev_cumulative_charge_lower_mwh[z,t]) 

    if 'Distributed_Power_Injections' in dir(mod):
        mod.Distributed_Power_Withdrawals.append('EVCharge')
    else:
        mod.Zone_Power_Withdrawals.append('EVCharge')



def load_inputs(mod, switch_data, inputs_dir):
    """

    Import virtual batteries specific location and power limits
    from an input directory.

    ev_limits.tab
        LOAD_ZONES, TIMEPOINT, ev_cumulative_charge_upper_mwh,
        ev_cumulative_charge_upper_mwh, ev_charge_limit_mw

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'ev_limits.tab'),
        autoselect=True,
        param=(mod.ev_cumulative_charge_lower_mwh, mod.ev_cumulative_charge_upper_mwh, mod.ev_charge_limit_mw))
