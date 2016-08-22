# -*- coding: utf-8 -*-
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

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

After the Chilean model is merged into the main branch, I plan to refactor
this code to move the core components into a switch_mod.hydro.core module,
the simplisit components into switch_mod.hydro.simple, and the advanced
components into switch_mod.hydro.water_network. That should set a good example
for other people who want to do other custom handling of hydro.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels',
...     'gen_tech', 'project.build', 'project.dispatch', 'project.no_commit',
...     'hydro_simple')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

from pyomo.environ import *
import os

def define_components(mod):
    """
    
    HYDRO_PROJECTS is the set of dispatchable hydro projects. This is a subet
    of PROJECTS, and is determined by the inputs file hydro_timeseries.tab.
    Members of this set can be called either proj, or hydro_proj.
    
    HYDRO_TIMESERIES is the set of Hydro projects and timeseries for which
    minimum and average flow are specified. Members of this set can be 
    abbreviated as (project, timeseries) or (proj, ts).
    
    HYDRO_PROJ_DISPATCH_POINTS is the set of Hydro projects and available
    dispatch points. This is a filtered version of PROJ_DISPATCH_POINTS that
    only includes hydro projects.

    hydro_min_flow_mw[(proj, ts) in HYDRO_TIMESERIES] is a parameter that
    determines minimum flow levels, specified in units of MW dispatch. 
    
    hydro_avg_flow_mw[(proj, ts) in HYDRO_TIMESERIES] is a parameter that
    determines average flow levels, specified in units of MW dispatch.

    Enforce_Hydro_Min_Flow[(proj, t) in HYDRO_PROJ_DISPATCH_POINTS] is a
    constraint that enforces minimum flow levels for each timepoint.
    
    Enforce_Hydro_Avg_Flow[(proj, ts) in HYDRO_TIMESERIES] is a constraint
    that enforces average flow levels across each timeseries.
    
    """

    mod.HYDRO_TIMESERIES = Set(
        dimen=2,
        validate=lambda m, proj, ts: (proj in m.PROJECTS) & (ts in m.TIMESERIES))
    mod.HYDRO_PROJECTS = Set(
        initialize=lambda m: set(proj for (proj, ts) in m.HYDRO_TIMESERIES),
        doc="Dispatchable hydro projects")
    mod.HYDRO_PROJ_DISPATCH_POINTS = Set(
        initialize=mod.PROJ_DISPATCH_POINTS,
        filter=lambda m, proj, t: proj in m.HYDRO_PROJECTS)

    # To do: Add validation check that timeseries data are specified for every
    # valid timepoint.

    mod.hydro_min_flow_mw = Param(
        mod.HYDRO_TIMESERIES,
        within=NonNegativeReals,
        default=0.0)
    mod.Enforce_Hydro_Min_Flow = Constraint(
        mod.HYDRO_PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (
            m.DispatchProj[proj, t] >= m.hydro_min_flow_mw[proj, m.tp_ts[t]]))

    mod.hydro_avg_flow_mw = Param(
        mod.HYDRO_TIMESERIES,
        within=NonNegativeReals,
        default=0.0)
    mod.Enforce_Hydro_Avg_Flow = Constraint(
        mod.HYDRO_TIMESERIES,
        rule=lambda m, proj, ts: (
            sum(m.DispatchProj[proj, t] for t in m.TS_TPS[ts]) / m.ts_num_tps[ts]
            == m.hydro_avg_flow_mw[proj, ts]))

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
        hydro_project, timeseries, hydro_min_flow_mw, hydro_avg_flow_mw

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.

    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'hydro_timeseries.tab'),
        select=('hydro_project', 'timeseries', 'hydro_min_flow_mw', 'hydro_avg_flow_mw'),
        index=mod.HYDRO_TIMESERIES,
        param=(mod.hydro_min_flow_mw, mod.hydro_avg_flow_mw)
    )
