# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines simple limitations on project dispatch without considering unit
commitment. This module is mutually exclusive with the operations.unitcommit
module which constrains dispatch to unit commitment decisions.
"""

from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties.properties', \
    'switch_model.generators.core.build', 'switch_model.generators.core.dispatch'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to constrain
    dispatch decisions subject to available capacity, renewable resource
    availability, and baseload restrictions. Unless otherwise stated,
    all power capacity is specified in units of MW and all sets and
    parameters are mandatory. This module estimates project dispatch
    limits and fuel consumption without consideration of unit
    commitment. This can be a useful approximation if fuel startup
    requirements are a small portion of overall fuel consumption, so
    that the aggregate fuel consumption with respect to energy
    production can be approximated as a line with a 0 intercept. This
    estimation method has been known to result in excessive cycling of
    Combined Cycle Gas Turbines in the SWITCH-WECC model.

    DispatchUpperLimit[(g, t) in GEN_TPS] is an
    expression that defines the upper bounds of dispatch subject to
    installed capacity, average expected outage rates, and renewable
    resource availability.

    DispatchLowerLimit[(g, t) in GEN_TPS] in an
    expression that defines the lower bounds of dispatch, which is 0
    except for baseload plants where is it the upper limit.

    Enforce_Dispatch_Lower_Limit[(g, t) in GEN_TPS] and
    Enforce_Dispatch_Upper_Limit[(g, t) in GEN_TPS] are
    constraints that limit DispatchGen to the upper and lower bounds
    defined above.

        DispatchLowerLimit <= DispatchGen <= DispatchUpperLimit

    GenFuelUseRate_Calculate[(g, t) in GEN_TPS]
    calculates fuel consumption for the variable GenFuelUseRate as
    DispatchGen * gen_full_load_heat_rate. The units become:
    MW * (MMBtu / MWh) = MMBTU / h

    DispatchGenByFuel[(g, t, f) in GEN_TP_FUELS]
    calculates power production by each project from each fuel during
    each timepoint.

    """

    # NOTE: DispatchBaseloadByPeriod should eventually be replaced by 
    # an "ActiveCapacityDuringPeriod" decision variable that applies to all
    # projects. This should be constrained
    # based on the amount of installed capacity each period, and then 
    # DispatchUpperLimit and DispatchLowerLimit should be calculated
    # relative to ActiveCapacityDuringPeriod. Fixed O&M (but not capital 
    # costs) should be calculated based on ActiveCapacityDuringPeriod.
    # This would allow mothballing (and possibly restarting) projects.

    # Choose flat operating level for baseload plants during each period
    # (not necessarily running all available capacity)
    # Note: this is unconstrained, because other constraints limit project 
    # dispatch during each timepoint and therefore the level of this variable.
    mod.DispatchBaseloadByPeriod = Var(mod.BASELOAD_GENS, mod.PERIODS)
    
    def DispatchUpperLimit_expr(m, g, t):
        if g in m.VARIABLE_GENS:
            return (m.GenCapacityInTP[g, t] * m.gen_availability[g] *
                    m.gen_max_capacity_factor[g, t])
        else:
            return m.GenCapacityInTP[g, t] * m.gen_availability[g]
    mod.DispatchUpperLimit = Expression(
        mod.GEN_TPS,
        rule=DispatchUpperLimit_expr)

    mod.Enforce_Dispatch_Baseload_Flat = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: 
            (m.DispatchGen[g, t] == m.DispatchBaseloadByPeriod[g, m.tp_period[t]])
                if g in m.BASELOAD_GENS
            else Constraint.Skip)

    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (
            m.DispatchGen[g, t] <= m.DispatchUpperLimit[g, t]))

    mod.GenFuelUseRate_Calculate = Constraint(
        mod._FUEL_BASED_GEN_TPS,
        rule=lambda m, g, t: (
            sum(m.GenFuelUseRate[g, t, f] 
                for f in m.FUELS_FOR_GEN[g])
            == m.DispatchGen[g, t] * m.gen_full_load_heat_rate[g]))
