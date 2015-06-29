# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines simple limitations on project dispatch without considering unit
commitment. This module is mutually exclusive with the project.commit
module which constrains dispatch to unit committment decisions.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels',
...     'gen_tech', 'project.build', 'project.dispatch', 'project.no_commit')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

from pyomo.environ import *


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

    DispatchUpperLimit[(proj, t) in PROJ_DISPATCH_POINTS] is an
    expression that defines the upper bounds of dispatch subject to
    installed capacity, average expected outage rates, and renewable
    resource availability.

    DispatchLowerLimit[(proj, t) in PROJ_DISPATCH_POINTS] in an
    expression that defines the lower bounds of dispatch, which is 0
    except for baseload plants where is it the upper limit.

    Enforce_Dispatch_Lower_Limit[(proj, t) in PROJ_DISPATCH_POINTS] and
    Enforce_Dispatch_Upper_Limit[(proj, t) in PROJ_DISPATCH_POINTS] are
    constraints that limit DispatchProj to the upper and lower bounds
    defined above.

        DispatchLowerLimit <= DispatchProj <= DispatchUpperLimit

    ProjFuelUseRate_Calculate[(proj, t) in PROJ_DISPATCH_POINTS]
    calculates fuel consumption for the variable ProjFuelUseRate as
    DispatchProj * proj_full_load_heat_rate. The units become:
    MW * (MMBtu / MWh) = MMBTU / h


    """

    def DispatchUpperLimit_expr(m, proj, t):
        if proj in m.VARIABLE_PROJECTS:
            return (m.ProjCapacityTP[proj, t] * m.proj_availability[proj] *
                    m.prj_max_capacity_factor[proj, t])
        else:
            return m.ProjCapacityTP[proj, t] * m.proj_availability[proj]
    mod.DispatchUpperLimit = Expression(
        mod.PROJ_DISPATCH_POINTS,
        initialize=DispatchUpperLimit_expr)

    def DispatchLowerLimit_expr(m, proj, t):
        if proj in m.BASELOAD_PROJECTS:
            return DispatchUpperLimit_expr(m, proj, t)
        else:
            return 0
    mod.DispatchLowerLimit = Expression(
        mod.PROJ_DISPATCH_POINTS,
        initialize=DispatchLowerLimit_expr)

    mod.Enforce_Dispatch_Lower_Limit = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchLowerLimit[proj, t] <= m.DispatchProj[proj, t]))
    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] <= m.DispatchUpperLimit[proj, t]))

    mod.ProjFuelUseRate_Calculate = Constraint(
        mod.PROJ_FUEL_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.ProjFuelUseRate[proj, t] ==
            m.DispatchProj[proj, t] * m.proj_full_load_heat_rate[proj]))
