# Copyright (c) 2016-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This module defines storage technologies. It builds on top of generic
generators, adding components for deciding how much energy to build into
storage, when to charge, energy accounting, etc.
"""

from pyomo.environ import *
import os, collections
from switch_model.financials import capital_recovery_factor as crf

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties', \
    'switch_model.generators.core.build', 'switch_model.generators.core.dispatch'

def define_components(mod):
    """
    
    STORAGE_GENS is the subset of projects that can provide energy storage.

    STORAGE_GEN_BLD_YRS is the subset of GEN_BLD_YRS, restricted
    to storage projects.

    gen_storage_efficiency[STORAGE_GENS] describes the round trip
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

    gen_store_to_release_ratio[STORAGE_GENS] describes the maximum rate
    that energy can be stored, expressed as a ratio of discharge power
    capacity. This is an optional parameter and will default to 1. If a
    storage project has 1 MW of dischage capacity and a max_store_rate
    of 1.2, then it can consume up to 1.2 MW of power while charging.

    gen_storage_energy_overnight_cost[(g, bld_yr) in
    STORAGE_GEN_BLD_YRS] is the overnight capital cost per MWh of
    energy capacity for building the given storage technology installed in the
    given investment period. This is only defined for storage technologies.
    Note that this describes the energy component and the overnight_cost
    describes the power component.
    
    BuildStorageEnergy[(g, bld_yr) in STORAGE_GEN_BLD_YRS]
    is a decision of how much energy capacity to build onto a storage
    project. This is analogous to BuildGen, but for energy rather than power.
    
    StorageEnergyInstallCosts[PERIODS] is an expression of the
    annual costs incurred by the BuildStorageEnergy decision.
    
    StorageEnergyCapacity[g, period] is an expression describing the
    cumulative available energy capacity of BuildStorageEnergy. This is
    analogous to GenCapacity.
    
    STORAGE_GEN_TPS is the subset of GEN_TPS,
    restricted to storage projects.

    ChargeStorage[(g, t) in STORAGE_GEN_TPS] is a dispatch
    decision of how much to charge a storage project in each timepoint.
    
    StorageNetCharge[LOAD_ZONE, TIMEPOINT] is an expression describing the
    aggregate impact of ChargeStorage in each load zone and timepoint.
    
    Charge_Storage_Upper_Limit[(g, t) in STORAGE_GEN_TPS]
    constrains ChargeStorage to available power capacity (accounting for
    gen_store_to_release_ratio)
    
    StateOfCharge[(g, t) in STORAGE_GEN_TPS] is a variable
    for tracking state of charge. This value stores the state of charge at
    the end of each timepoint for each storage project.
    
    Track_State_Of_Charge[(g, t) in STORAGE_GEN_TPS] constrains
    StateOfCharge based on the StateOfCharge in the previous timepoint,
    ChargeStorage and DispatchGen.
    
    State_Of_Charge_Upper_Limit[(g, t) in STORAGE_GEN_TPS]
    constrains StateOfCharge based on installed energy capacity.

    """

    mod.STORAGE_GENS = Set(within=mod.GENERATION_PROJECTS)
    mod.gen_storage_efficiency = Param(
        mod.STORAGE_GENS,
        within=PercentFraction)
    mod.gen_store_to_release_ratio = Param(
        mod.STORAGE_GENS,
        within=PositiveReals,
        default=1.0)

    mod.STORAGE_GEN_BLD_YRS = Set(
        dimen=2,
        initialize=mod.GEN_BLD_YRS,
        filter=lambda m, g, bld_yr: g in m.STORAGE_GENS)
    mod.gen_storage_energy_overnight_cost = Param(
        mod.STORAGE_GEN_BLD_YRS,
        within=NonNegativeReals)
    mod.min_data_check('gen_storage_energy_overnight_cost')
    mod.BuildStorageEnergy = Var(
        mod.STORAGE_GEN_BLD_YRS,
        within=NonNegativeReals)

    # Summarize capital costs of energy storage for the objective function.
    mod.StorageEnergyInstallCosts = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(m.BuildStorageEnergy[g, bld_yr] *
                   m.gen_storage_energy_overnight_cost[g, bld_yr] *
                   crf(m.interest_rate, m.gen_max_age[g])
                   for (g, bld_yr) in m.STORAGE_GEN_BLD_YRS))
    mod.Cost_Components_Per_Period.append(
        'StorageEnergyInstallCosts')

    mod.StorageEnergyCapacity = Expression(
        mod.STORAGE_GENS, mod.PERIODS,
        rule=lambda m, g, period: sum(
            m.BuildStorageEnergy[g, bld_yr]
            for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, period]))

    mod.STORAGE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) 
                for g in m.STORAGE_GENS
                    for tp in m.TPS_FOR_GEN[g]))

    mod.ChargeStorage = Var(
        mod.STORAGE_GEN_TPS,
        within=NonNegativeReals)
    
    # Summarize storage charging for the energy balance equations
    def StorageNetCharge_rule(m, z, t):
        # Construct and cache a set for summation as needed
        if not hasattr(m, 'Storage_Charge_Summation_dict'):
            m.Storage_Charge_Summation_dict = collections.defaultdict(set)
            for g, t2 in m.STORAGE_GEN_TPS:
                z2 = m.gen_load_zone[g]
                m.Storage_Charge_Summation_dict[z2, t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Storage_Charge_Summation_dict.pop((z, t))
        return sum(m.ChargeStorage[g, t] for g in relevant_projects)
    mod.StorageNetCharge = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        rule=StorageNetCharge_rule)
    # Register net charging with zonal energy balance. Discharging is already
    # covered by DispatchGen.
    mod.Zone_Power_Withdrawals.append('StorageNetCharge')

    def Charge_Storage_Upper_Limit_rule(m, g, t):
        return m.ChargeStorage[g,t] <= \
            m.DispatchUpperLimit[g, t] * m.gen_store_to_release_ratio[g]
    mod.Charge_Storage_Upper_Limit = Constraint(
        mod.STORAGE_GEN_TPS,
        rule=Charge_Storage_Upper_Limit_rule)
                
    mod.StateOfCharge = Var(
        mod.STORAGE_GEN_TPS,
        within=NonNegativeReals)

    def Track_State_Of_Charge_rule(m, g, t):
        return m.StateOfCharge[g, t] == \
            m.StateOfCharge[g, m.tp_previous[t]] + \
            (m.ChargeStorage[g, t] * m.gen_storage_efficiency[g] -
             m.DispatchGen[g, t]) * m.tp_duration_hrs[t]
    mod.Track_State_Of_Charge = Constraint(
        mod.STORAGE_GEN_TPS,
        rule=Track_State_Of_Charge_rule)

    def State_Of_Charge_Upper_Limit_rule(m, g, t):
        return m.StateOfCharge[g, t] <= \
            m.StorageEnergyCapacity[g, m.tp_period[t]]
    mod.State_Of_Charge_Upper_Limit = Constraint(
        mod.STORAGE_GEN_TPS,
        rule=State_Of_Charge_Upper_Limit_rule)
        

def load_inputs(mod, switch_data, inputs_dir):
    """

    Import storage parameters. Optional columns are noted with a *.

    generation_projects_info.tab
        GENERATION_PROJECT, ...
        gen_storage_efficiency, gen_store_to_release_ratio*

    gen_build_costs.tab
        GENERATION_PROJECT, build_year, ...
        gen_storage_energy_overnight_cost

    """
 
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'generation_projects_info.tab'),
        auto_select=True,
        optional_params=['gen_store_to_release_ratio'],
        param=(mod.gen_storage_efficiency, mod.gen_store_to_release_ratio))
    # Base the set of storage projects on storage efficiency being specified.
    switch_data.data()['STORAGE_GENS'] = {
        None: switch_data.data(name='gen_storage_efficiency').keys()}
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'gen_build_costs.tab'),
        auto_select=True,
        param=(mod.gen_storage_energy_overnight_cost))


def post_solve(instance, outdir):
    """
    Export storage build information to storage_builds.txt, and storage
    dispatch info to storage_dispatch.txt
    """
    import switch_model.reporting as reporting
    reporting.write_table(
        instance, instance.STORAGE_GEN_BLD_YRS,
        output_file=os.path.join(outdir, "storage_builds.txt"),
        headings=("project", "period", "load_zone", 
                  "IncrementalPowerCapacityMW", "IncrementalEnergyCapacityMWh",
                  "OnlinePowerCapacityMW", "OnlineEnergyCapacityMWh" ),
        values=lambda m, (g, bld_yr): (
            g, bld_yr, m.gen_load_zone[g],
            m.BuildGen[g, bld_yr], m.BuildStorageEnergy[g, bld_yr],
            m.GenCapacity[g, bld_yr], m.StorageEnergyCapacity[g, bld_yr]
            ))
    reporting.write_table(
        instance, instance.STORAGE_GEN_TPS,
        output_file=os.path.join(outdir, "storage_dispatch.txt"),
        headings=("project", "timepoint", "load_zone", 
                  "ChargeMW", "DischargeMW", "StateOfCharge"),
        values=lambda m, (g, t): (
            g, m.tp_timestamp[t], m.gen_load_zone[g],
            m.ChargeStorage[g, t], m.DispatchGen[g, t],
            m.StateOfCharge[g, t]
            ))
