# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines load zone parameters for the SWITCH-Pyomo model.
"""
import os
from pyomo.environ import *

dependencies = 'switch_mod.timescales'

def define_dynamic_lists(mod):
    """
    LZ_Energy_Components_Produce and LZ_Energy_Components_Consume are lists of
    components that contribute to load-zone level power balance equations.
    sum(LZ_Energy_Components_Produce[z,t]) == sum(LZ_Energy_Components_Consume[z,t])
        for all z,t
    Other modules may append to either list, as long as the components they
    add are indexed by [zone, timepoint] and have units of MW. Other modules
    often include Expressions to summarize decision variables on a zonal basis.
    """
    mod.LZ_Energy_Components_Produce = []
    mod.LZ_Energy_Components_Consume = []


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters that
    describe load zones and associated power balance equations. Unless
    otherwise stated, each set and parameter is mandatory.

    LOAD_ZONES is the set of load zones. mod uses a zonal
    transport model to describe the power grid. Each zone is effectively
    modeled as a single bus connected to the inter-zonal transmission
    network, and connected to loads via local transmission and
    distribution that incurs efficiency losses and must be upgraded over
    time to always meet peak demand. Load zones are abbreviated as lz in
    parameter names and as z for indexes.

    lz_demand_mw[z,t] describes the power demand from the high voltage
    transmission grid each load zone z and timepoint t. This will either go
    into the LZ_Energy_Components_Consume or the Distributed_Withdrawals power
    balance equations, depending on whether the local_td module is included
    and has defined a distributed node for power balancing. If the local_td
    module is excluded, this value should be the total withdrawals from the
    central grid and should include any distribution losses. If the local_td
    module is included, this should be set to total end-use demand (aka sales)
    and should not include distribution losses. lz_demand_mw must be
    non-negative.

    lz_dbid[z] stores an external database id for each load zone. This
    is optional and defaults to the name of the load zone. It will be
    printed out when results are exported.

    lz_ccs_distance_km[z] describes the length of a pipeline in
    kilometers that would need to be built to transport CO2 from a load
    zones central bus to the nearest viable CCS reservoir. This
    parameter is optional and defaults to 0.

    EXTERNAL_COINCIDENT_PEAK_DEMAND_ZONE_PERIODS is a set of load zones and
    periods (z,p) that have lz_expected_coincident_peak_demand specified.

    lz_expected_coincident_peak_demand[z,p] is an optional parameter than can
    be used to externally specify peak load planning requirements in MW.
    Currently local_td and planning_reserves determine capacity requirements
    use lz_expected_coincident_peak_demand as well as load timeseries. Do not
    specify this parameter if you wish for the model to endogenously determine
    capacity requirements after accounting for both load and Distributed
    Energy Resources (DER). 

    Derived parameters:

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
    mod.min_data_check('LOAD_ZONES', 'lz_demand_mw')
    if 'Distributed_Withdrawals' in dir(mod):
        mod.Distributed_Withdrawals.append('lz_demand_mw')
    else:
        mod.LZ_Energy_Components_Consume.append('lz_demand_mw')

    mod.EXTERNAL_COINCIDENT_PEAK_DEMAND_ZONE_PERIODS = Set(
        dimen=2, within=mod.LOAD_ZONES * mod.PERIODS,
        doc="Zone-Period combinations with lz_expected_coincident_peak_demand data.")
    mod.lz_expected_coincident_peak_demand = Param(
        mod.EXTERNAL_COINCIDENT_PEAK_DEMAND_ZONE_PERIODS,
        within=NonNegativeReals)
    mod.lz_total_demand_in_period_mwh = Param(
        mod.LOAD_ZONES, mod.PERIODS,
        within=NonNegativeReals,
        initialize=lambda m, z, p: (
            sum(m.lz_demand_mw[z, t] * m.tp_weight[t]
                for t in m.PERIOD_TPS[p])))


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
    of which is indexed by (z, t) - and ensures they are equal.

    """

    mod.Energy_Balance = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: (
            sum(
                getattr(m, component)[z, t]
                for component in m.LZ_Energy_Components_Produce
            ) == sum(
                getattr(m, component)[z, t]
                for component in m.LZ_Energy_Components_Consume)))


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import load zone data. The following tab-separated files are
    expected in the input directory. Their index columns need to be on
    the left, but the data columns can be in any order. Extra columns
    will be ignored during import, and optional columns can be dropped.
    Other modules (such as local_td) may look for additional columns in
    some of these files. If you don't want to specify data for any
    optional parameter, use a dot . for its value. Optional columns and
    files are noted with a *.

    load_zones.tab
        LOAD_ZONE, lz_ccs_distance_km*, lz_dbid*

    loads.tab
        LOAD_ZONE, TIMEPOINT, lz_demand_mw

    lz_coincident_peak_demand.tab*
        LOAD_ZONE, PERIOD, lz_expected_coincident_peak_demand

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
        filename=os.path.join(inputs_dir, 'lz_coincident_peak_demand.tab'),
        index=mod.EXTERNAL_COINCIDENT_PEAK_DEMAND_ZONE_PERIODS,
        select=('LOAD_ZONE', 'PERIOD', 'lz_expected_coincident_peak_demand'),
        param=(mod.lz_expected_coincident_peak_demand))


def post_solve(instance, outdir):
    """
    Default export of power balance per node and timepoint in tabular format.

    """
    import switch_mod.reporting as reporting
    reporting.write_table(
        instance, instance.LOAD_ZONES, instance.TIMEPOINTS,
        output_file=os.path.join(outdir, "load_balance.txt"),
        headings=("load_zone", "timestamp",) + tuple(
            instance.LZ_Energy_Components_Produce +
            instance.LZ_Energy_Components_Consume),
        values=lambda m, z, t: (z, m.tp_timestamp[t],) + tuple(
            getattr(m, component)[z, t]
            for component in (
                m.LZ_Energy_Components_Produce +
                m.LZ_Energy_Components_Consume)))
