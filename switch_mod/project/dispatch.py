# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines model components to describe generation projects build-outs for
the SWITCH-Pyomo model. This module requires either project.unitcommit or
project.no_commit to constrain project dispatch to either committed or
installed capacity.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels',
...     'gen_tech', 'project.build', 'project.dispatch')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe the
    dispatch decisions and constraints of generation and storage
    projects. Unless otherwise stated, all power capacity is specified
    in units of MW and all sets and parameters are mandatory.

    PROJ_DISPATCH_POINTS is a set of projects and timepoints in which
    they can be dispatched. A dispatch decisions is made for each member
    of this set. Members of this set can be abbreviated as (proj, t) or
    (prj, t).

    ProjCapacityTP[(proj, t) in PROJ_DISPATCH_POINTS] is the same as
    ProjCapacity but indexed by timepoint rather than period to allow
    more compact statements.

    DispatchProj[(proj, t) in PROJ_DISPATCH_POINTS] is the set
    of generation dispatch decisions: how much average power in MW to
    produce in each timepoint. This value can be multiplied by the
    duration of the timepoint in hours to determine the energy produced
    by a project in a timepoint.

    proj_forced_outage_rate[prj] and proj_scheduled_outage_rate[prj]
    describe the forces and scheduled outage rates for each project.
    These parameters can be specified for individual projects via an
    input file (see load_inputs() documentation), or generically for all
    projects of a given generation technology via
    g_scheduled_outage_rate and g_forced_outage_rate. You will get an
    error if any project is missing values for either of these
    parameters.

    proj_availability[prj] describes the fraction of a time a project is
    expected to be available. This is derived from the forced and
    scheduled outage rates of the project. For baseload or flexible
    baseload, this is determined from both forced and scheduled outage
    rates. For all other types of generation technologies, we assume the
    scheduled outages can be performed when the generators were not
    scheduled to produce power, so their availability is only derated
    based on their forced outage rates.

    proj_max_capacity_factor[prj, t] is defined for variable renewable
    projects and is the ratio of average power output to nameplate
    capacity in that timepoint. Most renewable capacity factors should
    be in the range of 0 to 1. Some solar capacity factors will be above
    1 because the nameplate capacity is based on solar radiation of 1.0
    kW/m^2 and solar radiation can exceed that value on very clear days
    or on partially cloudy days when light bounces off the bottom of
    clouds onto a solar panel. Some solar thermal capacity factors can
    be less than 0 because of auxillary loads: for example, parts of
    those plants need to be kept warm during winter nights to avoid
    freezing. Those heating loads can be significant during certain
    timepoints.

    proj_variable_om[proj] is the variable Operations and Maintenance
    costs (O&M) per MWh of dispatched capacity for a given project.

    proj_full_load_heat_rate[proj] is the full load heat rate in units
    of MMBTU/MWh that describes the thermal efficiency of a project when
    runnign at full load. This optional parameter overrides the generic
    heat rate of a generation technology. In the future, we may expand
    this to be indexed by fuel source as well if we need to support a
    multi-fuel generator whose heat rate depends on fuel source.

    Proj_Var_Costs_Hourly[t in TIMEPOINTS] is the sum of all variable
    costs associated with project dispatch for each timepoint expressed
    in $base_year/hour in the future period (rather than Net Present
    Value).

    PROJ_WITH_FUEL_DISPATCH_POINTS is a subset of PROJ_DISPATCH_POINTS
    showing all times when fuel-consuming projects could be dispatched 
    (used to identify timepoints when fuel use must match power production).

    PROJ_FUEL_DISPATCH_POINTS is a subset of PROJ_DISPATCH_POINTS * FUELS,
    showing all the valid combinations of project, timepoint and fuel,
    i.e., all the times when each project could consume a fuel that is 
    limited, costly or produces emissions.

    ProjFuelUseRate[(proj, t, f) in PROJ_FUEL_DISPATCH_POINTS] is a
    variable that describes fuel consumption rate in MMBTU/h. This
    should be constrained to the fuel consumed by a project in each
    timepoint and can be calculated as Dispatch [MW] *
    effective_heat_rate [MMBTU/MWh] -> [MMBTU/h]. The choice of how to
    constrain it depends on the treatment of unit commitment. Currently
    the project.no_commit module implements a simple treatment that
    ignores unit commitment and assumes a full load heat rate, while the
    project.unitcommit module implements unit commitment decisions with
    startup fuel requirements and a marginal heat rate.

    DispatchEmissions[(proj, t, f) in PROJ_FUEL_DISPATCH_POINTS] is the
    emissions produced by dispatching a fuel-based project in units of
    metric tonnes CO2 per hour. This is derived from the fuel
    consumption ProjFuelUseRate, the fuel's direct carbon intensity, the
    fuel's upstream emissions, as well as Carbon Capture efficiency for
    generators that implement Carbon Capture and Sequestration. This does
    not yet support multi-fuel generators.

    --- Delayed implementation, possibly relegated to other modules. ---

    Flexible baseload support for plants that can ramp slowly over the
    course of days. These kinds of generators can provide important
    seasonal support in high renewable and low emission futures.

    Parasitic loads that make solar thermal plants consume energy from
    the grid on cold nights to keep their fluids from getting too cold.

    Storage support.

    Hybrid project support (pumped hydro & CAES) will eventually get
    implemented in separate modules.

    """

    # I might be able to simplify this, but the current formulation
    # should exclude any timepoints in periods in which a project will
    # definitely be retired.
    def init_projects_active_in_timepoints(m,t):
        active_projects = set()
        for proj in m.PROJECTS:
            if len(m.PROJECT_PERIOD_ONLINE_BUILD_YRS[proj, m.tp_period[t]]) > 0:
                active_projects.add(proj)
        return active_projects
    mod.PROJECTS_ACTIVE_IN_TIMEPOINT = Set(
        mod.TIMEPOINTS,
        within=mod.PROJECTS,
        initialize=init_projects_active_in_timepoints)
    def init_dispatch_timepoints(m):
        dispatch_timepoints = set() # could technically be a list
        proj_op_periods = set()     # used to avoid duplicating effort
        for (proj, bld_yr) in m.PROJECT_BUILDYEARS:
            for period in m.PROJECT_BUILDS_OPERATIONAL_PERIODS[proj, bld_yr]:
                if (proj, period) not in proj_op_periods:
                    proj_op_periods.add((proj, period))
                    for t in m.PERIOD_TPS[period]:
                        dispatch_timepoints.add((proj, t))
        return dispatch_timepoints
    mod.PROJ_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=init_dispatch_timepoints)
    mod.ProjCapacityTP = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: m.ProjCapacity[proj, m.tp_period[t]])
    mod.DispatchProj = Var(
        mod.PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.LZ_NetDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, lz, t: sum(
            m.DispatchProj[p, t] for p in m.LZ_PROJECTS[lz]
            if (p, t) in m.PROJ_DISPATCH_POINTS))
    # Register net dispatch as contributing to a load zone's energy
    mod.LZ_Energy_Components_Produce.append('LZ_NetDispatch')

    # The next few parameters can be set to project-specific values if
    # they were given and otherwise will default to generic technology-
    # specific values if those were given. Throw an error if no data
    # source was provided.
    def proj_full_load_heat_rate_default_rule(m, pr):
        g = m.proj_gen_tech[pr]
        if g in m.g_full_load_heat_rate:
            return m.g_full_load_heat_rate[g]
        else:
            raise ValueError(
                ("Project {} uses a fuel, but there is no heat rate " +
                 "specified for this project or its generation technology " +
                 "{}.").format(pr, m.proj_gen_tech[pr]))
    mod.proj_full_load_heat_rate = Param(
        mod.FUEL_BASED_PROJECTS,
        within=PositiveReals,
        default=proj_full_load_heat_rate_default_rule)

    def proj_forced_outage_rate_default_rule(m, pr):
        g = m.proj_gen_tech[pr]
        if g in m.g_forced_outage_rate:
            return m.g_forced_outage_rate[g]
        else:
            raise ValueError(
                ("No data found for proj_forced_outage_rate for project {}" +
                 "; neither project-specific data nor technology-specific " +
                 "data was provided (tech={})."
                 ).format(pr, m.proj_gen_tech[pr]))
    mod.proj_forced_outage_rate = Param(
        mod.PROJECTS,
        within=PercentFraction,
        default=proj_forced_outage_rate_default_rule)

    def proj_scheduled_outage_rate_default_rule(m, pr):
        g = m.proj_gen_tech[pr]
        if g in m.g_scheduled_outage_rate:
            return m.g_scheduled_outage_rate[g]
        else:
            raise ValueError(
                ("No data found for proj_scheduled_outage_rate for project " +
                 "{}; neither project-specific data nor technology-specific " +
                 "data was provided (tech={})."
                 ).format(pr, m.proj_gen_tech[pr]))
    mod.proj_scheduled_outage_rate = Param(
        mod.PROJECTS,
        within=PercentFraction,
        default=proj_scheduled_outage_rate_default_rule)

    def init_proj_availability(model, proj):
        tech = model.proj_gen_tech[proj]
        if(model.g_is_baseload[tech] or
           model.g_is_flexible_baseload[tech]):
            return (
                (1 - model.proj_forced_outage_rate[proj]) *
                (1 - model.proj_scheduled_outage_rate[proj]))
        else:
            return (1 - model.proj_forced_outage_rate[proj])
    mod.proj_availability = Param(
        mod.PROJECTS,
        within=PositiveReals,
        initialize=init_proj_availability)

    mod.VAR_DISPATCH_POINTS = Set(
        initialize=mod.PROJ_DISPATCH_POINTS,
        filter=lambda m, proj, t: proj in m.VARIABLE_PROJECTS)
    mod.proj_max_capacity_factor = Param(
        mod.VAR_DISPATCH_POINTS,
        within=Reals,
        validate=lambda m, val, proj, t: -1 < val < 2)
    mod.min_data_check('proj_max_capacity_factor')

    mod.proj_variable_om = Param(
        mod.PROJECTS,
        within=NonNegativeReals,
        default=lambda m, proj: (
            m.g_variable_o_m[m.proj_gen_tech[proj]] *
            m.lz_cost_multipliers[m.proj_load_zone[proj]]))
    mod.PROJ_WITH_FUEL_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: 
            ((p, t) for p in m.FUEL_BASED_PROJECTS for t in m.TIMEPOINTS 
                if (p, t) in m.PROJ_DISPATCH_POINTS))
    # NOTE: below is another way to build PROJ_WITH_FUEL_DISPATCH_POINTS:
    # mod.PROJ_WITH_FUEL_DISPATCH_POINTS = Set(
    #     initialize=mod.PROJ_DISPATCH_POINTS,
    #     filter=lambda m, p, t: m.g_uses_fuel[m.proj_gen_tech[p]])
    mod.PROJ_FUEL_DISPATCH_POINTS = Set(
        dimen=3,
        initialize=lambda m: (
            (p, t, f) for (p, t) in m.PROJ_WITH_FUEL_DISPATCH_POINTS 
                    for f in m.G_FUELS[m.proj_gen_tech[p]]))
    mod.ProjFuelUseRate = Var(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        within=NonNegativeReals)

    def DispatchEmissions_rule(m, proj, t, f):
        g = m.proj_gen_tech[proj]
        if g not in m.GEN_TECH_CCS:
            return (
                m.ProjFuelUseRate[proj, t, f] *
                (m.f_co2_intensity[f] - m.f_upstream_co2_intensity[f]))
        else:
            ccs_emission_frac = 1 - m.g_ccs_capture_efficiency[g]
            return (
                m.ProjFuelUseRate[proj, t, f] *
                (m.f_co2_intensity[f] * ccs_emission_frac -
                 m.f_upstream_co2_intensity[f]))
    mod.DispatchEmissions = Expression(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        rule=DispatchEmissions_rule)

    mod.Proj_Var_Costs_Hourly = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] * m.proj_variable_om[proj]))
    # An expression to summarize costs for the objective function. Units
    # should be total future costs in $base_year real dollars. The
    # objective function will convert these to base_year Net Present
    # Value in $base_year real dollars.
    mod.Total_Proj_Var_Costs_Hourly = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.Proj_Var_Costs_Hourly[proj, t]
            for proj in m.PROJECTS_ACTIVE_IN_TIMEPOINT[t]))
    mod.cost_components_tp.append('Total_Proj_Var_Costs_Hourly')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import project-specific data from an input directory.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.tab
        PROJECT, timepoint, proj_max_capacity_factor

    project_info.tab is used by project.build and project.dispatch. The
    columns listed here are optional because they override values given
    by descriptions of generation technologies. Every project needs to
    have this data provided, but you get to decide what to specify by
    technology and what to specify by project. You may either drop data
    columns or put a dot . to mark "no data" for certain rows. Note:
    Load-zone cost adjustments will not be applied to any project-
    specific costs.

    project_info.tab
        PROJECT, proj_variable_om, proj_full_load_heat_rate,
        proj_forced_outage_rate, proj_scheduled_outage_rate

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'variable_capacity_factors.tab'),
        select=('PROJECT', 'timepoint', 'proj_max_capacity_factor'),
        param=(mod.proj_max_capacity_factor))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'project_info.tab'),
        auto_select=True,
        param=(mod.proj_variable_om, mod.proj_full_load_heat_rate,
               mod.proj_forced_outage_rate, mod.proj_scheduled_outage_rate))


def post_solve(instance, outdir):
    """
    Default export of project dispatch per timepoint in tabular format.

    """
    import switch_mod.export as export
    export.write_table(
        instance, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "dispatch.txt"),
        headings=("timestamp",)+tuple(instance.PROJECTS),
        values=lambda m, t: (m.tp_timestamp[t],) + tuple(
            m.DispatchProj[p, t] if (p, t) in m.PROJ_DISPATCH_POINTS
            else 0.0
            for p in m.PROJECTS
        )
    )
