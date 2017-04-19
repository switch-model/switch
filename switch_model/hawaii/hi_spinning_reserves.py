# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
This customizes the behavior of balancing.operating_reserves.spinning_reserve
to match Hawaii requirements.
"""
import os
from pyomo.environ import *

dependencies = (
    'switch_model.timescales',
    'switch_model.balancing.load_zones',
    'switch_model.balancing.operating_reserves.areas',
    'switch_model.financials',
    'switch_model.energy_sources.properties',
    'switch_model.generators.core.build',
    'switch_model.generators.core.dispatch',
    'switch_model.generators.core.commit.operate',
    'switch_model.balancing.operating_reserves.spinning_reserve',
)


def define_components(m):

    # these parameters were found by regressing the reserve requirements from
    # the GE RPS Study against wind and solar conditions each hour (see
    # Dropbox/Research/Shared/Switch-Hawaii/ge_validation/source_data/
    # reserve_requirements_oahu_scenarios charts.xlsx and
    # Dropbox/Research/Shared/Switch-Hawaii/ge_validation/
    # fit_renewable_reserves.ipynb ) 
    # TODO: supply these parameters in input files

    # regulating reserves required, as fraction of potential output (up to limit)
    m.var_gen_power_reserve = Param(['Central_PV', 'CentralTrackingPV', 'DistPV', 'OnshoreWind', 'OffshoreWind'], initialize={
        'Central_PV': 1.0,
        'CentralTrackingPV': 1.0,
        'DistPV': 1.0, # 0.81270193,
        'OnshoreWind': 1.0,
        'OffshoreWind': 1.0, # assumed equal to OnshoreWind
    })
    # maximum regulating reserves required, as fraction of installed capacity
    m.var_gen_cap_reserve_limit = Param(['Central_PV', 'CentralTrackingPV', 'DistPV', 'OnshoreWind', 'OffshoreWind'], initialize={
        'Central_PV': 0.21288916,
        'CentralTrackingPV': 0.21288916,
        'DistPV': 0.21288916, # 0.14153171,
        'OnshoreWind': 0.21624407,
        'OffshoreWind': 0.21624407, # assumed equal to OnshoreWind
    })
    # more conservative values (found by giving 10x weight to times when we provide less reserves than GE):
    # [1., 1., 1., 0.25760558, 0.18027923, 0.49123101]

    m.HawaiiVarGenUpSpinningReserveRequirement = Expression(
        m.BALANCING_AREA_TIMEPOINTS, 
        rule=lambda m, b, t: sum(
            m.ProjCapacityTP[g, t] 
            * min(
                m.var_gen_power_reserve[m.proj_gen_tech[g]] * m.proj_max_capacity_factor[g, t], 
                m.var_gen_cap_reserve_limit[m.proj_gen_tech[g]]
            )
            for g in m.VARIABLE_PROJECTS
            if (g, t) in m.VAR_DISPATCH_POINTS and b == m.zone_balancing_area[m.proj_load_zone[g]]),
        doc="The spinning reserves for backing up variable generation with Hawaii rules."
    )
    m.Spinning_Reserve_Up_Requirements.append('HawaiiVarGenUpSpinningReserveRequirement')

    def HawaiiLoadDownSpinningReserveRequirement_rule(m, b, t):
        if 'WithdrawFromCentralGrid' in dir(m):
            load = m.WithdrawFromCentralGrid
        else:
            load = m.lz_demand_mw
        return 0.10 * sum(load[z, t] for z in m.LOAD_ZONES if b == m.zone_balancing_area[z])
    m.HawaiiLoadDownSpinningReserveRequirement = Expression(
        m.BALANCING_AREA_TIMEPOINTS,
        rule=HawaiiLoadDownSpinningReserveRequirement_rule
    )
    m.Spinning_Reserve_Down_Requirements.append('HawaiiLoadDownSpinningReserveRequirement')
        
