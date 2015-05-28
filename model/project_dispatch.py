"""

Defines model components to describe generation projects build-outs for
the SWITCH-Pyomo model.

SYNOPSIS
>>> from coopr.pyomo import *
>>> import timescales
>>> import financials
>>> import load_zones
>>> import fuels
>>> import gen_tech
>>> import project_build
>>> import project_dispatch
>>> switch_model = AbstractModel()
>>> timescales.define_components(switch_model)
>>> financials.define_components(switch_model)
>>> load_zones.define_components(switch_model)
>>> fuels.define_components(switch_model)
>>> gen_tech.define_components(switch_model)
>>> project_build.define_components(switch_model)
>>> project_dispatch.define_components(switch_model)
>>> switch_data = DataPortal(model=switch_model)
>>> inputs_dir = 'test_dat'
>>> timescales.load_data(switch_model, switch_data, inputs_dir)
>>> financials.load_data(switch_model, switch_data, inputs_dir)
>>> load_zones.load_data(switch_model, switch_data, inputs_dir)
>>> fuels.load_data(switch_model, switch_data, inputs_dir)
>>> gen_tech.load_data(switch_model, switch_data, inputs_dir)
>>> project_build.load_data(switch_model, switch_data, inputs_dir)
>>> project_dispatch.load_data(switch_model, switch_data, inputs_dir)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest -v project_dispatch.py`

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

import os
from coopr.pyomo import *
import utilities


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe the
    dispatch decisions and constraints of generation and storage
    projects. Unless otherwise stated, all power capacity is specified
    in units of MW and all sets and parameters are mandatory.

    DISPATCH_TIMEPOINTS is a set of project builds and timepoints in
    which they can be dispatched. This set will not include timepoints
    that occur after a project build has reached the end of its life. A
    dispatch decisions is made for each member of this set: project,
    build_year and timepoint. Members of this set can be abbreviated as
    (proj, t) or (prj, t).

    DispatchProj[(proj, t) in DISPATCH_TIMEPOINTS] is the set
    of generation dispatch decisions: how much average power in MW to
    produce in each timepoint. This value can be multiplied by the
    duration of the timepoint in hours to determine the energy produced
    by a project in a timepoint. This will need to have another index of
    energy_source to fully support generators that use multiple fuels.

    proj_availability[prj] describes the fraction of a time a project is
    expected to be running. This is derived from the forced and
    scheduled outage rates of generation technologies. For baseload or
    flexible baseload, this is determined from both forced and scheduled
    outage rates. For all other types of generation technologies, we
    assume the scheduled outages can be performed when the generators
    were not scheduled to produce power, so their availability is only
    derated based on their forced outage rates.

    FLEXIBLE_DISPATCH_TIMEPOINTS is a subset of DISPATCH_TIMEPOINTS that
    is not baseload or variable generators.

    Dispatch_Capacity_Limit[(proj, t) in FLEXIBLE_DISPATCH_TIMEPOINTS]
    constraints DispatchProj to stay under the installed capacity after
    derating for maintenance. This constraint does not apply to baseload
    or variable renewable projects because they have different and more
    restrictive constraints.

        DispatchProj <= BuildProj * proj_availability

    BASELOAD_DISPATCH_TIMEPOINTS is a subset of DISPATCH_TIMEPOINTS
    that is limited to baseload generators.

    Dispatch_as_Baseload[(proj, t) in BASELOAD_DISPATCH_TIMEPOINTS]
    constraints DispatchProj for baseload plants to stay equal to the
    installed capacity after derating for maintenance.

        DispatchProj = BuildProj * proj_availability

    VAR_DISPATCH_TIMEPOINTS is a subset of DISPATCH_TIMEPOINTS
    that is limited to variable renewable generators.

    prj_capacity_factor[prj, t] is defined for variable renewable
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

    Variable_Gen_Limit[(prj, t) in VAR_DISPATCH_TIMEPOINTS] is
    a set of constraints that enforces the maximum power available from
    a variable generator in a given timepoint.

        DispatchProj <= prj_capacity_factor * BuildProj * proj_availability

    proj_variable_om[proj] is the variable Operations and Maintenance
    costs (O&M) per MWh of dispatched capacity for a given project.

    --- Delayed implementation ---

    THERMAL_DISPATCH_TIMEPOINTS is a subset of DISPATCH_TIMEPOINTS
    that is limited to thermal generators that could produce emissions.

    EmissionsInTimepoint[(proj, t) in THERMAL_DISPATCH_TIMEPOINTS]
    is an expression that defines the emissions in each timepoint from
    dispatching a thermal generator.
        = DispatchProj * proj_emission_rate

    Flexible baseload support for plants that can ramp slowly over the
    course of days. These kinds of generators can provide important
    seasonal support in high renewable and low emission futures.

    Storage support.

    Hybrid project support (pumped hydro & CAES) will eventually get
    implemented in separate modules.

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    # I might be able to simplify this, but the current formulation
    # should exclude any timepoints in periods in which a project will
    # definitely be retired.
    def init_dispatch_timepoints(m):
        dispatch_timepoints = set()
        for (proj, bld_yr) in m.PROJECT_BUILDYEARS:
            for period in m.PROJECT_BUILDS_OPERATIONAL_PERIODS[proj, bld_yr]:
                for t in m.TIMEPOINTS:
                    if(m.tp_period[t] == period):
                        dispatch_timepoints.add((proj, t))
        return dispatch_timepoints
    mod.DISPATCH_TIMEPOINTS = Set(
        dimen=2,
        initialize=init_dispatch_timepoints)

    mod.DispatchProj = Var(
        mod.DISPATCH_TIMEPOINTS,
        within=NonNegativeReals)
    mod.LZ_NetDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        initialize=lambda m, lz, tp: sum(
            m.DispatchProj[p, tp] for p in m.LZ_PROJECTS[lz]
            if (p, tp) in mod.DISPATCH_TIMEPOINTS))
    # Register net dispatch as contributing to a load zone's energy
    mod.LZ_Energy_Balance_components.append('LZ_NetDispatch')

    def init_proj_availability(model, project):
        tech = model.proj_gen_tech[project]
        if(model.g_is_baseload[tech] or
           model.g_is_flexible_baseload[tech]):
            return (1 - model.g_forced_outage_rate[tech]) * (
                1-model.g_scheduled_outage_rate[tech])
        else:
            return (1-model.g_forced_outage_rate[tech])
    mod.proj_availability = Param(
        mod.PROJECTS,
        within=PositiveReals,
        initialize=init_proj_availability)

    mod.BASELOAD_DISPATCH_TIMEPOINTS = Set(
        dimen=2,
        initialize=mod.DISPATCH_TIMEPOINTS,
        filter=lambda m, proj, t: (
            m.g_is_baseload[m.proj_gen_tech[proj]]))
    mod.VAR_DISPATCH_TIMEPOINTS = Set(
        dimen=2,
        initialize=mod.DISPATCH_TIMEPOINTS,
        filter=lambda m, proj, t: (
            m.g_is_variable[m.proj_gen_tech[proj]]))
    mod.FLEXIBLE_DISPATCH_TIMEPOINTS = Set(
        dimen=2,
        initialize=lambda m: set(
            m.DISPATCH_TIMEPOINTS - m.BASELOAD_DISPATCH_TIMEPOINTS -
            m.VAR_DISPATCH_TIMEPOINTS))
    mod.Dispatch_Capacity_Limit = Constraint(
        mod.FLEXIBLE_DISPATCH_TIMEPOINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] <=
            m.ProjCapacity[proj, m.tp_period[t]] *
            m.proj_availability[proj]))
    mod.Dispatch_as_Baseload = Constraint(
        mod.BASELOAD_DISPATCH_TIMEPOINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] ==
            m.ProjCapacity[proj, m.tp_period[t]] *
            m.proj_availability[proj]))
    mod.prj_capacity_factor = Param(
        mod.VAR_DISPATCH_TIMEPOINTS,
        within=Reals,
        validate=lambda m, val, proj, t: -1 < val < 2)
    mod.min_data_check('prj_capacity_factor')
    mod.Variable_Gen_Limit = Constraint(
        mod.VAR_DISPATCH_TIMEPOINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] <=
            m.ProjCapacity[proj, m.tp_period[t]] *
            m.proj_availability[proj] * m.prj_capacity_factor[proj, t]))

    mod.proj_variable_om = Param(
        mod.PROJECTS,
        within=NonNegativeReals,
        default=lambda m, proj, bld_yr: (
            m.g_variable_o_m[m.proj_gen_tech[proj], bld_yr] *
            m.lz_cost_multipliers[m.proj_load_zone[proj]]))


def load_data(mod, switch_data, inputs_dir):
    """

    Import project-specific data. The following files are expected in
    the input directory:

    variable_capacity_factors.tab
        PROJECT, timepoint, prj_capacity_factor

    The next file is optional and overrides generic costs for
    generators. Load-zone cost adjustments will not be applied to any
    costs specified in this file.

    proj_variable_costs.tab
        PROJECT, proj_variable_om

    """

    switch_data.load(
        filename=os.path.join(inputs_dir, 'variable_capacity_factors.tab'),
        select=('PROJECT', 'timepoint', 'prj_capacity_factor'),
        param=(mod.prj_capacity_factor))
    proj_variable_costs_path = os.path.join(
        inputs_dir, 'proj_variable_costs.tab')
    if os.path.isfile(proj_variable_costs_path):
        switch_data.load(
            filename=proj_variable_costs_path,
            select=('PROJECT', 'proj_variable_om'),
            param=(mod.proj_variable_om))
