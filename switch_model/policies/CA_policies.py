# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
Add emission policies to the model, either in the form of an added cost, or of
an emissions cap, depending on data inputs. The added cost could represent the
social cost of carbon, the expected clearing price of a cap-and-trade carbon
market, or a carbon tax.

Specifying carbon_cap_tco2_per_yr will add a system-wide emissions cap:
    AnnualEmissions[period] <= carbon_cap_tco2_per_yr[period]
Note: carbon_cap_tco2_per_yr defaults to infinity (no cap) for any data that
is unspecified.

Specifying carbon_cost_dollar_per_tco2 will add a term to the objective function:
    AnnualEmissions[period] * carbon_cost_dollar_per_tco2[period]
Note: carbon_cost_dollar_per_tco2 defaults to 0 (no cost) for any data that
is unspecified.

"""
import os
from pyomo.environ import Set, Param, Expression, Constraint, Suffix
import switch_model.reporting as reporting


def define_components(mod):
    mod.load_zone_state = Param(mod.LOAD_ZONES, default=None)

    mod.CA_ZONES = Set(
        initialize=mod.LOAD_ZONES,
        within=mod.LOAD_ZONES,
        filter=lambda m, z: m.load_zone_state[z] == "CA",
    )

    # mod.carbon_cap_tco2_per_yr_CA = Param(mod.PERIODS, default=float('inf'), doc=(
    #     "Emissions from this model must be less than this cap. "
    #     "This is specified in metric tonnes of CO2 per year."))
    # mod.AnnualEmissions_CA = Expression(mod.PERIODS,
    #                                     rule=lambda m, period: sum(
    #                                           m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
    #                                           for (g, t, f) in m.GEN_TP_FUELS
    #                                           if m.tp_period[t] == period and (m.gen_load_zone[g] in mod.CA_ZONES)),
    #                                     doc="CA's annual emissions, in metric tonnes of CO2 per year.")
    # mod.Enforce_Carbon_Cap_CA = Constraint(mod.PERIODS,
    #                                        rule=lambda m, p: m.AnnualEmissions_CA[p] <= m.carbon_cap_tco2_per_yr_CA[
    #                                              p],
    #                                        doc=("Enforces the carbon cap for generation-related emissions."))


def load_inputs(model, switch_data, inputs_dir):
    """
    Typically, people will specify either carbon caps or carbon costs, but not
    both. If you provide data for both columns, the results may be difficult
    to interpret meaningfully.

    Expected input files:
    load_zones.csv
        LOAD_ZONE, state (optional)

    load_zones.csv will have other columns used in balancing.load_zones

    carbon_policies.csv
        PERIOD, carbon_cap_tco2_per_yr_CA

    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "load_zones.csv"),
        optional_params=(model.load_zone_state,),
        auto_select=True,
        param=(model.load_zone_state,),
    )
    # switch_data.load_aug(
    #     filename=os.path.join(inputs_dir, 'carbon_policies.csv'),
    #     optional=True,
    #     optional_params=(model.carbon_cap_tco2_per_yr_CA,),
    #     auto_select=True,
    #     param=(model.carbon_cap_tco2_per_yr_CA,))


def post_solve(model, outdir):
    """
    Export annual emissions, carbon cap, and implicit carbon costs (where
    appropriate). The dual values of the carbon cap constraint represent an
    implicit carbon cost for purely linear optimization problems. For mixed
    integer optimization problems, the dual values lose practical
    interpretations, so dual values are only exported for purely linear
    models. If you include minimum build requirements, discrete unit sizes,
    discrete unit commitment, or other integer decision variables, the dual
    values will not be exported.
    """
    model.pprint(filename=os.path.join(outdir, "raw_output.txt"))
    # reporting.write_table(
    #     model, model.PERIODS,
    #     output_file=os.path.join(outdir, "emissions.txt"),
    #     headings=("PERIOD",
    #               "AnnualEmissions_tCO2_per_yr_CA",
    #               "carbon_cap_tco2_per_yr_CA",),
    #     values=lambda m, period: [period,
    #                               model.AnnualEmissions_CA[period],
    #                               model.carbon_cap_tco2_per_yr_CA[period]])
