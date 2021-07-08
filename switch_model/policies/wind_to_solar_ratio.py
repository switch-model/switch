"""
This module gives us the possibility to enforce a wind to solar capacity ratio.

It takes in wind_to_solar_ratio.csv that has the following format

PERIOD,wind_to_solar_ratio
2020,.
2030,0.5
2040,1
2050,1.5

Here when wind_to_solar_ratio is specified (i.e. not '.') a constraint is activated that enforces that

Online wind capacity = Online solar capacity * wind_to_solar_ratio

for the entire period.
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

    mod.wind_to_solar_ratio_const = Constraint(
        mod.PERIODS,
        rule=lambda m, p: Constraint.skip
        if m.wind_to_solar_ratio == 0
        else (m.WindCapacity[p] == m.SolarCapacity[p] * m.wind_to_solar_ratio[p]),
    )


def load_inputs(mod, switch_data, inputs_dir):
    switch_data.load_aug(
        index=mod.PERIODS,
        filename=os.path.join(inputs_dir, "wind_to_solar_ratio.csv"),
        auto_select=True,
        param=(mod.wind_to_solar_ratio,),
        optional=True,
    )


def post_solve(m, outdir):
    df = pd.DataFrame(
        {
            "WindCapacity (GW)": value(m.WindCapacity[p]) / 1000,
            "SolarCapacity (GW)": value(m.SolarCapacity[p]) / 1000,
            "ComputedRatio": value(m.WindCapacity[p] / m.SolarCapacity[p]),
            "ExpectedRatio": value(m.wind_to_solar_ratio[p]),
        }
        for p in m.PERIODS
        if m.wind_to_solar_ratio[p] != 0
    )
    write_table(
        m,
        output_file=os.path.join(outdir, "wind_to_solar_ratio.csv"),
        df=df,
        index=False,
    )
