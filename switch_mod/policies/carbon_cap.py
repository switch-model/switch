# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
Add a system-wide emissions cap to the model. 
"""
import os
from pyomo.environ import Set, Param, Expression, Constraint, Suffix
import switch_mod.reporting as reporting

def define_components(model):
    model.PERIODS_WITH_CARBON_CAPS = Set(within=model.PERIODS)
    model.carbon_cap_tco2_per_yr = Param(model.PERIODS_WITH_CARBON_CAPS, doc=(
        "Emissions from this model must be less than this cap. "
        "This is specified in metric tonnes of CO2 per year."))
    model.min_data_check('carbon_cap_tco2_per_yr')
    model.AnnualEmissions = Expression(model.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.PROJ_FUEL_DISPATCH_POINTS
            if m.tp_period[t] == period),
        doc="The system's annual emissions, in metric tonnes of CO2 per year.")
    model.Enforce_Carbon_Cap = Constraint(model.PERIODS_WITH_CARBON_CAPS,
        rule=lambda m, p: m.AnnualEmissions[p] <= m.carbon_cap_tco2_per_yr[p],
        doc=("Enforces the carbon cap for generation-related emissions."))
    # Make sure the model has a dual suffix
    if not hasattr(model, "dual"):
        model.dual = Suffix(direction=Suffix.IMPORT)


def load_inputs(model, switch_data, inputs_dir):
    """
    Expected input files:
    carbon_cap.tab
        PERIOD, carbon_cap_tco2_per_yr
    """
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'carbon_cap.tab'),
        auto_select=True,
        index=model.PERIODS_WITH_CARBON_CAPS,
        param=(model.carbon_cap_tco2_per_yr))


def post_solve(model, outdir):
    """
    Export annual emissions and carbon cap.
    """
#    import ipdb; ipdb.set_trace()
    def get_row(model, period):
        # Skip the carbon cap columns if a cap isn't defined in the period
        if period not in model.PERIODS_WITH_CARBON_CAPS:
            return (period, model.AnnualEmissions[period], '.', '.')
        # Skip the dual values if discrete variables are active because 
        # discrete variables mess up the interpretation of duals, often 
        # rendering duals meaningless.
        elif model.has_discrete_variables():
            return (period, model.AnnualEmissions[period], 
                    model.carbon_cap_tco2_per_yr[period], '.')
        else:
            return (period, model.AnnualEmissions[period],
                    model.carbon_cap_tco2_per_yr[period], 
                    model.dual[model.Enforce_Carbon_Cap[period]] / 
                    model.bring_annual_costs_to_base_year[period])

    reporting.write_table(
        model, model.PERIODS,
        output_file=os.path.join(outdir, "carbon_cap.txt"),
        headings=("PERIOD", "AnnualEmissions_tCO2_per_yr", "carbon_cap_tco2_per_yr", "carbon_cap_dual_future_dollar_per_tco2"),
        values=get_row)
