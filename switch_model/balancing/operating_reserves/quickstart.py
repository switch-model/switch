# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
A simple model of quickstart reserves to accompany the spinning_reserves
modules. Patterns from the spinning reserves modules were followed where
practical to simplify implementation and review.

Unlike spinning reserves, this module does not currently implement
contingency-based requirements because I lack an immediate use case for that.
The contigency reserves methodology from spinning reserve modules could
probably be adapted readily if needed.

For more discussion of operating reserve considerations and modeling
approaches, see the spinning_reserves module.

"""
import os
from pyomo.environ import *

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
optional_prerequisites = (
    'switch_model.balancing.operating_reserves.spinning_reserves',
    'switch_model.balancing.operating_reserves.spinning_reserves_advanced',    
)

# Uncomment this section when more than one rule is implemented.
# def define_arguments(argparser):
#     group = argparser.add_argument_group(__name__)
#     group.add_argument('--quickstart-requirement-rule', default="3+5",
#         dest='quickstart_requirement_rule',
#         choices = ["3+5"],
#         help=("Choose rules for quickstart reserves requirements as a function "
#               "of variable renewable power and load. '3+5' requires 3%% of "
#               "load and 5%% of variable renewable output, based on the "
#               "heuristic described in the 2010 Western Wind and Solar "
#               "Integration Study.")
#     )


def define_dynamic_lists(mod):
    """
    Quickstart_Reserve_Requirements is a list of model components that
    contribute to quickstart reserve requirements in each balancing area and
    timepoint.

    Quickstart_Reserve_Provisions is a list of model components that help
    satisfy spinning reserve requirements in each balancing area and
    timepoint.

    Each component in both lists needs to use units of MW and be indexed by:
    (b, t) in BALANCING_AREA_TIMEPOINTS.
    """
    mod.Quickstart_Reserve_Requirements = []
    mod.Quickstart_Reserve_Provisions = []


def nrel_3_5_quickstart_reserve_requirements(mod):
    """
    NREL35QuickstartRequirement[(b,t) in BALANCING_AREA_TIMEPOINTS] is
    an expression for quickstart reserve requirements of 3% of load plus 5% of
    renewable output, based on a heuristic described in NREL's 2010 Western
    Wind and Solar Integration study. It is added to the
    Quickstart_Reserve_Requirements list. If the local_td module is available
    with DER accounting, load will be set to WithdrawFromCentralGrid.
    Otherwise load will be set to lz_demand_mw.
    """
    def NREL35QuickstartRequirement_rule(m, b, t):
        try:
            load = m.WithdrawFromCentralGrid
        except AttributeError:
            load = m.lz_demand_mw
        return (0.03 * sum(load[z, t] for z in m.LOAD_ZONES
                           if b == m.zone_balancing_area[z])
              + 0.05 * sum(m.DispatchGen[g, t] for g in m.VARIABLE_GENS
                           if (g, t) in m.VARIABLE_GEN_TPS and
                              b == m.zone_balancing_area[m.gen_load_zone[g]]))
    mod.NREL35QuickstartRequirement = Expression(
        mod.BALANCING_AREA_TIMEPOINTS,
        rule=NREL35QuickstartRequirement_rule
    )
    mod.Quickstart_Reserve_Requirements.append('NREL35QuickstartRequirement')


def define_components(mod):
    """
    gen_can_provide_quickstart_reserves[g] is a binary flag indicating whether
    a generation project can provide quickstart reserves. Default to False for
    baseload & variable generators, otherwise defaults to True.

    QUICKSTART_RESERVE_GEN_TPS is a subset of GEN_TPS for generators that 
    have gen_can_provide_quickstart_reserves set to True.

    CommitQuickstartReserves[(g,t) in QUICKSTART_RESERVE_GEN_TPS] is a
    decision variable of how much quickstart reserve capacity to commit
    (in MW).

    CommitQuickstartReserves_Limit[(g,t) in SPINNING_RESERVE_GEN_TPS]
    constrain the CommitGenSpinningReserves variables based on CommitSlackUp
    (and CommitGenSpinningReservesSlackUp as applicable).
    
    For example, if discrete unit commitment is enabled, and a 5MW hydro
    generator is fully committed but only providing 2MW of power and 1 MW of
    spinning reserves, the remaining 2MW of capacity (summarized in
    CommitGenSpinningReservesSlackUp) could be committed to quickstart
    reserves.

    CommittedQuickstartReserves[(b,t) in BALANCING_AREA_TIMEPOINTS] is an
    expression summarizing the CommitQuickstartReserves variables for
    generators within each balancing area.

    See also: NREL35QuickstartRequirement defined in the function above.
    """
    mod.gen_can_provide_quickstart_reserves = Param(
        mod.GENERATION_PROJECTS,
        within=Boolean,
        default=lambda m, g: not (m.gen_is_baseload[g] or m.gen_is_variable[g]),
        doc="Denotes whether a generation project can provide quickstart "
            "reserves. Default to false for baseload & variable generators, "
            "otherwise true. Can be explicitly specified in an input file."
    )
    mod.QUICKSTART_RESERVE_GEN_TPS = Set(
        dimen=2,
        within=mod.GEN_TPS,
        initialize=lambda m: set(
            (g,t)
            for g in m.GENERATION_PROJECTS 
                if m.gen_can_provide_quickstart_reserves[g]
            for t in m.TPS_FOR_GEN[g]
        )
    )
    mod.CommitQuickstartReserves = Var(
        mod.QUICKSTART_RESERVE_GEN_TPS,
        within=NonNegativeReals
    )
    def CommitQuickstartReserves_Limit_rule(m, g, t):
        limit = m.CommitSlackUp[g,t]
        try:
            limit += m.CommitGenSpinningReservesSlackUp[g,t]
        except (AttributeError, KeyError):
            pass
        return (m.CommitQuickstartReserves[g,t] <= limit)            
    mod.CommitQuickstartReserves_Limit = Constraint(
        mod.QUICKSTART_RESERVE_GEN_TPS,
        doc="Constrain committed quickstart reserves to uncommited capacity "
            "plus any dispatch slack that is not committed to spinning "
            "reserves (if applicable).",
        rule=CommitQuickstartReserves_Limit_rule
    )

    mod.CommittedQuickstartReserves = Expression(
        mod.BALANCING_AREA_TIMEPOINTS,
        doc="Sum of committed quickstart reserve capacity per balancing "
            "area and timepoint.",
        rule=lambda m, b, t: (
            sum(m.CommitQuickstartReserves[g, t]
                for z in m.ZONES_IN_BALANCING_AREA[b]
                for g in m.GENS_IN_ZONE[z]
                if (g,t) in m.QUICKSTART_RESERVE_GEN_TPS
            )
        )
    )
    mod.Quickstart_Reserve_Provisions.append('CommittedQuickstartReserves')

    # These rules are in a separate function in anticipation of additional
    # rulesets eventually being defined and selectable via command line
    # arguments.
    nrel_3_5_quickstart_reserve_requirements(mod)


def define_dynamic_components(mod):
    """
    Satisfy_Quickstart_Requirement[(b,t) in BALANCING_AREA_TIMEPOINTS]
    is a constraint that ensures quickstart reserve requirements are
    being satisfied based on the sum of the dynamic lists
    Quickstart_Reserve_Requirements & Quickstart_Reserve_Provisions.
    """
    mod.Satisfy_Quickstart_Requirement = Constraint(
        mod.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, b, t: (
            sum(getattr(m, provision)[b,t]
                for provision in m.Quickstart_Reserve_Provisions
            ) >=
            sum(getattr(m, requirement)[b,t]
                for requirement in m.Quickstart_Reserve_Requirements
            )
        )
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
    All files & columns are optional. See notes above for default values.

    generation_projects_info.csv
        GENERATION_PROJECTS, ... gen_can_provide_quickstart_reserves
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        optional_params=['gen_can_provide_quickstart_reserves'],
        param=(mod.gen_can_provide_quickstart_reserves)
    )
