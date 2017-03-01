# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe generation projects build-outs for
the SWITCH-Pyomo model. This module requires either operations.unitcommit or
operations.no_commit to constrain project dispatch to either committed or
installed capacity.

"""

import os, collections
from pyomo.environ import *

dependencies = 'switch_mod.timescales', 'switch_mod.balancing.load_zones',\
    'switch_mod.financials', 'switch_mod.energy_sources.properties.properties', \
    'switch_mod.generators.core.build'

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
    
    PROJ_ACTIVE_PERIODS is a set array showing all periods when each 
    project is active (within the build -> retire window for existing or 
    new capacity). This is an efficient way to find active periods for an 
    individual project.
    
    PROJ_ACTIVE_TIMEPOINTS is a set array showing all timepoints when a 
    project is active. These are the timepoints corresponding to 
    PROJ_ACTIVE_PERIODS. This is the same data as PROJ_DISPATCH_POINTS, 
    but split into separate sets for each project.

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
    
    AnnualEmissions[p in PERIODS]:The system's annual emissions, in metric
    tonnes of CO2 per year.

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

    mod.ACTIVE_PROJ_PERIODS = Set(dimen=2, initialize=lambda m: {
        (proj, per)
            for proj, bld_yr in m.PROJECT_BUILDYEARS
                for per in m.PROJECT_BUILDS_OPERATIONAL_PERIODS[proj, bld_yr]
    })

    def period_active_proj_rule(m, per):
        if not hasattr(m, 'period_active_proj_dict'):
            m.period_active_proj_dict = collections.defaultdict(set)
            for (_proj, _per) in m.ACTIVE_PROJ_PERIODS:
                m.period_active_proj_dict[_per].add(_proj)
        result = m.period_active_proj_dict.pop(per)
        if len(m.period_active_proj_dict) == 0:
            delattr(m, 'period_active_proj_dict')
        return result
    mod.PERIOD_ACTIVE_PROJ = Set(
        mod.PERIODS, 
        initialize=period_active_proj_rule)
    
    def proj_active_periods_rule(m, proj):
        if not hasattr(m, 'proj_active_periods_dict'):
            m.proj_active_periods_dict = collections.defaultdict(set)
            for (_proj, _per) in m.ACTIVE_PROJ_PERIODS:
                m.proj_active_periods_dict[_proj].add(_per)
        result = m.proj_active_periods_dict.pop(proj)
        if len(m.proj_active_periods_dict) == 0:
            delattr(m, 'proj_active_periods_dict')
        return result
    mod.PROJ_ACTIVE_PERIODS = Set(
        mod.PROJECTS, 
        initialize=proj_active_periods_rule)

    mod.PROJ_ACTIVE_TIMEPOINTS = Set(mod.PROJECTS, initialize=lambda m, proj: (
        tp for per in m.PROJ_ACTIVE_PERIODS[proj] for tp in m.PERIOD_TPS[per]))

    mod.PROJ_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (proj, tp) 
                for proj in m.PROJECTS 
                    for tp in m.PROJ_ACTIVE_TIMEPOINTS[proj]))
    mod.VAR_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (proj, tp) 
                for proj in m.VARIABLE_PROJECTS
                    for tp in m.PROJ_ACTIVE_TIMEPOINTS[proj]))
    mod.PROJ_WITH_FUEL_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (proj, tp) 
                for proj in m.FUEL_BASED_PROJECTS
                    for tp in m.PROJ_ACTIVE_TIMEPOINTS[proj]))
    mod.PROJ_FUEL_DISPATCH_POINTS = Set(
        dimen=3,
        initialize=lambda m: (
            (proj, t, f) 
                for (proj, t) in m.PROJ_WITH_FUEL_DISPATCH_POINTS 
                    for f in m.PROJ_FUELS[proj]))

    mod.ProjCapacityTP = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: m.ProjCapacity[proj, m.tp_period[t]])
    mod.DispatchProj = Var(
        mod.PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.LZ_NetDispatch = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=lambda m, lz, t: \
            sum(m.DispatchProj[p, t]
                for p in m.LZ_PROJECTS[lz]
                if (p, t) in m.PROJ_DISPATCH_POINTS) -
            sum(m.DispatchProj[p, t] * m.proj_ccs_energy_load[p]
                for p in m.LZ_PROJECTS[lz]
                if (p, t) in m.PROJ_DISPATCH_POINTS and p in m.PROJECTS_WITH_CCS))
    # Register net dispatch as contributing to a load zone's energy
    mod.LZ_Energy_Components_Produce.append('LZ_NetDispatch')

    def init_proj_availability(m, proj):
        if m.proj_is_baseload[proj]:
            return (
                (1 - m.proj_forced_outage_rate[proj]) *
                (1 - m.proj_scheduled_outage_rate[proj]))
        else:
            return (1 - m.proj_forced_outage_rate[proj])
    mod.proj_availability = Param(
        mod.PROJECTS,
        within=PositiveReals,
        initialize=init_proj_availability)

    mod.proj_max_capacity_factor = Param(
        mod.VAR_DISPATCH_POINTS,
        within=Reals,
        validate=lambda m, val, proj, t: -1 < val < 2)
    mod.min_data_check('proj_max_capacity_factor')

    mod.ProjFuelUseRate = Var(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        within=NonNegativeReals)

    def DispatchEmissions_rule(m, proj, t, f):
        if proj not in m.PROJECTS_WITH_CCS:
            return (
                m.ProjFuelUseRate[proj, t, f] *
                (m.f_co2_intensity[f] + m.f_upstream_co2_intensity[f]))
        else:
            ccs_emission_frac = 1 - m.proj_ccs_capture_efficiency[proj]
            return (
                m.ProjFuelUseRate[proj, t, f] *
                (m.f_co2_intensity[f] * ccs_emission_frac +
                 m.f_upstream_co2_intensity[f]))
    mod.DispatchEmissions = Expression(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        rule=DispatchEmissions_rule)
    mod.AnnualEmissions = Expression(mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.PROJ_FUEL_DISPATCH_POINTS
            if m.tp_period[t] == period),
        doc="The system's annual emissions, in metric tonnes of CO2 per year.")

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
            for proj in m.PERIOD_ACTIVE_PROJ[m.tp_period[t]]))
    mod.cost_components_tp.append('Total_Proj_Var_Costs_Hourly')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import project-specific data from an input directory.

    variable_capacity_factors can be skipped if no variable
    renewable projects are considered in the optimization.

    variable_capacity_factors.tab
        PROJECT, timepoint, proj_max_capacity_factor

    """

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'variable_capacity_factors.tab'),
        select=('PROJECT', 'timepoint', 'proj_max_capacity_factor'),
        param=(mod.proj_max_capacity_factor))


def post_solve(instance, outdir):
    """
    Default export of project dispatch per timepoint in tabular format.

    """
    import switch_mod.reporting as reporting
    reporting.write_table(
        instance, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "dispatch.txt"),
        headings=("timestamp",)+tuple(instance.PROJECTS),
        values=lambda m, t: (m.tp_timestamp[t],) + tuple(
            m.DispatchProj[p, t] if (p, t) in m.PROJ_DISPATCH_POINTS
            else 0.0
            for p in m.PROJECTS
        )
    )
