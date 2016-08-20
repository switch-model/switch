# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines model components to describe fuel markets for the SWITCH-Pyomo
model.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'load_zones', 'financials', 'fuels', 'gen_tech',
...     'project.build', 'project.dispatch', 'fuel_markets')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
import csv
from pyomo.environ import *


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters to
    describe fuel markets. Unless otherwise stated, each set
    and parameter is mandatory. Unless otherwise specified, all dollar
    values are real dollars in BASE_YEAR.

    REGIONAL_FUEL_MARKET is the set of all regional fuel markets. This
    may be may be abbreviated as rfm in parameter names and indexes, and
    may occasionally be referred to as a fuel region. In the current
    implementation, the names of each regional fuel market need to be
    distinct for each fuel type. That is, you cannot use "SouthWest" as
    a name for both natural gas and coal fuels. This is because market
    boundaries may be different for different fuel types due to physical
    infrastructure. This implementation detail could be revisited later
    if it proves cumbersome. An alternate implementation could specify
    each regional fuel market as a tuple pair of (region, fuel), but
    this might make indexing parameters in the code more verbose,
    confusing and error prone.

    rfm_fuel[rfm] defines the fuel sold in a regional fuel market.

    LZ_FUELS is the set of fuels available in load zones. It is specified
    as set of 2-member tuples of (load_zone, fuel).

    lz_rfm[z, f] is the regional fuel market that supplies a a given load
    zone. Regional fuel markets may be referred to as fuel regions for
    brevity. A regional fuel market could be as small as a single load
    zone or as large as the entire study region. In general, each fuel
    type needs to separately specify its regional fuel market because
    most fuels have distinct transportation infrastructure, and
    bottlenecks in this infrastructure can form the physical divisions
    that define different regional markets.

    LZ_RFM is the set of all load-zone regional fuel market combinations.
    It is the input data from which lz_rfm[z,f] is derived.

    RFM_LOAD_ZONES[rfm] is an indexed set that lists the load zones
    within each regional fuel market.

    RFM_SUPPLY_TIERS is a set of 3-part tuples that stores:
    regional_fuel_market, period, supply_tier

    RFM_P_SUPPLY_TIERS[rfm, period] is an indexed set of supply tiers
    for a given regional fuel market and period. Supply tiers are an
    ordered set typically labeled 1 to n. Each tier of a supply curve
    have a cost and limit.

    rfm_supply_tier_cost[rfm, period, tier] is the cost of a fuel in a
    particular tier of a supply curve of a particular regional fuel
    market and investment period. The units are $ / MMBTU.

    rfm_supply_tier_limit[rfm, period, tier] is the annual limit of a
    fuel available at a particular cost in a supply curve of a
    particular regional fuel market and period. The default value of
    this parameter is infinity, indicating no limit. The units are MMBTU.

    FuelConsumptionByTier[rfm, period, tier] is a decision variable that
    denotes the amount of fuel consumed in each tier of a supply curve
    in a particular regional fuel market and period. It has an upper bound
    of rfm_supply_tier_limit.

    FuelConsumptionInMarket[rfm, period] is a derived decision variable
    specifying the total amount of fuel consumed in a regional fuel
    market in a given period. In a dispatch module, a constraint should
    set this equal to the sum of all fuel consumed in that region. At
    some point in the future, I may convert this from a decision
    variable to an expression.

    Enforce_Fuel_Consumption_By_Tier[rfm, period] is a constraint that
    forces the total fuel consumption FuelConsumptionInMarket to be
    divided into distinct supply tiers.
        FuelConsumptionInMarket = sum(FuelConsumptionByTier)

    lz_fuel_cost_adder[z, f, p] is an optional parameter that describes
    a localized flat cost adder for fuels. This could reflect local
    markup from a longer supply chain or more costly distribution
    infrastructure. The units are $ / MMBTU and the default value is 0.

    The total cost of of a given type of fuel is calculated as:
        sum(FuelConsumptionByTier * rfm_supply_tier_cost) +
        sum(fuel_consumption_in_load_zone * lz_fuel_cost_adder)

    Each regional fuel market has a supply curve with discrete tiers
    of escalating costs. Tiered supply curves are flexible format that
    allows anything from a flat cost in every load zone with no limits
    on consumption, to a detailed supply curve of biomass for each load
    zone. To specify a simple flat cost, you would lump every load zone
    into a single regional fuel markets and specify a single-tier supply
    curve with no upper limit. To specify a detailed biomass supply
    curve, you would assign each load zone to a distinct biomass
    regional fuel market and specify multiple tiers in each market,
    where each tier has an upper bound.

    There is a simple data input format for situations where regional
    supply curves are unnecessary or undesired. This format specifies a
    flat cost for a load zones, fuel and period combination. The import
    code will expand this into a regional fuel market containing a
    single load zone with a single supply tier that has no upper bound.
    See load_inputs() function documentation below for more details.

    In SWITCH-WECC, biomass regional fuel markets are defined for each
    load area due to relatively high transportation costs, while natural
    gas regional fuel markets span the entire WECC region reflecting the
    interconnectedness of the pipelines. Prices can differ between load
    zones within the region based on different costs of infrastructure
    or number of middlemen in the supply chain, but all costs are based
    on an underlying commodity supply curve. Load-zone level price
    adjustments are specified with the lz_fuel_cost_adder parameter,
    based on fuel regions used by the National Energy Modeling System.

    For tiers of a supply curve with upper limits, the total volume on
    the supply curve is determined by aggregating annual consumption
    over all load zones in the regional fuel market. The model could be
    adjusted to aggregate consumption over other time scales, but
    currently only annual aggregation is implemented for supply curves.
    This version of SWITCH does not distinguish costs incurred by
    different fuel consumers within a regional fuel market.

    This version of SWITCH does not include producer surplus, so the
    aggregate cost paid for a given level of consumption does not
    reflect a market clearing price. SWITCH looks for societally and
    technically optimal solutions on the efficiency frontier that
    minimizes total costs, while trying to avoid embedding assumptions
    about market structure and dynamics. There are two primary
    motivations for this approach. First, many applications of SWITCH
    are for non-markets contexts of regulated utilities or state-owned
    utilities. Second, we don't currently know how electricity markets
    should be structured in high-renewable futures to incentivize
    investments that meet long-term societal goals and ensure cost-
    effective and reliable electricity. In the future it is quite
    possible that a large volume of energy consumption will be procured
    with favorable long-term contracts near cost rather than on a spot
    market that sets a clearing price equal to the largest accepted bid,
    which can awarding significant producer surplus. Alternatively, if
    consumers choose what infrastructure they want access to, they may
    seek long-term capacity contracts that incentivize investment and
    guarantee receipts for capital repayments and fixed costs. I don't
    know what the future of energy institutions or markets will hold,
    and I don't want to limit the technical possibilities with market
    structures from the past. One of our hopes is results from
    optimization models such as  SWITCH can inform future market and
    institutional restructuring to ensure that our societal goals are
    achieved cost-effectively.

    That being said, if a future researcher wished to include producer
    surplus to model a different perspective, that would be relatively
    straightforward to accomplish. The basic method is to order each
    segment of the supply curve by price, then going from low to high,
    increase the cost of each tier to reflect the producer surplus
    incurred from moving up from the next cheapest tier.

    Currently the model only supports supply curves with monotonically
    increasing costs. In theory it would be possible to support supply
    curves showing economies of scale with costs falling with higher
    volumes, but this is not currently supported. Implementing arbitrary
    supply curves would require introducing integer variables and
    potentially exposing non-linearities. Also, most scenarios generally
    show fuel consumption declining over time as the power sector is
    decarbonized, while the optimization becomes insensitive to the
    direct cost of carbon-based fuel because the emissions associated
    with the fuel are a much larger driver of consumption than the fuel
    costs.

    RFM_DISPATCH_POINTS[regional_fuel_market, period] is an indexed set
    of PROJ_FUEL_DISPATCH_POINTS that contribute to a given regional
    fuel market's activity in a given period.

    Enforce_Fuel_Consumption is a constraint that ties the aggregate
    fuel consumption from dispatch into FuelConsumptionInMarket variable
    from the fuel module.

    AverageFuelCosts[regional_fuel_market, period] is an expression that
    calculates the average cost paid for fuel in each market and period.
    This can be useful for post-optimization calculations of costs. Do
    not use this term in the optimization or else the problem will
    become non-linear.

    """

    mod.REGIONAL_FUEL_MARKET = Set()
    mod.rfm_fuel = Param(mod.REGIONAL_FUEL_MARKET, within=mod.FUELS)
    mod.LZ_RFM = Set(
        dimen=2, validate=lambda m, lz, rfm: (
            rfm in m.REGIONAL_FUEL_MARKET and lz in m.LOAD_ZONES))
    mod.LZ_FUELS = Set(
        dimen=2, initialize=lambda m: set(
            (lz, m.rfm_fuel[rfm]) for (lz, rfm) in m.LZ_RFM))

    def lz_rfm_init(m, load_zone, fuel):
        for (lz, rfm) in m.LZ_RFM:
            if(lz == load_zone and fuel == m.rfm_fuel[rfm]):
                return rfm
    mod.lz_rfm = Param(
        mod.LZ_FUELS, within=mod.REGIONAL_FUEL_MARKET,
        initialize=lz_rfm_init)
    mod.min_data_check('REGIONAL_FUEL_MARKET', 'rfm_fuel', 'lz_rfm')
    mod.RFM_LOAD_ZONES = Set(
        mod.REGIONAL_FUEL_MARKET,
        initialize=lambda m, rfm: set(
            lz for (lz, r) in m.LZ_RFM if r == rfm))

    # RFM_SUPPLY_TIERS = [(regional_fuel_market, period, supply_tier_index)...]
    mod.RFM_SUPPLY_TIERS = Set(
        dimen=3, validate=lambda m, r, p, st: (
            r in m.REGIONAL_FUEL_MARKET and p in m.PERIODS))
    mod.rfm_supply_tier_cost = Param(
        mod.RFM_SUPPLY_TIERS, within=Reals)
    mod.rfm_supply_tier_limit = Param(
        mod.RFM_SUPPLY_TIERS, within=PositiveReals, default=float('inf'))
    mod.min_data_check(
        'RFM_SUPPLY_TIERS', 'rfm_supply_tier_cost', 'rfm_supply_tier_limit')
    mod.RFM_P_SUPPLY_TIERS = Set(
        mod.REGIONAL_FUEL_MARKET, mod.PERIODS, dimen=3,
        initialize=lambda m, rfm, ip: set(
            (r, p, st) for (r, p, st) in m.RFM_SUPPLY_TIERS
            if r == rfm and p == ip))

    mod.FuelConsumptionByTier = Var(
        mod.RFM_SUPPLY_TIERS,
        domain=NonNegativeReals,
        bounds=lambda m, rfm, p, st: (
            0, (m.rfm_supply_tier_limit[rfm, p, st]
                if value(m.rfm_supply_tier_limit[rfm, p, st]) != float('inf')
                else None)))
    # The if statement in the upper bound of FuelConsumptionByTier is a
    # work-around for a Pyomo bug in writing a cpxlp problem file for
    # glpk. Lines 771-774 of pyomo/repn/plugins/cpxlp.py prints '<= inf'
    # instead of '<= +inf' when the upper bound is infinity, but glpk
    # reqires all inf symbols to be preceeded by a + or - sign. The
    # cpxlp writer replaces None with +inf, so I'll rely on that
    # behavior for now. The simple bounds that works with some other
    # solvers is: 0, m.rfm_supply_tier_limit[rfm, p, st]))

    mod.FuelConsumptionInMarket = Var(
        mod.REGIONAL_FUEL_MARKET, mod.PERIODS,
        domain=NonNegativeReals)
    mod.Enforce_Fuel_Consumption_By_Tier = Constraint(
        mod.REGIONAL_FUEL_MARKET, mod.PERIODS,
        rule=lambda m, rfm, p: (
            m.FuelConsumptionInMarket[rfm, p] == sum(
                m.FuelConsumptionByTier[rfm_supply_tier]
                for rfm_supply_tier in m.RFM_P_SUPPLY_TIERS[rfm, p])))

    # Ensure that adjusted fuel costs of unbounded supply tiers are not
    # negative because that would create an unbounded optimization
    # problem.
    def lz_fuel_cost_adder_validate(model, val, lz, fuel, p):
        rfm = model.lz_rfm[lz, fuel]
        for rfm_supply_tier in model.RFM_P_SUPPLY_TIERS[rfm, p]:
            if(val + model.rfm_supply_tier_cost[rfm_supply_tier] < 0 and
               model.rfm_supply_tier_limit[rfm_supply_tier] == float('inf')):
                return False
        return True
    mod.lz_fuel_cost_adder = Param(
        mod.LZ_FUELS, mod.PERIODS,
        within=Reals, default=0, validate=lz_fuel_cost_adder_validate)

    # Summarize annual fuel costs for the objective function
    def rfm_annual_costs(m, rfm, p):
        return sum(
            m.FuelConsumptionByTier[rfm_st] * m.rfm_supply_tier_cost[rfm_st]
            for rfm_st in m.RFM_P_SUPPLY_TIERS[rfm, p])
    mod.Fuel_Costs_Annual = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            rfm_annual_costs(m, rfm, p)
            for rfm in m.REGIONAL_FUEL_MARKET))
    mod.cost_components_annual.append('Fuel_Costs_Annual')

    # Components to link aggregate fuel consumption from project
    # dispatch into market framework
    mod.RFM_DISPATCH_POINTS = Set(
        mod.REGIONAL_FUEL_MARKET, mod.PERIODS,
        within=mod.PROJ_FUEL_DISPATCH_POINTS,
        initialize=lambda m, rfm, p: [
            (proj, t, f) for (proj, t, f) in m.PROJ_FUEL_DISPATCH_POINTS
            if f == m.rfm_fuel[rfm] and
            m.proj_load_zone[proj] in m.RFM_LOAD_ZONES[rfm] and
            m.tp_period[t] == p])

    # could FuelConsumptionInMarket be an Expression instead of a constrained var?
    def Enforce_Fuel_Consumption_rule(m, rfm, p):
        return m.FuelConsumptionInMarket[rfm, p] == sum(
            m.ProjFuelUseRate[proj, t, f] * m.tp_weight_in_year[t]
            for (proj, t, f) in m.RFM_DISPATCH_POINTS[rfm, p])
    mod.Enforce_Fuel_Consumption = Constraint(
        mod.REGIONAL_FUEL_MARKET, mod.PERIODS,
        rule=Enforce_Fuel_Consumption_rule)

    # Calculate average fuel costs to allow post-optimization inspection
    # and cost allocation.
    mod.AverageFuelCosts = Expression(
        mod.REGIONAL_FUEL_MARKET, mod.PERIODS,
        rule=lambda m, rfm, p: (
            rfm_annual_costs(m, rfm, p) /
            sum(m.FuelConsumptionByTier[rfm_st]
                for rfm_st in m.RFM_P_SUPPLY_TIERS[rfm, p])))


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import fuel market data. The following files are expected in the
    input directory:

    regional_fuel_markets.tab:
        regional_fuel_market, fuel

    fuel_supply_curves.tab
        regional_fuel_market, period, tier, unit_cost, max_avail_at_cost

    lz_to_regional_fuel_market.tab
        load_zone, regional_fuel_market

    The next file is optional. If unspecified, lz_fuel_cost_adder will
    default to 0 for all load zones and periods.

    lz_fuel_cost_diff.tab
        load_zone, fuel, period, fuel_cost_adder

    The next file is also optional. This file allows simple
    specification of one cost per load zone per period. The extra layer
    of regional fuel markets could be cumbersome for folks working on
    simple models. Internally, the import process converts the simple
    cost specifications to a regional fuel market structure. Import of
    this  file is accomplished through the internal
    _load_simple_cost_data function.

    fuel_cost.tab
        load_zone, fuel, period, fuel_cost

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'regional_fuel_markets.tab'),
        select=('regional_fuel_market', 'fuel'),
        index=mod.REGIONAL_FUEL_MARKET,
        param=(mod.rfm_fuel))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'fuel_supply_curves.tab'),
        select=('regional_fuel_market', 'period', 'tier', 'unit_cost',
                'max_avail_at_cost'),
        index=mod.RFM_SUPPLY_TIERS,
        param=(mod.rfm_supply_tier_cost, mod.rfm_supply_tier_limit))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'lz_to_regional_fuel_market.tab'),
        set=mod.LZ_RFM)
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'lz_fuel_cost_diff.tab'),
        optional=True,
        select=('load_zone', 'fuel', 'period', 'fuel_cost_adder'),
        param=(mod.lz_fuel_cost_adder))

    # Load a simple specifications of costs if the file exists. The
    # actual loading, error checking, and casting into a supply curve is
    # slightly complicated, so I moved that logic to a separate function.
    path = os.path.join(inputs_dir, 'fuel_cost.tab')
    if os.path.isfile(path):
        _load_simple_cost_data(mod, switch_data, path)


def _load_simple_cost_data(mod, switch_data, path):
    with open(path, 'rb') as simple_cost_file:
        simple_cost_dat = list(csv.DictReader(simple_cost_file, delimiter='	'))
        # Scan once for error checking
        for row in simple_cost_dat:
            lz = row['load_zone']
            f = row['fuel']
            p = int(row['period'])
            f_cost = float(row['fuel_cost'])
            # Basic data validity checks
            if lz not in switch_data.data(name='LOAD_ZONES'):
                raise ValueError(
                    "Load zone " + lz + " in lz_simple_fuel_cost.tab is not " +
                    "a known load zone from load_zones.tab.")
            if f not in switch_data.data(name='FUELS'):
                raise ValueError(
                    "Fuel " + f + " in lz_simple_fuel_cost.tab is not " +
                    "a known fuel from fuels.tab.")
            if p not in switch_data.data(name='PERIODS'):
                raise ValueError(
                    "Period " + p + " in lz_simple_fuel_cost.tab is not " +
                    "a known investment period.")
            # Make sure they aren't overriding a supply curve or
            # regional fuel market defined in previous files.
            for (z, rfm) in switch_data.data(name='LZ_RFM'):
                if(z == lz and
                   switch_data.data(name='rfm_fuel')[rfm] == f):
                    raise ValueError(
                        "The supply for fuel '" + f + "' for load_zone '" + lz +
                        "' was already registered with the regional fuel " +
                        "market '" + rfm + "', so you cannot " +
                        "specify a simple fuel cost for it in " +
                        "lz_simple_fuel_cost.tab. You either need to delete " +
                        "that entry from lz_to_regional_fuel_market.tab, or " +
                        "remove those entries in lz_simple_fuel_cost.tab.")
            # Make a new single-load zone regional fuel market.
            rfm = lz + "_" + f
            if rfm in switch_data.data(name='REGIONAL_FUEL_MARKET'):
                raise ValueError(
                    "Trying to construct a simple Regional Fuel Market " +
                    "called " + rfm + " from data in lz_simple_fuel_cost.tab" +
                    ", but an RFM of that name already exists. Bailing out!")
        # Scan again and actually import the data
        for row in simple_cost_dat:
            lz = row['load_zone']
            f = row['fuel']
            p = int(row['period'])
            f_cost = float(row['fuel_cost'])
            # Make a new single-load zone regional fuel market unless we
            # already defined one in this loop for a different period.
            rfm = lz + "_" + f
            if(rfm not in switch_data.data(name='REGIONAL_FUEL_MARKET')):
                switch_data.data(name='REGIONAL_FUEL_MARKET').append(rfm)
                switch_data.data(name='rfm_fuel')[rfm] = f
                switch_data.data(name='LZ_RFM').append((lz, rfm))
            # Make a single supply tier for this RFM and period
            st = 0
            switch_data.data(name='RFM_SUPPLY_TIERS').append((rfm, p, st))
            switch_data.data(name='rfm_supply_tier_cost')[rfm, p, st] = f_cost
            switch_data.data(name='rfm_supply_tier_limit')[rfm, p, st] = \
                float('inf')
