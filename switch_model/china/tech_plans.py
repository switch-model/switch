# This module was prepared by Josiah Johnston in collaboration with Gang He
# This module can incorperate two types of technological plans: 1)technology plan by tech, period, and load zones, such as wind, solar development plan in each province; 2) national total tech plan/limit by period, such as national total coal capacity limit
# You can use either or both constraints but make sure plans are larger than actual historical data
# Add switch_model.china.tech_plans to the modules.txt file to use this module
# You can cite below two papers to use this module:
# - He, Gang, Jiang Lin, Froylan Sifuentes, Xu Liu, Nikit Abhyankar, and Amol Phadke. 2020. “Rapid Cost Decrease of Renewables and Storage Accelerates the Decarbonization of China’s Power System.” Nature Communications 11 (1): 2486. https://doi.org/10.1038/s41467-020-16184-x.
# - Zhang, Chao, Gang He, Josiah Johnston, and Lijin Zhong. 2021. “Long-Term Transition of China’s Power Sector under Carbon Neutrality Target and Water Withdrawal Constraint.” Journal of Cleaner Production 329 (December): 129765. https://doi.org/10.1016/j.jclepro.2021.129765.


import os
from pyomo.environ import *

"""
Enable capacity plans which establish a minimum capacity target for a
particular technology in given province & period. This supports both the wind, solar, & nuclear plans. 

Also enable upper limits on total generation capacity of particular
technologies per period. This supports plans of national nuclear limits.
"""

def define_components(mod):
    mod.CAPACITY_PLAN_INDEX = Set(
        dimen=3,
        within=mod.ENERGY_SOURCES * mod.LOAD_ZONES * mod.PERIODS)
    mod.planned_capacity_mw = Param(mod.CAPACITY_PLAN_INDEX)
    
    mod.TOTAL_CAPACITY_LIMIT_INDEX = Set(
        dimen=2,
        within=mod.ENERGY_SOURCES * mod.PERIODS)
    mod.total_capacity_limit_mw = Param(mod.TOTAL_CAPACITY_LIMIT_INDEX)

    # Only track for entries we are tracking to save time & RAM
    mod.CapacityByEnergySourceZonePeriod = Expression(
        mod.CAPACITY_PLAN_INDEX,
        # m:model; e: energy source; z: zone; p: period
        rule=lambda m, e, z, p: (   
            sum(m.GenCapacity[g, p]   
                # use GENS_BY_TECHNOLOGY if using technology plan
                for g in m.GENS_BY_ENERGY_SOURCE[e]
                if m.gen_load_zone[g] == z
            )
        )
    )
    mod.Enforce_Capacity_Plan = Constraint(
        mod.CAPACITY_PLAN_INDEX,
        rule=lambda m, e, z, p: (
            m.CapacityByEnergySourceZonePeriod[e,z,p] >= m.planned_capacity_mw[e,z,p]
        )
    )
    
    mod.TotalCapByEnergySource = Expression(
        mod.TOTAL_CAPACITY_LIMIT_INDEX,
        rule=lambda m, e, p: (
            sum(m.GenCapacity[g, p] for g in m.GENS_BY_ENERGY_SOURCE[e])
        )
    )
    mod.Enforce_Total_Capacity_Limit = Constraint(
        mod.TOTAL_CAPACITY_LIMIT_INDEX,
        rule=lambda m, e, p: (
             m.TotalCapByEnergySource[e,p] <= m.total_capacity_limit_mw[e,p]
        )
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
        Both files are optional.
        
        capacity_plans.csv
        ENERGY_SOURCES LOAD_ZONES PERIOD planned_capacity_mw

        total_capacity_limits.csv
        ENERGY_SOURCES PERIOD total_capacity_limit_mw
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'capacity_plans.csv'),
        optional=True,
        auto_select=True,
        index=mod.CAPACITY_PLAN_INDEX,
        param=(mod.planned_capacity_mw,))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'total_capacity_limits.csv'),
        optional=True,
        auto_select=True,
        index=mod.TOTAL_CAPACITY_LIMIT_INDEX,
        param=(mod.total_capacity_limit_mw,))
