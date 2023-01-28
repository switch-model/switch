# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
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
from __future__ import division
import os
from pyomo.environ import Set, Param, Expression, Constraint, Suffix, NonNegativeReals
import switch_model.reporting as reporting


def define_components(model):
    model.carbon_cap_tco2_per_yr = Param(
        model.PERIODS,
        within=NonNegativeReals,
        default=float("inf"),
        doc=(
            "Emissions from this model must be less than this cap. "
            "This is specified in metric tonnes of CO2 per year."
        ),
    )
    model.Enforce_Carbon_Cap = Constraint(
        model.PERIODS,
        rule=lambda m, p: Constraint.Skip
        if m.carbon_cap_tco2_per_yr[p] == float("inf")
        else m.AnnualEmissions[p] <= m.carbon_cap_tco2_per_yr[p],
        doc=("Enforces the carbon cap for generation-related emissions."),
    )
    # Make sure the model has a dual suffix for determining implicit carbon costs
    if not hasattr(model, "dual"):
        model.dual = Suffix(direction=Suffix.IMPORT)

    model.carbon_cost_dollar_per_tco2 = Param(
        model.PERIODS,
        within=NonNegativeReals,
        default=0.0,
        doc="The cost adder applied to emissions, in future dollars per metric tonne of CO2.",
    )
    model.EmissionsCosts = Expression(
        model.PERIODS,
        rule=lambda model, period: model.AnnualEmissions[period]
        * model.carbon_cost_dollar_per_tco2[period],
        doc=("Enforces the carbon cap for generation-related emissions."),
    )
    model.Cost_Components_Per_Period.append("EmissionsCosts")


def load_inputs(model, switch_data, inputs_dir):
    """
    Typically, people will specify either carbon caps or carbon costs, but not
    both. If you provide data for both columns, the results may be difficult
    to interpret meaningfully.

    Expected input files:
    carbon_policies.csv
        PERIOD, carbon_cap_tco2_per_yr, carbon_cost_dollar_per_tco2

    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "carbon_policies.csv"),
        optional=True,
        optional_params=(
            model.carbon_cap_tco2_per_yr,
            model.carbon_cost_dollar_per_tco2,
        ),
        param=(model.carbon_cap_tco2_per_yr, model.carbon_cost_dollar_per_tco2),
    )


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

    def get_row(model, period):
        row = [
            period,
            model.AnnualEmissions[period],
            model.carbon_cap_tco2_per_yr[period],
        ]
        # Only print the carbon cap dual value if it exists
        # Note: we previously only reported it if the model was also strictly
        # continuous, but now we let the user worry about that (some solvers
        # can report duals for integer models by fixing the variables to their
        # integer values, which is often a reasonable approach and should give
        # meaningful duals for the carbon cost, which occurs on a much higher
        # level).
        if (
            period in model.Enforce_Carbon_Cap
            and model.Enforce_Carbon_Cap[period] in model.dual
        ):
            row.append(
                model.dual[model.Enforce_Carbon_Cap[period]]
                / model.bring_annual_costs_to_base_year[period]
            )
        else:
            row.append(".")
        row.append(model.carbon_cost_dollar_per_tco2[period])
        row.append(
            model.carbon_cost_dollar_per_tco2[period] * model.AnnualEmissions[period]
        )
        return row

    reporting.write_table(
        model,
        model.PERIODS,
        output_file=os.path.join(outdir, "emissions.csv"),
        headings=(
            "PERIOD",
            "AnnualEmissions_tCO2_per_yr",
            "carbon_cap_tco2_per_yr",
            "carbon_cap_dual_future_dollar_per_tco2",
            "carbon_cost_dollar_per_tco2",
            "carbon_cost_annual_total",
        ),
        values=get_row,
    )
