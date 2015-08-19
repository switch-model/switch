# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines model components to describe local transmission & distribution
build-outs for the SWITCH-Pyomo model.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'local_td')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe local
    transmission and distribution portions of an electric grid. This
    includes parameters, build decisions and constraints. Unless
    otherwise stated, all power capacity is specified in units of MW and
    all sets and parameters are mandatory.

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

    lz_peak_demand_mw[z,p] describes the peak demand in each load zone z
    and each investment period p. This optional parameter defaults to
    the highest load in the lz_demand_mw timeseries for the given load
    zone & period.

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

    distribution_loss_rate is the proportion of energy that is lost in the
    local transmission & distribution system before delivery. This value
    is relative to delivered energy, so the total energy needed is load
    * (1 + distribution_loss_rate). This optional value defaults to 0.053
    based on ReEDS Solar Vision documentation:
    http://www1.eere.energy.gov/solar/pdfs/svs_appendix_a_model_descriptions_data.pdf

    distribution_losses[lz, t] is a derived parameter describing the
    energy that is lost in the distribution network in each timepoint
    while delivering energy to load. For the moment, this equals
    load[lz, t] multiplied by distribution_loss_rate.

    Meet_Local_TD[lz, period] is a constraint that enforces minimal
    local T&D requirements. Demand response may specify a more complex
    constraint.

        LocalTDCapacity >= max_local_demand

    local_td_annual_cost_per_mw[lz in LOAD_ZONES] describes the total
    annual costs for each MW of local transmission & distributino. This
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

    --- Delayed implementation ---

    # I implemented this in trans_params.dat, but wasn't using it
    # so I commented it out.
    # local_td_lifetime_yrs is a parameter describing the physical and
    # financial lifetime of local transmission & distribution. This
    # parameter is optional and defaults to 20 years.

    distributed PV don't incur distribution_loss_rate..

    local_td_sunk_annual_payment[lz in LOAD_ZONES] .. this was in the
    old model. It would be cleaner if I could copy the pattern for
    project.build where existing projects have the same data structure
    as new projects which includes both an installation date and
    retirement date. For that to work, I would need to knew (or
    estimate) the installation date of existing infrastructure so we
    could know when it needed to be replaced. The old implementation
    assumed a different annual cost of new and existing local T&D. The
    existing infrastructure was expected to remain online indefinitely
    at those costs. The new infrastructure was expected to be retired
    after 20 years, after which new infrastructure would be installed
    via the InstallLocalTD decision variable. The annual costs for
    existing infrastructure were 22-99 percent higher that for new
    infrastructure in the standard WECC datasets, but I don't know the
    reason for the discrepancy.

    --- NOTES ---

    SWITCH-Pyomo treats all transmission and distribution (long-
    distance or local) the same. Any capacity that is built will be kept
    online indefinitely. At the end of its financial lifetime, existing
    capacity will be retired and rebuilt, so the annual cost of a line
    upgrade will remain constant in every future year. See notes in the
    trans_build module for more a more detailed comparison to the old
    SWITCH-WECC model.

    """

    mod.EXISTING_LOCAL_TD_BLD_YRS = Set(
        dimen=2,
        initialize=lambda m: set((lz, 'Legacy') for lz in m.LOAD_ZONES))
    mod.existing_local_td = Param(mod.LOAD_ZONES, within=NonNegativeReals)
    mod.lz_peak_demand_mw = Param(
        mod.LOAD_ZONES, mod.PERIODS,
        within=NonNegativeReals,
        default=lambda m, lz, p: max(
            m.lz_demand_mw[lz, t] for t in m.PERIOD_TPS[p]))
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
    mod.distribution_losses = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        initialize=lambda m, lz, t: (
            m.lz_demand_mw[lz, t] * m.distribution_loss_rate))
    mod.LZ_Energy_Components_Consume.append('distribution_losses')
    mod.Meet_Local_TD = Constraint(
        mod.LOAD_ZONES, mod.PERIODS,
        rule=lambda m, lz, period: (
            m.LocalTDCapacity[lz, period] >= m.lz_peak_demand_mw[lz, period]))
    # mod.local_td_lifetime_yrs = Param(default=20)
    mod.local_td_annual_cost_per_mw = Param(
        mod.LOAD_ZONES,
        within=PositiveReals)
    mod.min_data_check('local_td_annual_cost_per_mw')
    # An expression to summarize annual costs for the objective
    # function. Units should be total annual future costs in $base_year
    # real dollars. The objective function will convert these to
    # base_year Net Present Value in $base_year real dollars.
    mod.LocalTD_Fixed_Costs_Annual = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.BuildLocalTD[lz, bld_yr] * m.local_td_annual_cost_per_mw[lz]
            for (lz, bld_yr) in m.PERIOD_RELEVANT_LOCAL_TD_BUILDS[p]))
    mod.cost_components_annual.append('LocalTD_Fixed_Costs_Annual')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import local transmission & distribution data. The following files
    are expected in the input directory. load_zones.tab will likely
    contain additional columns that are used by the load_zones module.

    load_zones.tab
        load_zone, existing_local_td, local_td_annual_cost_per_mw

    lz_peak_loads.tab is optional.
        LOAD_ZONE, PERIOD, peak_demand_mw

    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'load_zones.tab'),
        auto_select=True,
        param=(mod.existing_local_td, mod.local_td_annual_cost_per_mw))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'lz_peak_loads.tab'),
        select=('LOAD_ZONE', 'PERIOD', 'peak_demand_mw'),
        param=(mod.lz_peak_demand_mw))
