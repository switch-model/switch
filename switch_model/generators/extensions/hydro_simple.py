# -*- coding: utf-8 -*-
# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines a simple hydro electric model that ensures minimum and average
water dispatch levels that can vary by timepoint. Most people use this
as a starting point for working with hydro because it's simple, fairly
reasonable, and easy to work with. This supports dispatchable resevoir-
based hydro plants. This module is not needed to support run-of-river
plants; those may be specified as variable renewable plants with exogenous
energy availability. This module is generally sufficient for day-to-day
operations where reservoir volume levels are not a binding constraint, but
does not track seasonal planning for fluctuations in reservoir volume.

A more full-featured hydro model is available in the hydro_system module from
the Operations, Control and Markets laboratory at Pontificia Universidad
Católica de Chile. Where possible, I have used the same set and variable names
to aid interoperability. The Chilean module has a hydro model that includes
water networks that connect dams via waterways and ground infiltration. It
should be possible to describe a simple system using the advanced framework,
but the advanced framework would take longer to read and understand. To really
take advantage of it, you'll also need more data than we usually have
available.
"""
# ToDo: Refactor this code to move the core components into a
# switch_model.hydro.core module, the simplest components into
# switch_model.hydro.simple, and the advanced components into
# switch_model.hydro.water_network. That should set a good example
# for other people who want to do other custom handling of hydro.

from __future__ import division

import os

from pyomo.environ import *
from switch_model.utilities import unique_list

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties.properties",
    "switch_model.generators.core.build",
    "switch_model.generators.core.dispatch",
)


def define_components(mod):
    """
    HYDRO_GENS is the set of dispatchable hydro projects. This is a subset of
    GENERATION_PROJECTS, and is determined by the inputs file
    hydro_timeseries.csv.

    HYDRO_GEN_TS is the set of Hydro projects and timeseries for which
    minimum and average flow are specified.

    HYDRO_GEN_TPS is the set of Hydro projects and available
    dispatch points. This is a filtered version of GEN_TPS that
    only includes hydro projects.

    hydro_min_flow_mw[(g, ts) in HYDRO_GEN_TS] is a parameter that
    determines minimum flow levels, specified in units of MW dispatch.

    hydro_avg_flow_mw[(g, ts) in HYDRO_GEN_TS] is a parameter that
    determines average flow levels, specified in units of MW dispatch.

    Enforce_Hydro_Min_Flow[(g, t) in HYDRO_GEN_TPS] is a
    constraint that enforces minimum flow levels for each timepoint.

    SpillHydro[(g, t) in HYDRO_GEN_TPS] is an variable describing the amount
    of potential hydro power sent over the spillway (as opposed to being used
    to generate electricity). In high-flow or flood conditions, this can
    mitigate infeasibilities where the incoming flow is greater than the
    generator's capacity. It is specified in units of MW.

    Enforce_Hydro_Avg_Flow[(g, ts) in HYDRO_NONPUMPED_GEN_TS] is a constraint
    that enforces average flow levels across each timeseries. It requires the
    average of dispatched and spilled hydro over the course of a timeseries
    must equal to the corresponding hydro_avg_flow_mw parameter.
    """

    mod.HYDRO_GEN_TS_RAW = Set(
        dimen=2,
        validate=lambda m, g, ts: ((g in m.GENERATION_PROJECTS) & (ts in m.TIMESERIES)),
    )
    mod.HYDRO_GENS = Set(
        dimen=1,
        initialize=lambda m: unique_list(g for (g, ts) in m.HYDRO_GEN_TS_RAW),
        doc="Dispatchable hydro projects",
    )
    mod.HYDRO_GEN_TS = Set(
        dimen=2,
        initialize=lambda m: unique_list(
            (g, m.tp_ts[tp]) for g in m.HYDRO_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.HYDRO_GEN_TPS = Set(
        dimen=2, initialize=mod.GEN_TPS, filter=lambda m, g, t: g in m.HYDRO_GENS
    )

    # Validate that a timeseries data is specified for every hydro generator /
    # timeseries that we need. Extra data points (ex: outside of planning
    # horizon or beyond a plant's lifetime) can safely be ignored to make it
    # easier to create input files.
    mod.have_minimal_hydro_params = BuildCheck(
        mod.HYDRO_GEN_TS, rule=lambda m, g, ts: (g, ts) in m.HYDRO_GEN_TS_RAW
    )
    # Generate a warning if the input files specify timeseries for renewable
    # plant capacity factors that extend beyond the expected lifetime of the
    # plant. This could be caused by simple logic to build input files, or
    # could indicate that the user expects those plants to operate longer
    # than indicated.
    def _warn_on_extra_HYDRO_GEN_TS(m):
        extra_indexes = m.HYDRO_GEN_TS_RAW - m.HYDRO_GEN_TS
        extraneous = {g: [] for (g, t) in extra_indexes}
        for (g, t) in extra_indexes:
            extraneous[g].append(t)
        pprint = "\n".join(
            "* {}: {} to {}".format(g, min(tps), max(tps))
            for g, tps in extraneous.items()
        )
        warning_msg = (
            "{} hydro plants with predetermined builds have timeseries data "
            "in periods when they are not operating (either after retirement, "
            "or before construction is complete). This "
            "could indicate a benign issue where the process that built "
            "the dataset used simplified logic and/or didn't know the "
            "scheduled operating dates. If you expect those datapoints to "
            "be useful, then those plants need to either come online earlier, "
            "have longer lifetimes, or have options to build new capacity "
            "when the old capacity reaches the provided end-of-life date."
            "\n".format(len(extraneous))
        )
        if extra_indexes:
            m.logger.warning(warning_msg)
            m.logger.info("Plants with extra timepoints:\n{}".format(pprint))
        return True

    mod.warn_on_extra_HYDRO_GEN_TS = BuildCheck(rule=_warn_on_extra_HYDRO_GEN_TS)

    mod.hydro_min_flow_mw = Param(
        mod.HYDRO_GEN_TS_RAW, within=NonNegativeReals, default=0.0
    )
    mod.Enforce_Hydro_Min_Flow = Constraint(
        mod.HYDRO_GEN_TPS,
        rule=lambda m, g, t: (
            m.DispatchGen[g, t] >= m.hydro_min_flow_mw[g, m.tp_ts[t]]
        ),
    )

    mod.hydro_avg_flow_mw = Param(
        mod.HYDRO_GEN_TS_RAW, within=NonNegativeReals, default=0.0
    )
    mod.SpillHydro = Var(mod.HYDRO_GEN_TPS, within=NonNegativeReals)
    mod.Enforce_Hydro_Avg_Flow = Constraint(
        mod.HYDRO_GEN_TS,
        rule=lambda m, g, ts: (
            sum(m.DispatchGen[g, t] + m.SpillHydro[g, t] for t in m.TPS_IN_TS[ts])
            == m.hydro_avg_flow_mw[g, ts] * m.ts_num_tps[ts]
        ),
    )

    mod.min_data_check("hydro_min_flow_mw", "hydro_avg_flow_mw")


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import hydro data. The single file hydro_timeseries.csv needs to contain
    entries for each dispatchable hydro project. The set of hydro projects
    is derived from this file, and this file should cover all time periods
    in which the hydro plant can operate.

    Run-of-River hydro projects should not be included in this file; RoR
    hydro is treated like any other variable renewable resource, and
    expects data in variable_capacity_factors.csv.

    hydro_timeseries.csv
        hydro_generation_project, timeseries, hydro_min_flow_mw,
        hydro_avg_flow_mw

    """
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "hydro_timeseries.csv"),
        index=mod.HYDRO_GEN_TS_RAW,
        param=(mod.hydro_min_flow_mw, mod.hydro_avg_flow_mw),
    )
