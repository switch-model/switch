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

INPUT FILE INFORMATION

    The file hydro_timeseries.csv needs to contain
    entries for each dispatchable hydro project. The set of hydro projects
    is derived from this file, and this file should cover all time periods
    in which the hydro plant can operate.

    Run-of-River hydro projects should not be included in this file; RoR
    hydro is treated like any other variable renewable resource, and
    expects data in variable_capacity_factors.csv.

    hydro_timeseries.csv
        hydro_generation_project, timeseries, hydro_min_flow_mw,
        hydro_avg_flow_mw

    The file hydro_timepoints.csv is an optional mapping of timepoints
    to a hydro timeseries. Hydro timeseries are different from the SWITCH
    timeseries (timeseries.csv) as this allows hydro constraints to be
    specified over a different time period.

    hydro_timepoints.csv (optional)
        timepoint,tp_to_hts
"""
from __future__ import division
# ToDo: Refactor this code to move the core components into a
# switch_model.hydro.core module, the simplist components into
# switch_model.hydro.simple, and the advanced components into
# switch_model.hydro.water_network. That should set a good example
# for other people who want to do other custom handling of hydro.
import os.path

from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties.properties', \
    'switch_model.generators.core.build', 'switch_model.generators.core.dispatch'

def define_components(mod):
    """
    HYDRO_GENS is the set of dispatchable hydro projects. This is a subet
    of GENERATION_PROJECTS, and is determined by the inputs file hydro_timeseries.csv.
    Members of this set can be called either g, or hydro_g.

    HYDRO_TS is the set of hydro timeseries over which the average flow constraint is defined.
    These hydro timeseries are different from the timeseries used in the reset of SWITCH
    and are defined by the input file hydro_timepoints.csv. If hydro_timepoints.csv doesn't exist,
    the default is for the timeseries to be the same as the SWITCH timeseries from timeseries.csv.
    Members of this set can be abbreviated as hts.

    HYDRO_GEN_TS is the set of Hydro projects and hydro timeseries for which
    minimum and average flow are specified. Members of this set can be
    abbreviated as (project, hydro_timeseries) or (g, hts).

    HYDRO_GEN_TPS is the set of Hydro projects and available
    dispatch points. This is a filtered version of GEN_TPS that
    only includes hydro projects.

    tp_to_hts[tp in TIMEPOINTS] is a parameter that returns the hydro timeseries
    for a given timepoint. It is defined in hydro_timepoints.csv and if unspecified
    it defaults to be equal to tp_ts.

    hydro_min_flow_mw[(g, hts) in HYDRO_GEN_TS] is a parameter that
    determines minimum flow levels, specified in units of MW dispatch.

    hydro_avg_flow_mw[(g, hts) in HYDRO_GEN_TS] is a parameter that
    determines average flow levels, specified in units of MW dispatch.

    Enforce_Hydro_Min_Flow[(g, t) in HYDRO_GEN_TPS] is a
    constraint that enforces minimum flow levels for each timepoint.

    Enforce_Hydro_Avg_Flow[(g, hts) in HYDRO_GEN_TS] is a constraint
    that enforces average flow levels across each hydro timeseries.
    """
    mod.tp_to_hts = Param(
        mod.TIMEPOINTS,
        input_file='hydro_timepoints.csv',
        default=lambda m, tp: m.tp_ts[tp],
        doc="Mapping of timepoints to a hydro series.",
        within=Any
    )

    mod.HYDRO_TS = Set(
        dimen=1,
        ordered=False,
        initialize=lambda m: set(m.tp_to_hts[tp] for tp in m.TIMEPOINTS),
        doc="Set of hydro timeseries as defined in the mapping."
    )

    mod.TPS_IN_HTS = Set(
        mod.HYDRO_TS,
        within=mod.TIMEPOINTS,
        ordered=False,
        initialize=lambda m, hts: set(t for t in m.TIMEPOINTS if m.tp_to_hts[t] == hts),
        doc="Set of timepoints in each hydro timeseries"
    )

    mod.hydro_ts_duration = Param(
        mod.HYDRO_TS,
        initialize=lambda m, hts: sum(m.tp_duration_hrs[tp] for tp in m.TPS_IN_HTS[hts]),
        doc="Total duration in hours of each hydro timeseries."
    )

    mod.HYDRO_GEN_TS_RAW = Set(
        dimen=2,
        input_file='hydro_timeseries.csv',
        input_optional=True,
        validate=lambda m, g, hts: (g in m.GENERATION_PROJECTS) & (hts in m.HYDRO_TS), )

    mod.HYDRO_GENS = Set(
        dimen=1,
        ordered=False,
        initialize=lambda m: set(g for (g, hts) in m.HYDRO_GEN_TS_RAW),
        doc="Dispatchable hydro projects")

    mod.HYDRO_GEN_TPS = Set(
        initialize=mod.GEN_TPS,
        filter=lambda m, g, t: g in m.HYDRO_GENS)

    mod.HYDRO_GEN_TS = Set(
        dimen=2,
        initialize=lambda m: set((g, m.tp_to_hts[tp]) for (g, tp) in m.HYDRO_GEN_TPS))

    # Validate that a timeseries data is specified for every hydro generator /
    # timeseries that we need. Extra data points (ex: outside of planning
    # horizon or beyond a plant's lifetime) can safely be ignored to make it
    # easier to create input files.
    mod.have_minimal_hydro_params = BuildCheck(
        mod.HYDRO_GEN_TS,
        rule=lambda m, g, hts: (g, hts) in m.HYDRO_GEN_TS_RAW)

    # Todo: Add validation check that timeseries data are specified for every valid timepoint.

    mod.hydro_min_flow_mw = Param(
        mod.HYDRO_GEN_TS_RAW,
        within=NonNegativeReals,
        input_file='hydro_timeseries.csv',
        default=0.0)
    mod.Enforce_Hydro_Min_Flow = Constraint(
        mod.HYDRO_GEN_TPS,
        rule=lambda m, g, t: Constraint.Skip
        if m.hydro_min_flow_mw[g, m.tp_to_hts[t]] == 0
        else m.DispatchGen[g, t] >= m.hydro_min_flow_mw[g, m.tp_to_hts[t]])

    mod.hydro_avg_flow_mw = Param(
        mod.HYDRO_GEN_TS_RAW,
        within=NonNegativeReals,
        input_file='hydro_timeseries.csv',
        default=0.0)

    # We use a scaling factor to improve the numerical properties
    # of the model. The scaling factor was determined using trial
    # and error and this tool https://github.com/staadecker/lp-analyzer.
    # Learn more by reading the documentation on Numerical Issues.
    enforce_hydro_avg_flow_scaling_factor = 1e1
    mod.Enforce_Hydro_Avg_Flow = Constraint(
        mod.HYDRO_GEN_TS,
        rule=lambda m, g, hts:
        Constraint.Skip if m.hydro_avg_flow_mw[g, hts] == 0 else
        enforce_hydro_avg_flow_scaling_factor *
        sum(m.DispatchGen[g, t] * m.tp_duration_hrs[t] for t in m.TPS_IN_HTS[hts]) / m.hydro_ts_duration[hts]
        == m.hydro_avg_flow_mw[g, hts] * enforce_hydro_avg_flow_scaling_factor
    )

    mod.min_data_check('hydro_min_flow_mw', 'hydro_avg_flow_mw')
