"""
Defines balacing area components for the SWITCH-Pyomo model.

SYNOPSIS
>>> import switch_mod.utilities as utilities
>>> switch_modules = ('timescales', 'load_zones', 'balancing_areas')
>>> utilities.load_modules(switch_modules)
>>> switch_model = utilities.define_AbstractModel(switch_modules)
>>> inputs_dir = 'test_dat'
>>> switch_data = utilities.load_data(switch_model, inputs_dir, switch_modules)
>>> switch_instance = switch_model.create(switch_data)

Note, this can be tested with `python -m doctest balancing_areas.py`
within the switch_mod source directory.

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""
import os
from pyomo.environ import *
import switch_mod.utilities as utilities


def define_components(mod):
    """

    Augments a Pyomo abstract model object with sets and parameters that
    describe balancing areas. Unless otherwise stated, each set and
    parameter is mandatory.

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

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    mod.lz_balancing_area = Param(mod.LOAD_ZONES)
    mod.min_data_check('lz_balancing_area')
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


def load_data(mod, switch_data, inputs_dir):
    """

    Import balancing_area data. The following files are expected in the input
    directory:

    lz_balancing_areas.tab should be a tab-separated file with the columns:
        LOAD_ZONE, balancing_area

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
        filename=os.path.join(inputs_dir, 'lz_balancing_areas.tab'),
        select=('LOAD_ZONE', 'balancing_area'),
        param=(mod.lz_balancing_area))
    path = os.path.join(inputs_dir, 'balancing_areas.tab')
    if os.path.isfile(path):
        # Load balancing area data from a file if it exists.
        switch_data.load(
            filename=path,
            select=(
                'BALANCING_AREAS', 'quickstart_res_load_frac',
                'quickstart_res_wind_frac', 'quickstart_res_solar_frac',
                'spinning_res_load_frac', 'spinning_res_wind_frac',
                'spinning_res_solar_frac'),
            param=(mod.quickstart_res_load_frac, mod.quickstart_res_wind_frac,
                   mod.quickstart_res_solar_frac, mod.spinning_res_load_frac,
                   mod.spinning_res_wind_frac, mod.spinning_res_solar_frac))
