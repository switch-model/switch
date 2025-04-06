# This module was prepared by Josiah Johnston in collaboration with Gang He
# This module introduces water withdrawal constraints per water basin per period.
# Data needed: gene_info.csv table needs gen_water_basin, gen_cooling_water_m3_per_mwh for each plant; water_limit_annual.csv     WATER_BASINS PERIOD water_basin_name_cn water_basin_limit_mm3
# Add switch_model.china.water_limit to the modules.txt file to use this module
# You can cite below paper to use this module:
# - Zhang, Chao, Gang He, Josiah Johnston, and Lijin Zhong. 2021. “Long-Term Transition of China’s Power Sector under Carbon Neutrality Target and Water Withdrawal Constraint.” Journal of Cleaner Production 329 (December): 129765. https://doi.org/10.1016/j.jclepro.2021.129765.

import os
import pandas as pd

from pyomo.environ import *

"""
Limit cooling water withdrawals for thermal power plants based on annual water
withdrawals goals per water basin.
"""

def define_components(mod):
    mod.WATER_BASIN_PERIODS = Set(
        dimen=2,
        validate=lambda m, b, p: p in m.PERIODS)
    mod.WATER_BASINS = Set(
        initialize=lambda m: set([b for b, p in m.WATER_BASIN_PERIODS]))

    mod.water_basin_limit_mm3 = Param(mod.WATER_BASIN_PERIODS)
    mod._water_basin_name_cn_raw = Param(mod.WATER_BASIN_PERIODS)

    # Validate water basin english-Chinese names are consistent in every record
    mod.consistent_water_basin_names = BuildCheck(
        mod.WATER_BASINS,
        rule=lambda m, wb: \
            len(set(
                [m._water_basin_name_cn_raw[wb,p] 
                 for _wb, p in m.WATER_BASIN_PERIODS if _wb == wb]
            )) == 1
    )

    def default_water_basin_name_cn(m, wb):
        names = set([
            m._water_basin_name_cn_raw[wb,p] 
            for _wb, p in m.WATER_BASIN_PERIODS if _wb == wb
        ])
        if names:
            return names.pop()
        else:
            return wb
    mod.water_basin_name_cn = Param(mod.WATER_BASINS,
        initialize=default_water_basin_name_cn)
    
    mod.gen_water_basin = Param(mod.GENERATION_PROJECTS, within=mod.WATER_BASINS)
    mod.gen_cooling_water_m3_per_mwh = Param(mod.GENERATION_PROJECTS)

    mod.GENS_IN_WATER_BASIN = Set(
        mod.WATER_BASINS,
        initialize=lambda m, wb: set(
            g for g in m.GENERATION_PROJECTS if m.gen_water_basin[g] == wb))
    mod.AnnualCoolingWaterWithdrawals_mm3 = Expression(
        mod.WATER_BASIN_PERIODS,
        rule=lambda m, wb, p: sum(
            m.gen_cooling_water_m3_per_mwh[g] * 
            sum(m.DispatchGen[g, t] * m.tp_weight_in_year[t] 
                for t in m.TPS_FOR_GEN_IN_PERIOD[g, p]
            )
            for g in m.GENS_IN_WATER_BASIN[wb] 
        ) / 1000000.0,
        doc="Total cooling water withdrawals per basin by thermal plants, "
            "scaled to annual average in units of million cubic meters."
    )
    mod.Enforce_Cooling_Water_Limits = Constraint(
        mod.WATER_BASIN_PERIODS,
        rule=lambda m, wb, p: (
            m.AnnualCoolingWaterWithdrawals_mm3[wb,p] <= m.water_basin_limit_mm3[wb,p]
        )
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
    generation_projects_info.csv needs these extra columns: 
        gen_water_basin, gen_cooling_water_m3_per_mwh

    water_limit_annual.csv
    WATER_BASINS PERIOD water_basin_name_cn water_basin_limit_mm3
    
    Note: The optional Chinese-character basin name (water_basin_name_cn) in
    water_limit_annual is de-normalized because it is actually keyed by
    WATER_BASINS, not WATER_BASINS & PERIOD. It exists to make manual review &
    input file preparation more convenient, and is normalized & checked for
    consistency during model creation.
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.csv'),
        auto_select=True,
        param=(mod.gen_water_basin, mod.gen_cooling_water_m3_per_mwh))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'water_limit_annual.csv'),
        optional_params=['water_basin_name_cn'],
        select=['WATER_BASINS', 'PERIOD', 'water_basin_name_cn',
                'water_basin_limit_mm3'],
        index=mod.WATER_BASIN_PERIODS,
        param=(mod._water_basin_name_cn_raw, mod.water_basin_limit_mm3))


def post_solve(instance, outdir):
    m = instance
    normalized_dat = [{
        "WATER_BASIN": wb,
        "PERIOD": p,
        "water_basin_name_cn": m.water_basin_name_cn[wb],
        "water_basin_limit_mm3": m.water_basin_limit_mm3[wb, p], 
        "AnnualCoolingWaterWithdrawals_mm3": value(m.AnnualCoolingWaterWithdrawals_mm3[wb, p])
    } for wb, p in m.WATER_BASIN_PERIODS]
    df = pd.DataFrame(normalized_dat)
    df.sort_values(by=["WATER_BASIN", "PERIOD"], inplace=True)
    df.set_index(["WATER_BASIN", "PERIOD"], inplace=True)
    df.to_csv(os.path.join(outdir, "cooling_water.csv"))
