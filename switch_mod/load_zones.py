"""
Defines load zone parameters for the SWITCH-Pyomo model.

SYNOPSIS
>>> import switch_mod.utilities as utilities
>>> switch_modules = ('timescales', 'load_zones')
>>> utilities.load_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest load_zones.py`
within the switch_mod source directory.

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""
import os
from pyomo.environ import *
import switch_mod.utilities as utilities


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

    lz_demand_mw[z,t] describes the average power demand in each load
    zone z and timepoint t. This is a non negative value.

    lz_demand_mw_as_consumption[z,t] is the same as lz_demand_mw but
    with a negative sign for the benefit of energy balancing equations.

    lz_peak_demand_mw[z,p] describes the peak demand in each load zone z
    and each investment period p.

    lz_dbid[z] stores an external database id for each load zone. This
    is optional and defaults to None. It (or the default value) will be
    printed out when results are exported.

    lz_cost_multipliers[z] is an zone-specific economic multiplier that
    modifies all costs incurred in each load zone. This could reflect
    differential costs of labor, regional inflation, etc. This is an
    optional parameter with a default of 1. mod-WECC uses values
    from the Army Corps of Engineers Civil Works Construction Cost Index
    System with values ranging from 0.92 to 1.20.

    lz_ccs_distance_km[z] describes the length of a pipeline in
    kilometers that would need to be built to transport CO2 from a load
    zones central bus to the nearest viable CCS reservoir. This
    parameter wont be used if Carbon Capture and Sequestration
    technologies are not enabled in a simulation.

    DumpPower[load_zone, timepoint] is a decision variable that allows
    overproduction of energy in every load zone and timepoint.
    This may be interpretted either as the aggregate curtailment needed,
    or as a literal dump load. In the language of linear programming,
    this is a "slack variable" for an energy balancing constraint.

    LZ_Energy_Balance_components is a list of components that contribute
    to load-zone level energy balance equations. Other modules may add
    elements to this list. The energy_balance module will construct a
    Satisfy_Load constraint using this list. Each component in this list
    needs to be indexed by [load_zone, timepoint]. If this indexing is
    not convenient for native model components, I advise writing an
    Expression object indexed by [lz,t] that contains logic to access or
    summarize native model components.

    Derived parameters:

    lz_total_demand_in_period_mwh[z,p] describes the total energy demand
    of each load zone in each period in Megawatt hours.

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    mod.LOAD_ZONES = Set()
    mod.lz_demand_mw = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS, within=NonNegativeReals)
    mod.lz_peak_demand_mw = Param(
        mod.LOAD_ZONES, mod.INVEST_PERIODS, within=PositiveReals)
    mod.lz_cost_multipliers = Param(mod.LOAD_ZONES, within=PositiveReals)
    mod.lz_ccs_distance_km = Param(mod.LOAD_ZONES, within=NonNegativeReals)
    mod.lz_dbid = Param(mod.LOAD_ZONES)
    # Verify that mandatory data exists before using it.
    mod.min_data_check(
        'LOAD_ZONES', 'lz_demand_mw', 'lz_dbid', 'lz_cost_multipliers',
        'lz_ccs_distance_km')
    mod.lz_total_demand_in_period_mwh = Param(
        mod.LOAD_ZONES, mod.INVEST_PERIODS, within=PositiveReals,
        initialize=lambda mod, z, p: (
            sum(mod.lz_demand_mw[z, t] * mod.tp_weight[t]
                for t in mod.PERIOD_TPS[p])))
    mod.lz_demand_mw_as_consumption = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        initialize=lambda m, lz, t: -1 * m.lz_demand_mw[lz, t])
    mod.DumpPower = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonPositiveReals)
    mod.LZ_Energy_Balance_components = [
        'lz_demand_mw_as_consumption', 'DumpPower']


def load_data(mod, switch_data, inputs_directory):
    """

    Import load zone data. The following files are expected in the input
    directory:

    load_zones.tab should be a tab-separated file with the columns:
        LOAD_ZONE, cost_multipliers, ccs_distance_km, dbid

    lz_peak_loads.tab should be a tab-separated file with the columns:
        LOAD_ZONE, PERIOD, peak_demand_mw

    loads.tab should be a tab-separated file with the columns:
        LOAD_ZONE, TIMEPOINT, demand_mw

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load(
        filename=os.path.join(inputs_directory, 'load_zones.tab'),
        select=('LOAD_ZONE', 'cost_multipliers', 'ccs_distance_km',
                'dbid'),
        index=mod.LOAD_ZONES,
        param=(mod.lz_cost_multipliers, mod.lz_ccs_distance_km,
               mod.lz_dbid))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'lz_peak_loads.tab'),
        select=('LOAD_ZONE', 'PERIOD', 'peak_demand_mw'),
        param=(mod.lz_peak_demand_mw))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'loads.tab'),
        select=('LOAD_ZONE', 'TIMEPOINT', 'demand_mw'),
        param=(mod.lz_demand_mw))
