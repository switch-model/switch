# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
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


infinity = float("inf")


def timepoint_fuel_cost(m, z, f, t):
    """
    Report cost of fuel f in zone z during timepoint t.
    This returns the fuel_cost_per_timepoint if available, otherwise the
    fuel_cost_per_period if available, otherwise infinity.
    """
    try:
        return m.fuel_cost_per_timepoint[z, f, t]
    except KeyError:
        try:
            return m.fuel_cost[z, f, m.tp_period[t]]
        except KeyError:
            return infinity


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters to
    describe simple fuel costs. Unless otherwise stated, each set and
    parameter is mandatory. Unless otherwise specified, all dollar
    values are real dollars in BASE_YEAR.

    ZONE_FUEL_PERIODS is a set of (load_zone, fuel, period) for which fuel_cost
    has been provided. Can be overridden by fuel_cost_per_period.

    fuel_cost[(z, f, p) in ZONE_FUEL_PERIODS] describes flat fuel costs
    for each supply of fuel. Costs can vary by load zone and period.

    ZONE_FUEL_TIMEPOINTS is a set of (load_zone, fuel, period) for which
    fuel_cost_per_timepoint has been specified.

    fuel_cost_per_timepoint[(z, f, t) in ZONE_FUEL_TIMEPOINTS] describes flat
    fuel costs for each supply of fuel. Costs can vary by load zone and
    timepoint. Overrides per-period fuel_cost if both are specified.

    Note that fuels can only be used in the locations and times for which
    fuel_cost and/or fuel_cost_per_timepoint have been specified.

    GEN_TP_FUELS_UNAVAILABLE is a subset of GEN_TP_FUELS that describes which
    points don't have fuel available.

    Enforce_Fuel_Unavailability[(g, t, f) in GEN_TP_FUELS_UNAVAILABLE] is a
    constraint that restricts GenFuelUseRate to 0 for in load zones and periods
    where the projects' fuel is unavailable.

    FuelCostsPerTP[t in TIMEPOINTS] is an expression that summarizes fuel costs
    for the objective function.

    """

    mod.ZONE_FUEL_PERIODS = Set(
        dimen=3,
        validate=lambda m, z, f, p: (
            z in m.LOAD_ZONES and f in m.FUELS and p in m.PERIODS
        ),
    )
    mod.fuel_cost = Param(
        mod.ZONE_FUEL_PERIODS, within=NonNegativeReals, default=infinity
    )  # specify a default to make column optional
    mod.ZONE_FUEL_TIMEPOINTS = Set(
        dimen=3,
        validate=lambda m, z, f, p: (
            z in m.LOAD_ZONES and f in m.FUELS and p in m.TIMEPOINTS
        ),
    )
    mod.fuel_cost_per_timepoint = Param(
        mod.ZONE_FUEL_TIMEPOINTS, within=NonNegativeReals, default=infinity
    )
    # note: this could be done more neatly by defining fuel_cost_per_timepoint
    # for all LOAD_ZONES, FUELS and TIMEPOINTS, with a default equal to the
    # per-period fuel_cost, which in turn defaults to infinity. But that would
    # create a large parameter that is not needed in most models.

    def Specify_Fuel_Cost_rule(m):
        if not m.ZONE_FUEL_PERIODS and not m.ZONE_FUEL_TIMEPOINTS:
            raise ValueError(
                "You must provide at least one fuel cost value in "
                "fuel_cost.csv and/or fuel_cost_per_timepoint.csv "
                "when using the {} module.".format(__name__)
            )

    mod.Specify_Fuel_Cost = BuildAction(rule=Specify_Fuel_Cost_rule)

    mod.GEN_TP_FUELS_UNAVAILABLE = Set(
        initialize=mod.GEN_TP_FUELS,
        filter=lambda m, g, t, f: timepoint_fuel_cost(m, m.gen_load_zone[g], f, t)
        == infinity,
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
                    m.FuelCostsPerTP_dict[t2] += m.GenFuelUseRate[
                        g, t2, f
                    ] * timepoint_fuel_cost(m, m.gen_load_zone[g], f, t2)
        # return a result from the dictionary and pop the element each time
        # to release memory
        result = m.FuelCostsPerTP_dict.pop(t)
        if not m.FuelCostsPerTP_dict:
            del m.FuelCostsPerTP_dict  # remove empty dict
        return result

    mod.FuelCostsPerTP = Expression(mod.TIMEPOINTS, rule=FuelCostsPerTP_rule)
    mod.Cost_Components_Per_TP.append("FuelCostsPerTP")


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import simple fuel cost data. At least one of the following files should be
    in the input directory (if not, no fuels will be available):

    # per-period fuel costs
    fuel_cost.csv
        load_zone, fuel, period, fuel_cost

    # per-timepoint fuel costs (experimental/untested)
    fuel_cost_per_timepoint.csv
        load_zone, fuel, period, fuel_cost_per_timepoint
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "fuel_cost.csv"),
        autoselect=True,
        index=mod.ZONE_FUEL_PERIODS,
        optional=True,
        param=[mod.fuel_cost],
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "fuel_cost_per_timepoint.csv"),
        autoselect=True,
        index=mod.ZONE_FUEL_TIMEPOINTS,
        optional=True,
        param=[mod.fuel_cost_per_timepoint],
    )
