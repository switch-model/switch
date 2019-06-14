# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
This is an advanced version of the basic spinning_reserves reserves module, and
can be used in place of it (not in addition to).
"""
import os
from collections import defaultdict
from pyomo.environ import *
from switch_model.utilities import iteritems


dependencies = (
    'switch_model.timescales',
    'switch_model.balancing.load_zones',
    'switch_model.balancing.operating_reserves.areas',
    'switch_model.financials',
    'switch_model.energy_sources.properties',
    'switch_model.generators.core.build',
    'switch_model.generators.core.dispatch',
    'switch_model.generators.core.commit.operate',
)


def define_arguments(argparser):
    group = argparser.add_argument_group(__name__)
    group.add_argument('--unit-contingency', default=False, action='store_true',
        help=("This will enable an n-1 contingency based on a single unit of "
              "a generation project falling offline. Note: This create a new "
              "binary variable for each timepoint for each generation project "
              "that has a gen_unit_size specified.")
    )
    group.add_argument('--project-contingency', default=False, action='store_true',
        help=("This will enable an n-1 contingency based on the entire "
              "committed capacity of a generation project falling offline. "
              "Unlike unit contingencies, this is a purely linear expression.")
    )
    group.add_argument('--fixed-contingency', type=float, default=0.0,
        help=("Add a fixed generator contingency reserve margin, specified in MW. "
              "This can be used alone or in combination with the other "
              "contingency options.")
    )
    group.add_argument('--spinning-requirement-rule', default=None,
        choices = ["Hawaii", "3+5", "none"],
        help=("Choose rules for spinning reserves requirements as a function "
              "of variable renewable power and load. Hawaii uses rules "
              "bootstrapped from the GE RPS study, and '3+5' requires 3%% of "
              "load and 5%% of variable renewable output, based on the heuristic "
              "described in the 2010 Western Wind and Solar Integration Study. "
              "Specify 'none' if applying your own rules instead. "
        )
    )
    # TODO: define these inputs in data files
    group.add_argument(
        '--contingency-reserve-type', dest='contingency_reserve_type',
        default='spinning',
        help=
            "Type of reserves to use to meet the contingency reserve requirements "
            "defined for generation projects and sometimes for loss-of-load events "
            "(e.g., 'contingency' or 'spinning'); default is 'spinning'."
    )
    group.add_argument(
        '--regulating-reserve-type', dest='regulating_reserve_type',
        default='spinning',
        help=
            "Type of reserves to use to meet the regulating reserve requirements "
            "defined by the spinning requirements rule (e.g., 'spinning' or "
            "'regulation'); default is 'spinning'."
    )




def define_dynamic_lists(m):
    """
    Spinning_Reserve_Requirements and Spinning_Reserve_Provisions are
    dicts of lists of components that contribute to the requirement or provision
    of spinning reserves. Entries in each dict are indexed by reserve
    product. In the simple scenario, you may only have a single product called
    'spinning'. In other scenarios where some generators are limited in what
    kind of reserves they can provide, you may have "regulation" and
    "contingency" reserve products.
    The dicts are setup as defaultdicts, so they will automatically
    return an empty list if nothing has been added for a particular
    type of reserves.

    Spinning_Reserve_Up_Requirements and Spinning_Reserve_Down_Requirements
    list model components that increase reserve requirements in each balancing
    area and timepoint.

    Spinning_Reserve_Up_Provisions and Spinning_Reserve_Down_Provisions list
    model components that help satisfy spinning reserve requirements in
    each balancing area and timepoint.

    Spinning_Reserve_Up_Contingencies and Spinning_Reserve_Down_Contingencies
    list model components describing maximum contingency events. Elements of
    this list are summarized into a MaximumContingency variable that is added
    to the Spinning_Reserve_Requirements['contingency'] list.

    Each component in the Requirements and Provisions lists needs to use units
    of MW and be indexed by reserve type, balancing area and timepoint. Missing
    entries will be treated as zero (no reserves required or no reserves available).

    Each component in the Contingencies list should be in MW and indexed by
    (ba, tp) in BALANCING_AREA_TIMEPOINTS.
    """
    m.Spinning_Reserve_Up_Requirements = []
    m.Spinning_Reserve_Down_Requirements = []
    m.Spinning_Reserve_Up_Provisions = []
    m.Spinning_Reserve_Down_Provisions = []

    m.Spinning_Reserve_Up_Contingencies = []
    m.Spinning_Reserve_Down_Contingencies = []


def gen_fixed_contingency(m):
    """
    Add a fixed contingency reserve margin (much faster than unit-by-unit
    reserve margins, and reasonable when there is a single largest plant
    that is usually online and/or reserves are cheap).
    """
    m.GenFixedContingency = Param(
        m.BALANCING_AREA_TIMEPOINTS,
        initialize=lambda m: m.options.fixed_contingency
    )
    m.Spinning_Reserve_Up_Contingencies.append('GenFixedContingency')

def gen_unit_contingency(m):
    """
    Add components for unit-level contingencies. A generation project can
    include one or more discretely sized generation units. This will model
    contingencies of individual generation units that have discrete sizes
    specified. Caution, this adds binary variables to the model for every
    GEN_TPS for DISCRETELY_SIZED_GENS. This many binary variables can impact
    runtime.

    UNIT_CONTINGENCY_DISPATCH_POINTS is a subset of GEN_TPS for
    DISCRETELY_SIZED_GENS

    GenIsCommitted[(g,t) in UNIT_CONTINGENCY_DISPATCH_POINTS] is a binary
    variable that tracks whether generation projects at least one units
    committed.

    Enforce_GenIsCommitted[(g,t) in UNIT_CONTINGENCY_DISPATCH_POINTS] is a
    constraint that enforces the tracking behavior of GenIsCommitted.

    GenUnitLargestContingency[(b,t) in BALANCING_AREA_TIMEPOINTS] is a
    variable that tracks the size of the largest contingency in each balancing
    area, accounting for all of the discretely sized units that are currently
    committed. This is added to the dynamic list Spinning_Reserve_Contingencies.

    Enforce_GenUnitLargestContingency[(g,t) in UNIT_CONTINGENCY_DISPATCH_POINTS]
    is a constraint that enforces the behavior of GenUnitLargestContingency,
    by making GenUnitLargestContingency >= the capacity of each of the
    committed units in its balancing area.

    """
    # UNIT_CONTINGENCY_DISPATCH_POINTS duplicates
    # DISCRETE_GEN_TPS from generators.core.commit.discrete. I
    # justify the duplication because I don't think discrete unit commitment
    # should be a prerequisite for this functionality.
    m.UNIT_CONTINGENCY_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m:
            [(g, t) for g in m.DISCRETELY_SIZED_GENS for t in m.TPS_FOR_GEN[g]]
    )
    m.GenIsCommitted = Var(
        m.UNIT_CONTINGENCY_DISPATCH_POINTS,
        within=Binary,
        doc="Stores the status of unit committment as a binary variable."
    )
    m.Enforce_GenIsCommitted = Constraint(
        m.UNIT_CONTINGENCY_DISPATCH_POINTS,
        rule=lambda m, g, tp:
            m.CommitGen[g, tp] <= m.GenIsCommitted[g, tp] * (
                m._gen_max_cap_for_binary_constraints
                if g not in m.CAPACITY_LIMITED_GENS
                else m.gen_capacity_limit_mw[g]
            )
    )
    # TODO: would it be faster to add all generator contingencies directly
    # to Spinning_Reserve_Contingencies instead of introducing this intermediate
    # variable and constraint?
    m.GenUnitLargestContingency = Var(
        m.BALANCING_AREA_TIMEPOINTS, within=NonNegativeReals,
        doc="Largest generating unit that could drop offline.")
    def Enforce_GenUnitLargestContingency_rule(m, g, t):
        b = m.zone_balancing_area[m.gen_load_zone[g]]
        return (m.GenUnitLargestContingency[b,t] >=
                m.GenIsCommitted[g, t] * m.gen_unit_size[g])
    m.Enforce_GenUnitLargestContingency = Constraint(
        m.UNIT_CONTINGENCY_DISPATCH_POINTS,
        rule=Enforce_GenUnitLargestContingency_rule,
        doc=("Force GenUnitLargestContingency to be at least as big as the "
             "maximum unit contingency.")
    )
    m.Spinning_Reserve_Up_Contingencies.append('GenUnitLargestContingency')


def gen_project_contingency(m):
    """
    Add components for project-level contingencies based on committed capacity.
    A generation project can include one or more discretely sized generation
    units. This will model contingencies of entire generation projects -
    basically entire plants tripping offline, rather than individual
    generation units in a plan tripping offline.

    GenProjectLargestContingency[(b,t) in BALANCING_AREA_TIMEPOINTS] is a
    variable that tracks the size of the largest contingency in each balancing
    area, accounting for all of the capacity that is committed. This is
    added to the dynamic list Spinning_Reserve_Contingencies.

    Enforce_GenProjectLargestContingency[(g,t) in GEN_TPS] is a constraint
    that enforces the behavior of GenProjectLargestContingency by making
        GenProjectLargestContingency >= DispatchGen
    for each generation project in a balancing area. If a generation project
    is capable of providing upward reserves, then CommitGenSpinningReservesUp
    is added to the right hand side.

    """
    m.GenProjectLargestContingency = Var(
        m.BALANCING_AREA_TIMEPOINTS,
        doc="Largest generating project that could drop offline.")
    def Enforce_GenProjectLargestContingency_rule(m, g, t):
        b = m.zone_balancing_area[m.gen_load_zone[g]]
        if g in m.SPINNING_RESERVE_CAPABLE_GENS:
            total_up_reserves = sum(
                m.CommitGenSpinningReservesUp[rt, g, t]
                for rt in m.SPINNING_RESERVE_TYPES_FOR_GEN[g])
            return m.GenProjectLargestContingency[b, t] >= \
                m.DispatchGen[g, t] + total_up_reserves
        else:
            return m.GenProjectLargestContingency[b, t] >= m.DispatchGen[g, t]
    m.Enforce_GenProjectLargestContingency = Constraint(
        m.GEN_TPS,
        rule=Enforce_GenProjectLargestContingency_rule,
        doc=("Force GenProjectLargestContingency to be at least as big as the "
             "maximum generation project contingency.")
    )
    m.Spinning_Reserve_Up_Contingencies.append('GenProjectLargestContingency')

def hawaii_spinning_reserve_requirements(m):
    # These parameters were found by regressing the reserve requirements from
    # the GE RPS Study against wind and solar conditions each hour (see
    # Dropbox/Research/Shared/Switch-Hawaii/ge_validation/source_data/
    # reserve_requirements_oahu_scenarios charts.xlsx and
    # Dropbox/Research/Shared/Switch-Hawaii/ge_validation/
    # fit_renewable_reserves.ipynb )
    # TODO: supply all the parameters for this function in input files.

    # Calculate and register regulating reserve requirements
    # (currently only considers variable generation, only underforecasting)
    # (could eventually use some linearized quadratic formulation based
    # on load, magnitude of renewables and geographic dispersion of renewables)
    m.var_gen_power_reserve = Param(
        m.VARIABLE_GENS, default=1.0,
        doc=("Spinning reserves required to back up variable renewable "
             "generators, as fraction of potential output.")
    )
    def var_gen_cap_reserve_limit_default(m, g):
        if m.gen_energy_source[g] == 'SUN':
            return 0.21288916
        elif m.gen_energy_source[g] == 'WND':
            return 0.21624407
        else:
            raise ValueError(
                "Unable to calculate reserve requirement for energy source {}".format(m.gen_energy_source[g])
            )
    m.var_gen_cap_reserve_limit = Param(
        m.VARIABLE_GENS,
        default=var_gen_cap_reserve_limit_default,
        doc="Maximum spinning reserves required, as fraction of installed capacity"
    )
    m.HawaiiVarGenUpSpinningReserveRequirement = Expression(
        [m.options.regulating_reserve_type],
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, rt, b, t: sum(
            m.GenCapacityInTP[g, t]
            * min(
                m.var_gen_power_reserve[g] * m.gen_max_capacity_factor[g, t],
                m.var_gen_cap_reserve_limit[g]
            )
            for z in m.ZONES_IN_BALANCING_AREA[b]
            for g in m.VARIABLE_GENS_IN_ZONE[z]
            if (g, t) in m.VARIABLE_GEN_TPS),
        doc="The spinning reserves for backing up variable generation with Hawaii rules."
    )
    m.Spinning_Reserve_Up_Requirements.append('HawaiiVarGenUpSpinningReserveRequirement')

    # Calculate and register loss-of-load (down) contingencies
    if hasattr(m, 'WithdrawFromCentralGrid'):
        rule = lambda m, ba, tp: 0.10 * sum(
            m.WithdrawFromCentralGrid[z, tp] for z in m.ZONES_IN_BALANCING_AREA[ba]
        )
    else:
        # TODO: include effect of demand response here
        rule = lambda m, ba, tp: 0.10 * sum(
            m.zone_demand_mw[z, tp] for z in m.ZONES_IN_BALANCING_AREA[ba]
        )
    m.HawaiiLoadDownContingency = Expression(
        m.BALANCING_AREA_TIMEPOINTS, rule=rule
    )
    m.Spinning_Reserve_Down_Contingencies.append('HawaiiLoadDownContingency')


def nrel_3_5_spinning_reserve_requirements(m):
    """
    NREL35VarGenSpinningReserveRequirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is an expression for upward and downward spinning reserve requirements of
    3% of load plus 5% of renewable output, based on a heuristic described in
    NREL's 2010 Western Wind and Solar Integration study. It is added to the
    Spinning_Reserve_Up_Requirements and Spinning_Reserve_Down_Requirements
    lists. If the local_td module is available with DER accounting, load will
    be set to WithdrawFromCentralGrid. Otherwise load will be set to
    zone_demand_mw.
    """
    def NREL35VarGenSpinningReserveRequirement_rule(m, rt, b, t):
        try:
            load = m.WithdrawFromCentralGrid
        except AttributeError:
            load = m.zone_demand_mw
        return (
            0.03 * sum(load[z, t]
                       for z in m.LOAD_ZONES
                       if b == m.zone_balancing_area[z])
            + 0.05 * sum(m.DispatchGen[g, t]
                         for g in m.VARIABLE_GENS
                         if (g, t) in m.VARIABLE_GEN_TPS and
                            b == m.zone_balancing_area[m.gen_load_zone[g]]))
    m.NREL35VarGenSpinningReserveRequirement = Expression(
        [m.options.regulating_reserve_type],
        m.BALANCING_AREA_TIMEPOINTS,
        rule=NREL35VarGenSpinningReserveRequirement_rule
    )
    m.Spinning_Reserve_Up_Requirements.append('NREL35VarGenSpinningReserveRequirement')
    m.Spinning_Reserve_Down_Requirements.append('NREL35VarGenSpinningReserveRequirement')


def define_components(m):
    """
    contingency_safety_factor is a parameter that increases the contingency
    requirements. This is defaults to 1.0.

    GEN_SPINNING_RESERVE_TYPES is a set of all allowed reserve types for each generation
    project. This is read from generation_projects_reserve_availability.tab.
    If that file doesn't exist, this defaults to GENERATION_PROJECTS x {"spinning"}

    gen_reserve_type_max_share specifies the maximum amount of committed
    capacity that can be used to provide each type of reserves. It is indexed
    by GEN_SPINNING_RESERVE_TYPES. This is read from generation_projects_reserve_availability.tab
    and defaults to 1 if not specified. (Not currently implemented.)

    SPINNING_RESERVE_CAPABLE_GEN_TPS is a subset of GEN_TPS of generators that can
    provide spinning reserves based on generation_projects_reserve_capability.tab.

    CommitGenSpinningReservesUp[(r,g,t) in SPINNING_SPINNING_RESERVE_CAPABLE_GEN_TPS] is a
    decision variable of how much upward spinning reserve capacity to commit
    (in MW).

    CommitGenSpinningReservesDown[(r,g,t) in SPINNING_SPINNING_RESERVE_CAPABLE_GEN_TPS] is a
    corresponding variable for downward spinning reserves.

    CommitGenSpinningReservesUp_Limit[(g,t) in SPINNING_SPINNING_RESERVE_CAPABLE_GEN_TPS] and
    CommitGenSpinningReservesDown_Limit constraint the CommitGenSpinningReserves
    variables based on DispatchSlackUp and DispatchSlackDown.

    CommittedSpinningReserveUp[(b,t) in BALANCING_AREA_TIMEPOINTS] and
    CommittedSpinningReserveDown are expressions summarizing the
    CommitGenSpinningReserves variables for generators within each balancing
    area.

    Depending on the configuration parameters unit_contingency,
    project_contingency and spinning_requirement_rule, other components may be
    added by other functions which are documented above.
    """
    m.contingency_safety_factor = Param(default=1.0,
        doc=("The spinning reserve requiremet will be set to this value "
             "times the maximum contingency. This defaults to 1 to provide "
             "n-1 security for the largest committed generator. "))

    m.GEN_SPINNING_RESERVE_TYPES = Set(dimen=2)
    m.gen_reserve_type_max_share = Param(
        m.GEN_SPINNING_RESERVE_TYPES,
        within=PercentFraction,
        default=1.0
    )

    # reserve types that are supplied by generation projects
    # and generation projects that can provide reserves
    # note: these are also the indexing sets of the above set arrays; maybe that could be used?
    m.SPINNING_RESERVE_TYPES_FROM_GENS = Set(
        initialize=lambda m: set(rt for (g, rt) in m.GEN_SPINNING_RESERVE_TYPES)
    )
    m.SPINNING_RESERVE_CAPABLE_GENS = Set(
        initialize=lambda m: set(g for (g, rt) in m.GEN_SPINNING_RESERVE_TYPES)
    )

    # slice GEN_SPINNING_RESERVE_TYPES both ways for later use
    def rule(m):
        m.SPINNING_RESERVE_TYPES_FOR_GEN_dict = defaultdict(list)
        m.GENS_FOR_SPINNING_RESERVE_TYPE_dict = defaultdict(list)
        for g, rt in m.GEN_SPINNING_RESERVE_TYPES:
            m.SPINNING_RESERVE_TYPES_FOR_GEN_dict[g].append(rt)
            m.GENS_FOR_SPINNING_RESERVE_TYPE_dict[rt].append(g)
    m.build_spinning_reserve_indexed_sets = BuildAction(rule=rule)

    m.SPINNING_RESERVE_TYPES_FOR_GEN = Set(
        m.SPINNING_RESERVE_CAPABLE_GENS,
        rule=lambda m, g: m.SPINNING_RESERVE_TYPES_FOR_GEN_dict.pop(g)
    )
    m.GENS_FOR_SPINNING_RESERVE_TYPE = Set(
        m.SPINNING_RESERVE_TYPES_FROM_GENS,
        rule=lambda m, rt: m.GENS_FOR_SPINNING_RESERVE_TYPE_dict.pop(rt)
    )

    # types, generators and timepoints when reserves could be supplied
    m.SPINNING_RESERVE_TYPE_GEN_TPS = Set(dimen=3, initialize=lambda m: (
        (rt, g, tp)
        for g, rt in m.GEN_SPINNING_RESERVE_TYPES
        for tp in m.TPS_FOR_GEN[g]
    ))
    # generators and timepoints when reserves could be supplied
    m.SPINNING_RESERVE_CAPABLE_GEN_TPS = Set(dimen=2, initialize=lambda m: (
        (g, tp)
        for g in m.SPINNING_RESERVE_CAPABLE_GENS
        for tp in m.TPS_FOR_GEN[g]
    ))

    # decide how much of each type of reserves to produce from each generator
    # during each timepoint
    m.CommitGenSpinningReservesUp = Var(m.SPINNING_RESERVE_TYPE_GEN_TPS, within=NonNegativeReals)
    m.CommitGenSpinningReservesDown = Var(m.SPINNING_RESERVE_TYPE_GEN_TPS, within=NonNegativeReals)

    # constrain reserve provision appropriately
    m.CommitGenSpinningReservesUp_Limit = Constraint(
        m.SPINNING_RESERVE_CAPABLE_GEN_TPS,
        rule=lambda m, g, tp:
            sum(m.CommitGenSpinningReservesUp[rt, g, tp] for rt in m.SPINNING_RESERVE_TYPES_FOR_GEN[g])
            <=
            m.DispatchSlackUp[g, tp]
            # storage can give more up response by stopping charging
            + (m.ChargeStorage[g, tp] if g in getattr(m, 'STORAGE_GENS', []) else 0.0)
    )
    m.CommitGenSpinningReservesDown_Limit = Constraint(
        m.SPINNING_RESERVE_CAPABLE_GEN_TPS,
        rule=lambda m, g, tp:
            sum(m.CommitGenSpinningReservesDown[rt, g, tp] for rt in m.SPINNING_RESERVE_TYPES_FOR_GEN[g])
            <=
            m.DispatchSlackDown[g, tp]
            + ( # storage could give more down response by raising ChargeStorage to the maximum rate
                (m.DispatchUpperLimit[g, tp] * m.gen_store_to_release_ratio[g] - m.ChargeStorage[g, tp])
                if g in getattr(m, 'STORAGE_GENS', [])
                else 0.0
            )
    )

    # Calculate total spinning reserves from generation projects,
    # and add to the list of reserve provisions.
    # Note: this is done in a BuildAction because we don't know the indexing
    # set until the model is constructed
    def rule(m):
        up = defaultdict(float)
        down = defaultdict(float)
        for g, rt in m.GEN_SPINNING_RESERVE_TYPES:
            ba = m.zone_balancing_area[m.gen_load_zone[g]]
            for tp in m.TPS_FOR_GEN[g]:
                up[rt, ba, tp] += m.CommitGenSpinningReservesUp[rt, g, tp]
                down[rt, ba, tp] += m.CommitGenSpinningReservesDown[rt, g, tp]
        m.TotalGenSpinningReservesUp = Expression(up.keys(), initialize=dict(up))
        m.TotalGenSpinningReservesDown = Expression(down.keys(), initialize=dict(down))
        # construct these, so they can be used immediately
        for c in [m.TotalGenSpinningReservesUp, m.TotalGenSpinningReservesDown]:
            c.index_set().construct()
            c.construct()
        m.Spinning_Reserve_Up_Provisions.append('TotalGenSpinningReservesUp')
        m.Spinning_Reserve_Down_Provisions.append('TotalGenSpinningReservesDown')
    m.TotalGenSpinningReserves_aggregate = BuildAction(rule=rule)

    # define reserve requirements
    if m.options.fixed_contingency:
        gen_fixed_contingency(m)
    if m.options.unit_contingency:
        gen_unit_contingency(m)
    if m.options.project_contingency:
        gen_project_contingency(m)
    if m.options.spinning_requirement_rule == 'Hawaii':
        hawaii_spinning_reserve_requirements(m)
    elif m.options.spinning_requirement_rule == '3+5':
        nrel_3_5_spinning_reserve_requirements(m)
    elif m.options.spinning_requirement_rule == 'none':
        pass # users can turn off the rules and use their own instead
    else:
        raise ValueError('No --spinning-requirement-rule specified on command line; unable to allocate reserves.')


def define_dynamic_components(m):
    """
    MaximumContingency[(b,t) in BALANCING_AREA_TIMEPOINTS] is a variable that
    tracks the size of the largest contingency in each balancing area,
    accounting for every contingency that has been registered with
    Spinning_Reserve_Contingencies.

    BALANCING_AREA_TIMEPOINT_CONTINGENCIES is a set of (b, t, contingency) formed
    from the cross product of the set BALANCING_AREA_TIMEPOINTS and the dynamic
    list Spinning_Reserve_Contingencies.

    Enforce_MaximumContingency[(b,t,contingency) in BALANCING_AREA_TIMEPOINT_CONTINGENCIES]
    is a constraint that enforces the behavior of MaximumContingency by making
    MaximumContingency >= contingency for each contingency registered in the
    dynamic list Spinning_Reserve_Contingencies.

    Satisfy_Spinning_Reserve_Up_Requirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is a constraint that ensures upward spinning reserve requirements are
    being satisfied based on the sums of the two dynamic lists
    Spinning_Reserve_Up_Provisions and Spinning_Reserve_Up_Requirements.

    Satisfy_Spinning_Reserve_Down_Requirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is a matching constraint that uses the downward reserve lists.
    """

    # TODO: add contingency down reserves (loss-of-load events)

    # define largest contingencies
    m.MaximumContingencyUp = Var(
        m.BALANCING_AREA_TIMEPOINTS, within=NonNegativeReals,
        doc=("Maximum of the registered Spinning_Reserve_Up_Contingencies, after "
             "multiplying by contingency_safety_factor.")
    )
    m.MaximumContingencyDown = Var(
        m.BALANCING_AREA_TIMEPOINTS, within=NonNegativeReals,
        doc=("Maximum of the registered Spinning_Reserve_Down_Contingencies, after "
             "multiplying by contingency_safety_factor.")
    )
    m.Calculate_MaximumContingencyUp = Constraint(
        m.BALANCING_AREA_TIMEPOINTS,
        m.Spinning_Reserve_Up_Contingencies, # list of contingency events
        rule=lambda m, b, t, contingency:
            m.MaximumContingencyUp[b, t] >= m.contingency_safety_factor * getattr(m, contingency)[b, t]
    )
    m.Calculate_MaximumContingencyDown = Constraint(
        m.BALANCING_AREA_TIMEPOINTS,
        m.Spinning_Reserve_Down_Contingencies, # list of contingency events
        rule=lambda m, b, t, contingency:
            m.MaximumContingencyDown[b, t] >= m.contingency_safety_factor * getattr(m, contingency)[b, t]
    )

    # create reserve requirements equal to the largest contingencies
    # (these could eventually be region-specific)
    m.MaximumContingencyUpRequirement = Expression(
        [m.options.contingency_reserve_type],
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, rt, ba, tp: m.MaximumContingencyUp[ba, tp]
    )
    m.MaximumContingencyDownRequirement = Expression(
        [m.options.contingency_reserve_type],
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, rt, ba, tp: m.MaximumContingencyDown[ba, tp]
    )

    m.Spinning_Reserve_Up_Requirements.append('MaximumContingencyUpRequirement')
    m.Spinning_Reserve_Down_Requirements.append('MaximumContingencyDownRequirement')

    # aggregate the requirements for each type of reserves during each timepoint
    def rule(m):
        def makedict(m, lst):
            # lst is the name of a dynamic list from which to aggregate components
            d = defaultdict(float)
            for comp in getattr(m, lst):
                for key, val in iteritems(getattr(m, comp)):
                    d[key] += val
            setattr(m, lst + '_dict', d)
        makedict(m, 'Spinning_Reserve_Up_Requirements')
        makedict(m, 'Spinning_Reserve_Down_Requirements')
        makedict(m, 'Spinning_Reserve_Up_Provisions')
        makedict(m, 'Spinning_Reserve_Down_Provisions')
    m.Aggregate_Spinning_Reserve_Details = BuildAction(rule=rule)

    m.SPINNING_RESERVE_REQUIREMENT_UP_BALANCING_AREA_TIMEPOINTS = Set(
        dimen=3,
        rule=lambda m: m.Spinning_Reserve_Up_Requirements_dict.keys()
    )
    m.SPINNING_RESERVE_REQUIREMENT_DOWN_BALANCING_AREA_TIMEPOINTS = Set(
        dimen=3,
        rule=lambda m: m.Spinning_Reserve_Down_Requirements_dict.keys()
    )

    # satisfy all spinning reserve requirements
    m.Satisfy_Spinning_Reserve_Up_Requirement = Constraint(
        m.SPINNING_RESERVE_REQUIREMENT_UP_BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, rt, ba, tp:
            m.Spinning_Reserve_Up_Provisions_dict.pop((rt, ba, tp), 0.0)
            >=
            m.Spinning_Reserve_Up_Requirements_dict.pop((rt, ba, tp))
    )
    m.Satisfy_Spinning_Reserve_Down_Requirement = Constraint(
        m.SPINNING_RESERVE_REQUIREMENT_DOWN_BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, rt, ba, tp:
            m.Spinning_Reserve_Down_Provisions_dict.pop((rt, ba, tp), 0.0)
            >=
            m.Spinning_Reserve_Down_Requirements_dict.pop((rt, ba, tp))
    )


def load_inputs(m, switch_data, inputs_dir):
    """
    All files & columns are optional.

    generation_projects_reserve_capability.tab
        GENERATION_PROJECTS, RESERVE_TYPES, [gen_reserve_type_max_share]

    spinning_reserve_params.dat may override the default value of
    contingency_safety_factor. Note that this is a .dat file, not a .tab file.
    """
    path=os.path.join(inputs_dir, 'generation_projects_reserve_capability.tab')
    switch_data.load_aug(
        filename=path,
        optional=True,
        auto_select=True,
        optional_params=['gen_reserve_type_max_share]'],
        index=m.GEN_SPINNING_RESERVE_TYPES,
        param=(m.gen_reserve_type_max_share)
    )
    if not os.path.isfile(path):
        gen_projects = switch_data.data()['GENERATION_PROJECTS'][None]
        switch_data.data()['GEN_SPINNING_RESERVE_TYPES'] = {}
        switch_data.data()['GEN_SPINNING_RESERVE_TYPES'][None] = \
            [(g, "spinning") for g in gen_projects]

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'spinning_reserve_params.dat'),
        optional=True,
    )
