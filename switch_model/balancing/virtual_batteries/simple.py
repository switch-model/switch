# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
This module defines a Virtual Batteries of Electric Vehicles for defining 
Charging Profiles for the SWITCH-Pyomo model. Virtual Batteries represents the
aggregation of several batteries from electric vehicles. The charging of a 
virtual battery can be delayed according to a limit on the cummulative charge
that depends on mobility patterns and users availability. Virtual Batteries are
not allowed to inject energy to the grid and at the end of each timeseries 
they must be charged at some specific level according to users necessity.

"""

import os
from pyomo.environ import *

dependencies = "switch_model.timescales", "switch_model.balancing.load_zones"
optional_dependencies = "switch_model.transmission.local_td"


def define_components(mod):

    """
    Adds components to a Pyomo abstract model object to describe a virtual
    battery charging pattern.

    VIRTUAL_BATTERIES is the set of virtual batteries. Each battery is
    connected in a specific load zone and requires to meet charging
    requirements.  Virtual batteries are abbreviated as vbat in
    parameter names and as vb for indexes.

    vbat_load_zone[vb] is the load zone in which this battery is connected.

    VBATS_IN_ZONE[z in LOAD_ZONES] is an indexed set that lists all
    virtual batteries within each load zone.

    vbat_charge_limit[vb] is a parameter that describes the maximum
    instantaneous charge (power limit) in MW for a virtual battery.

    vbat_cumulative_charge_upper_mwh[vb,t] is a parameter that describes the
    upper limit to the cumulative charge state in MWh at a timepoint t.

    vbat_cumulative_charge_lower_mwh[vb,t] is a parameter that describes the
    lower limit to the cumulative charge state in MWh at a timepoint t. This
    parameter should be equal to the upper limit at the end of a timeseries.

    VbatCharge[vb,t] is a decision variable that describes how much MW
    (in average) are being injected to the virtual battery at a timepoint t.
    This parameter models the power requirements from the grid and not the
    state of charge of the battery (i.e. no efficiency is considered).

    VbatCumulativeCharge[vb,t] is an expression that calculates the cumulative
    charge of the virtual battery at timepoint t in MWh. It is calculated by
    summing all the charges at previous timepoints of t within its timeseries
    and multiplying them by their duration in hours.

    Vbat_Cumulative_Charge_Upper_Limit[vb,t] is a constraint that limits the
    cumulative charge of the virtual battery to its upper limit defined on
    vbat_cumulative_charge_upper.

    Vbat_Cumulative_Charge_Upper_Limit[vb,t] is a constraint that limits the
    cumulative charge of the virtual battery to its lower limit defined on
    vbat_cumulative_charge_lower.

    ZoneTotalCharge[z,t] is a expression that calculates the total power
    consumed by the virtual batteries located at each load zone z at a
    timepoint t.

    If the local_td module is included, ZoneTotalCharge[z,t] will be registered
    with local_td's distributed node for energy balancing purposes. If
    local_td is not included, it will be registered with load zone's central
    node and will not reflect efficiency losses in the distribution network.


    """

    mod.VIRTUAL_BATTERIES = Set()

    mod.vbat_load_zone = Param(mod.VIRTUAL_BATTERIES, within=mod.LOAD_ZONES)

    mod.VBATS_IN_ZONE = Set(
        mod.LOAD_ZONES,
        initialize=lambda m, z: set(
            vb for vb in m.VIRTUAL_BATTERIES if m.vbat_load_zone[vb] == z
        ),
    )

    mod.vbat_charge_limit = Param(
        mod.VIRTUAL_BATTERIES, default=float("inf"), within=NonNegativeReals
    )

    mod.vbat_cumulative_charge_upper_mwh = Param(
        mod.VIRTUAL_BATTERIES, mod.TIMEPOINTS, within=NonNegativeReals
    )

    mod.vbat_cumulative_charge_lower_mwh = Param(
        mod.VIRTUAL_BATTERIES, mod.TIMEPOINTS, within=NonNegativeReals
    )

    mod.VbatCharge = Var(
        mod.VIRTUAL_BATTERIES,
        mod.TIMEPOINTS,
        within=NonNegativeReals,
        bounds=lambda m, vb, t: (0.0, m.vbat_charge_limit[vb]),
    )

    mod.VbatCumulativeCharge = Expression(
        mod.VIRTUAL_BATTERIES,
        mod.TIMEPOINTS,
        rule=lambda m, vb, t: sum(
            m.VbatCharge[vb, tau] * m.tp_duration_hrs[tau]
            for tau in m.TPS_IN_TS[m.tp_ts[t]]
            if tau <= t
        ),
    )

    mod.Vbat_Cumulative_Charge_Upper_Limit = Constraint(
        mod.VIRTUAL_BATTERIES,
        mod.TIMEPOINTS,
        rule=lambda m, vb, t: m.VbatCumulativeCharge[vb, t]
        <= m.vbat_cumulative_charge_upper_mwh[vb, t],
    )

    mod.Vbat_Cumulative_Charge_Lower_Limit = Constraint(
        mod.VIRTUAL_BATTERIES,
        mod.TIMEPOINTS,
        rule=lambda m, vb, t: m.VbatCumulativeCharge[vb, t]
        >= m.vbat_cumulative_charge_lower_mwh[vb, t],
    )

    mod.ZoneTotalCharge = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: sum(m.VbatCharge[vb, t] for vb in m.VBATS_IN_ZONE[z]),
    )

    if "Distributed_Power_Injections" in dir(mod):
        mod.Distributed_Power_Injections.append("ZoneTotalCharge")
    else:
        mod.Zone_Power_Withdrawals.append("ZoneTotalCharge")


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import virtual batteries specific location and power limits
    from an input directory.

    vbat_info.tab
        VIRTUAL_BATTERIES, vbat_load_zone, vbat_charge_limit

    vbat_limits.tab
        VIRTUAL_BATTERIES, TIMEPOINT, vbat_cumulative_charge_upper_mwh,
        vbat_cumulative_charge_upper_mwh

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "vbat_info.tab"),
        auto_select=True,
        index=mod.VIRTUAL_BATTERIES,
        param=(mod.vbat_load_zone, mod.vbat_charge_limit),
    )

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "vbat_limits.tab"),
        autoselect=True,
        param=(
            mod.vbat_cumulative_charge_lower_mwh,
            mod.vbat_cumulative_charge_upper_mwh,
        ),
    )
