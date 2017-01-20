# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines model components to describe unit commitment of projects for the
SWITCH-Pyomo model. This module is mutually exclusive with the
operations.no_commit module which specifies simplified dispatch
constraints. If you want to use this module directly in a list of switch
modules (instead of including the package operations.unitcommit), you will also
need to include the module operations.unitcommit.fuel_use.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels',
...     'investment.proj_build', 'operations.proj_dispatch',
...     'operations.unitcommit')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *


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
    calculate these directly directly within the linear program because
    linear programs don't have if statements. Instead, we'll define extra
    decision variables that are tightly constrained. Since startup incurs
    costs and shutdown does not, the linear program will not simultaneously
    set both of these to non-zero values.

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

    g_startup_fuel[g in GEN_TECH_WITH_FUEL] describes fuel
    requirements of starting up additional generation capacity expressed
    in units of MMBTU / MW. This optional parameter has a default value
    of 0.

    proj_startup_fuel[proj in FUEL_BASED_PROJECTS] is the same as
    g_startup_fuel except on a project basis. This optional parameter
    defaults to g_startup_fuel.

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

    -- Dispatch limits based on committed capacity --

    g_min_load_fraction[g] describes the minimum loading level of a
    generation technology as a fraction of committed capacity. Many
    fossil plants - especially baseload - have a minimum run level which
    should be stored here. Note that this is only applied to committed
    capacity. This is an optional parameter that defaults to 1 for
    generation technologies marked baseload and 0 for all other
    generators. This parameter is only relevant when considering unit
    commitment so it is defined here rather than the gen_tech module.

    proj_min_cap_factor[(proj, t) in PROJ_DISPATCH_POINTS] describes the
    minimum loadding level for each project and timepoint as a fraction
    of committed capacity. This is an optional parameter that defaults
    to g_min_load_fraction, which in turn defaults to 0. You may wish to
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
        rule=lambda m, pr, t: (
            m.CommitProject[pr, m.tp_previous[t]] +
            m.Startup[pr, t] - m.Shutdown[pr, t] == m.CommitProject[pr, t]))
    
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
               mod.proj_startup_om))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'proj_commit_bounds_timepoints.tab'),
        auto_select=True,
        param=(mod.proj_min_commit_fraction, 
            mod.proj_max_commit_fraction, mod.proj_min_load_fraction_TP))
