# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines model components to describe generation technologies for the
SWITCH-Pyomo model.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
import csv
from pyomo.environ import *


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe
    generators and storage technologies. Unless otherwise stated, each
    set and parameter is mandatory.

    GENERATION_TECHNOLOGIES is a set of all generation and storage
    technologies. It is abbreviated as gen for parameter names and g for
    indexes. By default, certain attributes of a generation technology
    such as heat rates and maximum lifetime remain constant over time,
    while cost attributes may change over time. If you expect those
    constant attributes of generation technologies to actually change in
    the future (such as improved heat rates or reduced outage rates),
    you could model those improvements as additional technologies, or
    you could edit the model to index those attribute by year. Members
    of this set are abbreviated as g or gt in parameter names and
    indexes.

    g_dbid[g] is an optional parameter that stores an external
    database id for each generation technology.

    G_ENERGY_SOURCES[g] is an indexed set of the energy sources a
    generator or storage plant can consume. Most traditional generators
    can be modeled as consuming a single primary energy source such as
    Natural Gas or Coal, even if they consume significant amounts of
    electricity from the grid for their internal loads. Other generators
    need to explicitly be modeled as consuming multiple energy sources.
    Pumped Hydro has two primary energy sources: water from the upstream
    river and electricity from the grid. Similarly, Compressed Air
    Energy Storage with natural gas combustion turbines consume natural
    gas and electricity. Pure storage projects consume electricity, but
    under a Renewable Portfolio Standards, the electricity may be
    classified further as Renewable or NonRenewable. Many oil generators
    require distillate fuel oil for starting up, but can transition to
    cheaper residual fuel oil or potentially more renewable crude plant
    oils after they are warmed up. Some coal plants are cofired with
    biomass... To support all of these situations, any generator may
    have multiple energy sources.

    g_uses_fuel[g] is a derived binary parameter that is True if a
    generator uses a fuel to produce electricity. Generators with this
    flag set are expected to have a heat rate.

    FUEL_BASED_GEN is a subset of GENERATION_TECHNOLOGIES for which
    g_uses_fuel is true.

    g_max_age[g] is how many years a plant can remain operational once
    construction is complete.

    g_min_build_capacity[g] describes the smallest project size in MW
    that can be built. This is most relevant for existing civilian
    nuclear technologies that are not economically or technically
    feasible below a certain size. This is an optional parameter with a
    default of 0.

    g_scheduled_outage_rate[g] is the fraction of time that this type of
    generator is expected to be down for scheduled maintenance.
    Load-zone wide capacity available for dispatch is derated by this
    factor to reflect the fraction of generation that will be down at
    any given time. The model could alternatively be written to include
    more specific scheduled maintenance requirements and attempt to
    coordinate scheduled maintenance with load and other generators.
    This factor is not used for capacity reserve margins because we
    assume that scheduled maintenance can be scheduled at a time other
    than peak load.

    g_forced_outage_rate[g] is the fraction of time that this type of
    generator is expected to be down for unscheduled maintenance. The
    installed capacity available for dispatch in a load zone is derated
    by this factor, as is the contribution to capacity reserve margins
    because these outages cannot be scheduled. We think this methodology
    of using expected forced outage rates is reasonable for long-term
    planning, but may need to be replaced with a more rigorous security
    analysis for detailed operations or trueing up an overall investment
    portfolio.

    NOTE: The generator designations of variable, baseload, flexible
    baseload and dispatchable are all mutually exclusive. A generator
    can only belong to one of these categories because they imply
    different operational regimes.

    g_is_variable[g] is a binary flag indicating whether a generator is a
    variable renewable resource that provides generation on a "use-it-
    or-lose-it" basis. Key examples of variable technologies are solar
    panels and wind turbines. Run-of-river hydro may fall into this
    category, depending on the specific definition being used.

    g_is_baseload[g] is a binary flag indicating whether a generation
    technology needs to be operated constantly at maximum capacity in
    "baseload" mode. Several coal, geothermal and nuclear plants fall
    into this category.

    g_is_flexible_baseload[g] is a binary flag indicating whether a
    generation technology needs to to be operated with constant output
    from hour to hour, but its output can be varied from day to day.
    Some coal plants fall into this category.

    g_is_dispatchable[g] is a binary flag indicating whether a generation
    technology can be ramped up or down to a large degree from hour to
    hour.

    g_is_cogen[g] is a binary flag indicating whether a generation
    technology is a combined heat and power plant that cogenerates heat
    with electricity. A related parameter cogen_thermal_demand[p] can be
    defined for projects of this type.

    g_competes_for_space[g] is a binary flag indicating whether a
    generation technology competes for space with other generation
    technologies. A driving example is that one plot of land can only
    support so many solar panels or solar-powered steam generators.
    Projects that compete for space have additional parameters defined
    in the projects module. This is an optional parameter with a default
    of False.

    GEN_TECH_WITH_UNIT_SIZES is a subset of GENERATION_TECHNOLOGIES for
    which the size of individual units, or generators, is specified.

    g_unit_size[g in GEN_TECH_WITH_UNIT_SIZES] specifies the unit size
    of individual generators in MW of nameplate capacity. This parameter
    is optional in general, but is required if you wish to enforce
    discrete build or unit commitment decisions. This could have been
    defined for all generation technologies with a default value of 0,
    but I'm very uncomfortable stuffing generator attributes into data
    values instead of separate explicit flags. If you wanted to use this
    parameter to determine the number of units that are needed to build
    a given amount of capacity, a zero-value would generate a divide-by-
    zero error. You could elaborate the code to look for which
    technologies have a value of 0 for this parameter and take
    appropriate action in those cases. However, if there needs to be
    custom logic to handle this, it's better to be clear and exlicit
    rather than relying on implicit encoding.

    STORAGE_TECHNOLOGIES is a subset of GENERATION_TECHNOLOGIES that can
    store electricity for later discharge. STORAGE_TECHNOLOGIES consume
    electricity and possibly additional energy sources such as upstream
    water in the case of pumped hydro. If a technology is storage, then
    SWITCH preprocessing will augment the ENERGY_SOURCES[g] list to
    include electricity. If Renewable Portfolio Standards are enabled,
    SWITCH preprocessing will separate electricity into RPS-eligible and
    non-RPS-eligible categories. The following two parameters are only
    defined for storage technologies.

    g_storage_efficiency[g] describes the round trip efficiency of a
    storage technology. A storage technology that is 75 percent
    efficient would have a storage_efficiency of .75. If 1 MWh was
    stored in such a storage project, 750 kWh would be available for
    extraction later. Internal leakage or energy dissipation of storage
    technologies is assumed to be neglible, which is consistent with
    short-duration storage technologies currently on the market which
    tend to consume stored power within 1 day. If a given storage
    technology has significant internal discharge when it stores power
    for extended time perios, then those behaviors will need to be
    modeled in more detail.

    g_store_to_release_ratio[g] describes the maximum rate that energy
    can be stored, expressed as a ratio of discharge power capacity. If
    a storage project has 1 MW of dischage capacity and a max_store_rate
    of 1.2, then it can consume up to 1.2 MW of power while charging.

    CCS_TECHNOLOGIES is a subset of generation technologies that
    use Carbon Capture and Sequestration (CCS). The model assumes
    that all CCS technologies combust fuels such as coal, natural gas or
    biomass. The following two parameters are only defined for CCS
    technologies.

    g_ccs_capture_efficiency[g] is the fraction of CO2 captured from
    smokestacks.

    g_ccs_energy_load[g] is the fraction of a plant's output needed to
    operate the CCS equipment. If a generator with a nameplate capacity
    of 1 MW consumes 0.3 MW to operate CCS equipment, this factor would
    be 0.3. In past versions of SWITCH, this energy load was modeled as
    a distinct heat rate for the plant that was higher than a non-CCS
    version of the plant. I felt this new formulation allowed for more
    explicit accounting of CCS operations and simplified analysis of new
    proposed CCS technologies.

    --- COST COMPONENTS ---

    NEW_GENERATION_BUILDYEARS is a two-dimensional set of generation and
    investment periods [g, p] that describe when new generators can be
    built. This set effectively replaces the min_online_year and
    construction_time_years from the ampl versions of SWITCH. The
    following default cost components are indexed by this set. These
    generic costs may be overridden by individual projects, and are
    often overridden for existing plants that were built before the
    first investment period.

    g_overnight_cost[g, p] is the overnight capital cost per MW of
    capacity for building the given generation technology installed in
    the given period. By "installed in the given period", I mean that it
    comes online at the beginning of the given period and construction
    starts before that.

    g_fixed_o_m[g, p] is the fixed Operations and Maintenance costs (O&M)
    per MW of installed capacity for given generation technology that
    was installed in the given period.

    g_variable_o_m[g] is the variable Operations and Maintenance costs
    (O&M) per MWh of dispatched capacity for given generation technology.
    This is assumed to remain constant over time.

    g_full_load_heat_rate[g in FUEL_BASED_GEN] provides the default full
    load heat rate of a generation technology in units of MMBTU per MWh.
    Specific projects may override this heat rate. This is optional, but
    if you don't supply a value, then you must specify a heat for each
    project of this type.

    --- DELAYED IMPLEMENATION ---

    The following parameters are not implemented at this time.

    g_energy_capacity_overnight_cost[g, y] is the overnight capital cost
    per MWh of energy capacity for building the given storage technology
    installed in the given year. This is only defined for storage
    technologies. Note that this describes the energy component and the
    overnight_cost describes the power component.

    other storage cost components: Separate storage power cap from
    release power cap. decided whether to implement compound projects
    that link storage and non-storage components that are each a project
    or hybrid augmented projects that are multi-energy soure with
    storage and non-storage.

    g_construction_schedule[g,y] Describes which fraction of overnight
    cost of capital is spent in each year of construction from year 1
    through completion. This frequently has a small impact on the
    overall cost of construction because interest on loans taken early
    in the process have to be paid during construction. For simplicity,
    this assumes the overnight cost of capital has been adjusted to
    reflect these costs, which is consistent with the assumption that
    all expenses are incurred in the last construction year.

    g_max_spinning_reserve_fraction[g] is the maximum fraction of a
    generator's capacity that can be dedicated to spinning reserves. In
    general, the amount of capacity that can be provided for spinning
    reserves is the generator's 10-minute ramp rate.


    """

    mod.GENERATION_TECHNOLOGIES = Set()
    mod.g_dbid = Param(mod.GENERATION_TECHNOLOGIES)
    mod.g_max_age = Param(
        mod.GENERATION_TECHNOLOGIES, within=PositiveReals)
    mod.g_scheduled_outage_rate = Param(
        mod.GENERATION_TECHNOLOGIES, within=PercentFraction)
    mod.g_forced_outage_rate = Param(
        mod.GENERATION_TECHNOLOGIES, within=PercentFraction)
    mod.g_is_variable = Param(
        mod.GENERATION_TECHNOLOGIES, within=Boolean)
    mod.g_is_baseload = Param(
        mod.GENERATION_TECHNOLOGIES, within=Boolean)
    mod.g_is_flexible_baseload = Param(
        mod.GENERATION_TECHNOLOGIES, within=Boolean)
    mod.g_is_dispatchable = Param(
        mod.GENERATION_TECHNOLOGIES, within=Boolean)
    mod.g_is_cogen = Param(
        mod.GENERATION_TECHNOLOGIES, within=Boolean)
    mod.g_min_build_capacity = Param(
        mod.GENERATION_TECHNOLOGIES, within=NonNegativeReals,
        default=0)
    mod.g_competes_for_space = Param(
        mod.GENERATION_TECHNOLOGIES, within=Boolean,
        default=0)

    mod.GEN_TECH_WITH_UNIT_SIZES = Set(
        within=mod.GENERATION_TECHNOLOGIES)
    mod.g_unit_size = Param(
        mod.GEN_TECH_WITH_UNIT_SIZES,
        within=PositiveReals)

    mod.G_ENERGY_SOURCES = Set(
        mod.GENERATION_TECHNOLOGIES, within=mod.ENERGY_SOURCES)
    mod.g_uses_fuel = Param(
        mod.GENERATION_TECHNOLOGIES,
        initialize=lambda m, g: len(
            set(m.G_ENERGY_SOURCES[g]) & set(m.FUELS)) > 0)
    mod.FUEL_BASED_GEN = Set(
        initialize=mod.GENERATION_TECHNOLOGIES,
        filter=lambda m, g: m.g_uses_fuel[g])

    mod.STORAGE_TECHNOLOGIES = Set(within=mod.GENERATION_TECHNOLOGIES)
    mod.g_storage_efficiency = Param(
        mod.STORAGE_TECHNOLOGIES, within=PercentFraction)
    mod.g_store_to_release_ratio = Param(
        mod.STORAGE_TECHNOLOGIES, within=PositiveReals)

    mod.CCS_TECHNOLOGIES = Set(within=mod.GENERATION_TECHNOLOGIES)
    mod.g_ccs_capture_efficiency = Param(
        mod.CCS_TECHNOLOGIES, within=PercentFraction)
    mod.g_ccs_energy_load = Param(
        mod.CCS_TECHNOLOGIES, within=PercentFraction)

    # New generation vintages need to be within the cross product of
    # generation technologies and investment periods.
    mod.NEW_GENERATION_BUILDYEARS = Set(
        dimen=2,
        within=mod.GENERATION_TECHNOLOGIES * mod.PERIODS)
    mod.g_overnight_cost = Param(
        mod.GENERATION_TECHNOLOGIES, mod.PERIODS,
        within=NonNegativeReals)
    mod.g_fixed_o_m = Param(
        mod.GENERATION_TECHNOLOGIES, mod.PERIODS,
        within=NonNegativeReals)
    mod.g_variable_o_m = Param(
        mod.GENERATION_TECHNOLOGIES,
        within=NonNegativeReals)

    mod.g_full_load_heat_rate = Param(
        mod.FUEL_BASED_GEN,
        within=PositiveReals)

    mod.min_data_check(
        'GENERATION_TECHNOLOGIES', 'g_dbid',
        'g_max_age', 'g_min_build_capacity',
        'g_scheduled_outage_rate', 'g_forced_outage_rate',
        'g_is_variable', 'g_is_baseload',
        'g_is_flexible_baseload', 'g_is_dispatchable', 'g_is_cogen',
        'g_competes_for_space', 'G_ENERGY_SOURCES')

    # Make sure no generator has an empty list of energy sources
    mod.mandatory_energy_source = BuildCheck(
        mod.GENERATION_TECHNOLOGIES,
        rule=lambda m, g: len(m.G_ENERGY_SOURCES[g]) > 0)
    # Quick hack to mandate each technology has a single energy source
    mod.single_energy_source = BuildCheck(
        mod.GENERATION_TECHNOLOGIES,
        rule=lambda m, g: len(m.G_ENERGY_SOURCES[g]) == 1)


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import generator data. The following files are expected in the input
    directory:

    The unit size column in generator_info is optional and you can put a
    dot for any row where you do not wish to specify a data value.

    generator_info.tab
        generation_technology, g_dbid, g_max_age, g_min_build_capacity,
        g_scheduled_outage_rate, g_forced_outage_rate,
        g_is_variable, g_is_baseload,
        g_is_flexible_baseload, g_is_dispatchable, g_is_cogen,
        g_competes_for_space, g_variable_o_m

    ccs_info.tab
        generation_technology, g_ccs_capture_efficiency, g_ccs_energy_load

    generator_energy_sources.tab
        generation_technology, energy_source

    gen_new_build_costs is optional in a production cost simulation where
    all projects were built before the start of the first period. In
    that situation, all existing projects could have costs specified in
    project_specific_costs.tab

    gen_new_build_costs.tab
        generation_technology, investment_period,
        g_overnight_cost, g_fixed_o_m

    storage_info does not have to be specified if no storage
    technologies are included in the optimization.

    storage_info.tab
        generation_technology, g_storage_efficiency, g_store_to_release_ratio

    unit_sizes.tab is optional and should only contain entries for
    technologies with valid, non-zero data for g_unit_size.

    unit_sizes.tab
        generation_technology, g_unit_size

    gen_heat_rates.tab
        generation_technology, full_load_heat_rate

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generator_info.tab'),
        select=('generation_technology',
                'g_dbid', 'g_max_age', 'g_min_build_capacity',
                'g_scheduled_outage_rate', 'g_forced_outage_rate',
                'g_is_variable', 'g_is_baseload',
                'g_is_flexible_baseload', 'g_is_dispatchable',
                'g_is_cogen', 'g_competes_for_space', 'g_variable_o_m'),
        index=mod.GENERATION_TECHNOLOGIES,
        param=(
            mod.g_dbid, mod.g_max_age,
            mod.g_min_build_capacity, mod.g_scheduled_outage_rate,
            mod.g_forced_outage_rate,
            mod.g_is_variable, mod.g_is_baseload,
            mod.g_is_flexible_baseload, mod.g_is_dispatchable,
            mod.g_is_cogen, mod.g_competes_for_space, mod.g_variable_o_m))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'gen_new_build_costs.tab'),
        select=('generation_technology', 'investment_period',
                'g_overnight_cost', 'g_fixed_o_m'),
        index=mod.NEW_GENERATION_BUILDYEARS,
        param=(mod.g_overnight_cost, mod.g_fixed_o_m))
    # CCS info is optional because there may not be any CCS technologies
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'ccs_info.tab'),
        select=(
            'generation_technology',
            'g_ccs_capture_efficiency', 'g_ccs_energy_load'),
        index=mod.CCS_TECHNOLOGIES,
        param=(mod.g_ccs_capture_efficiency, mod.g_ccs_energy_load))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'storage_info.tab'),
        select=('generation_technology',
                'g_storage_efficiency', 'g_store_to_release_ratio'),
        index=mod.STORAGE_TECHNOLOGIES,
        param=(mod.g_storage_efficiency, mod.g_store_to_release_ratio))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'unit_sizes.tab'),
        select=('generation_technology', 'g_unit_size'),
        index=mod.GEN_TECH_WITH_UNIT_SIZES,
        param=(mod.g_unit_size))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'gen_heat_rates.tab'),
        select=('generation_technology', 'full_load_heat_rate'),
        param=(mod.g_full_load_heat_rate))
    # Pyomo's DataPortal doesn't work so well with indexed sets like
    # G_ENERGY_SOURCES, so I need to read those in and manually add them
    # to the DataPortal dictionary. I could have added a dummy tuple set
    # of these pairs and used that to initialize G_ENERGY_SOURCES, but
    # that would have added a redundant model component that would need
    # documentation but does not contribute to the logical structure.
    path = os.path.join(inputs_dir, 'generator_energy_sources.tab')
    with open(path, 'rb') as energy_source_file:
        # Initialize the G_ENERGY_SOURCES entry in the DataPortal object
        switch_data.data()['G_ENERGY_SOURCES'] = {}
        G_ENERGY_SOURCES = switch_data.data(name='G_ENERGY_SOURCES')
        # Create an array entry for each generation technology
        for g in switch_data.data(name='GENERATION_TECHNOLOGIES'):
            G_ENERGY_SOURCES[g] = []
        # Read in a 2-variable tuple of generator, energy source
        energy_source_dat = list(
            csv.reader(energy_source_file, delimiter='\t'))
        # Discard the header row
        energy_source_dat.pop(0)
        # import logging
        # logging.warning("energy_source_dat is...")
        # logging.warning(energy_source_dat)
        # Add energy sources to each generator
        for (g, e) in energy_source_dat:
            G_ENERGY_SOURCES[g].append(e)
