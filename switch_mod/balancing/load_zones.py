# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines load zone parameters for the SWITCH-Pyomo model.
"""
import os
from pyomo.environ import *

dependencies = 'switch_mod.timescales'

def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters that
    describe load zones and some related geographic areas. Unless
    otherwise stated, each set and parameter is mandatory.

    LOAD_ZONES is the set of load zones. mod uses a zonal
    transport model to describe the power grid. Each zone is effectively
    modeled as a single bus connected to the inter-zonal transmission
    network, and connected to loads via local transmission and
    distribution that incurs efficiency losses and must be upgraded over
    time to always meet peak demand. Load zones are abbreviated as lz in
    parameter names and as z for indexes.

    lz_demand_mw[z,t] describes the power demand from the high voltage
    transmission grid each load zone z and timepoint t. If the local_td module
    is excluded, this value should be the total withdrawals from the central
    grid and should include any distribution losses. If the local_td module is
    included, this should be set to total end-use demand (aka sales) and should
    not include distribution losses. This is a non negative value.

    lz_dbid[z] stores an external database id for each load zone. This
    is optional and defaults to the name of the load zone. It will be
    printed out when results are exported.

    lz_ccs_distance_km[z] describes the length of a pipeline in
    kilometers that would need to be built to transport CO2 from a load
    zones central bus to the nearest viable CCS reservoir. This
    parameter is optional and defaults to 0.

    LZ_Energy_Components_Produce and LZ_Energy_Components_Consume are
    lists of components that contribute to load-zone level energy
    balance equations. Other modules may add elements to either list.
    The energy_balance module will construct a Satisfy_Load constraint
    using these lists. Each component needs to be indexed by [load_zone,
    timepoint]. If this indexing is not convenient for native model
    components, I advise writing an Expression object indexed by [lz,t]
    that contains logic to access or summarize native model components.

    Derived parameters:

    lz_peak_demand_mw[z,p] describes the peak demand in each load zone z
    and each investment period p. This optional parameter defaults to
    the highest load in the lz_demand_mw timeseries for the given load
    zone & period.

    lz_total_demand_in_period_mwh[z,p] describes the total energy demand
    of each load zone in each period in Megawatt hours.

    """

    mod.LOAD_ZONES = Set()
    mod.ZONE_TIMEPOINTS = Set(dimen=2,
        initialize=lambda m: m.LOAD_ZONES * m.TIMEPOINTS,
        doc="The cross product of load zones and timepoints, used for indexing.")
    mod.lz_demand_mw = Param(
        mod.ZONE_TIMEPOINTS,
        within=NonNegativeReals)
    mod.lz_ccs_distance_km = Param(
        mod.LOAD_ZONES,
        within=NonNegativeReals,
        default=0.0)
    mod.lz_dbid = Param(
        mod.LOAD_ZONES,
        default=lambda m, lz: lz)
    # Verify that mandatory data exists before using it.
    mod.min_data_check('LOAD_ZONES', 'lz_demand_mw')
    mod.lz_peak_demand_mw = Param(
        mod.LOAD_ZONES, mod.PERIODS,
        within=NonNegativeReals,
        default=lambda m, lz, p: max(
            m.lz_demand_mw[lz, t] for t in m.PERIOD_TPS[p]))
    mod.lz_total_demand_in_period_mwh = Param(
        mod.LOAD_ZONES, mod.PERIODS,
        within=NonNegativeReals,
        initialize=lambda m, z, p: (
            sum(m.lz_demand_mw[z, t] * m.tp_weight[t]
                for t in m.PERIOD_TPS[p])))
    mod.LZ_Energy_Components_Produce = []
    mod.LZ_Energy_Components_Consume = ['lz_demand_mw']


def define_dynamic_components(mod):
    """

    Adds components to a Pyomo abstract model object to enforce the
    first law of thermodynamics at the level of load zone busses. Unless
    otherwise stated, all terms describing power are in units of MW and
    all terms describing energy are in units of MWh.

    Energy_Balance[load_zone, timepoint] is a constraint that mandates
    conservation of energy in every load zone and timepoint. This
    constraint sums the model components in the lists
    LZ_Energy_Components_Produce and LZ_Energy_Components_Consume - each
    of which is indexed by (lz, t) - and ensures they are equal.

    """

    mod.Energy_Balance = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, lz, t: (
            sum(
                getattr(m, component)[lz, t]
                for component in m.LZ_Energy_Components_Produce
            ) == sum(
                getattr(m, component)[lz, t]
                for component in m.LZ_Energy_Components_Consume)))


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import load zone data. The following tab-separated files are
    expected in the input directory. Their index columns need to be on
    the left, but the data columns can be in any order. Extra columns
    will be ignored during import, and optional columns can be dropped.
    Other modules (such as local_td) may look for additional columns in
    some of these files. If you don't want to specify data for any
    optional parameter, use a dot . for its value. All columns in
    load_zones.tab except for the name of the load zone are optional.

    load_zones.tab
        LOAD_ZONE, lz_ccs_distance_km, lz_dbid

    loads.tab
        LOAD_ZONE, TIMEPOINT, lz_demand_mw

    lz_peak_loads.tab is optional.
        LOAD_ZONE, PERIOD, peak_demand_mw

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'load_zones.tab'),
        auto_select=True,
        index=mod.LOAD_ZONES,
        param=(mod.lz_ccs_distance_km, mod.lz_dbid))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'loads.tab'),
        auto_select=True,
        param=(mod.lz_demand_mw))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'lz_peak_loads.tab'),
        select=('LOAD_ZONE', 'PERIOD', 'peak_demand_mw'),
        param=(mod.lz_peak_demand_mw))


def post_solve(instance, outdir):
    """
    Default export of energy balance per node and timepoint in tabular format.

    """
    import switch_mod.reporting as reporting
    reporting.write_table(
        instance, instance.LOAD_ZONES, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "load_balance.txt"),
        headings=("load_zone", "timestamp",) + tuple(
            instance.LZ_Energy_Components_Produce +
            instance.LZ_Energy_Components_Consume),
        values=lambda m, lz, t: (lz, m.tp_timestamp[t],) + tuple(
            getattr(m, component)[lz, t]
            for component in (
                m.LZ_Energy_Components_Produce +
                m.LZ_Energy_Components_Consume)))
