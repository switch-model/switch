# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.
"""
Specify policy constraints that are specific to the state of california in the SWITCH-WECC model.
"""
from __future__ import division
import os
from pyomo.environ import Set, Param, Expression, Constraint, Suffix

def define_components(model):
    CA_regions = ["CA_IID", "CA_LADWP", "CA_PGE_BAY", "CA_PGE_CEN", "CA_PGE_N", "CA_PGE_S", "CA_SCE_CEN", "CA_SCE_S",
                  "CA_SCE_SE", "CA_SCE_VLY", "CA_SDGE", "CA_SMUD"]

    min_CA_production = 0.8
