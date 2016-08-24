# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

A simple description of flat fuel costs for the SWITCH-Pyomo model that
serves as an alternative to the more complex fuel_markets with tiered
supply curves. This is mutually exclusive with the fuel_markets module.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'load_zones', 'financials', 'fuels', 'gen_tech',
...     'project.build', 'project.dispatch', 'fuel_cost')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters to
    describe simple fuel costs. Unless otherwise stated, each set and
    parameter is mandatory. Unless otherwise specified, all dollar
    values are real dollars in BASE_YEAR.

    FUEL_AVAILABILITY is a set that describes fuel availability. Each
    element of the set is (load_zone, fuel, period).

    fuel_cost[(lz, f, p) in FUEL_AVAILABILITY] describes flat fuel costs
    for each supply of fuel. Costs can vary by load zone and period.

    PROJ_FUEL_DISPATCH_POINTS_UNAVAILABLE is a subset of
    PROJ_FUEL_DISPATCH_POINTS that describes which points don't have fuel
    available.

    Enforce_Fuel_Availability[(proj, t) in
    PROJ_FUEL_DISPATCH_POINTS_UNAVAILABLE] is a constraint that restricts
    ProjFuelUseRate to 0 for in load zones and periods where the
    projects' fuel is unavailable.

    Fuel_Costs_TP[t in TIMEPOINTS] is an expression that summarizes fuel
    costs for the objective function.

    """

    mod.FUEL_AVAILABILITY = Set(
        dimen=3,
        validate=lambda m, lz, f, p: (
            lz in m.LOAD_ZONES and
            f in m.FUELS and
            p in m.PERIODS))
    mod.fuel_cost = Param(
        mod.FUEL_AVAILABILITY,
        within=PositiveReals)
    mod.min_data_check('FUEL_AVAILABILITY', 'fuel_cost')

    mod.PROJ_FUEL_DISPATCH_POINTS_UNAVAILABLE = Set(
        initialize=mod.PROJ_FUEL_DISPATCH_POINTS,
        filter=lambda m, pr, t, f: (
            (m.proj_load_zone[pr], f, m.tp_period[t])
            not in m.FUEL_AVAILABILITY))
    mod.Enforce_Fuel_Availability = Constraint(
        mod.PROJ_FUEL_DISPATCH_POINTS_UNAVAILABLE,
        rule=lambda m, pr, t, f: m.ProjFuelUseRate[pr, t, f] == 0)

    # Summarize total fuel costs in each timepoint for the objective function
    def Fuel_Costs_TP_rule(m, t):
        if not hasattr(m, 'Fuel_Costs_TP_dict'):
            # cache all Fuel_Cost_TP values in a dictionary (created in one pass)
            m.Fuel_Costs_TP_dict = {t2: 0.0 for t2 in m.TIMEPOINTS}
            for (proj, t2, f) in m.PROJ_FUEL_DISPATCH_POINTS:
                if (m.proj_load_zone[proj], f, m.tp_period[t2]) in m.FUEL_AVAILABILITY:
                    m.Fuel_Costs_TP_dict[t2] += (
                        m.ProjFuelUseRate[proj, t2, f] 
                        * m.fuel_cost[m.proj_load_zone[proj], f, m.tp_period[t2]])
        # return a result from the dictionary and pop the element each time 
        # to release memory
        return m.Fuel_Costs_TP_dict.pop(t)
    mod.Fuel_Costs_TP = Expression(mod.TIMEPOINTS, rule=Fuel_Costs_TP_rule)
    mod.cost_components_tp.append('Fuel_Costs_TP')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import simple fuel cost data. The following files are expected in
    the input directory:

    fuel_cost.tab
        load_zone, fuel, period, fuel_cost

    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'fuel_cost.tab'),
        select=('load_zone', 'fuel', 'period', 'fuel_cost'),
        index=mod.FUEL_AVAILABILITY,
        param=[mod.fuel_cost])
