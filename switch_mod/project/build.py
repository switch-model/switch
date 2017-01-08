# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines model components to describe generation projects build-outs for
the SWITCH-Pyomo model.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels',
...     'gen_tech', 'project.build')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *
from switch_mod.financials import capital_recovery_factor as crf


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe
    generation and storage projects. Unless otherwise stated, all power
    capacity is specified in units of MW and all sets and parameters
    are mandatory.

    PROJECTS is the set of generation and storage projects that have
    been built or could potentially be built. A project is a combination
    of generation technology, load zone and location. A particular
    build-out of a project should also include the year in which
    construction was complete and additional capacity came online.
    Members of this set are abbreviated as proj or prj in parameter
    names and indexes. Use of p instead of prj is discouraged because p
    is reserved for period.

    proj_dbid[prj] is an external database id for each project. This is
    an optional parameter than defaults to the project index.

    proj_gen_tech[prj] describes what kind of generation technology a
    projects is using.

    proj_load_zone[prj] is the load zone this project is built in.

    VARIABLE_PROJECTS is a subset of PROJECTS that only includes
    variable generators such as wind or solar that have exogenous
    constraints on their energy production.

    BASELOAD_PROJECTS is a subset of PROJECTS that only includes
    baseload generators such as coal or geothermal.

    LZ_PROJECTS[lz in LOAD_ZONES] is an indexed set that lists all
    projects within each load zone.

    PROJECTS_CAP_LIMITED is the subset of PROJECTS that are capacity
    limited. Most of these will be generator types that are resource
    limited like wind, solar or geothermal, but this can be specified
    for any project. Some existing or proposed projects may have upper
    bounds on increasing capacity or replacing capacity as it is retired
    based on permits or local air quality regulations.

    proj_capacity_limit_mw[proj] is defined for generation technologies
    that are resource limited and do not compete for land area. This
    describes the maximum possible capacity of a project in units of
    megawatts.

    -- CONSTRUCTION --

    PROJECT_BUILDYEARS is a two-dimensional set of projects and the
    years in which construction or expansion occured or can occur. You
    can think of a project as a physical site that can be built out over
    time. BuildYear is the year in which construction is completed and
    new capacity comes online, not the year when constrution begins.
    BuildYear will be in the past for existing projects and will be the
    first year of an investment period for new projects. Investment
    decisions are made for each project/invest period combination. This
    set is derived from other parameters for all new construction. This
    set also includes entries for existing projects that have already
    been built; information for legacy projects come from other files
    and their build years will usually not correspond to the set of
    investment periods. There are two recommended options for
    abbreviating this set for denoting indexes: typically this should be
    written out as (proj, build_year) for clarity, but when brevity is
    more important (prj, b) is acceptable.

    NEW_PROJ_BUILDYEARS is a subset of PROJECT_BUILDYEARS that only
    includes projects that have not yet been constructed. This is
    derived by joining the set of PROJECTS with the set of
    NEW_GENERATION_BUILDYEARS using generation technology.

    EXISTING_PROJ_BUILDYEARS is a subset of PROJECT_BUILDYEARS that
    only includes existing projects.

    proj_existing_cap[(proj, build_year) in EXISTING_PROJ_BUILDYEARS] is
    a parameter that describes how much capacity was built in the past
    for existing projects.

    BuildProj[proj, build_year] is a decision variable that describes
    how much capacity of a project to install in a given period. This also
    stores the amount of capacity that was installed in existing projects
    that are still online.

    ProjCapacity[proj, period] is an expression that returns the total
    capacity online in a given period. This is the sum of installed capacity
    minus all retirements.

    Max_Build_Potential[proj] is a constraint defined for each project
    that enforces maximum capacity limits for resource-limited projects.

        ProjCapacity <= proj_capacity_limit_mw

    proj_final_period[(proj, build_year) in PROJECT_BUILDYEARS] is the last
    investment period in the simulation that a given project build will
    be operated. It can either indicate retirement or the end of the
    simulation. This is derived from g_max_age.

    NEW_PROJ_WITH_MIN_BUILD_YEARS is the subset of NEW_PROJ_BUILDYEARS for
    which minimum capacity build-out constraints will be enforced.

    ProjCommitToMinBuild[proj, build_year] is a binary variable that indicates
    whether a project will build capacity in a period or not. If the model is
    committing to building capacity, then the minimum must be enforced.

    Enforce_Min_Build_Lower[proj, build_year]  and
    Enforce_Min_Build_Upper[proj, build_year] are a pair of constraints that
    force project build-outs to meet the minimum build requirements for
    generation technologies that have those requirements. They force BuildProj
    to be 0 when ProjCommitToMinBuild is 0, and to be greater than
    g_min_build_capacity when ProjCommitToMinBuild is 1. In the latter case,
    the upper constraint should be non-binding; the upper limit is set to 10
    times the peak non-conincident demand of the entire system.

    --- OPERATIONS ---

    PROJECT_BUILDS_OPERATIONAL_PERIODS[proj, build_year] is an indexed
    set that describes which periods a given project build will be
    operational.

    PROJECT_PERIOD_ONLINE_BUILD_YRS[proj, period] is a complementary
    indexed set that identify which build years will still be online
    for the given project in the given period. For some project-period
    combinations, this will be an empty set.

    PROJECT_OPERATIONAL_PERIODS describes periods in which projects
    could be operational. Unlike the related sets above, it is not
    indexed. Instead it is specified as a set of (proj, period)
    combinations useful for indexing other model components.


    --- COSTS ---

    proj_connect_cost_per_mw[prj] is the cost of grid upgrades to support a
    new project, in dollars per peak MW. These costs include new
    transmission lines to a substation, substation upgrades and any
    other grid upgrades that are needed to deliver power from the
    interconnect point to the load center or from the load center to the
    broader transmission network.

    The following cost components are defined for each project and build
    year. These parameters will always be available, but will typically
    be populated by the generic costs specified in generator costs
    inputs file and the load zone cost adjustment multipliers from
    load_zones inputs file.

    proj_overnight_cost[proj, build_year] is the overnight capital cost per
    MW of capacity for building a project in the given period. By
    "installed in the given period", I mean that it comes online at the
    beginning of the given period and construction starts before that.

    proj_fixed_om[proj, build_year] is the annual fixed Operations and
    Maintenance costs (O&M) per MW of capacity for given project that
    was installed in the given period.

    -- Derived cost parameters --

    proj_capital_cost_annual[proj, build_year] is the annualized loan
    payments for a project's capital and connection costs in units of
    $/MW per year. This is specified in non-discounted real dollars in a
    future period, not real dollars in net present value.

    Proj_Fixed_Costs_Annual[proj, period] is the total annual fixed
    costs (capital as well as fixed operations & maintenance) incurred
    by a project in a period. This reflects all of the builds are
    operational in the given period. This is an expression that reflect
    decision variables.

    Total_Proj_Fixed_Costs_Annual[period] is the sum of
    Proj_Fixed_Costs_Annual[proj, period] for all projects that could be
    online in the target period. This aggregation is performed for the
    benefit of the objective function.

    --- DELAYED IMPLEMENATION ---

    The following components are not implemented at this time.

    proj_energy_capacity_overnight_cost[proj, period] defaults to the
    generic costs of the energy component of a storage technology. It
    can be overridden if different projects have different cost
    components. For new CAES projects, this could easily be overridden
    based on whether an empty gas well was nearby that could be reused,
    whether the local geological conditions made it easy or difficult to
    drill and construct underground storage, or whether an above-ground
    pressurized vessel would be needed. For new battery projects, a
    generic cost would be completely sufficient.

    proj_replacement_id[prj] is defined for projects that could replace
    existing generators.

    LOCATIONS_WITH_COMPETITION is the set of locations that have limited
    land area where multiple projects can compete for space. Members of
    this set are abbreviated as either loc or a lowercase L "l" in
    parameter names and indexes.

    loc_area_km2[l] describes the land area available for development
    at a particular location in units of square kilometers.

    proj_location[prj] is only defined for projects that compete with each
    other for limited land space at a given location. It refers to a
    member of the set LOCATIONS_WITH_COMPETITION. For example, if solar
    thermal and solar PV projects were competing for the same parcel of
    land, they would need the same location id.

    proj_land_footprint_mw_km2[prj] describes the land footprint of a project
    in units of megawatts per square kilometer.

    Max_Build_Location[location] is a constraint defined for each project
    that enforces maximum capacity limits for resource-limited locations.

        sum(BuildProj/proj_land_footprint_mw_km2) <= loc_area_km2

    ccs_pipeline_cost_per_mw[proj, build_year] is the normalize cost of
    a ccs pipeline sized relative to a project's emissions intensity.

    Decommission[proj, build_year, period] is a decision variable that
    allows early retirement of portions of projects. Any portion of a
    project that is decomisssioned early will not incur fixed O&M
    costs and cannot be brought back into service in later periods.

    NameplateCapacity[proj, build_year, period] is an expression that
    describes the amount of capacity available from a particular project
    build in a given period. This takes into account any decomissioning
    that occured.

        NameplateCapacity = BuildProj - sum(Decommission)

    """

    mod.PROJECTS = Set()
    mod.proj_dbid = Param(mod.PROJECTS, default=lambda m, proj: proj)
    mod.proj_gen_tech = Param(mod.PROJECTS, within=mod.GENERATION_TECHNOLOGIES)
    mod.proj_load_zone = Param(mod.PROJECTS, within=mod.LOAD_ZONES)
    mod.min_data_check('PROJECTS', 'proj_gen_tech', 'proj_load_zone')
    mod.VARIABLE_PROJECTS = Set(
        initialize=mod.PROJECTS,
        filter=lambda m, proj: (
            m.g_is_variable[m.proj_gen_tech[proj]]))
    mod.BASELOAD_PROJECTS = Set(
        initialize=mod.PROJECTS,
        filter=lambda m, proj: (
            m.g_is_baseload[m.proj_gen_tech[proj]]))
    mod.LZ_PROJECTS = Set(
        mod.LOAD_ZONES,
        initialize=lambda m, lz: set(
            p for p in m.PROJECTS if m.proj_load_zone[p] == lz))
    mod.PROJECTS_CAP_LIMITED = Set(within=mod.PROJECTS)
    mod.proj_capacity_limit_mw = Param(
        mod.PROJECTS_CAP_LIMITED,
        within=PositiveReals)
    # Add PROJECTS_LOCATION_LIMITED & associated stuff later

    mod.FUEL_BASED_PROJECTS = Set(
        initialize=mod.PROJECTS,
        filter=lambda m, pr: m.g_uses_fuel[m.proj_gen_tech[pr]])
    mod.NON_FUEL_BASED_PROJECTS = Set(
        initialize=mod.PROJECTS,
        filter=lambda m, pr: not m.g_uses_fuel[m.proj_gen_tech[pr]])

    def init_proj_buildyears(m):
        project_buildyears = set()
        for proj in m.PROJECTS:
            g = m.proj_gen_tech[proj]
            for b in m.G_NEW_BUILD_YEARS[g]:
                project_buildyears.add((proj, b))
        return project_buildyears
    mod.NEW_PROJ_BUILDYEARS = Set(
        dimen=2,
        initialize=init_proj_buildyears)
    mod.EXISTING_PROJ_BUILDYEARS = Set(
        dimen=2)
    mod.proj_existing_cap = Param(
        mod.EXISTING_PROJ_BUILDYEARS,
        within=NonNegativeReals)
    mod.min_data_check('proj_existing_cap')
    mod.PROJECT_BUILDYEARS = Set(
        dimen=2,
        initialize=lambda m: set(
            m.EXISTING_PROJ_BUILDYEARS | m.NEW_PROJ_BUILDYEARS))

    def init_proj_final_period(m, proj, build_year):
        g = m.proj_gen_tech[proj]
        max_age = m.g_max_age[g]
        earliest_study_year = m.period_start[m.PERIODS.first()]
        if build_year + max_age < earliest_study_year:
            return build_year + max_age
        for p in m.PERIODS:
            if build_year + max_age <= m.period_start[p] + m.period_length_years[p]:
                break
        return p
    mod.proj_final_period = Param(
        mod.PROJECT_BUILDYEARS,
        initialize=init_proj_final_period)
    mod.min_data_check('proj_final_period')

    mod.PROJECT_BUILDS_OPERATIONAL_PERIODS = Set(
        mod.PROJECT_BUILDYEARS,
        within=mod.PERIODS,
        ordered=True,
        initialize=lambda m, proj, bld_yr: set(
            p for p in m.PERIODS
            if bld_yr <= p <= m.proj_final_period[proj, bld_yr]))
    # The set of build years that could be online in the given period
    # for the given project.
    mod.PROJECT_PERIOD_ONLINE_BUILD_YRS = Set(
        mod.PROJECTS, mod.PERIODS,
        initialize=lambda m, proj, p: set(
            bld_yr for (prj, bld_yr) in m.PROJECT_BUILDYEARS
            if prj == proj and bld_yr <= p <= m.proj_final_period[proj, bld_yr]))

    def bounds_BuildProj(model, proj, bld_yr):
        if((proj, bld_yr) in model.EXISTING_PROJ_BUILDYEARS):
            return (model.proj_existing_cap[proj, bld_yr],
                    model.proj_existing_cap[proj, bld_yr])
        elif(proj in model.PROJECTS_CAP_LIMITED):
            # This does not replace Max_Build_Potential because
            # Max_Build_Potential applies across all build years.
            return (0, model.proj_capacity_limit_mw[proj])
        else:
            return (0, None)
    mod.BuildProj = Var(
        mod.PROJECT_BUILDYEARS,
        within=NonNegativeReals,
        bounds=bounds_BuildProj)
    # Some projects are retired before the first study period, so they
    # don't appear in the objective function or any constraints. 
    # In this case, pyomo may leave the variable value undefined even 
    # after a solve, instead of assigning a value within the allowed
    # range. This causes errors in the Progressive Hedging code, which
    # expects every variable to have a value after the solve. So as a 
    # starting point we assign an appropriate value to all the existing 
    # projects here.
    def BuildProj_assign_default_value(m, proj, bld_yr):
        m.BuildProj[proj, bld_yr] = m.proj_existing_cap[proj, bld_yr]
    mod.BuildProj_assign_default_value = BuildAction(
        mod.EXISTING_PROJ_BUILDYEARS,
        rule=BuildProj_assign_default_value
    )

    # To Do: Subtract retirements after I write support for that.
    mod.ProjCapacity = Expression(
        mod.PROJECTS, mod.PERIODS,
        rule=lambda m, proj, period: sum(
            m.BuildProj[proj, bld_yr]
            for bld_yr in m.PROJECT_PERIOD_ONLINE_BUILD_YRS[proj, period]))

    mod.Max_Build_Potential = Constraint(
        mod.PROJECTS_CAP_LIMITED, mod.PERIODS,
        rule=lambda m, proj, p: (
            m.proj_capacity_limit_mw[proj] >= m.ProjCapacity[proj, p]))

    # The following components enforce minimum capacity build-outs.
    # Note that this adds binary variables to the model.
    mod.NEW_PROJ_WITH_MIN_BUILD_YEARS = Set(
        initialize=mod.NEW_PROJ_BUILDYEARS,
        filter=lambda m, pr, p: (
            m.g_min_build_capacity[m.proj_gen_tech[pr]] > 0))
    mod.ProjCommitToMinBuild = Var(
        mod.NEW_PROJ_WITH_MIN_BUILD_YEARS, within=Binary)
    mod.Enforce_Min_Build_Lower = Constraint(
        mod.NEW_PROJ_WITH_MIN_BUILD_YEARS,
        rule=lambda m, proj, p: (
            m.ProjCommitToMinBuild[proj, p] *
            m.g_min_build_capacity[m.proj_gen_tech[proj]] <=
            m.BuildProj[proj, p]))
    mod.Enforce_Min_Build_Upper = Constraint(
        mod.NEW_PROJ_WITH_MIN_BUILD_YEARS,
        rule=lambda m, proj, p: (
            m.BuildProj[proj, p] <=
            m.ProjCommitToMinBuild[proj, p] * 10 * 
            sum(m.lz_peak_demand_mw[lz, p]
                for lz in m.LOAD_ZONES)))

    # Costs
    mod.proj_connect_cost_per_mw = Param(mod.PROJECTS, within=NonNegativeReals)
    mod.min_data_check('proj_connect_cost_per_mw')

    # The next few parameters need values, but those can come from
    # their parent technology or this specific project. If neither
    # data source was provided, throw an error.
    def proj_overnight_cost_default_rule(m, proj, bld_yr):
        g = m.proj_gen_tech[proj]
        if (g, bld_yr) in m.g_overnight_cost:
            return(m.g_overnight_cost[g, bld_yr] *
                   m.lz_cost_multipliers[m.proj_load_zone[proj]])
        else:
            raise ValueError(
                ("No overnight costs were provided for project {} " +
                 "or its generation technology {}.").format(proj, g))
    mod.proj_overnight_cost = Param(
        mod.PROJECT_BUILDYEARS,
        within=NonNegativeReals,
        default=proj_overnight_cost_default_rule)

    def proj_fixed_om_default_rule(m, proj, bld_yr):
        g = m.proj_gen_tech[proj]
        if (g, bld_yr) in m.g_fixed_o_m:
            return(m.g_fixed_o_m[g, bld_yr] *
                   m.lz_cost_multipliers[m.proj_load_zone[proj]])
        else:
            raise ValueError(
                ("No fixed O & M costs were provided for project {} " +
                 "or its generation technology {}.").format(proj, g))
    mod.proj_fixed_om = Param(
        mod.PROJECT_BUILDYEARS,
        within=NonNegativeReals,
        default=proj_fixed_om_default_rule)
    # Derived annual costs
    mod.proj_capital_cost_annual = Param(
        mod.PROJECT_BUILDYEARS,
        initialize=lambda m, proj, bld_yr: (
            (m.proj_overnight_cost[proj, bld_yr] +
                m.proj_connect_cost_per_mw[proj]) *
            crf(m.interest_rate, m.g_max_age[m.proj_gen_tech[proj]])))

    mod.PROJECT_OPERATIONAL_PERIODS = Set(
        dimen=2,
        initialize=lambda m: set(
            (proj, p)
            for (proj, bld_yr) in m.PROJECT_BUILDYEARS
            for p in m.PROJECT_BUILDS_OPERATIONAL_PERIODS[proj, bld_yr]))
    mod.Proj_Fixed_Costs_Annual = Expression(
        mod.PROJECT_OPERATIONAL_PERIODS,
        rule=lambda m, proj, p: sum(
            m.BuildProj[proj, bld_yr] *
            (m.proj_capital_cost_annual[proj, bld_yr] +
             m.proj_fixed_om[proj, bld_yr])
            for (prj, bld_yr) in m.PROJECT_BUILDYEARS
            if (p in m.PROJECT_BUILDS_OPERATIONAL_PERIODS[prj, bld_yr] and
                proj == prj)))
    # Summarize costs for the objective function. Units should be total
    # annual future costs in $base_year real dollars. The objective
    # function will convert these to base_year Net Present Value in
    # $base_year real dollars.
    mod.Total_Proj_Fixed_Costs_Annual = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.Proj_Fixed_Costs_Annual[proj, p]
            for (proj, period) in m.PROJECT_OPERATIONAL_PERIODS
            if p == period))
    mod.cost_components_annual.append('Total_Proj_Fixed_Costs_Annual')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import data describing project builds. The following files are
    expected in the input directory.

    project_info.tab has mandatory and optional columns. The
    project.dispatch module will also look for additional columns in
    this file. You may drop optional columns entirely or mark blank
    values with a dot '.' for select rows for which the column does not
    apply. Mandatory columns are:
        PROJECT, proj_gen_tech, proj_load_zone, proj_connect_cost_per_mw
    Optional columns are:
        proj_dbid, proj_capacity_limit_mw

    The proj_capacity_limit_mw column is optional because some systems
    will not have capacity limited projects.

    The following file lists existing builds of projects, and is
    optional:

    proj_existing_builds.tab
        PROJECT, build_year, proj_existing_cap

    The following file is optional because it override generic values
    given by descriptions of generation technologies. Note: Load-zone
    cost adjustments will not be applied to any costs specified in
    proj_build_costs.tab.

    proj_build_costs.tab
        PROJECT, build_year, proj_overnight_cost, proj_fixed_om

    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'project_info.tab'),
        auto_select=True,
        optional_params=['proj_capacity_limit_mw'],
        index=mod.PROJECTS,
        param=(mod.proj_dbid, mod.proj_gen_tech,
               mod.proj_load_zone, mod.proj_connect_cost_per_mw,
               mod.proj_capacity_limit_mw))
    # Make a list of projects that have capacity limits specified.
    if 'proj_capacity_limit_mw' in switch_data.data():
        switch_data.data()['PROJECTS_CAP_LIMITED'] = {
            None: switch_data.data(name='proj_capacity_limit_mw').keys()
        }
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'proj_existing_builds.tab'),
        select=('PROJECT', 'build_year', 'proj_existing_cap'),
        index=mod.EXISTING_PROJ_BUILDYEARS,
        param=(mod.proj_existing_cap))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'proj_build_costs.tab'),
        select=('PROJECT', 'build_year',
                'proj_overnight_cost', 'proj_fixed_om'),
        param=(mod.proj_overnight_cost, mod.proj_fixed_om))
