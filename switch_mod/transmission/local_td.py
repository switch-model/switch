# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe local transmission & distribution
build-outs for the SWITCH-Pyomo model.
"""

import os
from pyomo.environ import *

dependencies = 'switch_mod.timescales', 'switch_mod.balancing.load_zones',\
    'switch_mod.financials'

def define_components(mod):
    """

    Define local transmission and distribution portions of an electric grid.
    This models load zones as two nodes: the central grid node described in
    the load_zones module, and a distributed (virtual) node that is connected
    to the central bus via a local_td pathway with losses described by
    distribution_loss_rate. Distributed Energy Resources (DER) such as
    distributed solar, demand response, efficiency programs, etc will need to
    register with the Distributed_Withdrawals and Distributed_Injections lists
    which are used for power balance equations. This module is divided into
    two sections: the distribution node and the local_td pathway that connects
    it to the central grid.
    
    Note: This module interprets the parameter lz_demand_mw[z,t] as the end-
    use sales rather than the withdrawals from the central grid, and moves
    lz_demand_mw from the LZ_Energy_Components_Consume list to the
    Distributed_Withdrawals list so that distribution losses can be accounted
    for.
    
    Unless otherwise stated, all power capacity is specified in units of MW and
    all sets and parameters are mandatory.

    DISTRIBUTED NODE

    WithdrawFromCentralGrid[z, t] is a decision variable that describes the
    power exchanges between the central grid and the distributed network, from
    the perspective of the central grid. We currently prohibit injections into
    the central grid because it would create a mathematical loophole for
    "spilling power" and we currently lack use cases that need this. We cannot
    use a single unsigned varaible for this without introducing errrors in
    calculating Local T&D line losses. WithdrawFromCentralGrid is added to the
    load_zone power balance, and has a corresponding expression from the
    perspective of the distributed node:
    
    InjectIntoDistributedGrid[z,t] = WithdrawFromCentralGrid[z,t] * (1-distribution_loss_rate)
        
    Distributed_Injections and Distributed_Withdrawals are lists of DER model
    components that inject and withdraw from a load zone's distributed node.
    Distributed_Injections is initially set to InjectIntoDistributedGrid, and
    Distributed_Withdrawals is initial set to lz_demand_mw. Each component in
    either of these lists will need to be indexed by (z,t) across all
    LOAD_ZONES and TIMEPOINTS.

    The Distributed_Energy_Balance constraint is defined in define_dynamic_components.


    LOCAL_TD PATHWAY

    LOCAL_TD_BUILD_YEARS is the set of load zones with local
    transmission and distribution and years in which construction has or
    could occur. This set includes past and potential future builds. All
    future builds must come online in the first year of an investment
    period. This set is composed of two elements with members:
    (load_zone, build_year). For existing capacity where the build year
    is unknown or spread out over time, build_year is set to 'Legacy'.

    EXISTING_LOCAL_TD_BLD_YRS is a subset of LOCAL_TD_BUILD_YEARS that
    lists builds that happened before the first investment period. For
    most datasets the build year is unknown, so is it always set to
    'Legacy'.

    existing_local_td[lz in LOAD_ZONES] is the amount of local
    transmission and distribution capacity in MW that has already been
    built.

    BuildLocalTD[(lz, bld_yr) in LOCAL_TD_BUILD_YEARS] is a decision
    variable describing how much local transmission and distribution to
    build in a load zone. For existing builds, this variable is locked
    to existing capacity. Without demand response, the optimal value of
    this variable is trivially computed based on the load zone's peak
    expected load. With demand response, this decision becomes less
    obvious in high solar conditions where it may be desirable to shift
    some demand from evening into afternoon to coincide with the solar
    peak.

    LocalTDCapacity[lz, period] is an expression that describes how much
    local transmission and distribution has been built to date in each
    load zone.

    distribution_loss_rate is the ratio of average losses for local T&D. This
    value is relative to delivered energy, so the total energy needed is load
    * (1 + distribution_loss_rate). This optional value defaults to 0.053
    based on ReEDS Solar Vision documentation:
    http://www1.eere.energy.gov/solar/pdfs/svs_appendix_a_model_descriptions_data.pdf

    Meet_Local_TD[lz, period] is a constraint that enforces minimal
    local T&D requirements.
        LocalTDCapacity >= max_local_demand

    local_td_annual_cost_per_mw[lz in LOAD_ZONES] describes the total
    annual costs for each MW of local transmission & distribution. This
    value should include the annualized capital costs as well as fixed
    operations & maintenance costs. These costs will be applied to
    existing and new infrastructure. We assume that existing capacity
    will be replaced at the end of its life, so these costs will
    continue indefinitely.

    PERIOD_RELEVANT_LOCAL_TD_BUILDS[p in PERIODS] is an indexed set that
    describes which local transmission & distribution builds will be
    operational in a given period. Currently, local T & D lines are kept
    online indefinitely, with parts being replaced as they wear out.
    PERIOD_RELEVANT_LOCAL_TD_BUILDS[p] will return a subset of (lz,
    bld_yr) in LOCAL_TD_BUILD_YEARS. Same idea as
    PERIOD_RELEVANT_TRANS_BUILDS, but with a different scope.

    --- NOTES ---

    SWITCH-Pyomo treats all transmission and distribution (long-
    distance or local) the same. Any capacity that is built will be kept
    online indefinitely. At the end of its financial lifetime, existing
    capacity will be retired and rebuilt, so the annual cost of a line
    upgrade will remain constant in every future year. See notes in the
    trans_build module for more a more detailed comparison to the old
    SWITCH-WECC model.

    """

    # Local T&D
    mod.EXISTING_LOCAL_TD_BLD_YRS = Set(
        dimen=2,
        initialize=lambda m: set((lz, 'Legacy') for lz in m.LOAD_ZONES))
    mod.existing_local_td = Param(mod.LOAD_ZONES, within=NonNegativeReals)
    mod.min_data_check('existing_local_td')
    mod.LOCAL_TD_BUILD_YEARS = Set(
        dimen=2,
        initialize=lambda m: set(
            (m.LOAD_ZONES * m.PERIODS) | m.EXISTING_LOCAL_TD_BLD_YRS))
    mod.PERIOD_RELEVANT_LOCAL_TD_BUILDS = Set(
        mod.PERIODS,
        within=mod.LOCAL_TD_BUILD_YEARS,
        initialize=lambda m, p: set(
            (lz, bld_yr) for (lz, bld_yr) in m.LOCAL_TD_BUILD_YEARS
            if bld_yr <= p))

    def bounds_BuildLocalTD(model, lz, bld_yr):
        if((lz, bld_yr) in model.EXISTING_LOCAL_TD_BLD_YRS):
            return (model.existing_local_td[lz],
                    model.existing_local_td[lz])
        else:
            return (0, None)
    mod.BuildLocalTD = Var(
        mod.LOCAL_TD_BUILD_YEARS,
        within=NonNegativeReals,
        bounds=bounds_BuildLocalTD)
    mod.LocalTDCapacity = Expression(
        mod.LOAD_ZONES, mod.PERIODS,
        rule=lambda m, lz, period: sum(
            m.BuildLocalTD[lz, bld_yr]
            for (lz2, bld_yr) in m.LOCAL_TD_BUILD_YEARS
            if lz2 == lz and (bld_yr == 'Legacy' or bld_yr <= period)))
    mod.distribution_loss_rate = Param(default=0.053)
#    mod.distribution_loss_rate = Param(default=0.053/(1+0.053))

    mod.Meet_Local_TD = Constraint(
        mod.LOAD_ZONES, mod.PERIODS,
        rule=lambda m, lz, period: (
            m.LocalTDCapacity[lz, period] >= m.lz_peak_demand_mw[lz, period]))
    mod.local_td_annual_cost_per_mw = Param(
        mod.LOAD_ZONES,
        within=PositiveReals)
    mod.min_data_check('local_td_annual_cost_per_mw')
    mod.LocalTD_Fixed_Costs_Annual = Expression(
        mod.PERIODS,
        doc="Summarize annual local T&D costs for the objective function.",
        rule=lambda m, p: sum(
            m.BuildLocalTD[lz, bld_yr] * m.local_td_annual_cost_per_mw[lz]
            for (lz, bld_yr) in m.PERIOD_RELEVANT_LOCAL_TD_BUILDS[p]))
    mod.cost_components_annual.append('LocalTD_Fixed_Costs_Annual')


    # DISTRIBUTED NODE
    mod.WithdrawFromCentralGrid = Var(
        mod.ZONE_TIMEPOINTS,
        within=NonNegativeReals,
        doc="Power withdrawn from a zone's central node sent over local T&D.")
    mod.Enforce_Local_TD_Capacity_Limit = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t:
            m.WithdrawFromCentralGrid[z,t] <= m.LocalTDCapacity[z,m.tp_period[t]])
    mod.InjectIntoDistributedGrid = Expression(
        mod.ZONE_TIMEPOINTS,
        doc="Describes WithdrawFromCentralGrid after line losses.",
        rule=lambda m, z, t: m.WithdrawFromCentralGrid[z,t] * (1-m.distribution_loss_rate))
    mod.LZ_Energy_Components_Consume.append('WithdrawFromCentralGrid')
    mod.LZ_Energy_Components_Produce.remove('LZ_NetDistributedInjections')
    mod.Distributed_Injections = ['InjectIntoDistributedGrid', 'LZ_NetDistributedInjections']
    mod.LZ_Energy_Components_Consume.remove('lz_demand_mw')
    mod.Distributed_Withdrawals = ['lz_demand_mw']


def define_dynamic_components(mod):
    """

    Adds components to a Pyomo abstract model object to enforce the
    first law of thermodynamics at the level of distibuted nodes. Unless
    otherwise stated, all terms describing power are in units of MW and
    all terms describing energy are in units of MWh.

    Distributed_Energy_Balance[z, t] is a constraint that sets the sums of
    Distributed_Injections and Distributed_Withdrawals equal to each other in
    every zone and timepoint. 

    """

    mod.Distributed_Energy_Balance = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: (
            sum(
                getattr(m, component)[z, t]
                for component in m.Distributed_Injections
            ) == sum(
                getattr(m, component)[z, t]
                for component in m.Distributed_Withdrawals)))


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import local transmission & distribution data. The following files
    are expected in the input directory. load_zones.tab will
    contain additional columns that are used by the load_zones module.

    load_zones.tab
        load_zone, existing_local_td, local_td_annual_cost_per_mw

    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'load_zones.tab'),
        auto_select=True,
        param=(mod.existing_local_td, mod.local_td_annual_cost_per_mw))
