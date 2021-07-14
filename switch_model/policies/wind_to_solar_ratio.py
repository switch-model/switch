"""
This module gives us the possibility to enforce a wind to solar capacity ratio.

It takes in wind_to_solar_ratio.csv that has the following format

PERIOD,wind_to_solar_ratio,wind_to_solar_ratio_const_gt
2020,.,.
2030,0.5,0
2040,1,0
2050,1.5,1

Here when wind_to_solar_ratio is specified (i.e. not '.') a constraint is activated that enforces that

Online wind capacity >=/<= Online solar capacity * wind_to_solar_ratio

for the entire period.

When wind_to_solar_ratio_const_gt is true (1) the constraint is a >= constraint.
When wind_to_solar_ratio_const_gt is False (0) the constraint is a <= constraint.
"""
import os

import pandas as pd
from pyomo.environ import *

from switch_model.reporting import write_table

_WIND_ENERGY_TYPE = "Wind"
_SOLAR_ENERGY_TYPE = "Solar"


def define_components(mod):
    mod.WindCapacity = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.GenCapacity[g, p]
            for g in m.VARIABLE_GENS
            if m.gen_energy_source[g] == _WIND_ENERGY_TYPE
        ),
    )

    mod.SolarCapacity = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.GenCapacity[g, p]
            for g in m.VARIABLE_GENS
            if m.gen_energy_source[g] == _SOLAR_ENERGY_TYPE
        ),
    )

    mod.wind_to_solar_ratio = Param(
        mod.PERIODS,
        default=0,  # 0 means the constraint is inactive
        within=NonNegativeReals,
    )

    mod.wind_to_solar_ratio_const_gt = Param(mod.PERIODS, default=True, within=Boolean)

    # We use a scaling factor to improve the numerical properties
    # of the model.
    # Learn more by reading the documentation on Numerical Issues.
    # 1e-3 was picked since this value is normally on the order of GW instead of MW
    scaling_factor = 1e-3

    def wind_to_solar_ratio_const_rule(m, p):
        if m.wind_to_solar_ratio[p] == 0:  # 0 means Constraint is inactive
            return Constraint.Skip

        lhs = m.WindCapacity[p] * scaling_factor
        rhs = m.SolarCapacity[p] * m.wind_to_solar_ratio[p] * scaling_factor
        if m.wind_to_solar_ratio_const_gt[p]:
            return lhs >= rhs
        else:
            return lhs <= rhs

    mod.wind_to_solar_ratio_const = Constraint(
        mod.PERIODS, rule=wind_to_solar_ratio_const_rule
    )


def load_inputs(mod, switch_data, inputs_dir):
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "wind_to_solar_ratio.csv"),
        auto_select=True,
        param=(mod.wind_to_solar_ratio, mod.wind_to_solar_ratio_const_gt),
        optional=True,  # We want to allow including this module even if the file isn't there
    )


def post_solve(m, outdir):
    df = pd.DataFrame(
        {
            "WindCapacity (GW)": value(m.WindCapacity[p]) / 1000,
            "SolarCapacity (GW)": value(m.SolarCapacity[p]) / 1000,
            "ComputedRatio": value(m.WindCapacity[p] / m.SolarCapacity[p])
            if value(m.SolarCapacity[p]) != 0
            else ".",
            "ExpectedRatio": value(m.wind_to_solar_ratio[p])
            if m.wind_to_solar_ratio[p] != 0
            else ".",
        }
        for p in m.PERIODS
    )
    write_table(
        m,
        output_file=os.path.join(outdir, "wind_to_solar_ratio.csv"),
        df=df,
        index=False,
    )
