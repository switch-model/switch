# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to force discrete builds for generation technologies
that have proj_unit_size specified.
"""

from pyomo.environ import *

dependencies = 'switch_mod.timescales', 'switch_mod.load_zones',\
    'switch_mod.financials.minimize_cost', 'switch_mod.energy_sources', \
    'switch_mod.investment.proj_build'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to force discrete
    builds for generation technologies that have proj_unit_size specified.
    Unless otherwise stated, all power capacity is specified in units of
    MW and all sets and parameters are mandatory.

    NEW_PROJ_BUILDYEARS_DISCRETE is a subset of NEW_PROJ_BUILDYEARS that
    only includes projects that have proj_unit_size defined for their
    technology.

    BuildUnits[(proj, bld_yr) in NEW_PROJ_BUILDYEARS_DISCRETE] is an
    integer decision variable of how many units to build.

    Build_Units_Consistency[(proj, bld_yr) in NEW_PROJ_BUILDYEARS_DISCRETE]
    is a constraint that forces the continous decision variable
    BuildProj to be equal to BuildUnits * proj_unit_size.

    """

    mod.NEW_PROJ_BUILDYEARS_DISCRETE = Set(
        initialize=mod.NEW_PROJ_BUILDYEARS,
        filter=lambda m, proj, bld_yr: proj in m.PROJECTS_WITH_UNIT_SIZES)
    mod.BuildUnits = Var(
        mod.NEW_PROJ_BUILDYEARS_DISCRETE,
        within=NonNegativeIntegers)
    mod.Build_Units_Consistency = Constraint(
        mod.NEW_PROJ_BUILDYEARS_DISCRETE,
        rule=lambda m, proj, bld_yr: (
            m.BuildProj[proj, bld_yr] ==
            m.BuildUnits[proj, bld_yr] * m.proj_unit_size[proj]))
