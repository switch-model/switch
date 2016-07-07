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

#>>> instance.pprint()

"""

import os
from pyomo.environ import *


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe
    generators and storage technologies. Unless otherwise stated, each
    set and parameter is mandatory. Many attributes describing a
    generation technology are optional and provide default values that
    individual projects may override.

    GENERATION_TECHNOLOGIES is a set of all generation and storage
    technologies. By default, certain attributes of a generation
    technology such as heat rates and maximum lifetime remain constant
    over time, while cost attributes may change over time. If you expect
    those constant attributes of generation technologies to actually
    change in the future (such as improved heat rates or reduced outage
    rates), you could model those improvements as additional
    technologies, or you could edit the model to index those attribute
    by year. Members of this set are abbreviated as gen and g in
    parameter names and indexes.

    g_dbid[g] is an optional parameter that stores an external
    database id for each generation technology. This is used for
    reporting results and defaults to g.

    g_energy_source[g] is a mandatory parameter that defines the primary
    energy source used by each generator. For generation technologies
    with one primary energy source, g_energy_source specifies that energy 
    source, and should be a member of the set ENERGY_SOURCES. If a generator 
    uses multiple energy sources, then g_energy_source should be set to 
    "multiple", and the energy sources should be specified in 
    generator_multi_fuel.tab. This can be used to support generators like
    pumped hydro that consumes either upstream water or electricity for
    storage, or compressed air energy storage that consumes electricity
    for storage and natural gas, or oil generators that need to start
    with high-quality distilled oil but can subsequently shift to low-
    quality residual fuel oil, or plants that can run on either oil or LNG. 

    g_uses_fuel[g] is a derived binary parameter that is True if a
    generator uses a fuel to produce electricity. Generators with this
    flag set are expected to have a heat rate.

    GEN_TECH_WITH_FUEL is a subset of GENERATION_TECHNOLOGIES for which
    g_uses_fuel is true.
    
    GEN_TECH_WITH_MULTI_FUEL is a subset of GENERATION_TECHNOLOGIES for 
    which multiple allowed fuels have been specified.
    
    G_FUELS is a list of all allowed fuels for each fuel-consuming 
    generator technology. It may contain one or more fuels for each
    technology.

    g_max_age[g] is how many years a plant can remain operational once
    construction is complete.

    g_min_build_capacity[g] describes the smallest project size in MW
    that can be built. This is most relevant for existing civilian
    nuclear technologies that are not economically or technically
    feasible below a certain size. This is an optional parameter with a
    default of 0.

    g_scheduled_outage_rate[g] is the fraction of time that this type of
    generator is expected to be down for scheduled maintenance. This
    optional parameter supplies default values for all projects of this
    technology. Load-zone wide capacity available for dispatch is
    derated by this factor to reflect the fraction of generation that
    will be down at any given time. The model could alternatively be
    written to include more specific scheduled maintenance requirements
    and attempt to coordinate scheduled maintenance with load and other
    generators. This factor is not used for capacity reserve margins
    because we assume that scheduled maintenance can be scheduled at a
    time other than peak load.

    g_forced_outage_rate[g] is the fraction of time that this type of
    generator is expected to be down for unscheduled maintenance. This
    optional parameter supplies default values for all projects of this
    technology. The installed capacity available for dispatch in a load
    zone is derated by this factor, as is the contribution to capacity
    reserve margins because these outages cannot be scheduled. We think
    this methodology of using expected forced outage rates is reasonable
    for long-term planning, but may need to be replaced with a more
    rigorous security analysis for detailed operations or trueing up an
    overall investment portfolio.

    NOTE: The generator designations of variable, baseload, and flexible
    baseload are all mutually exclusive. A generator may only belong to
    one of these categories because they imply different operational
    regimes.

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

    GEN_TECH_STORAGE is a subset of GENERATION_TECHNOLOGIES that can
    store electricity for later discharge. GEN_TECH_STORAGE consume
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

    GEN_TECH_CCS is a subset of generation technologies that
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
    
    G_NEW_BUILD_YEARS[g] describes the periods in which new builds are allowed
    for each generation type. This is the same information as 
    NEW_GENERATION_BUILDYEARS, but indexed by generation for convenience.

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

    g_full_load_heat_rate[g in GEN_TECH_WITH_FUEL] provides the default full
    load heat rate of a generation technology in units of MMBTU per MWh.
    Specific projects may override this heat rate. This is optional, but
    if you don't supply a value, then you must specify a heat for each
    project of this type.

    G_MULTI_FUELS is an indexed set showing all the fuels that can be used by
    each multi-fuel generation technology. If a list is specified here, then
    g_energy_source should be set to "multiple".

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
    mod.g_dbid = Param(
        mod.GENERATION_TECHNOLOGIES,
        default=lambda m, g: g)
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

    mod.g_energy_source = Param(
        mod.GENERATION_TECHNOLOGIES,
        validate=lambda m, val, g: val in m.ENERGY_SOURCES or val == "multiple")
    mod.g_uses_fuel = Param(
        mod.GENERATION_TECHNOLOGIES,
        initialize=lambda m, g: 
            m.g_energy_source[g] in m.FUELS or m.g_energy_source[g] == "multiple")
    mod.GEN_TECH_WITH_FUEL = Set(
        initialize=mod.GENERATION_TECHNOLOGIES,
        filter=lambda m, g: m.g_uses_fuel[g])
    mod.GEN_TECH_WITH_MULTI_FUEL = Set(
        initialize=mod.GENERATION_TECHNOLOGIES,
        filter=lambda m, g: m.g_energy_source[g] == "multiple")
    mod.G_MULTI_FUELS = Set(mod.GEN_TECH_WITH_MULTI_FUEL, within=mod.FUELS)
    mod.G_FUELS = Set(mod.GEN_TECH_WITH_FUEL, initialize=lambda m, g:
        m.G_MULTI_FUELS[g] if m.g_energy_source[g] == "multiple" else [m.g_energy_source[g]])

    mod.GEN_TECH_STORAGE = Set(within=mod.GENERATION_TECHNOLOGIES)
    mod.g_storage_efficiency = Param(
        mod.GEN_TECH_STORAGE, within=PercentFraction)
    mod.g_store_to_release_ratio = Param(
        mod.GEN_TECH_STORAGE, within=PositiveReals)

    mod.GEN_TECH_CCS = Set(within=mod.GENERATION_TECHNOLOGIES)
    mod.g_ccs_capture_efficiency = Param(
        mod.GEN_TECH_CCS, within=PercentFraction)
    mod.g_ccs_energy_load = Param(
        mod.GEN_TECH_CCS, within=PercentFraction)

    # New generation vintages need to be within the cross product of
    # generation technologies and investment periods.
    mod.NEW_GENERATION_BUILDYEARS = Set(
        dimen=2,
        within=mod.GENERATION_TECHNOLOGIES * mod.PERIODS)
    mod.G_NEW_BUILD_YEARS = Set(
        mod.GENERATION_TECHNOLOGIES,
        initialize=lambda m, g: set(
            b for (gen, b) in m.NEW_GENERATION_BUILDYEARS if gen == g))
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
        mod.GEN_TECH_WITH_FUEL,
        within=NonNegativeReals)

    mod.min_data_check(
        'GENERATION_TECHNOLOGIES',
        'g_max_age',
        'g_is_variable', 'g_is_baseload',
        'g_is_flexible_baseload', 'g_is_cogen',
        'g_energy_source')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import generator data. The following files are expected in the input
    directory. You may drop optional columns, or put a dot . in rows
    for which you do not wish to specify data. Some other modules may look
    for additional columns in generator_info.tab.

    generator_info.tab has a mix of mandatory and optional columns. The
    mandatory columns are:
        generation_technology, g_max_age,
        g_is_variable, g_is_baseload,
        g_is_flexible_baseload, g_is_cogen,
        g_competes_for_space, g_variable_o_m, g_energy_source

    The optional columns are:
        g_dbid, g_scheduled_outage_rate, g_forced_outage_rate,
        g_min_build_capacity, g_full_load_heat_rate, g_unit_size,
        g_ccs_capture_efficiency, g_ccs_energy_load,
        g_storage_efficiency, g_store_to_release_ratio

    Note: The model does not yet support CCS or storage. Those columns
    exist primarily as place-holders for now. CCS is mostly written, but
    untested. Storage is not written.

    gen_new_build_costs is optional to support production cost
    simulations where all projects were built before the start of the
    first period. In that context, all existing projects could
    reasonably have costs specified in proj_build_costs.tab

    gen_new_build_costs.tab
        generation_technology, investment_period,
        g_overnight_cost, g_fixed_o_m

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generator_info.tab'),
        auto_select=True,
        optional_params=[
            'g_unit_size', 'g_scheduled_outage_rate', 'g_forced_outage_rate',
            'g_ccs_capture_efficiency', 'g_ccs_energy_load',
            'g_storage_efficiency', 'g_store_to_release_ratio'],
        index=mod.GENERATION_TECHNOLOGIES,
        param=(
            mod.g_dbid, mod.g_max_age, mod.g_min_build_capacity,
            mod.g_scheduled_outage_rate, mod.g_forced_outage_rate,
            mod.g_is_variable, mod.g_is_baseload,
            mod.g_is_flexible_baseload, mod.g_is_cogen,
            mod.g_competes_for_space, mod.g_variable_o_m,
            mod.g_energy_source, mod.g_full_load_heat_rate,
            mod.g_unit_size, mod.g_ccs_capture_efficiency,
            mod.g_ccs_energy_load, mod.g_storage_efficiency,
            mod.g_store_to_release_ratio))
    # Construct sets of storage and CCS technologies as well as
    # technologies with discrete unit sizes.
    if 'g_unit_size' in switch_data.data():
        switch_data.data()['GEN_TECH_WITH_UNIT_SIZES'] = {
            None: switch_data.data(name='g_unit_size').keys()
        }
    if 'g_ccs_capture_efficiency' in switch_data.data():
        switch_data.data()['GEN_TECH_CCS'] = {
            None: switch_data.data(name='g_ccs_capture_efficiency').keys()
        }
    if 'g_storage_efficiency' in switch_data.data():
        switch_data.data()['GEN_TECH_STORAGE'] = {
            None: switch_data.data(name='g_storage_efficiency').keys()
        }
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'gen_new_build_costs.tab'),
        auto_select=True,
        index=mod.NEW_GENERATION_BUILDYEARS,
        param=[mod.g_overnight_cost, mod.g_fixed_o_m])

    # read G_MULTI_FUELS from gen_multiple_fuels.dat if available
    multi_fuels_path = os.path.join(inputs_dir, 'gen_multiple_fuels.dat')
    if os.path.isfile(multi_fuels_path):
        switch_data.load(filename=multi_fuels_path)
