"""
Defines load zone parameters for the SWITCH-Pyomo model.

SYNOPSIS
>>> from coopr.pyomo import *
>>> import timescales
>>> import load_zones
>>> switch_model = AbstractModel()
>>> timescales.define_components(switch_model)
>>> load_zones.define_components(switch_model)
>>> switch_data = DataPortal(model=switch_model)
>>> timescales.load_data(switch_model, switch_data, 'test_dat')
>>> load_zones.load_data(switch_model, switch_data, 'test_dat')
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest -v load_zones.py`
"""
from coopr.pyomo import *
import os

from utilities import check_mandatory_components


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
    zone z and timepoint t.

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

    lz_balancing_area[z] describes which balancing area each load zone
    belongs to.

    BALANCING_AREAS describes the set of balancing areas in which
    operational reserves must be met. These are the unique names
    specified in the lz_balancing_area[z] parameter. You can override
    the default operational reserve requirements (described below) by
    including an additional file in the input directory. See
    load_data() documentation for more details. Balancing areas
    are abbreviated as b for the purposed of indexing.

    quickstart_res_load_frac[b] describes the quickstart reserve
    requirements as a fraction of total load in the balancing area in
    each hour. This defaults to 0.03.

    quickstart_res_wind_frac[b] describes the quickstart reserve
    requirements as a fraction of wind energy produced in the balancing
    area in each hour. This defaults to 0.05.

    quickstart_res_solar_frac[b] describes the quickstart reserve
    requirements as a fraction of solar energy produced in the balancing
    area in each hour. This defaults to 0.05.

    spinning_res_load_frac[b] describes the spinning reserve
    requirements as a fraction of total load in the balancing area in
    each hour. This defaults to 0.03.

    spinning_res_wind_frac[b] describes the spinning reserve
    requirements as a fraction of wind energy produced in the balancing
    area in each hour. This defaults to 0.05.

    spinning_res_solar_frac[b] describes the spinning reserve
    requirements as a fraction of solar energy produced in the balancing
    area in each hour. This defaults to 0.05.

    Derived parameters:

    lz_total_demand_in_disp_scen_mwh[z,p] describes the total energy demand
    of each load zone in each dispatch scenario in Megawatt hours.

    """

    mod.LOAD_ZONES = Set()
    mod.lz_demand_mw = Param(
        mod.LOAD_ZONES, mod.TIMEPOINTS, within=NonNegativeReals)
    mod.lz_peak_demand_mw = Param(
        mod.LOAD_ZONES, mod.INVEST_PERIODS, within=PositiveReals)
    mod.lz_cost_multipliers = Param(
        mod.LOAD_ZONES, within=PositiveReals)
    mod.lz_ccs_distance_km = Param(
        mod.LOAD_ZONES, within=NonNegativeReals)
    mod.lz_balancing_area = Param(mod.LOAD_ZONES)
    mod.lz_dbid = Param(mod.LOAD_ZONES)
    # Verify that mandatory data exists before using it.
    mod.minimal_lz_data = BuildCheck(
        rule=lambda mod: check_mandatory_components(
            mod, 'LOAD_ZONES', 'lz_demand_mw', 'lz_dbid',
            'lz_cost_multipliers', 'lz_ccs_distance_km', 'lz_balancing_area'))
    mod.lz_total_demand_in_disp_scen_mwh = Param(
        mod.LOAD_ZONES, mod.DISPATCH_SCENARIOS, within=PositiveReals,
        initialize=lambda mod, z, disp_scen: (
            sum(mod.lz_demand_mw[z, t] * mod.tp_weight[t]
                for t in mod.DISP_SCEN_TPS[disp_scen])))

    mod.BALANCING_AREAS = Set(initialize=lambda mod: set(
        mod.lz_balancing_area[z] for z in mod.LOAD_ZONES))
    mod.quickstart_res_load_frac = Param(
        mod.BALANCING_AREAS, within=PositiveReals, default=0.03,
        validate=lambda mod, val, b: val < 1)
    mod.quickstart_res_wind_frac = Param(
        mod.BALANCING_AREAS, within=PositiveReals, default=0.05,
        validate=lambda mod, val, b: val < 1)
    mod.quickstart_res_solar_frac = Param(
        mod.BALANCING_AREAS, within=PositiveReals, default=0.05,
        validate=lambda mod, val, b: val < 1)
    mod.spinning_res_load_frac = Param(
        mod.BALANCING_AREAS, within=PositiveReals, default=0.03,
        validate=lambda mod, val, b: val < 1)
    mod.spinning_res_wind_frac = Param(
        mod.BALANCING_AREAS, within=PositiveReals, default=0.05,
        validate=lambda mod, val, b: val < 1)
    mod.spinning_res_solar_frac = Param(
        mod.BALANCING_AREAS, within=PositiveReals, default=0.05,
        validate=lambda mod, val, b: val < 1)

def load_data(mod, switch_data, inputs_directory):
    """

    Import load zone data. The following files are expected in the input
    directory:

    load_zones.tab should be a tab-separated file with the columns:
        LOAD_ZONE, cost_multipliers, ccs_distance_km, balancing_area,
        dbid

    lz_peak_loads.tab should be a tab-separated file with the columns:
        LOAD_ZONE, PERIOD, peak_demand_mw

    loads.tab should be a tab-separated file with the columns:
        LOAD_ZONE, TIMEPOINT, peak_demand_mw

    balancing_areas.tab is optional and should be specified if you want
    to override the default values for operational reserves. If
    provided, it needs to be formatted as a tab-separated file with the
    columns:
        BALANCING_AREAS, quickstart_res_load_frac,
        quickstart_res_wind_frac, quickstart_res_solar_frac,
        spinning_res_load_frac, spinning_res_wind_frac,
        spinning_res_solar_frac

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load(
        filename=os.path.join(inputs_directory, 'load_zones.tab'),
        select=('LOAD_ZONE', 'cost_multipliers', 'ccs_distance_km',
                'balancing_area', 'dbid'),
        index=mod.LOAD_ZONES,
        param=(mod.lz_cost_multipliers, mod.lz_ccs_distance_km,
               mod.lz_balancing_area, mod.lz_dbid))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'lz_peak_loads.tab'),
        select=('LOAD_ZONE', 'PERIOD', 'peak_demand_mw'),
        param=(mod.lz_peak_demand_mw))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'loads.tab'),
        select=('LOAD_ZONE', 'TIMEPOINT', 'demand_mw'),
        param=(mod.lz_demand_mw))
    balancing_area_path = os.path.join(inputs_directory, 'balancing_areas.tab')
    if os.path.isfile(balancing_area_path):
        # Load balancing area data from a file if it exists.
        switch_data.load(
            filename=balancing_area_path,
            select=(
                'BALANCING_AREAS', 'quickstart_res_load_frac',
                'quickstart_res_wind_frac', 'quickstart_res_solar_frac',
                'spinning_res_load_frac', 'spinning_res_wind_frac',
                'spinning_res_solar_frac'),
            param=(mod.quickstart_res_load_frac, mod.quickstart_res_wind_frac,
                   mod.quickstart_res_solar_frac, mod.spinning_res_load_frac,
                   mod.spinning_res_wind_frac, mod.spinning_res_solar_frac))
