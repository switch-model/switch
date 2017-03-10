# Copyright (c) 2016-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This module defines storage technologies. It builds on top of generic
generators, adding components for deciding how much energy to build into
storage, when to charge, energy accounting, etc.
"""

from pyomo.environ import *
import os, collections
from switch_mod.financials import capital_recovery_factor as crf

dependencies = 'switch_mod.timescales', 'switch_mod.balancing.load_zones',\
    'switch_mod.financials', 'switch_mod.energy_sources.properties', \
    'switch_mod.generators.core.build', 'switch_mod.generators.core.dispatch'

def define_components(mod):
    """
    
    STORAGE_PROJECTS is the subset of projects that can provide energy storage.

    STORAGE_PROJECT_BUILDYEARS is the subset of PROJECT_BUILDYEARS, restricted
    to storage projects.

    proj_storage_efficiency[STORAGE_PROJECTS] describes the round trip
    efficiency of a storage technology. A storage technology that is 75
    percent efficient would have a storage_efficiency of .75. If 1 MWh
    was stored in such a storage project, 750 kWh would be available for
    extraction later. Internal leakage or energy dissipation of storage
    technologies is assumed to be neglible, which is consistent with
    short-duration storage technologies currently on the market which
    tend to consume stored power within 1 day. If a given storage
    technology has significant internal discharge when it stores power
    for extended time perios, then those behaviors will need to be
    modeled in more detail.

    proj_store_to_release_ratio[STORAGE_PROJECTS] describes the maximum rate
    that energy can be stored, expressed as a ratio of discharge power
    capacity. This is an optional parameter and will default to 1. If a
    storage project has 1 MW of dischage capacity and a max_store_rate
    of 1.2, then it can consume up to 1.2 MW of power while charging.

    proj_storage_energy_overnight_cost[(proj, bld_yr) in
    STORAGE_PROJECT_BUILDYEARS] is the overnight capital cost per MWh of
    energy capacity for building the given storage technology installed in the
    given investment period. This is only defined for storage technologies.
    Note that this describes the energy component and the overnight_cost
    describes the power component.
    
    BuildStorageEnergyMWh[(proj, bld_yr) in STORAGE_PROJECT_BUILDYEARS]
    is a decision of how much energy capacity to build onto a storage
    project. This is analogous to BuildProj, but for energy rather than power.
    
    Total_Storage_Energy_Install_Costs_Annual[PERIODS] is an expression of the
    annual costs incurred by the BuildStorageEnergyMWh decision.
    
    StorageEnergyCapacity[proj, period] is an expression describing the
    cumulative available energy capacity of BuildStorageEnergyMWh. This is
    analogous to ProjCapacity.
    
    STORAGE_PROJ_DISPATCH_POINTS is the subset of PROJ_DISPATCH_POINTS,
    restricted to storage projects.

    ChargeStorage[(proj, t) in STORAGE_PROJ_DISPATCH_POINTS] is a dispatch
    decision of how much to charge a storage project in each timepoint.
    
    LZ_NetCharge[LOAD_ZONE, TIMEPOINT] is an expression describing the
    aggregate impact of ChargeStorage in each load zone and timepoint.
    
    Charge_Storage_Upper_Limit[(proj, t) in STORAGE_PROJ_DISPATCH_POINTS]
    constrains ChargeStorage to available power capacity (accounting for
    proj_store_to_release_ratio)
    
    StateOfChargeMWh[(proj, t) in STORAGE_PROJ_DISPATCH_POINTS] is a variable
    for tracking state of charge. This value stores the state of charge at
    the end of each timepoint for each storage project.
    
    Track_State_Of_Charge[(proj, t) in STORAGE_PROJ_DISPATCH_POINTS] constrains
    StateOfChargeMWh based on the StateOfChargeMWh in the previous timepoint,
    ChargeStorage and DispatchProj.
    
    State_Of_Charge_Upper_Limit[(proj, t) in STORAGE_PROJ_DISPATCH_POINTS]
    constrains StateOfChargeMWh based on installed energy capacity.

    """

    mod.STORAGE_PROJECTS = Set(within=mod.PROJECTS)
    mod.proj_storage_efficiency = Param(
        mod.STORAGE_PROJECTS,
        within=PercentFraction)
    mod.proj_store_to_release_ratio = Param(
        mod.STORAGE_PROJECTS,
        within=PositiveReals,
        default=1.0)

    mod.STORAGE_PROJECT_BUILDYEARS = Set(
        dimen=2,
        initialize=mod.PROJECT_BUILDYEARS,
        filter=lambda m, proj, bld_yr: proj in m.STORAGE_PROJECTS)
    mod.proj_storage_energy_overnight_cost = Param(
        mod.STORAGE_PROJECT_BUILDYEARS,
        within=NonNegativeReals)
    mod.min_data_check('proj_storage_energy_overnight_cost')
    mod.BuildStorageEnergyMWh = Var(
        mod.STORAGE_PROJECT_BUILDYEARS,
        within=NonNegativeReals)

    # Summarize capital costs of energy storage for the objective function.
    mod.Total_Storage_Energy_Install_Costs_Annual = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(m.BuildStorageEnergyMWh[proj, bld_yr] *
                   m.proj_storage_energy_overnight_cost[proj, bld_yr] *
                   crf(m.interest_rate, m.proj_max_age[proj])
                   for (proj, bld_yr) in m.STORAGE_PROJECT_BUILDYEARS))
    mod.cost_components_annual.append(
        'Total_Storage_Energy_Install_Costs_Annual')

    mod.StorageEnergyCapacity = Expression(
        mod.STORAGE_PROJECTS, mod.PERIODS,
        rule=lambda m, proj, period: sum(
            m.BuildStorageEnergyMWh[proj, bld_yr]
            for bld_yr in m.PROJECT_PERIOD_ONLINE_BUILD_YRS[proj, period]))

    mod.STORAGE_PROJ_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (proj, tp) 
                for proj in m.STORAGE_PROJECTS
                    for tp in m.PROJ_ACTIVE_TIMEPOINTS[proj]))

    mod.ChargeStorage = Var(
        mod.STORAGE_PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    
    # Summarize storage charging for the energy balance equations
    def LZ_NetCharge_rule(m, lz, t):
        # Construct and cache a set for summation as needed
        if not hasattr(m, 'Storage_Charge_Summation_dict'):
            m.Storage_Charge_Summation_dict = collections.defaultdict(set)
            for proj, t2 in m.STORAGE_PROJ_DISPATCH_POINTS:
                lz2 = m.proj_load_zone[proj]
                m.Storage_Charge_Summation_dict[lz2, t2].add(proj)
        # Use pop to free memory
        relevant_projects = m.Storage_Charge_Summation_dict.pop((lz, t))
        return sum(m.ChargeStorage[proj, t] for proj in relevant_projects)
    mod.LZ_NetCharge = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=LZ_NetCharge_rule)
    # Register net dispatch as contributing to a load zone's energy
    mod.LZ_Energy_Components_Consume.append('LZ_NetCharge')

    def Charge_Storage_Upper_Limit_rule(m, proj, t):
        return m.ChargeStorage[proj,t] <= \
            m.DispatchUpperLimit[proj, t] * m.proj_store_to_release_ratio[proj]
    mod.Charge_Storage_Upper_Limit = Constraint(
        mod.STORAGE_PROJ_DISPATCH_POINTS,
        rule=Charge_Storage_Upper_Limit_rule)
                
    mod.StateOfChargeMWh = Var(
        mod.STORAGE_PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)

    def Track_State_Of_Charge_rule(m, proj, t):
        return m.StateOfChargeMWh[proj, t] == \
            m.StateOfChargeMWh[proj, m.tp_previous[t]] + \
            (m.ChargeStorage[proj, t] * m.proj_storage_efficiency[proj] -
             m.DispatchProj[proj, t]) * m.tp_duration_hrs[t]
    mod.Track_State_Of_Charge = Constraint(
        mod.STORAGE_PROJ_DISPATCH_POINTS,
        rule=Track_State_Of_Charge_rule)

    def State_Of_Charge_Upper_Limit_rule(m, proj, t):
        return m.StateOfChargeMWh[proj, t] <= \
            m.StorageEnergyCapacity[proj, m.tp_period[t]]
    mod.State_Of_Charge_Upper_Limit = Constraint(
        mod.STORAGE_PROJ_DISPATCH_POINTS,
        rule=State_Of_Charge_Upper_Limit_rule)
        

def load_inputs(mod, switch_data, inputs_dir):
    """

    Import storage parameters. Optional columns are noted with a *.

    project_info.tab
        PROJECT, ...
        proj_storage_efficiency, proj_store_to_release_ratio*

    proj_build_costs.tab
        PROJECT, build_year, ...
        proj_storage_energy_overnight_cost

    """
 
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'project_info.tab'),
        auto_select=True,
        optional_params=['proj_store_to_release_ratio'],
        param=(mod.proj_storage_efficiency, mod.proj_store_to_release_ratio))
    # Base the set of storage projects on storage efficiency being specified.
    switch_data.data()['STORAGE_PROJECTS'] = {
        None: switch_data.data(name='proj_storage_efficiency').keys()}
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'proj_build_costs.tab'),
        auto_select=True,
        param=(mod.proj_storage_energy_overnight_cost))


def post_solve(instance, outdir):
    """
    Export storage build information to storage_builds.txt, and storage
    dispatch info to storage_dispatch.txt
    """
    import switch_mod.reporting as reporting
    reporting.write_table(
        instance, instance.STORAGE_PROJECT_BUILDYEARS,
        output_file=os.path.join(outdir, "storage_builds.txt"),
        headings=("project", "period", "load_zone", 
                  "IncrementalPowerCapacityMW", "IncrementalEnergyCapacityMWh",
                  "OnlinePowerCapacityMW", "OnlineEnergyCapacityMWh" ),
        values=lambda m, (proj, bld_yr): (
            proj, bld_yr, m.proj_load_zone[proj],
            m.BuildProj[proj, bld_yr], m.BuildStorageEnergyMWh[proj, bld_yr],
            m.ProjCapacity[proj, bld_yr], m.StorageEnergyCapacity[proj, bld_yr]
            ))
    reporting.write_table(
        instance, instance.STORAGE_PROJ_DISPATCH_POINTS,
        output_file=os.path.join(outdir, "storage_dispatch.txt"),
        headings=("project", "timepoint", "load_zone", 
                  "ChargeMW", "DischargeMW", "StateOfChargeMWh"),
        values=lambda m, (proj, t): (
            proj, m.tp_timestamp[t], m.proj_load_zone[proj],
            m.ChargeStorage[proj, t], m.DispatchProj[proj, t],
            m.StateOfChargeMWh[proj, t]
            ))
