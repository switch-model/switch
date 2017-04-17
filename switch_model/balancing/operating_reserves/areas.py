# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines balancing areas for operational reserves.
"""
import os
from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones'

def define_components(mod):
    """
    Augments a Pyomo abstract model object with sets and parameters that
    describe balancing areas. Unless otherwise stated, each set and
    parameter is mandatory.

    zone_balancing_area[z] describes which balancing area each load zone
    belongs to. This defaults to "system_wide_balancing_area".

    BALANCING_AREAS is the set of balancing areas in which operational
    reserves must be met. These are the unique names specified in the
    zone_balancing_area[z] parameter. This can be abbreviated as b for indexes.
    
    ZONES_IN_BALANCING_AREA[b] is the set of load zones in a given balancing
    area.
    
    BALANCING_AREA_TIMEPOINTS is the cross product of BALANCING_AREAS and 
    TIMEPOINTS.

    """

    mod.zone_balancing_area = Param(mod.LOAD_ZONES, default='system_wide_balancing_area')
    mod.BALANCING_AREAS = Set(initialize=lambda m: set(
        m.zone_balancing_area[z] for z in m.LOAD_ZONES))
    mod.ZONES_IN_BALANCING_AREA = Set(
        mod.BALANCING_AREAS,
        initialize=lambda m, b: (
            z for z in m.LOAD_ZONES if m.zone_balancing_area[z] == b))
    mod.BALANCING_AREA_TIMEPOINTS = Set(
        initialize=mod.BALANCING_AREAS * mod.TIMEPOINTS)        


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import balancing_area data. The following files are expected in the input
    directory:

    load_zones.tab 
        LOAD_ZONE, ..., zone_balancing_area

    """
    # Include select in each load() function so that it will check out
    # column names, be indifferent to column order, and throw an error
    # message if some columns are not found.
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'load_zones.tab'),
        auto_select=True,
        param=(mod.zone_balancing_area))
