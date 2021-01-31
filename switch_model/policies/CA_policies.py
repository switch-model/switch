# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
Module to enforce policies specific to the state of California for the WECC model.

Module reads the load_zone_state column from load_zones.csv. If the state is "CA"
this will be considered a load zone in California and the following policies will apply.

Policies:

1. A carbon cap on California for a given period can be enforced through carbon_policies_ca_cap.csv.
The constraint doesn't account for transmission across state boundaries.

"""
import os
from pyomo.environ import Set, Param, Expression, Constraint
import switch_model.reporting as reporting


def define_components(mod):
    """
    load_zone_state[z] is the two-letter state code of a load zone.
    Values are read from load_zones.csv and are optional (default
    is None). If the value is "CA" this load zone is considered to be
    part of California (and contributes to California's emissions)

    carbon_cap_tco2_per_yr_CA[p] is the carbon cap for a given period
    on all emission generated in load zones within California.
    """
    mod.load_zone_state = Param(
        mod.LOAD_ZONES,
        default=None,
        doc="2-letter state code for each load zone (optional).",
    )

    mod.CA_ZONES = Set(
        initialize=mod.LOAD_ZONES,
        within=mod.LOAD_ZONES,
        filter=lambda m, z: m.load_zone_state[z] == "CA",
    )

    mod.carbon_cap_tco2_per_yr_CA = Param(
        mod.PERIODS,
        default=float("inf"),
        doc=(
            "Emissions from California must be less than this cap. "
            "This is specified in metric tonnes of CO2 per year."
        ),
    )

    mod.AnnualEmissions_CA = Expression(
        mod.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period
            and (m.load_zone_state[m.gen_load_zone[g]] == "CA")
        ),
        doc="CA's annual emissions, in metric tonnes of CO2 per year.",
    )

    mod.Enforce_Carbon_Cap_CA = Constraint(
        mod.PERIODS,
        rule=lambda m, p: m.AnnualEmissions_CA[p] <= m.carbon_cap_tco2_per_yr_CA[p],
        doc="Enforces the carbon cap for generation-related emissions.",
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
    Expected input files:
    load_zones.csv
        LOAD_ZONE, load_zone_state

    carbon_policies_ca_cap.csv
        PERIOD, carbon_cap_tco2_per_yr_CA


    load_zones.csv will have other columns used in the balancing.load_zones module.
    load_zone_state can leave all values empty (".") except for those in california ("CA").
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "load_zones.csv"),
        auto_select=True,
        param=(mod.load_zone_state,),
    )

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "carbon_policies_ca_cap.csv"),
        optional=True,
        optional_params=(mod.carbon_cap_tco2_per_yr_CA,),
        auto_select=True,
        param=(mod.carbon_cap_tco2_per_yr_CA,),
    )


def post_solve(model, outdir):
    """
    Export california's annual emissions and its carbon caps
    for each period.
    """
    # Todo remove print statement
    model.pprint(filename=os.path.join(outdir, "raw_output.txt"))

    reporting.write_table(
        model,
        model.PERIODS,
        output_file=os.path.join(outdir, "emissions_ca.csv"),
        headings=(
            "PERIOD",
            "AnnualEmissions_tCO2_per_yr_CA",
            "carbon_cap_tco2_per_yr_CA",
        ),
        values=lambda m, period: [
            period,
            model.AnnualEmissions_CA[period],
            model.carbon_cap_tco2_per_yr_CA[period],
        ],
    )
