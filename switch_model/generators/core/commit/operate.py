# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines model components to describe unit commitment of projects for the
Switch model. This module is mutually exclusive with the
operations.no_commit module which specifies simplified dispatch
constraints. If you want to use this module directly in a list of switch
modules (instead of including the package operations.unitcommit), you will also
need to include the module operations.unitcommit.fuel_use.
"""
from __future__ import division

import os, itertools
from pyomo.environ import *

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties.properties",
    "switch_model.generators.core.build",
    "switch_model.generators.core.dispatch",
)


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe
    unit commitment for projects. Unless otherwise stated, all power
    capacity is specified in units of MW and all sets and parameters
    are mandatory.

    -- Commit decision, limits, and headroom --

    CommitGen[(g, t) in GEN_TPS] is a decision
    variable of how much capacity (MW) from each project to commit in
    each timepoint. By default, this operates in continuous mode.
    Include the project.unitcommit.discrete module to force this to
    operate with discrete unit commitment.

    gen_max_commit_fraction[(g, t) in GEN_TPS]
    describes the maximum commit level as a fraction of available
    capacity (capacity that is built and expected to be available for
    commitment; derated by annual expected outage rate). This has
    limited  use cases, but could be used to simulate outages (scheduled
    or non-scheduled) in a production-cost simulation. This optional
    parameter has a default value of 1.0, indicating that all available
    capacity can be commited.  If you wish to have discrete unit
    commitment, I advise overriding the default behavior and specifying
    a more discrete treatment of outages.

    gen_min_commit_fraction[(g, t) in GEN_TPS]
    describes the minimum commit level as a fraction of available
    capacity. This is useful for describing must-run plants that ensure
    reliable grid operations, and for forcing hydro plants operate at
    some minimal level to maintain streamflow. This can also be used to
    specify baseload plants that must be run year-round. This optional
    parameter will default to gen_max_commit_fraction for generation
    technologies marked baseload and 0 for all other generators.

    CommitLowerLimit[(g, t) in GEN_TPS] is an expression that describes the
    minimum capacity that must be committed. This is derived from installed
    capacity, gen_availability and gen_min_commit_fraction.

    CommitUpperLimit[(g, t) in GEN_TPS] is an expression that describes the
    maximum capacity available for commitment. This is derived from installed
    capacity, gen_availability and gen_max_commit_fraction.

    Enforce_Commit_Lower_Limit[(g, t) in GEN_TPS] and
    Enforce_Commit_Upper_Limit[(g, t) in GEN_TPS] are
    constraints that limit CommitGen to the upper and lower bounds
    defined above.

        CommitLowerLimit <= CommitGen <= CommitUpperLimit

    CommitSlackUp[(g, t) in GEN_TPS] is an expression
    that describes the amount of additional capacity available for
    commitment: CommitUpperLimit - CommitGen

    CommitSlackDown[(g, t) in GEN_TPS] is an expression
    that describes the amount of committed capacity  that could be taken
    offline: CommitGen - CommitLowerLimit

    -- StartupGenCapacity and ShutdownGenCapacity --

    The capacity started up or shutdown is completely determined by
    the change in CommitGen from one hour to the next, but we can't
    calculate these directly within the linear program because linear
    programs don't have if statements. Instead, we'll define extra decision
    variables that are tightly constrained. Since startup incurs costs and
    shutdown does not, the linear program will not simultaneously set both
    of these to non-zero values.

    StartupGenCapacity[(g, t) in GEN_TPS] is a decision variable
    describing how much additional capacity was brought online in a given
    timepoint. Committing additional capacity incurs startup costs for
    fossil plants from fuel requirements as well as additional O&M
    costs.

    ShutdownGenCapacity[(g, t) in GEN_TPS] is a decision variable
    describing how much committed capacity to take offline in a given
    timepoint.

    Commit_StartupGenCapacity_ShutdownGenCapacity_Consistency[(g, t) in
    GEN_TPS] is a constraint that forces consistency
    between commitment decision from one hour to the next with startup
    and shutdown.

    gen_startup_fuel[g in FUEL_BASED_GENS] describes fuel
    requirements for starting up additional generation capacity, expressed
    in units of MMBTU / MW. This optional parameter has a default value
    of 0.

    g_startup_om[g in GENERATION_TECHNOLOGIES] describes operations and
    maintenance costs incured from starting up additional generation
    capacity expressed in units of $base_year / MW. This could represent
    direct maintenance requirements or some overall depreciation rate
    from accelerated wear and tear. This optional parameter has a
    default value of 0.

    gen_startup_om[g in GENERATION_PROJECTS] is the same as g_startup_om except
    on a project basis. This optional parameter defaults to g_startup_om.

    Total_StartupGenCapacity_OM_Costs[t in TIMEPOINTS] is an expression for passing
    total startup O&M costs to the sys_cost module.

    gen_min_uptime[g] and gen_min_downtime[g] show the minimum time that a
    generator can be committed (turned on) or uncommitted (turned off), in
    hours. These usually reflect rules intended to limit thermal stress on
    generator units. They default to 0 (free to turn on or off at any
    point) if not provided. Note: in practice, these will be rounded to
    the nearest integer number of timepoints, so a project will be off for
    1 timepoint if gen_min_downtime is 4 and ts_duration_of_tp is 3. If more
    conservative behavior is needed, gen_min_uptime or gen_min_downtime should
    be raised to the desired multiple of ts_duration_of_tp.

    UPTIME_CONSTRAINED_GEN_TPS and DOWNTIME_CONSTRAINED_GEN_TPS
    are sets of (project, timepoint) tuples when minimum uptime or
    downtime constraints are active. These are the indexing sets for the
    Enforce_Min_Uptime and Enforce_Min_Downtime constraints, and are
    probably not useful elsewhere.

    Enforce_Min_Uptime[(g, t) in UPTIME_CONSTRAINED_GEN_TPS] and
    Enforce_Min_Downtime[(g, t) in DOWNTIME_CONSTRAINED_GEN_TPS]
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

    gen_min_load_fraction[g] describes the minimum loading level of a
    project as a fraction of committed capacity. Many fossil plants -
    especially baseload - have a minimum run level which should be stored
    here. Note that this is only applied to committed capacity. This is an
    optional parameter that defaults to 1 for generation technologies
    marked baseload and 0 for all other generators. This parameter is only
    relevant when considering unit commitment so it is defined here rather
    than in the gen_dispatch module.

    gen_min_load_fraction_TP[g, t] is the same as
    gen_min_load_fraction, but has separate entries for each timepoint.
    This could be used, for example, for non-curtailable renewable energy
    projects. This defaults to the value of gen_min_load_fraction[g].

    gen_min_cap_factor[(g, t) in GEN_TPS] describes the
    minimum loadding level for each project and timepoint as a fraction
    of committed capacity. This is an optional parameter that defaults
    to gen_min_load_fraction. You may wish to
    vary this by timepoint to establish minimum flow rates for
    hydropower, to specify thermal demand for a cogeneration project, or
    specify must-run reliability constraints in a geographically or
    temporally detailed model. This could also be used to constrain
    dispatch of distributed solar resources that cannot be curtailed by
    the system operator.

    DispatchLowerLimit[(g, t) in GEN_TPS] and
    DispatchUpperLimit[(g, t) in GEN_TPS] are
    expressions that define the lower and upper bounds of dispatch.
    Lower bounds are calculated as CommitGen * gen_min_cap_factor,
    and upper bounds are calculated relative to committed capacity and
    renewable resource availability.

    Enforce_Dispatch_Lower_Limit[(g, t) in GEN_TPS] and
    Enforce_Dispatch_Upper_Limit[(g, t) in GEN_TPS] are
    constraints that limit DispatchGen to the upper and lower bounds
    defined above.

        DispatchLowerLimit <= DispatchGen <= DispatchUpperLimit

    DispatchSlackUp[(g, t) in GEN_TPS] is an expression
    that describes the amount of additional commited capacity available
    for dispatch: DispatchUpperLimit - DispatchGen

    DispatchSlackDown[(g, t) in GEN_TPS] is an
    expression that describes the amount by which dispatch could be
    lowered, that is how much downramp potential each project has
    in each timepoint: DispatchGen - DispatchLowerLimit


    """

    # Commitment decision, bounds and associated slack variables
    mod.CommitGen = Var(mod.GEN_TPS, within=NonNegativeReals)
    mod.gen_max_commit_fraction = Param(
        mod.GEN_TPS, within=PercentFraction, default=lambda m, g, t: 1.0
    )
    mod.gen_min_commit_fraction = Param(
        mod.GEN_TPS,
        within=PercentFraction,
        default=lambda m, g, t: (
            m.gen_max_commit_fraction[g, t] if g in m.BASELOAD_GENS else 0.0
        ),
    )
    mod.CommitLowerLimit = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (
            m.GenCapacityInTP[g, t]
            * m.gen_availability[g]
            * m.gen_min_commit_fraction[g, t]
        ),
    )
    mod.CommitUpperLimit = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (
            m.GenCapacityInTP[g, t]
            * m.gen_availability[g]
            * m.gen_max_commit_fraction[g, t]
        ),
    )
    mod.Enforce_Commit_Lower_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.CommitLowerLimit[g, t] <= m.CommitGen[g, t]),
    )
    mod.Enforce_Commit_Upper_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.CommitGen[g, t] <= m.CommitUpperLimit[g, t]),
    )
    mod.CommitSlackUp = Expression(
        mod.GEN_TPS, rule=lambda m, g, t: (m.CommitUpperLimit[g, t] - m.CommitGen[g, t])
    )
    mod.CommitSlackDown = Expression(
        mod.GEN_TPS, rule=lambda m, g, t: (m.CommitGen[g, t] - m.CommitLowerLimit[g, t])
    )
    # StartupGenCapacity & ShutdownGenCapacity (at start of each timepoint)
    mod.StartupGenCapacity = Var(mod.GEN_TPS, within=NonNegativeReals)
    mod.ShutdownGenCapacity = Var(mod.GEN_TPS, within=NonNegativeReals)
    mod.Commit_StartupGenCapacity_ShutdownGenCapacity_Consistency = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: m.CommitGen[g, m.tp_previous[t]]
        + m.StartupGenCapacity[g, t]
        - m.ShutdownGenCapacity[g, t]
        == m.CommitGen[g, t],
    )

    # StartupGenCapacity costs
    mod.gen_startup_fuel = Param(
        mod.FUEL_BASED_GENS, default=0.0, within=NonNegativeReals
    )
    mod.gen_startup_om = Param(
        mod.GENERATION_PROJECTS, default=0.0, within=NonNegativeReals
    )
    # Note: lump-sum startup O&M cost is divided by the duration of the
    # timepoint to give a cost-per-hour during this timepoint, as needed by
    # Cost_Components_Per_TP.
    mod.Total_StartupGenCapacity_OM_Costs = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.gen_startup_om[g] * m.StartupGenCapacity[g, t] / m.tp_duration_hrs[t]
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
        ),
    )
    mod.Cost_Components_Per_TP.append("Total_StartupGenCapacity_OM_Costs")

    mod.gen_min_uptime = Param(
        mod.GENERATION_PROJECTS, within=NonNegativeReals, default=0.0
    )
    mod.gen_min_downtime = Param(
        mod.GENERATION_PROJECTS, within=NonNegativeReals, default=0.0
    )

    def hrs_to_num_tps(m, hrs, t):
        return int(round(hrs / m.ts_duration_of_tp[m.tp_ts[t]]))

    def time_window(m, t, hrs, add_one=False):
        """Return a the set of timepoints, starting at t and going
        back the specified number of hours"""
        n = hrs_to_num_tps(m, hrs, t)
        if add_one:
            n += 1
        window = [m.TPS_IN_TS[m.tp_ts[t]].prevw(t, i) for i in range(n)]
        return window

    mod.UPTIME_CONSTRAINED_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: [
            (g, t)
            for g in m.GENERATION_PROJECTS
            if m.gen_min_uptime[g] > 0.0
            for t in m.TPS_FOR_GEN[g]
            if hrs_to_num_tps(m, m.gen_min_uptime[g], t) > 0
        ],
    )
    mod.DOWNTIME_CONSTRAINED_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: [
            (g, t)
            for g in m.GENERATION_PROJECTS
            if m.gen_min_downtime[g] > 0.0
            for t in m.TPS_FOR_GEN[g]
            if hrs_to_num_tps(m, m.gen_min_downtime[g], t) > 0
        ],
    )
    mod.Enforce_Min_Uptime = Constraint(
        mod.UPTIME_CONSTRAINED_GEN_TPS,
        doc="All capacity turned on in the last x hours must still be on now",
        rule=lambda m, g, t: (
            m.CommitGen[g, t]
            >= sum(
                m.StartupGenCapacity[g, t_prior]
                for t_prior in time_window(m, t, m.gen_min_uptime[g])
            )
        ),
    )
    # Matthias notes on Enforce_Min_Downtime: The max(...) term finds the
    # largest fraction of capacity that could have been committed in the last
    # x hours, including the current hour. We assume that everything above
    # this band must remain turned off (e.g., on maintenance outage). Note:
    # this band extends one step prior to the first relevant shutdown, since
    # that capacity could have been online in the prior step. This attempts to
    # implement a band of capacity that does not participate in the minimum
    # downtime constraint. Without that term, the model can turn off some
    # capacity, and then get around the min-downtime rule by turning on other
    # capacity which is actually forced off by gen_max_commit_fraction, e.g.,
    # due to a maintenance outage.
    # The max() term & documentation is confusing to Josiah.
    # See https://github.com/switch-model/switch/issues/123 for discussion.
    mod.Enforce_Min_Downtime = Constraint(
        mod.DOWNTIME_CONSTRAINED_GEN_TPS,
        doc=(
            "All recently shutdown capacity remains offline: "
            "committed <= committable capacity - recent shutdowns"
        ),
        rule=lambda m, g, t: (
            m.CommitGen[g, t]
            <=
            # We can't use max(CommitUpperLimit) and fit within LP guidelines,
            # so rederive the CommitUpperLimit expression and apply max to a
            # constant.
            (
                m.GenCapacityInTP[g, t]
                * m.gen_availability[g]
                * max(
                    m.gen_max_commit_fraction[g, t_prior]
                    for t_prior in time_window(
                        m, t, m.gen_min_downtime[g], add_one=True
                    )
                )
            )
            - sum(
                m.ShutdownGenCapacity[g, t_prior]
                for t_prior in time_window(m, t, m.gen_min_downtime[g])
            )
        ),
    )

    # Dispatch limits relative to committed capacity.
    mod.gen_min_load_fraction = Param(
        mod.GENERATION_PROJECTS,
        within=PercentFraction,
        default=lambda m, g: 1.0 if m.gen_is_baseload[g] else 0.0,
    )
    mod.gen_min_load_fraction_TP = Param(
        mod.GEN_TPS,
        default=lambda m, g, t: m.gen_min_load_fraction[g],
        within=NonNegativeReals,
    )
    mod.DispatchLowerLimit = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.CommitGen[g, t] * m.gen_min_load_fraction_TP[g, t]),
    )

    def DispatchUpperLimit_expr(m, g, t):
        if g in m.VARIABLE_GENS:
            return m.CommitGen[g, t] * m.gen_max_capacity_factor[g, t]
        else:
            return m.CommitGen[g, t]

    mod.DispatchUpperLimit = Expression(mod.GEN_TPS, rule=DispatchUpperLimit_expr)

    mod.Enforce_Dispatch_Lower_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchLowerLimit[g, t] <= m.DispatchGen[g, t]),
    )
    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g, t] <= m.DispatchUpperLimit[g, t]),
    )
    mod.DispatchSlackUp = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchUpperLimit[g, t] - m.DispatchGen[g, t]),
    )
    mod.DispatchSlackDown = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g, t] - m.DispatchLowerLimit[g, t]),
    )


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import data to support unit commitment. The following files are
    expected in the input directory. All files and fields are optional.
    If you only want to override default values for certain columns in a
    row, insert a dot . into the other columns.

    gen_info.csv
        GENERATION_PROJECT, gen_min_load_fraction, gen_startup_fuel,
        gen_startup_om

    Note: If you need to specify minimum loading fraction or startup
    costs for a non-fuel based generator, you must put a dot . in the
    gen_startup_fuel column to avoid an error.

    gen_timepoint_commit_bounds.csv
        GENERATION_PROJECT, TIMEPOINT, gen_min_commit_fraction_TP,
        gen_max_commit_fraction_TP, gen_min_load_fraction_TP

    """
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "gen_info.csv"),
        param=(
            mod.gen_min_load_fraction,
            mod.gen_startup_fuel,
            mod.gen_startup_om,
            mod.gen_min_uptime,
            mod.gen_min_downtime,
        ),
    )
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "gen_timepoint_commit_bounds.csv"),
        param=(
            mod.gen_min_commit_fraction,
            mod.gen_max_commit_fraction,
            mod.gen_min_load_fraction_TP,
        ),
    )
