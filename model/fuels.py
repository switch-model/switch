"""
Defines model components to describe fuels and other energy sources for
the SWITCH-Pyomo model.

SYNOPSIS
>>> from coopr.pyomo import *
>>> import timescales
>>> import load_zones
>>> import fuels
>>> switch_model = AbstractModel()
>>> timescales.define_components(switch_model)
>>> load_zones.define_components(switch_model)
>>> fuels.define_components(switch_model)
>>> switch_data = DataPortal(model=switch_model)
>>> inputs_dir = 'test_dat'
>>> timescales.load_data(switch_model, switch_data, inputs_dir)
>>> load_zones.load_data(switch_model, switch_data, inputs_dir)
>>> fuels.load_data(switch_model, switch_data, inputs_dir)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest -v fuels.py`
"""

import os
import csv
from coopr.pyomo import *
import utilities


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters to
    describe energy sources and fuels. Unless otherwise stated, each set
    and parameter is mandatory.

    ENERGY_SOURCES is the set of primary energy sources used to generate
    electricity. Some of these are fuels like coal, uranium or biomass,
    and  some are renewable sources like wind, solar and water. The one
    odd entry is "Storage" which gets assigned to battery banks, and the
    storage portion of pumped hydro or Compressed Air Energy Storage.
    Non-fuel energy sources come with a minimal set of information and
    are mainly used to group similar technologies together, or to
    determine if a given technology qualifies as renewable in a given
    jurisdiction. Energy sources may be abbreviated as es in parameter
    names and indexes.

    NON_FUEL_ENERGY_SOURCES is a subset of ENERGY_SOURCES that lists
    primary energy sources that are not fuels. Things like sun, wind,
    water, or geothermal belong here.

    FUELS is a subset of ENERGY_SOURCES that lists primary energy
    sources that store potential energy that can be released to do
    useful work. Many fuels are fossil-based, but the set of fuels also
    includes biomass, biogas and uranium. If people started synthesizing
    fuels such as ammonium, they could go into this set as well. Several
    additional pieces of information need to be provided for fuels
    including carbon intensity, costs, etc. These are described below.
    Fuels may be abbreviated as f in parameter names and indexes.

    In this formulation of SWITCH, fuels are described in terms of heat
    content rather than mass. This simplifies some aspects of modeling,
    but it could be equally valid to describe fuels in terms of $/mass,
    heat_content/mass (high- heating value and low heating value),
    carbon_content/mass, upstream_co2_emissions/mass, then to normalize
    all of those to units of heat content. We have chosen not to
    implement that yet because we don't have a compelling reason.

    For these data inputs, you may use either the high heating value or
    low heating value for any given fuel. Just make sure that all of the
    heat rates for generators that consume a given fuel match the
    heating value you have chosen.

    f_co2_intensity[f] describes the carbon intensity of direct
    emissions incurred when a fuel is combusted in units of metric
    tonnes of Carbon Dioxide per Million British Thermal Units
    (tCO2/MMBTU). This is non-zero for all carbon-based combustible
    fuels, including biomass. Currently the only fuel that can have a
    value of 0 for this is uranium.

    f_upstream_co2_intensity[f] is the carbon emissions attributable to
    a fuel before it is consumed in units of tCO2/MMBTU. For sustainably
    harvested biomass, this can be negative to reflect the CO2 that was
    extracted from the atmosphere while the biomass was growing. For
    most fuels this can be set to 0 unless you wish to perform Life
    Cycle Analysis investigations. The carbon intensity and upstream
    carbon intensity need to be defined separately to support Biomass
    Energy with Carbon Capture and Sequestration (BECCS) generation
    technologies. This is an optional parameter that defaults to 0.

    In BECCS it is important to know the carbon embedded in a given
    amount of fuel as well as the amount of negative emissions achieved
    when the biomass was growing. In a simple BECCS analysis of
    sustainably harvested crop residues, crops suck CO2 from the
    atmosphere while they are growing and producing biomass
    (f_upstream_co2_intensity). Combusting the the biomass in a power
    plant releases that entire amount of CO2 (f_co2_intensity). If this
    process were happening without CCS, the overall carbon intensity
    would be 0 because f_upstream_co2_intensity = -1 * f_co2_intensity
    under ideal conditions for sustainably harvested biomass. With CCS,
    the overall carbon intensity is negative because a large portion of
    the direct emissions are captured and sequestered in stable
    underground geological formations with a capture and storage
    efficiency determined by the BECCS technology.

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
    confusing and more error prone.

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
    ordered set typically labeled 1-n. Each tier of a supply curve have
    a cost and limit.

    rfm_supply_tier_cost[rfm, period, tier] is the cost of a fuel in a
    particular tier of a supply curve of a particular regional fuel
    market and investment period. The units are $BASE_YEAR / MMBTU.

    rfm_supply_tier_limit[rfm, period, tier] is the annual limit of a
    fuel available at a particular cost in a supply curve of a
    particular regional fuel market and period. The default value of
    this parameter is infinity, indicating no limit. The units are MMBTU.

    lz_fuel_cost_adder[z, f, p] is an optional parameter that describes
    a localized flat cost adder for fuels. This could reflect local
    markup from a longer supply chain or more costly distribution
    infrastructure. The units are $BASE_YEAR / MMBTU.

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
    See load_data function documentation below for more details.

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


    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    mod.NON_FUEL_ENERGY_SOURCES = Set()
    mod.FUELS = Set()
    mod.f_co2_intensity = Param(mod.FUELS, within=NonNegativeReals)
    mod.f_upstream_co2_intensity = Param(
        mod.FUELS, within=Reals, default=0)
    mod.min_data_check(
        'FUELS', 'NON_FUEL_ENERGY_SOURCES', 'f_co2_intensity',
        'f_upstream_co2_intensity')
    # Ensure that fuel and non-fuel sets have no overlap.
    mod.e_source_is_fuel_or_not_check = BuildCheck(
        rule=lambda m: len(m.FUELS & m.NON_FUEL_ENERGY_SOURCES) == 0)

    # ENERGY_SOURCES is the union of fuel and non-fuels sets. Pipe | is
    # the union operator for Pyomo sets.
    mod.ENERGY_SOURCES = Set(
        initialize=mod.NON_FUEL_ENERGY_SOURCES | mod.FUELS)

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
            r in m.REGIONAL_FUEL_MARKET and p in m.INVEST_PERIODS))
    mod.rfm_supply_tier_cost = Param(
        mod.RFM_SUPPLY_TIERS, within=Reals)
    mod.rfm_supply_tier_limit = Param(
        mod.RFM_SUPPLY_TIERS, within=PositiveReals, default=float('inf'))
    mod.min_data_check(
        'RFM_SUPPLY_TIERS', 'rfm_supply_tier_cost', 'rfm_supply_tier_limit')
    mod.RFM_P_SUPPLY_TIERS = Set(
        mod.REGIONAL_FUEL_MARKET, mod.INVEST_PERIODS, dimen=3,
        initialize=lambda m, rfm, ip: set(
            (r, p, st) for (r, p, st) in m.RFM_SUPPLY_TIERS
            if r == rfm and p == ip))

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
        mod.LZ_FUELS, mod.INVEST_PERIODS,
        within=Reals, default=0, validate=lz_fuel_cost_adder_validate)


def load_data(mod, switch_data, inputs_directory):
    """

    Import fuel data. To skip optional parameters such as
    upstream_co2_intensity, you need to specify 'default' in the given column
    rather than leaving them blank. Leaving a column blank will generate
    an error message like "IndexError: list index out of range". The
    following files are expected in the input directory:

    non_fuel_energy_sources.tab
        energy_source

    fuels.tab
        fuel, co2_intensity, upstream_co2_intensity

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

    lz_simple_fuel_cost.tab
        load_zone, fuel, period, fuel_cost

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.

    switch_data.load(
        filename=os.path.join(inputs_directory, 'non_fuel_energy_sources.tab'),
        set=('NON_FUEL_ENERGY_SOURCES'))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'fuels.tab'),
        select=('fuel', 'co2_intensity', 'upstream_co2_intensity'),
        index=mod.FUELS,
        param=(mod.f_co2_intensity, mod.f_upstream_co2_intensity))
    # Optional parameters with default values can have values of 'default' in
    # the input file. Find and delete those entries to prevent type errors.
    for f in switch_data.data(name='FUELS'):
        if switch_data.data(name='f_upstream_co2_intensity')[f] == 'default':
            del switch_data.data(name='f_upstream_co2_intensity')[f]
    switch_data.load(
        filename=os.path.join(inputs_directory, 'regional_fuel_markets.tab'),
        select=('regional_fuel_market', 'fuel'),
        index=mod.REGIONAL_FUEL_MARKET,
        param=(mod.rfm_fuel))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'fuel_supply_curves.tab'),
        select=('regional_fuel_market', 'period', 'tier', 'unit_cost',
                'max_avail_at_cost'),
        index=mod.RFM_SUPPLY_TIERS,
        param=(mod.rfm_supply_tier_cost, mod.rfm_supply_tier_limit))
    switch_data.load(
        filename=os.path.join(
            inputs_directory, 'lz_to_regional_fuel_market.tab'),
        set=mod.LZ_RFM)
    # Load load zone fuel cost adder data if the file is available.
    lz_fuel_cost_adder_path = os.path.join(
        inputs_directory, 'lz_fuel_cost_diff.tab')
    if os.path.isfile(lz_fuel_cost_adder_path):
        switch_data.load(
            filename=lz_fuel_cost_adder_path,
            select=('load_zone', 'fuel', 'period', 'fuel_cost_adder'),
            param=(mod.lz_fuel_cost_adder))

    # Load a simple specifications of costs if the file exists. The
    # actual loading, error checking, and casting into a supply curve is
    # slightly complicated, so I moved that logic to a separate function.
    simple_cost_path = os.path.join(inputs_directory, 'lz_simple_fuel_cost.tab')
    if os.path.isfile(simple_cost_path):
        _load_simple_cost_data(mod, switch_data, simple_cost_path)


def _load_simple_cost_data(mod, switch_data, simple_cost_path):
    with open(simple_cost_path, 'rb') as simple_cost_file:
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
            if p not in switch_data.data(name='INVEST_PERIODS'):
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
                        "' was already registered with the regional fuel" +
                        "market '" + mod.lz_rfm[lz, f] + "', so you cannot " +
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
