# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines model components to describe unit commitment of projects for the
SWITCH-Pyomo model. This module is mutually exclusive with the
operations.no_commit module which specifies simplified dispatch
constraints. If you want to use this module directly in a list of switch
modules (instead of including the package operations.unitcommit), you will also
need to include the module operations.unitcommit.fuel_use.
"""

import os, itertools
from pyomo.environ import *

dependencies = 'switch_mod.timescales', 'switch_mod.load_zones',\
    'switch_mod.financials.minimize_cost', 'switch_mod.energy_sources', \
    'switch_mod.investment.proj_build', 'switch_mod.operations.proj_dispatch'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe
    unit commitment for projects. Unless otherwise stated, all power
    capacity is specified in units of MW and all sets and parameters
    are mandatory.

    -- Commit decision, limits, and headroom --

    CommitProject[(proj, t) in PROJ_DISPATCH_POINTS] is a decision
    variable of how much capacity (MW) from each project to commit in
    each timepoint. By default, this operates in continuous mode.
    Include the project.unitcommit.discrete module to force this to
    operate with discrete unit commitment.

    proj_max_commit_fraction[(proj, t) in PROJ_DISPATCH_POINTS]
    describes the maximum commit level as a fraction of available
    capacity (capacity that is built and expected to be available for
    commitment; derated by annual expected outage rate). This has
    limited  use cases, but could be used to simulate outages (scheduled
    or non-scheduled) in a production-cost simulation. This optional
    parameter has a default value of 1.0, indicating that all available
    capacity can be commited.  If you wish to have discrete unit
    commitment, I advise overriding the default behavior and specifying
    a more discrete treatment of outages.

    proj_min_commit_fraction[(proj, t) in PROJ_DISPATCH_POINTS]
    describes the minimum commit level as a fraction of available
    capacity. This is useful for describing must-run plants that ensure
    reliable grid operations, and for forcing hydro plants operate at
    some minimal level to maintain streamflow. This can also be used to
    specify baseload plants that must be run year-round. This optional
    parameter will default to proj_max_commit_fraction for generation
    technologies marked baseload and 0 for all other generators.

    CommitLowerLimit[(proj, t) in PROJ_DISPATCH_POINTS] is an expression
    that describes the minimum capacity that must be committed. This is
    derived from installed capacity and proj_min_commit_fraction.

    CommitUpperLimit[(proj, t) in PROJ_DISPATCH_POINTS] is an expression
    that describes the maximum capacity available for commitment. This
    is derived from installed capacity and proj_max_commit_fraction.

    Enforce_Commit_Lower_Limit[(proj, t) in PROJ_DISPATCH_POINTS] and
    Enforce_Commit_Upper_Limit[(proj, t) in PROJ_DISPATCH_POINTS] are
    constraints that limit CommitProject to the upper and lower bounds
    defined above.

        CommitLowerLimit <= CommitProject <= CommitUpperLimit

    CommitSlackUp[(proj, t) in PROJ_DISPATCH_POINTS] is an expression
    that describes the amount of additional capacity available for
    commitment: CommitUpperLimit - CommitProject

    CommitSlackDown[(proj, t) in PROJ_DISPATCH_POINTS] is an expression
    that describes the amount of committed capacity  that could be taken
    offline: CommitProject - CommitLowerLimit

    -- Startup and Shutdown --

    The capacity started up or shutdown is completely determined by
    the change in CommitProject from one hour to the next, but we can't
    calculate these directly within the linear program because linear
    programs don't have if statements. Instead, we'll define extra decision 
    variables that are tightly constrained. Since startup incurs costs and 
    shutdown does not, the linear program will not simultaneously set both 
    of these to non-zero values.

    Startup[(proj, t) in PROJ_DISPATCH_POINTS] is a decision variable
    describing how much additional capacity was brought online in a given
    timepoint. Committing additional capacity incurs startup costs for
    fossil plants from fuel requirements as well as additional O&M
    costs.

    Shutdown[(proj, t) in PROJ_DISPATCH_POINTS] is a decision variable
    describing how much committed capacity to take offline in a given
    timepoint.

    Commit_Startup_Shutdown_Consistency[(proj, t) in
    PROJ_DISPATCH_POINTS] is a constraint that forces consistency
    between commitment decision from one hour to the next with startup
    and shutdown.

    proj_startup_fuel[proj in FUEL_BASED_PROJECTS] describes fuel
    requirements for starting up additional generation capacity, expressed
    in units of MMBTU / MW. This optional parameter has a default value
    of 0.

    g_startup_om[g in GENERATION_TECHNOLOGIES] describes operations and
    maintenance costs incured from starting up additional generation
    capacity expressed in units of $base_year / MW. This could represent
    direct maintenance requirements or some overall depreciation rate
    from accelerated wear and tear. This optional parameter has a
    default value of 0.

    proj_startup_om[proj in PROJECTS] is the same as g_startup_om except
    on a project basis. This optional parameter defaults to g_startup_om.

    Total_Startup_OM_Costs[t in TIMEPOINTS] is an expression for passing
    total startup O&M costs to the sys_cost module.

    proj_min_uptime[g] and proj_min_downtime[g] show the minimum time that a
    generator can be committed (turned on) or uncommitted (turned off), in
    hours. These usually reflect rules intended to limit thermal stress on
    generator units. They default to 0 (free to turn on or off at any
    point) if not provided. Note: in practice, these will be rounded to
    the nearest integer number of timepoints, so a project will be off for
    1 timepoint if proj_min_downtime is 4 and ts_duration_of_tp is 3. If more
    conservative behavior is needed, proj_min_uptime or proj_min_downtime should
    be raised to the desired multiple of ts_duration_of_tp.

    PROJ_MIN_UPTIME_DISPATCH_POINTS and PROJ_MIN_DOWNTIME_DISPATCH_POINTS
    are sets of (project, timepoint) tuples when minimum uptime or
    downtime constraints are active. These are the indexing sets for the
    Enforce_Min_Uptime and Enforce_Min_Downtime constraints, and are
    probably not useful elsewhere.
    
    Enforce_Min_Uptime[(proj, tp) in PROJ_MIN_UPTIME_DISPATCH_POINTS] and
    Enforce_Min_Downtime[(proj, tp) in PROJ_MIN_DOWNTIME_DISPATCH_POINTS]
    are constraints that ensure that unit commitment respects the minimum
    uptime and downtime for each project. These are enforced on an
    aggregate basis for each project rather than tracking individual
    units: the amount of generation capacity that can be committed in each
    timepoint is equal to the amount of capacity that has been offline for
    longer than the minimum downtime; the amount that can be decommitted
    is equal to the amount that has been online for longer than the
    minimum uptime. These rules are expressed by requiring that all
    capacity that was started up during a lookback window (equal to
    minimum uptime) is still online, and all capacity that was shutdown
    during the downtime lookback window is still offline. Note: if a slice
    of capacity has been forced off for the entire downtime lookback
    window (e.g., on maintenance outage), the Enforce_Min_Downtime
    constraint requires that capacity to stay offline during the current
    timepoint. i.e., it is not possible to shutdown some units and then
    startup units in the forced-off band to satisfy the min-downtime
    rules. On the other hand any capacity that could have been committed
    at some point in the lookback window can be startup now, possibly
    replacing other units that were shutdown recently.
    
    -- Dispatch limits based on committed capacity --

    proj_min_load_fraction[proj] describes the minimum loading level of a
    project as a fraction of committed capacity. Many fossil plants -
    especially baseload - have a minimum run level which should be stored
    here. Note that this is only applied to committed capacity. This is an
    optional parameter that defaults to 1 for generation technologies
    marked baseload and 0 for all other generators. This parameter is only
    relevant when considering unit commitment so it is defined here rather
    than in the proj_dispatch module.

    proj_min_load_fraction_TP[proj, tp] is the same as
    proj_min_load_fraction, but has separate entries for each timepoint.
    This could be used, for example, for non-curtailable renewable energy
    projects. This defaults to the value of proj_min_load_fraction[proj].
    
    proj_min_cap_factor[(proj, t) in PROJ_DISPATCH_POINTS] describes the
    minimum loadding level for each project and timepoint as a fraction
    of committed capacity. This is an optional parameter that defaults
    to proj_min_load_fraction. You may wish to
    vary this by timepoint to establish minimum flow rates for
    hydropower, to specify thermal demand for a cogeneration project, or
    specify must-run reliability constraints in a geographically or
    temporally detailed model. This could also be used to constrain
    dispatch of distributed solar resources that cannot be curtailed by
    the system operator.

    DispatchLowerLimit[(proj, t) in PROJ_DISPATCH_POINTS] and
    DispatchUpperLimit[(proj, t) in PROJ_DISPATCH_POINTS] are
    expressions that define the lower and upper bounds of dispatch.
    Lower bounds are calculated as CommitProject * proj_min_cap_factor,
    and upper bounds are calculated relative to committed capacity and
    renewable resource availability.

    Enforce_Dispatch_Lower_Limit[(proj, t) in PROJ_DISPATCH_POINTS] and
    Enforce_Dispatch_Upper_Limit[(proj, t) in PROJ_DISPATCH_POINTS] are
    constraints that limit DispatchProj to the upper and lower bounds
    defined above.

        DispatchLowerLimit <= DispatchProj <= DispatchUpperLimit

    DispatchSlackUp[(proj, t) in PROJ_DISPATCH_POINTS] is an expression
    that describes the amount of additional commited capacity available
    for dispatch: DispatchUpperLimit - DispatchProj

    DispatchSlackDown[(proj, t) in PROJ_DISPATCH_POINTS] is an
    expression that describes the amount by which dispatch could be
    lowered, that is how much downramp potential each project has
    in each timepoint: DispatchProj - DispatchLowerLimit


    """

    # Commitment decision, bounds and associated slack variables
    mod.CommitProject = Var(
        mod.PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.proj_max_commit_fraction = Param(
        mod.PROJ_DISPATCH_POINTS,
        within=PercentFraction,
        default=lambda m, proj, t: 1.0)
    mod.proj_min_commit_fraction = Param(
        mod.PROJ_DISPATCH_POINTS,
        within=PercentFraction,
        default=lambda m, proj, t: (
            m.proj_max_commit_fraction[proj, t]
            if proj in m.BASELOAD_PROJECTS
            else 0.0))
    mod.CommitLowerLimit = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.ProjCapacityTP[proj, t] * m.proj_availability[proj] *
            m.proj_min_commit_fraction[proj, t]))
    mod.CommitUpperLimit = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.ProjCapacityTP[proj, t] * m.proj_availability[proj] *
            m.proj_max_commit_fraction[proj, t]))
    mod.Enforce_Commit_Lower_Limit = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.CommitLowerLimit[proj, t] <= m.CommitProject[proj, t]))
    mod.Enforce_Commit_Upper_Limit = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.CommitProject[proj, t] <= m.CommitUpperLimit[proj, t]))
    mod.CommitSlackUp = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.CommitUpperLimit[proj, t] - m.CommitProject[proj, t]))
    mod.CommitSlackDown = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.CommitProject[proj, t] - m.CommitLowerLimit[proj, t]))
    # Startup & Shutdown
    mod.Startup = Var(
        mod.PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.Shutdown = Var(
        mod.PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.Commit_Startup_Shutdown_Consistency = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, pr, t: 
            m.CommitProject[pr, m.tp_previous[t]] 
            + m.Startup[pr, t] - m.Shutdown[pr, t] 
            == m.CommitProject[pr, t])
    
    # Startup costs
    mod.proj_startup_fuel = Param(mod.FUEL_BASED_PROJECTS, default=0.0)
    mod.proj_startup_om = Param(mod.PROJECTS, default=0.0)
    # Startup costs need to be divided over the duration of the
    # timepoint because it is a one-time expenditure in units of $
    # but cost_components_tp requires an hourly cost rate in $ / hr.
    mod.Total_Startup_OM_Costs = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.proj_startup_om[proj] * m.Startup[proj, t] / m.tp_duration_hrs[t]
            for (proj, t2) in m.PROJ_DISPATCH_POINTS
            if t == t2))
    mod.cost_components_tp.append('Total_Startup_OM_Costs')

    mod.proj_min_uptime = Param(
        mod.PROJECTS,
        within=NonNegativeReals,
        default=0.0)
    mod.proj_min_downtime = Param(
        mod.PROJECTS,
        within=NonNegativeReals,
        default=0.0)
    mod.PROJ_MIN_UPTIME_DISPATCH_POINTS = Set(dimen=2, initialize=lambda m: [
        (pr, tp) 
            for pr in m.PROJECTS if m.proj_min_uptime[pr] > 0.0
                for tp in m.PROJ_ACTIVE_TIMEPOINTS[pr] 
    ])
    mod.PROJ_MIN_DOWNTIME_DISPATCH_POINTS = Set(dimen=2, initialize=lambda m: [
        (pr, tp) 
            for pr in m.PROJECTS if m.proj_min_downtime[pr] > 0.0
                for tp in m.PROJ_ACTIVE_TIMEPOINTS[pr] 
    ])
    
    def tp_prev(m, tp, n=1):
        # find nth previous timepoint, wrapping from start to end of day
        return m.TS_TPS[m.tp_ts[tp]].prevw(tp, n)
    # min_time_projects = set()
    def min_time_rule(m, pr, tp, up):
        """ This uses a simple rule: all capacity turned on in the last x
        hours must still be on now (or all capacity recently turned off
        must still be off)."""
        
        # how many timepoints must the project stay on/off once it's
        # started/shutdown?
        n_tp = int(round(
            m.proj_min_downtime[pr] 
            / m.ts_duration_of_tp[m.tp_ts[tp]]
        ))
        if n_tp == 1:
            # project can be shutdown and restarted in the same timepoint
            rule = Constraint.Skip
        else:
            # note: this rule stops one short of n_tp steps back (normal
            # behavior of range()), because the current timepoint is
            # included in the duration when the capacity will be on/off.
            if up:
                rule = (    
                    # online capacity >= recent startups 
                    # (all recent startups are still online)
                    m.CommitProject[pr, tp] 
                    >= 
                    sum(m.Startup[pr, tp_prev(m, tp, i)] for i in range(1, n_tp))
                )
            else:
                # Find the largest fraction of capacity that could have
                # been committed in the last x hours, including the
                # current hour. We assume that everything above this band
                # must remain turned off (e.g., on maintenance outage). 
                committable_fraction = m.proj_availability[pr] * max(
                    m.proj_max_commit_fraction[pr, tp_prev(m, tp, i)] 
                        for i in range(0, n_tp)
                )
                rule = (    
                    # offline capacity >= forced-off + recent shutdowns 
                    # (all recent shutdowns are still offline)
                    # This is 
                    # capacity - committed >=
                    # (1-committable)*capacity + shutdowns
                    # which becomes
                    # committable * capacity - committed >= shutdowns
                    m.ProjCapacityTP[pr, tp] * committable_fraction
                    - m.CommitProject[pr, tp] 
                    >= 
                    sum(m.Shutdown[pr, tp_prev(m, tp, i)] for i in range(1, n_tp))
                )
        return rule
    mod.Enforce_Min_Uptime = Constraint(
        mod.PROJ_MIN_UPTIME_DISPATCH_POINTS, rule=lambda *a: min_time_rule(*a, up=True)
    )
    mod.Enforce_Min_Downtime = Constraint(
        mod.PROJ_MIN_DOWNTIME_DISPATCH_POINTS, rule=lambda *a: min_time_rule(*a, up=False)
    )
    
    # Dispatch limits relative to committed capacity.
    mod.proj_min_load_fraction = Param(
        mod.PROJECTS,
        within=PercentFraction,
        default=lambda m, proj: 1.0 if m.proj_is_baseload[proj] else 0.0)
    mod.proj_min_load_fraction_TP = Param(
        mod.PROJ_DISPATCH_POINTS,
        default=lambda m, proj, t: m.proj_min_load_fraction[proj])
    mod.DispatchLowerLimit = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.CommitProject[proj, t] * m.proj_min_load_fraction_TP[proj, t]))

    def DispatchUpperLimit_expr(m, proj, t):
        if proj in m.VARIABLE_PROJECTS:
            return m.CommitProject[proj, t]*m.proj_max_capacity_factor[proj, t]
        else:
            return m.CommitProject[proj, t]
    mod.DispatchUpperLimit = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=DispatchUpperLimit_expr)

    mod.Enforce_Dispatch_Lower_Limit = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchLowerLimit[proj, t] <= m.DispatchProj[proj, t]))
    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] <= m.DispatchUpperLimit[proj, t]))
    mod.DispatchSlackUp = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchUpperLimit[proj, t] - m.DispatchProj[proj, t]))
    mod.DispatchSlackDown = Expression(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] - m.DispatchLowerLimit[proj, t]))


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import data to support unit commitment. The following files are
    expected in the input directory. All files and fields are optional.
    If you only want to override default values for certain columns in a
    row, insert a dot . into the other columns.

    project_info.tab
        PROJECT, proj_min_load_fraction, proj_startup_fuel, proj_startup_om

    Note: If you need to specify minimum loading fraction or startup
    costs for a non-fuel based generator, you must put a dot . in the
    proj_startup_fuel column to avoid an error.

    proj_commit_bounds_timepoints.tab
        PROJECT, TIMEPOINT, proj_min_commit_fraction_TP,
        proj_max_commit_fraction_TP, proj_min_load_fraction_TP

    """
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'project_info.tab'),
        auto_select=True,
        param=(mod.proj_min_load_fraction, mod.proj_startup_fuel,
               mod.proj_startup_om, mod.proj_min_uptime, mod.proj_min_downtime))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'proj_commit_bounds_timepoints.tab'),
        auto_select=True,
        param=(mod.proj_min_commit_fraction, 
            mod.proj_max_commit_fraction, mod.proj_min_load_fraction_TP))
