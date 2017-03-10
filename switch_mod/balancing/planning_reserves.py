# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
This module defines planning reserves margins to support resource adequacy
requirements.

Planning reserve margins have been an industry standard for decades that are
roughly defined as: (GenerationCapacity - Demand) / Demand. The idea was that
if you have 15% generation capacity above and beyond demand, the grid could
maintain high reliability. Generation capacity typically includes local
capacity and scheduled imports, while demand typically accounts for demand
response and other distributed energy resources.

This simple definition is problematic for energy-constrained resources such as
hydro, wind, solar, or storage. It also fails to account whether a resource
will be available when it is needed. As this problem became more recognized,
people shifted terminology from "planning reserve margin" to "resource
adequacy requirements" which had more dynamic rules based on time of day,
weather conditions, season, etc.

The "correct" treatment of energy constrained resources is still being debated.
This module implements a simple and flexible treatment, where the user can
specify capacity_value timeseries for any generator, so the available capacity
will be: GenCapacity[g] * capacity_value[g,t]. For renewable resources, this
capacity value timeseries will default to their capacity factor timeseries.

By default, storage and transmission will be credited with their expected 
net power delivery.

References:
http://www.nerc.com/pa/RAPA/ri/Pages/PlanningReserveMargin.aspx
https://www.caiso.com/Documents/RenewableResourcesandCaliforniaElectricPowerIndustry-SystemOperations_WholesaleMarketsandGridPlanning.pdf
https://www.caiso.com/Documents/Jan29_2016_Comments_2017Track1Proposals_ResourceAdequacyProgram_R14-10-010.pdf
https://www.spp.org/documents/23549/resource%20adequacy%20in%20spp%20part%201%20blog.pdf

"""

import os
from pyomo.environ import *

dependencies = (
    'switch_mod.timescales',
    'switch_mod.financials',
    'switch_mod.balancing.load_zones',
    'switch_mod.energy_sources.properties',
    'switch_mod.generators.core.build',
    'switch_mod.generators.core.dispatch',
)
optional_prerequisites = (
    'switch_mod.generators.storage',
    'switch_mod.transmission.local_td',
    'switch_mod.transmission.transport.build',
    'switch_mod.transmission.transport.dispatch',
)

def define_dynamic_lists(model):
    """
    CAPACITY_FOR_RESERVES is a list of model components than can contribute
    to capacity reserve margins. Each component mentioned here should be 
    indexed by zone and timepoint.
    """
    model.CAPACITY_FOR_RESERVES = []


def define_components(model):
    """
    capacity_reserve_margin is a ratio of reserve margin requirements. Default
    is 0.15
    
    capacity_value[proj, t] is a ratio of how much the project's installed
    capacity should be credited towards capacity reserve requirements. This
    defaults to proj_max_capacity_factor for renewable projects with variable
    output and 1.0 for other plants.
    
    AvailableReserveCapacity[z,t] summarizes the available generation capacity
    in each load zone, taking into account capacity_value. If storage projects
    are being modeled, they are credited with their scheduled net deliveries
    (dispatch - charging). This is added to the CAPACITY_FOR_RESERVES list.
    
    If LZ_TXNet is defined in the model, it will be added to the
    CAPACITY_FOR_RESERVES list.

    CapacityRequirements[z,t] is (1+capacity_reserve_margin) * load
    If the local_td module has been included, load will be set to
    WithdrawFromCentralGrid, which accounts for Distributed Energy Resources
    reducing (or increasing) net load to the central grid.
    If the local_td module is not include, load is set to lz_demand_mw and
    will not reflect any DER activities.
    """
    model.capacity_reserve_margin = Param(within=NonNegativeReals, default=0.15)
    model.capacity_value = Param(
        model.PROJ_DISPATCH_POINTS,
        within=PercentFraction,
        default=lambda m, proj, t: \
            1.0 if proj not in m.VARIABLE_PROJECTS \
            else m.proj_max_capacity_factor[proj, t])

    def AvailableReserveCapacity_rule(m, z, t):
        reserve_cap = 0.0
        # The storage module may or may not be included
        if 'LZ_NetCharge' in dir(m):
            reserve_cap -= m.LZ_NetCharge[z,t]
        PROJECTS = [pr for pr in m.LZ_PROJECTS[z] if (pr, t) in m.PROJ_DISPATCH_POINTS]
        for proj in PROJECTS:
            # Storage is only credited with its expected output
            if 'STORAGE_PROJECTS' in dir(m) and proj in m.STORAGE_PROJECTS:
                reserve_cap += DispatchProj[proj, t]
            # If local_td is included with DER modeling, avoid allocating
            # distributed generation to central grid capacity because it will
            # be credited with adjusting load at the distribution node.
            elif 'local_td' not in m.module_list or not m.proj_is_distributed[proj]:
                reserve_cap += m.capacity_value[proj, t] * m.ProjCapacityTP[proj, t]
        return reserve_cap

    model.AvailableReserveCapacity = Expression(
        model.ZONE_TIMEPOINTS, rule=AvailableReserveCapacity_rule)
    model.CAPACITY_FOR_RESERVES.append('AvailableReserveCapacity')

    if 'LZ_TXNet' in model:
        model.CAPACITY_FOR_RESERVES.append('LZ_TXNet')

    def CapacityRequirements_rule(m, z, t):
        if 'WithdrawFromCentralGrid' in dir(m):
            return (1 + m.capacity_reserve_margin) * m.WithdrawFromCentralGrid[z,t]
        else:
            return (1 + m.capacity_reserve_margin) * m.lz_demand_mw[z,t]
    model.CapacityRequirements = Expression(
        model.ZONE_TIMEPOINTS, rule=CapacityRequirements_rule)


def define_dynamic_components(model):
    """
    """
    model.Enforce_Planning_Reserve_Margin = Constraint(
        model.ZONE_TIMEPOINTS, rule=lambda m, z, t: (
            sum(getattr(m, reserve_cap)[z,t]
                for reserve_cap in m.CAPACITY_FOR_RESERVES
            ) >= m.CapacityRequirements[z,t]),
        doc=("Ensures that the sum of CAPACITY_FOR_RESERVES satisfies "
             "CapacityRequirements"))


def load_inputs(mod, switch_data, inputs_dir):
    """
    reserve_capacity_value.tab
        ZONE, TIMEPOINT, capacity_value
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'reserve_capacity_value.tab'),
        optional=True,
        auto_select=True,
        param=(mod.capacity_value))

