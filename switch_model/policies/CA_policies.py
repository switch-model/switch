# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
Module to enforce policies specific to the state of California for the WECC model.

The state of the load zone is determined based on the letters prior to the first underscore.
For example, "CA_PGE_BAY" gives a state code of "CA" and will be considered as part of California.

Three possible policy constraints can be specified in ca_policies.csv. See documentation below.
"""
import os
from pyomo.environ import Set, Param, Expression, Constraint, PercentFraction
import switch_model.reporting as reporting


def define_components(mod):
    """
    load_zone_state[z] is the two-letter state code of a load zone.
    Values are inferred from the prefix of the load_zone id. For
    example, "CA_PGE_BAY" gives a state code of "CA". Note that
    this method isn't perfect. For example, "CAN_ALB" gives a "state"
    code of "CAN".
    If the state value is "CA" this load zone is considered to be
    part of California.
    TODO : Add a column in load_zones.csv with the load_zone's
        two-letter state code and read load_zone_state[z] from there
        instead of trying to infer it from the LOAD_ZONE id. If
        someone plans to implement this, the code was already
        implemented at
        https://github.com/RAEL-Berkeley/switch/tree/a0b80829a8dfad2018cb30f91893687565e0c4fe.
        So you can use that code as starters (database still needs
        updating though).


    carbon_cap_tco2_per_yr_CA[p] is the carbon cap for a given period
    on all CO2 emission generated in load zones within California.

    ca_min_gen_period_ratio[p] sets the fraction of California's
    demand that must be satisfied from generation within California.
    For example, this constraint could specify that over a period,
    at least 80% of California's demand must be supplied by Californian
    projects. Note that we don't do "electron tracking", meaning
    that energy generated in California and transmitted to neighbouring states
    still counts towards satisfying California's demand for this constraint.
    This constraint is applied to the total generation and demand over
    a period.

    ca_min_gen_timepoint_ratio[p] is equivalent to ca_min_gen_period_ratio[p]
    but applies the constraint at every timepoint, rather than over
    an entire period.

    AnnualEmissions_CA[p] is California's emissions throughout a period
    in metric tonnes of CO2 per year. This doesn't account for
    emissions from power imported from outside of California.

    CA_Dispatch[t] is California's generation in MW at a timepoint.

    CA_Demand[t] is California's demand in MW at a timepoint.

    CA_AnnualDispatch[p] is California's total energy generation throughout
    a year in MWh.

    CA_AnnualDemand[p] is California's total energy demand throughout a year in MWh.
    """
    mod.load_zone_state = Param(
        mod.LOAD_ZONES,
        # Returns the letters before the first underscore, if there's no underscore, simply return the entire id
        rule=lambda m, z: z.partition("_")[0],
        doc="Two-letter state code for each load zone inferred from the load zone id.")

    mod.CA_ZONES = Set(initialize=mod.LOAD_ZONES, within=mod.LOAD_ZONES,
                       filter=lambda m, z: m.load_zone_state[z] == "CA",
                       doc="Set of load zones within California.")

    mod.ca_min_gen_timepoint_ratio = Param(mod.PERIODS, within=PercentFraction, default=0,
                                           doc="Fraction of demand that must be satisfied through in-state"
                                               "generation during each timepoint.")

    mod.ca_min_gen_period_ratio = Param(mod.PERIODS, within=PercentFraction, default=0,
                                        doc="Fraction of demand that must be satisfied through in-state"
                                            "generation across an entire period.")

    mod.carbon_cap_tco2_per_yr_CA = Param(mod.PERIODS, default=float('inf'), doc=(
        "Emissions from California must be less than this cap. Specified in metric tonnes of CO2 per year."))

    mod.AnnualEmissions_CA = Expression(mod.PERIODS,
                                        rule=lambda m, period: sum(
                                            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
                                            for (g, t, f) in m.GEN_TP_FUELS
                                            if m.tp_period[t] == period and (
                                                    m.load_zone_state[m.gen_load_zone[g]] == "CA")),
                                        doc="CA's annual emissions, in metric tonnes of CO2 per year.")

    mod.Enforce_Carbon_Cap_CA = Constraint(mod.PERIODS,
                                           rule=lambda m, p: m.AnnualEmissions_CA[p] <= m.carbon_cap_tco2_per_yr_CA[
                                               p],
                                           doc="Enforces the carbon cap for generation-related emissions.")

    mod.CA_Dispatch = Expression(
        mod.TIMEPOINTS,
        # Sum of all power injections except for transmission
        rule=lambda m, t: sum(
            sum(
                getattr(m, component)[z, t] for z in m.CA_ZONES
            ) for component in m.Zone_Power_Injections if component != "TXPowerNet")
    )

    mod.CA_Demand = Expression(
        mod.TIMEPOINTS,
        # Sum of all power withdrawals
        rule=lambda m, t: sum(
            sum(
                getattr(m, component)[z, t] for z in m.CA_ZONES
            ) for component in m.Zone_Power_Withdrawals)
    )

    mod.CA_AnnualDispatch = Expression(mod.PERIODS, rule=lambda m, p: sum(m.CA_Dispatch[t] * m.tp_weight_in_year[t] for t in m.TPS_IN_PERIOD[p]))
    mod.CA_AnnualDemand = Expression(mod.PERIODS, rule=lambda m, p: sum(m.CA_Demand[t] * m.tp_weight_in_year[t] for t in m.TPS_IN_PERIOD[p]))

    mod.CA_Min_Gen_Timepoint_Constraint = Constraint(
        mod.TIMEPOINTS,
        rule=lambda m, t: m.CA_Dispatch[t] >= m.CA_Demand[t] * m.ca_min_gen_timepoint_ratio[m.tp_period[t]]
    )

    mod.CA_Min_Gen_Period_Constraint = Constraint(
        mod.PERIODS,
        rule=lambda m, p: m.CA_AnnualDispatch[p] >= m.ca_min_gen_period_ratio[p] * m.CA_AnnualDemand[p]
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
    Expected input files:
    load_zones.csv
        LOAD_ZONE, load_zone_state

    ca_policies.csv
        PERIOD,ca_min_gen_timepoint_ratio,ca_min_gen_period_ratio,carbon_cap_tco2_per_yr_CA
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ca_policies.csv'),
        optional_params=(mod.ca_min_gen_timepoint_ratio, mod.ca_min_gen_period_ratio, mod.carbon_cap_tco2_per_yr_CA),
        auto_select=True,
        param=(mod.ca_min_gen_timepoint_ratio, mod.ca_min_gen_period_ratio, mod.carbon_cap_tco2_per_yr_CA)
    )


def post_solve(model, outdir):
    """
    Export california's annual emissions and its carbon caps
    for each period.
    """
    reporting.write_table(
        model, model.PERIODS,
        output_file=os.path.join(outdir, "ca_policies.csv"),
        headings=("PERIOD",
                  "AnnualEmissions_tCO2_per_yr_CA", "carbon_cap_tco2_per_yr_CA", "CA_AnnualDispatch", "CA_AnnualDemand",
                  "Dispatch/Demand ratio", "Minimum ratio"),
        values=lambda m, p: [p,
                             m.AnnualEmissions_CA[p],
                             m.carbon_cap_tco2_per_yr_CA[p],
                             m.CA_AnnualDispatch[p],
                             m.CA_AnnualDemand[p],
                             m.CA_AnnualDispatch[p] / m.CA_AnnualDemand[p],
                             m.ca_min_gen_period_ratio[p]
                             ])
