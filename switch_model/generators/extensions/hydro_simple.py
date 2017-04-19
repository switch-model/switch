# -*- coding: utf-8 -*-
# Copyright (c) 2016-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines a simple hydro electric model that ensures minimum and average
water dispatch levels that can vary by timepoint. Most people use this
as a starting point for working with hydro because it's simple, fairly
reasonable, and easy to work with. This supports dispatchable resevoir-
based hydro plants. This module is not needed to support run-of-river
plants; those may be specified as variable renewable plants with exogenous
energy availability.

A more full-featured hydro model is available from the Operations, Control
and Markets laboratory at Pontificia Universidad Católica de Chile.
Where possible, I have used the same set and variable names to hopefully
make it easier to merge that into the codebase later. The Chilean branch
has a hydro model that includes water networks that connect dams via waterways
and ground infiltration. It should be possible to describe a simple system 
using the advanced framework, but the advanced framework would take longer to
read and understand. To really take advantage of it, you'll also need more
data than we usually have available.
"""
# ToDo: Refactor this code to move the core components into a
# switch_model.hydro.core module, the simplist components into
# switch_model.hydro.simple, and the advanced components into
# switch_model.hydro.water_network. That should set a good example
# for other people who want to do other custom handling of hydro.

from pyomo.environ import *
import os

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties.properties', \
    'switch_model.generators.core.build', 'switch_model.generators.core.dispatch'

def define_components(mod):
    """
    
    HYDRO_GENS is the set of dispatchable hydro projects. This is a subet
    of GENERATION_PROJECTS, and is determined by the inputs file hydro_timeseries.tab.
    Members of this set can be called either g, or hydro_g.
    
    HYDRO_GEN_TS is the set of Hydro projects and timeseries for which
    minimum and average flow are specified. Members of this set can be 
    abbreviated as (project, timeseries) or (g, ts).
    
    HYDRO_GEN_TPS is the set of Hydro projects and available
    dispatch points. This is a filtered version of GEN_TPS that
    only includes hydro projects.

    hydro_min_flow_mw[(g, ts) in HYDRO_GEN_TS] is a parameter that
    determines minimum flow levels, specified in units of MW dispatch. 
    
    hydro_avg_flow_mw[(g, ts) in HYDRO_GEN_TS] is a parameter that
    determines average flow levels, specified in units of MW dispatch.

    Enforce_Hydro_Min_Flow[(g, t) in HYDRO_GEN_TPS] is a
    constraint that enforces minimum flow levels for each timepoint.
    
    Enforce_Hydro_Avg_Flow[(g, ts) in HYDRO_GEN_TS] is a constraint
    that enforces average flow levels across each timeseries.
    
    """

    mod.HYDRO_GEN_TS = Set(
        dimen=2,
        validate=lambda m, g, ts: (g in m.GENERATION_PROJECTS) & (ts in m.TIMESERIES))
    mod.HYDRO_GENS = Set(
        initialize=lambda m: set(g for (g, ts) in m.HYDRO_GEN_TS),
        doc="Dispatchable hydro projects")
    mod.HYDRO_GEN_TPS = Set(
        initialize=mod.GEN_TPS,
        filter=lambda m, g, t: g in m.HYDRO_GENS)

    # To do: Add validation check that timeseries data are specified for every
    # valid timepoint.

    mod.hydro_min_flow_mw = Param(
        mod.HYDRO_GEN_TS,
        within=NonNegativeReals,
        default=0.0)
    mod.Enforce_Hydro_Min_Flow = Constraint(
        mod.HYDRO_GEN_TPS,
        rule=lambda m, g, t: (
            m.DispatchGen[g, t] >= m.hydro_min_flow_mw[g, m.tp_ts[t]]))

    mod.hydro_avg_flow_mw = Param(
        mod.HYDRO_GEN_TS,
        within=NonNegativeReals,
        default=0.0)
    mod.Enforce_Hydro_Avg_Flow = Constraint(
        mod.HYDRO_GEN_TS,
        rule=lambda m, g, ts: (
            sum(m.DispatchGen[g, t] for t in m.TPS_IN_TS[ts]) / m.ts_num_tps[ts]
            == m.hydro_avg_flow_mw[g, ts]))

    mod.min_data_check('hydro_min_flow_mw', 'hydro_avg_flow_mw')


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import hydro data. The single file hydro_timeseries.tab needs to contain
    entries for each dispatchable hydro project. The set of hydro projects
    is derived from this file, and this file should cover all time periods
    in which the hydro plant can operate.
    
    Run-of-River hydro projects should not be included in this file; RoR
    hydro is treated like any other variable renewable resource, and
    which expects data in variable_capacity_factors.tab.

    hydro_timeseries.tab
        hydro_generation_project, timeseries, hydro_min_flow_mw,
        hydro_avg_flow_mw

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'hydro_timeseries.tab'),
        autoselect=True,
        index=mod.HYDRO_GEN_TS,
        param=(mod.hydro_min_flow_mw, mod.hydro_avg_flow_mw)
    )
