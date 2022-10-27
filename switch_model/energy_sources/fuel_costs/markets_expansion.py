"""
Defines model components to allow capital investment to expand fuel markets.
"""

# TODO: eventually this should be extended to use capital costs instead of fixed
# per-unit costs (probably as part of a generalized asset tracking system).

# TODO: create indexing set for fuel markets expansion that only refers to
# limited-capacity tiers, then only define the variables and constraints over
# that set. This will simplify the code some -- no need to force activation of
# unlimited tiers. We could go further and only consider the tiers with prices.
# But covering all the limited tiers may make it easier to interpret the output
# files, and also allows users to add side constraints (e.g., some other side
# effect happens in the year a tier is built, even if it's a zero-cost tier).
# If users want costs and/or side-constraints for activation of unlimited tiers
# (e.g., to model fuel switching for a utility), they should supply a limit. If
# we didn't require them to provide a limit, then we would have to create an
# arbitrary limit here anyway for the big-M constraint that prevents usage if
# the tier is not activated.

import os
from pyomo.environ import *

infinity = float("inf")


def define_components(m):
    """
    This makes it possible to invest capital to gain access to a fuel supply
    tier, as defined in ./markets.py. Each fuel market tier is one
    capacity-expansion choice, and it must be fully built and/or activated each
    period. To do this, we add binary variables and confine additions and
    activations to match them. Each tier has a fixed and variable cost and
    duration (locked in if it is developed). Variable costs are
    implemented in markets.py, and this module adds fixed costs. These are
    defined as a cost per MMBtu of fuel supply made _available_ by that tier (not
    necessarily used). In the future we may replace this with a more complete
    capital cost system, similar to generation projects.

    This module defines binary activation variables for all supply tiers, but
    forces activation of tiers with unlimited capacity, because otherwise we
    would need to introduce an arbitrary limit for them for the big-M
    constraints below. This requirement doesn't affect costs, because unlimited
    tiers must have zero cost in the current formulation. If there are side
    effects of the build/activate decisions, then users should provide high
    limits for these tiers,  (but not infinite limits, which are the default).

    Unlimited tiers must also have zero cost to avoid infinite activation cost
    in the current formulation (with per-unit fixed costs). We could instead use
    lump-sum activation costs, but then it would be a bad idea to force
    activation of unlimited tiers with nonzero costs. So we would instead need
    to introduce an arbitrary limit for the big-M constraints.

    This module defines the following components:

    rfm_supply_tier_fixed_cost[RFM_SUPPLY_TIERS]: cost to activate each supply
    tier, expressed per MMBtu of potential supply. Defaults to 0.0 (same as if
    this module were not used). Should be specified as 'fixed_cost' in
    fuel_supply_curves.csv.

    rfm_supply_tier_max_age[RFM_SUPPLY_TIERS]: lifetime for each tier, once it is placed in
    service. Default is one period. Should be specified as 'max_age' in
    fuel_supply_curves.csv.

    RFMBuildSupplyTier[RFM_SUPPLY_TIERS]: binary variable indicating whether
    this tier is first deployed in the specified period

    RFMSupplyTierActive[RFM_SUPPLY_TIERS]: binary expression indicating whether
    this tier is active in the specified period (based on whether
    RFMBuildSupplyTier was set within the previous rfm_supply_tier_max_age
    years)

    RFM_Fixed_Costs_Annual[PERIODS]: total fixed cost for supply tiers that have
    been activated; included in model objective function.

    Only_One_RFMSupplyTierActive: constraint that prevents activating a single
    tier multiple times in the same year (e.g., by building once, then building
    again before retirement)

    Force_Activate_Unlimited_RFM_Supply_Tier: constraint that forces all
    unlimited tiers to be activated; avoids applying the big-M constraint
    with an infinite upper limit.

    Enforce_RFM_Supply_Tier_Activated: constraint that prevents delivery of fuel
    from tiers that have not been activated
    """

    # fixed cost (per mmBtu/year of capacity) of having each tier in service
    # during each period note: this must be zero if a tier has unlimited
    # capacity, to avoid having infinite cost
    m.rfm_supply_tier_fixed_cost = Param(
        m.RFM_SUPPLY_TIERS,
        default=0.0,
        within=NonNegativeReals,
        validate=lambda m, v, r, p, st: v == 0.0
        or m.rfm_supply_tier_limit[r, p, st] < infinity,
    )

    # lifetime for each tier, once it is placed in service
    # (default is one period)
    m.rfm_supply_tier_max_age = Param(
        m.RFM_SUPPLY_TIERS,
        default=lambda m, r, p, st: m.period_length_years[p],
        within=NonNegativeReals,
    )

    # Note: in large regions, a tier represents a block of expandable capacity,
    # so this could be continuous. But to model that, you can just lump the
    # fixed cost into the variable cost and not use this module.
    m.RFMBuildSupplyTier = Var(m.RFM_SUPPLY_TIERS, within=Binary)

    # will the tier be active during each period?
    m.RFMSupplyTierActive = Expression(
        m.RFM_SUPPLY_TIERS,
        rule=lambda m, r, p, st: sum(
            m.RFMBuildSupplyTier[r, vintage, st]
            for vintage in m.PERIODS
            if (
                # starts before end of current period
                vintage < m.period_start[p] + m.period_length_years[p]
                # available to be built
                and (r, vintage, st) in m.RFM_SUPPLY_TIERS
                # ends after start of current period
                and vintage + m.rfm_supply_tier_max_age[r, vintage, st]
                > m.period_start[p]
            )
        ),
    )

    # Don't double-activate any tier
    m.Only_One_RFMSupplyTierActive = Constraint(
        m.RFM_SUPPLY_TIERS,
        rule=lambda m, r, p, st: m.RFMSupplyTierActive[r, p, st] <= 1,
    )

    # force all unlimited tiers to be activated (since they must have no cost,
    # and to avoid a limit of 0.0 * infinity in the constraint below)
    m.Force_Activate_Unlimited_RFM_Supply_Tier = Constraint(
        m.RFM_SUPPLY_TIERS,
        rule=lambda m, r, p, st: (m.RFMSupplyTierActive[r, p, st] == 1)
        if (m.rfm_supply_tier_limit[r, p, st] == infinity)
        else Constraint.Skip,
    )

    # only allow delivery from activated tiers
    # (and skip unlimited tiers to avoid a complaint by glpk about these)
    # note: this could be merged with the previous constraint, since they are
    # complementary
    m.Enforce_RFM_Supply_Tier_Activated = Constraint(
        m.RFM_SUPPLY_TIERS,
        rule=lambda m, r, p, st: (
            m.ConsumeFuelTier[r, p, st]
            <= m.RFMSupplyTierActive[r, p, st] * m.rfm_supply_tier_limit[r, p, st]
        )
        if m.rfm_supply_tier_limit[r, p, st] < infinity
        else Constraint.Skip,
    )

    # total cost incurred for all the activated supply tiers
    m.RFM_Fixed_Costs_Annual = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            (
                # note: we dance around projects with unlimited supply and 0.0 fixed cost
                0.0
                if m.rfm_supply_tier_fixed_cost[rfm_st] == 0.0
                else (
                    m.rfm_supply_tier_fixed_cost[rfm_st]
                    * m.RFMSupplyTierActive[rfm_st]
                    * m.rfm_supply_tier_limit[rfm_st]
                )
            )
            for r in m.REGIONAL_FUEL_MARKETS
            for rfm_st in m.SUPPLY_TIERS_FOR_RFM_PERIOD[r, p]
        ),
    )
    m.Cost_Components_Per_Period.append("RFM_Fixed_Costs_Annual")


def load_inputs(m, switch_data, inputs_dir):
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "fuel_supply_curves.csv"),
        select=("regional_fuel_market", "period", "tier", "fixed_cost", "max_age"),
        param=(m.rfm_supply_tier_fixed_cost, m.rfm_supply_tier_max_age),
    )
