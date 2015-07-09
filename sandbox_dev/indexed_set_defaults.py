#!/usr/local/bin/python
# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Goal: Specify default values for an indexed set that can be partially
or entirely overriden by computed values injected into data portal.


Attempt 1: Use initialize to specify default values, then stuff data
into a data portal.

Fail. If you specify any data for an indexed set, it completely
overrides the initialization function.
"""

from pyomo.environ import *

mod = AbstractModel()

mod.GEN_TECH_WITH_FUEL = Set()
mod.g_full_load_heat_rate = Param(
    mod.GEN_TECH_WITH_FUEL)

mod.GEN_FUEL_USE_SEGMENTS = Set(
    mod.GEN_TECH_WITH_FUEL,
    dimen=2)

data_portal = DataPortal(model=mod)
data_portal.load(filename='indexed_set_defaults.dat')
data_portal.data()['GEN_FUEL_USE_SEGMENTS'] = {
    'NG-CCGT': [(2, 5), (1, 6)]
}


instance = mod.create(data_portal)
instance.pprint()

"""
Attempt 2: Stuff data in through the dataportal, then use BuildAction
to fill in any blanks.

Success.
"""


def GEN_FUEL_USE_SEGMENTS_default_rule(m, g):
    if g not in m.GEN_FUEL_USE_SEGMENTS:
        m.GEN_FUEL_USE_SEGMENTS[g] = [(0, m.g_full_load_heat_rate[g])]
mod.GEN_FUEL_USE_SEGMENTS_default = BuildAction(
    mod.GEN_TECH_WITH_FUEL,
    rule=GEN_FUEL_USE_SEGMENTS_default_rule)

instance = mod.create(data_portal)
instance.pprint()

"""
When I tried to reuse this example code in my full model, it didn't
work with p_full_load_heat_rate and was super-buggy. What follows is
an attempt to replicate that bug in a simple manner.

The key factor was mutable=True for p_full_load_heat_rate .. a hold-
over from when I was playing around with a BuildAction to either
populate empty values with g_full_load_heat_rate or throw an error if
both sources of data were missing. BuildAction threw an error when
setting the p_full_load_heat_rate unless mutable was set to True. I
later realized I could more cleanly accomplish that by putting the
same logic into the function that set default values, but after moving
the code there, I forgot to remove the mutable flag. When I take
mutable=True out, this works fine. New Hypothesis: anytime you use a
mutable parameter, wrap it in an value() statement to avoid craziness.
"""
mod.FUEL_BASED_PROJECTS = Set()
mod.proj_gen_tech = Param(mod.FUEL_BASED_PROJECTS)
mod.p_full_load_heat_rate = Param(
    mod.FUEL_BASED_PROJECTS,
    default=lambda m, p: m.g_full_load_heat_rate[m.proj_gen_tech[p]],
    mutable=True)
mod.PROJ_FUEL_USE_SEGMENTS = Set(
    mod.FUEL_BASED_PROJECTS,
    dimen=2)


def PROJ_FUEL_USE_SEGMENTS_default_rule(m, pr):
    if pr not in m.PROJ_FUEL_USE_SEGMENTS:
        m.PROJ_FUEL_USE_SEGMENTS[pr] = [(0, m.p_full_load_heat_rate[pr])]
mod.PROJ_FUEL_USE_SEGMENTS_default = BuildAction(
    mod.FUEL_BASED_PROJECTS,
    rule=PROJ_FUEL_USE_SEGMENTS_default_rule)

data_portal = DataPortal(model=mod)
data_portal.load(filename='indexed_set_defaults2.dat')
data_portal.data()['PROJ_FUEL_USE_SEGMENTS'] = {
    'S-NG-CCGT': [(2, 5), (1, 6)]
}

instance = mod.create(data_portal)
instance.pprint()
