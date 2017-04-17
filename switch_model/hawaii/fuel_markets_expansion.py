# For large systems, each fuel market tier is a category of capacity expansion, and
# it can be built fractionally. For small systems, each fuel market tier is one 
# capacity-expansion project, and it must be fully built and/or activated each period.
# To do this, we add binary variables and confine additions and activations to match them.
# Each tier has a capital cost and duration (locked in if it is developed)
# and a fixed and variable cost. Variable costs are already shown in fuel_markets.py,
# and this module adds fixed costs (some economies of scale, but assuming 100% salvage
# value at all times, i.e., projects can be deactivated without losing any capital cost.)
# Later we may add a more complete capital cost system.

import os
from pyomo.environ import *

inf = float('inf')

def define_components(m):

    # eventually this should be extended to include capital costs and fixed lifetimes
    # for fuel supply infrastructure, but then it gets fairly complicated (equivalent
    # to the project build / activate / operate system) 
    # Maybe we can setup some sort of inheritance system for different types of object 
    # -- base capital assets, which could then be power production projects (of which some 
    # are generators (fuel-based or intermittent), and some are storage), fuel-supply projects, 
    # transmission lines, etc.
    
    
    # fixed cost (per mmBtu/year of capacity) of having each tier in service during each period
    # note: this must be zero if a tier has unlimited capacity, to avoid having infinite cost
    m.rfm_supply_tier_fixed_cost = Param(m.RFM_SUPPLY_TIERS, default=0.0,
        validate=lambda m, v, r, p, st: v == 0.0 or m.rfm_supply_tier_limit[r, p, st] < inf)
    
    # lifetime for each tier, once it is placed in service 
    # (default is one period)
    m.rfm_supply_tier_max_age = Param(m.RFM_SUPPLY_TIERS, default=lambda m, r, p, st: m.period_length_years[p])

    # Note: in large regions, a tier represents a block of expandable capacity, 
    # so this could be continuous, but then you could just lump the fixed cost 
    # into the variable cost and not use this module.
    m.RFMBuildSupplyTier = Var(m.RFM_SUPPLY_TIERS, within=Binary)

    # will the tier be active during each period?
    m.RFMSupplyTierActivate = Var(m.RFM_SUPPLY_TIERS, within=PercentFraction)
    
    # force activation to match build decision
    m.RFM_Build_Activate_Consistency = Constraint(m.RFM_SUPPLY_TIERS, rule=lambda m, r, p, st:
        m.RFMSupplyTierActivate[r, p, st]
        == 
        sum(
            m.RFMBuildSupplyTier[r, vintage, st] 
                for vintage in m.PERIODS 
                    if vintage < m.period_start[p] + m.period_length_years[p]                        # starts before end of current period
                        and vintage + m.rfm_supply_tier_max_age[r, vintage, st] > m.period_start[p]  # ends after start of current period
        )
    )
    
    # force all unlimited tiers to be activated (since they must have no cost, 
    # and to avoid a limit of 0.0 * inf in the constraint below)
    m.Force_Activate_Unlimited_RFM_Supply_Tier = Constraint(m.RFM_SUPPLY_TIERS, 
        rule=lambda m, r, p, st:
            (m.RFMSupplyTierActivate[r, p, st] == 1) if (m.rfm_supply_tier_limit[r, p, st] == inf)
            else Constraint.Skip
    )
    
    # only allow delivery from activated tiers 
    # (and skip unlimited tiers to avoid a complaint by glpk about these)
    # note: this could be merged with the previous constraint, since they are complementary
    m.Enforce_RFM_Supply_Tier_Activated = Constraint(
        m.RFM_SUPPLY_TIERS, 
        rule=lambda m, r, p, st:
            (
                m.ConsumeFuelTier[r, p, st]
                <=
                m.RFMSupplyTierActivate[r, p, st] * m.rfm_supply_tier_limit[r, p, st]
            ) if m.rfm_supply_tier_limit[r, p, st] < inf else Constraint.Skip
    )
    
    # Eventually, when we add capital costs for capacity expansion, we will need a 
    # variable showing how much of each tier to build each period (and then the upper
    # limit could be a lifetime limit rather than a limit on what can be added each
    # period). Then we may want to make the expansion variable Binary for small systems
    # and continuous for large systems. That could be done by building a shadow list
    # of binary variables and constraining the actual decisions to match the binary
    # version if some flag is set in the data.

    m.RFM_Fixed_Costs_Annual = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            (
                # note: we dance around projects with unlimited supply and 0.0 fixed cost
                0.0 if m.rfm_supply_tier_fixed_cost[rfm_st] == 0.0 
                else m.rfm_supply_tier_fixed_cost[rfm_st]
                    * m.RFMSupplyTierActivate[rfm_st] * m.rfm_supply_tier_limit[rfm_st]
            )
            for r in m.REGIONAL_FUEL_MARKETS
                for rfm_st in m.SUPPLY_TIERS_FOR_RFM_PERIOD[r, p]))

    m.Cost_Components_Per_Period.append('RFM_Fixed_Costs_Annual')

def load_inputs(m, switch_data, inputs_dir):
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'fuel_supply_curves.tab'),
        select=('regional_fuel_market', 'period', 'tier', 'fixed_cost', 'max_age'),
        param=(m.rfm_supply_tier_fixed_cost,m.rfm_supply_tier_max_age))
