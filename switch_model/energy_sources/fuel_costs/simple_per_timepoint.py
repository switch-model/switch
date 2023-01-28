# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""

A simple description of flat fuel costs for the Switch model that
serves as an alternative to the more complex fuel_markets with tiered
supply curves. This is mutually exclusive with the fuel_markets module.

"""
import os
from pyomo.environ import *

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.energy_sources.properties.properties",
    "switch_model.generators.core.build",
    "switch_model.generators.core.dispatch",
)


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters to
    describe simple fuel costs. Unless otherwise stated, each set and
    parameter is mandatory. Unless otherwise specified, all dollar
    values are real dollars in BASE_YEAR.

    ZONE_FUEL_TIMEPOINTS is a set of (load_zone, fuel, period) for which
    fuel_cost_per_timepoint has been specified.

    fuel_cost_per_timepoint[(z, f, t) in ZONE_FUEL_TIMEPOINTS] describes flat
    fuel costs for each supply of fuel. Costs can vary by load zone and
    timepoint.

    Note that fuels can only be used in the locations and times for which
    fuel_cost_per_timepoint has been specified.

    GEN_TP_FUELS_UNAVAILABLE is a subset of GEN_TP_FUELS that describes which
    points don't have fuel available.

    Enforce_Fuel_Unavailability[(g, t, f) in GEN_TP_FUELS_UNAVAILABLE] is a
    constraint that restricts GenFuelUseRate to 0 for in load zones and periods
    where the projects' fuel is unavailable.

    FuelCostsPerTP[t in TIMEPOINTS] is an expression that summarizes fuel costs
    for the objective function.

    """

    # TODO: maybe rename fuel_cost_per_timepoint component and/or .csv file to fuel_cost
    # (but that could cause confusion in the documentation?)
    mod.ZONE_FUEL_TIMEPOINTS = Set(
        dimen=3,
        validate=lambda m, z, f, p: (
            z in m.LOAD_ZONES and f in m.FUELS and p in m.TIMEPOINTS
        ),
    )
    mod.fuel_cost_per_timepoint = Param(
        mod.ZONE_FUEL_TIMEPOINTS, within=NonNegativeReals
    )
    mod.min_data_check("ZONE_FUEL_TIMEPOINTS", "fuel_cost_per_timepoint")

    # don't allow use of a fuel when no cost has been specified
    mod.GEN_TP_FUELS_UNAVAILABLE = Set(
        dimen=3,
        initialize=mod.GEN_TP_FUELS,
        filter=lambda m, g, t, f: (m.gen_load_zone[g], f, t)
        not in m.ZONE_FUEL_TIMEPOINTS,
    )
    mod.Enforce_Fuel_Unavailability = Constraint(
        mod.GEN_TP_FUELS_UNAVAILABLE,
        rule=lambda m, g, t, f: m.GenFuelUseRate[g, t, f] == 0,
    )

    # Summarize total fuel costs in each timepoint for the objective function
    def FuelCostsPerTP_rule(m, t):
        if not hasattr(m, "FuelCostsPerTP_dict"):
            # cache all Fuel_Cost_TP values in a dictionary (created in one pass)
            m.FuelCostsPerTP_dict = {t2: 0.0 for t2 in m.TIMEPOINTS}
            for (g, t2, f) in m.GEN_TP_FUELS:
                if (g, t2, f) not in m.GEN_TP_FUELS_UNAVAILABLE:
                    m.FuelCostsPerTP_dict[t2] += (
                        m.GenFuelUseRate[g, t2, f]
                        * m.fuel_cost_per_timepoint[m.gen_load_zone[g], f, t2]
                    )
        # return a result from the dictionary and pop the element each time
        # to release memory
        return m.FuelCostsPerTP_dict.pop(t)

    mod.FuelCostsPerTP = Expression(mod.TIMEPOINTS, rule=FuelCostsPerTP_rule)
    mod.Cost_Components_Per_TP.append("FuelCostsPerTP")


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import simple fuel cost data. The following file is expected in
    the input directory:

    fuel_cost_per_timepoint.csv
        load_zone, fuel, period, fuel_cost_per_timepoint

    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "fuel_cost_per_timepoint.csv"),
        index=mod.ZONE_FUEL_TIMEPOINTS,
        param=[mod.fuel_cost_per_timepoint],
    )
