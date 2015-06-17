"""

Defines model components to describe generation projects build-outs for
the SWITCH-Pyomo model. This module requires either project.unitcommit or
project.no_commit to constrain project dispatch to either committed or
installed capacity.

SYNOPSIS
>>> import switch_mod.utilities as utilities
>>> switch_modules = ('timescales', 'financials', 'load_zones', 'fuels',\
    'gen_tech', 'project.build', 'project.dispatch')
>>> utilities.load_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest project/dispatch.py`
within the switch_mod source directory.

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

import os
from pyomo.environ import *
import switch_mod.utilities as utilities


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
    by a project in a timepoint. This will need to have another index of
    energy_source to fully support generators that use multiple fuels.

    proj_availability[prj] describes the fraction of a time a project is
    expected to be available. This is derived from the forced and
    scheduled outage rates of generation technologies. For baseload or
    flexible baseload, this is determined from both forced and scheduled
    outage rates. For all other types of generation technologies, we
    assume the scheduled outages can be performed when the generators
    were not scheduled to produce power, so their availability is only
    derated based on their forced outage rates.

    prj_max_capacity_factor[prj, t] is defined for variable renewable
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

    Proj_Var_Costs_Hourly[t in TIMEPOINTS] is the sum of all variable
    costs associated with project dispatch for each timepoint expressed
    in $base_year/hour in the future period (rather than Net Present
    Value).

    PROJ_FUEL_DISPATCH_POINTS is a subset of PROJ_DISPATCH_POINTS
    for projects that consume fuel and could produce emissions.

    ConsumeFuelProj[(proj, t) in PROJ_FUEL_DISPATCH_POINTS] is a
    variable that describes fuel consumption rate in MMBTU/h. This
    should be constrained to the fuel consumed by a project in each
    timepoint and can be calculated as Dispatch [MW] *
    effective_heat_rate [MMBTU/MWh] -> [MMBTU/h]. The choice of how to
    constrain it depends on the treatment of unit commitment. Currently
    the project.no_commit module implements a simple treatment that
    ignores unit commitment and assumes a full load heat rate, while the
    project.unitcommit module implements unit commitment decisions with
    startup fuel requirements and a marginal heat rate.

    DispatchEmissions[(proj, t) in PROJ_FUEL_DISPATCH_POINTS] is the
    emissions produced by dispatching a fuel-based project in units of
    metric tonnes CO2 per hour. This is derived from the fuel
    consumption ConsumeFuelProj, the fuel's direct carbon intensity, the
    fuel's upstream emissions, as well as Carbon Capture efficiency for
    generators that implement Carbon Capture and Sequestration. This does
    not yet support multi-fuel generators.

    --- Delayed implementation ---

    EmissionsInTimepoint[(proj, t) in PROJ_FUEL_DISPATCH_POINTS]
    is an expression that defines the emissions in each timepoint from
    dispatching a thermal generator.
        = DispatchProj * proj_emission_rate

    Flexible baseload support for plants that can ramp slowly over the
    course of days. These kinds of generators can provide important
    seasonal support in high renewable and low emission futures.

    Parasitic loads that make solar thermal plants consume energy from
    the grid on cold nights to keep their fluids from getting too cold.

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
    mod.PROJ_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=init_dispatch_timepoints)
    mod.ProjCapacityTP = Expression(
        mod.PROJ_DISPATCH_POINTS,
        initialize=lambda m, proj, t: m.ProjCapacity[proj, m.tp_period[t]])
    mod.DispatchProj = Var(
        mod.PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.LZ_NetDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        initialize=lambda m, lz, t: sum(
            m.DispatchProj[p, t] for p in m.LZ_PROJECTS[lz]
            if (p, t) in m.PROJ_DISPATCH_POINTS))
    # Register net dispatch as contributing to a load zone's energy
    mod.LZ_Energy_Balance_components.append('LZ_NetDispatch')

    def init_proj_availability(model, project):
        tech = model.proj_gen_tech[project]
        if(model.g_is_baseload[tech] or
           model.g_is_flexible_baseload[tech]):
            return (1 - model.g_forced_outage_rate[tech]) * (
                1 - model.g_scheduled_outage_rate[tech])
        else:
            return (1 - model.g_forced_outage_rate[tech])
    mod.proj_availability = Param(
        mod.PROJECTS,
        within=PositiveReals,
        initialize=init_proj_availability)

    mod.VAR_DISPATCH_POINTS = Set(
        initialize=mod.PROJ_DISPATCH_POINTS,
        filter=lambda m, proj, t: proj in m.VARIABLE_PROJECTS)
    mod.prj_max_capacity_factor = Param(
        mod.VAR_DISPATCH_POINTS,
        within=Reals,
        validate=lambda m, val, proj, t: -1 < val < 2)
    mod.min_data_check('prj_max_capacity_factor')

    mod.proj_variable_om = Param(
        mod.PROJECTS,
        within=NonNegativeReals,
        default=lambda m, proj: (
            m.g_variable_o_m[m.proj_gen_tech[proj]] *
            m.lz_cost_multipliers[m.proj_load_zone[proj]]))

    mod.PROJ_FUEL_DISPATCH_POINTS = Set(
        initialize=mod.PROJ_DISPATCH_POINTS,
        filter=lambda m, proj, t: proj in m.FUEL_BASED_PROJECTS)
    mod.ConsumeFuelProj = Var(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        within=NonNegativeReals)

    def DispatchEmissions_rule(m, proj, t):
        g = m.proj_gen_tech[proj]
        f = m.proj_fuel[proj]
        if g not in m.CCS_TECHNOLOGIES:
            return (
                m.ConsumeFuelProj[proj, t] *
                (m.f_co2_intensity[f] - m.f_upstream_co2_intensity[f]))
        else:
            ccs_emission_frac = 1 - m.g_ccs_capture_efficiency[g]
            return (
                m.ConsumeFuelProj[proj, t] *
                (m.f_co2_intensity[f] * ccs_emission_frac -
                 m.f_upstream_co2_intensity[f]))
    mod.DispatchEmissions = Expression(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        initialize=DispatchEmissions_rule)

    mod.Proj_Var_Costs_Hourly = Expression(
        mod.PROJ_DISPATCH_POINTS,
        initialize=lambda m, proj, t: (
            m.DispatchProj[proj, t] * m.proj_variable_om[proj]))
    # An expression to summarize costs for the objective function. Units
    # should be total future costs in $base_year real dollars. The
    # objective function will convert these to base_year Net Present
    # Value in $base_year real dollars.
    mod.Total_Proj_Var_Costs_Hourly = Expression(
        mod.TIMEPOINTS,
        initialize=lambda m, t: sum(
            m.Proj_Var_Costs_Hourly[proj, t]
            for (proj, t2) in m.PROJ_DISPATCH_POINTS
            if t == t2))
    mod.cost_components_tp.append('Total_Proj_Var_Costs_Hourly')


def load_data(mod, switch_data, inputs_dir):
    """

    Import project-specific data from an input directory. Both files are
    optional.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.tab
        PROJECT, timepoint, prj_capacity_factor

    proj_variable_costs optional and overrides generic costs for
    generators. Load-zone cost adjustments will not be applied to any
    costs specified in this file.

    proj_variable_costs.tab
        PROJECT, proj_variable_om

    """

    variable_capacity_factors_path = os.path.join(
        inputs_dir, 'variable_capacity_factors.tab')
    if os.path.isfile(variable_capacity_factors_path):
        switch_data.load(
            filename=variable_capacity_factors_path,
            select=('PROJECT', 'timepoint', 'prj_capacity_factor'),
            param=(mod.prj_max_capacity_factor))
    proj_variable_costs_path = os.path.join(
        inputs_dir, 'proj_variable_costs.tab')
    if os.path.isfile(proj_variable_costs_path):
        switch_data.load(
            filename=proj_variable_costs_path,
            select=('PROJECT', 'proj_variable_om'),
            param=(mod.proj_variable_om))
