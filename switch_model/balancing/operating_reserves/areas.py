# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines balancing areas for operational reserves.

INPUT FILE INFORMATION

    Import balancing_area data. The following files are expected in the input
    directory:

    load_zones.csv
        LOAD_ZONE, ..., zone_balancing_area
"""
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

    mod.zone_balancing_area = Param(
        mod.LOAD_ZONES,
        input_file="load_zones.csv",
        default='system_wide_balancing_area', within=Any)
    mod.BALANCING_AREAS = Set(
        ordered=False,
        initialize=lambda m: set(
        m.zone_balancing_area[z] for z in m.LOAD_ZONES))
    mod.ZONES_IN_BALANCING_AREA = Set(
        mod.BALANCING_AREAS,
        initialize=lambda m, b: (
            z for z in m.LOAD_ZONES if m.zone_balancing_area[z] == b))
    mod.BALANCING_AREA_TIMEPOINTS = Set(
        initialize=mod.BALANCING_AREAS * mod.TIMEPOINTS)