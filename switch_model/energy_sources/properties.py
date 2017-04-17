# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe both fuels and non-fuel energy sources
for the SWITCH-Pyomo model.

"""

import os
from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones'

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

    """

    mod.NON_FUEL_ENERGY_SOURCES = Set()
    mod.FUELS = Set()
    mod.f_co2_intensity = Param(mod.FUELS, within=NonNegativeReals)
    mod.f_upstream_co2_intensity = Param(
        mod.FUELS, within=Reals, default=0)
    mod.min_data_check('f_co2_intensity')
    # Ensure that fuel and non-fuel sets have no overlap.
    mod.e_source_is_fuel_or_not_check = BuildCheck(
        rule=lambda m: len(m.FUELS & m.NON_FUEL_ENERGY_SOURCES) == 0)

    # ENERGY_SOURCES is the union of fuel and non-fuels sets. Pipe | is
    # the union operator for Pyomo sets.
    mod.ENERGY_SOURCES = Set(
        initialize=mod.NON_FUEL_ENERGY_SOURCES | mod.FUELS)
    mod.min_data_check('ENERGY_SOURCES')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import fuel data. To skip optional parameters such as
    upstream_co2_intensity, put a dot . in the relevant cell rather than
    leaving them blank. Leaving a cell blank will generate an error
    message like "IndexError: list index out of range". The following
    files are expected in the input directory. Each is optional because
    you could have either an all-renewable or all-fuel-based system, but
    the model will generate an error if no energy sources are available.

    Note: non_fuel_energy_sources serves to check for data entry errors.
    This could be theoretically derived from any energy sources in the
    generator_energy_sources file that are not listed in the fuels
    table, but that would mean any mispelled fuel or fuel that was
    unlisted in fuels.tab would be automatically classified as a free
    renewable source.

    non_fuel_energy_sources.tab
        energy_source

    fuels.tab
        fuel, co2_intensity, upstream_co2_intensity

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'non_fuel_energy_sources.tab'),
        set=('NON_FUEL_ENERGY_SOURCES'))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'fuels.tab'),
        select=('fuel', 'co2_intensity', 'upstream_co2_intensity'),
        index=mod.FUELS,
        param=(mod.f_co2_intensity, mod.f_upstream_co2_intensity))
