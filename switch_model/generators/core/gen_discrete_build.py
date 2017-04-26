# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to force discrete builds for generation technologies
that have gen_unit_size specified.
"""

from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties', \
    'switch_model.generators.core.build'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to force discrete
    builds for generation technologies that have gen_unit_size specified.
    Unless otherwise stated, all power capacity is specified in units of
    MW and all sets and parameters are mandatory.

    NEW_DISCRETE_GEN_BLD_YRS is a subset of NEW_GEN_BLD_YRS that
    only includes projects that have gen_unit_size defined.

    BuildUnits[(g, bld_yr) in NEW_DISCRETE_GEN_BLD_YRS] is an
    integer decision variable of how many units to build.

    Build_Units_Consistency[(g, bld_yr) in NEW_DISCRETE_GEN_BLD_YRS]
    is a constraint that forces the continous decision variable
    BuildGen to be equal to BuildUnits * gen_unit_size.

    """

    mod.NEW_DISCRETE_GEN_BLD_YRS = Set(
        initialize=mod.NEW_GEN_BLD_YRS,
        filter=lambda m, g, bld_yr: g in m.DISCRETELY_SIZED_GENS)
    mod.BuildUnits = Var(
        mod.NEW_DISCRETE_GEN_BLD_YRS,
        within=NonNegativeIntegers)
    mod.Build_Units_Consistency = Constraint(
        mod.NEW_DISCRETE_GEN_BLD_YRS,
        rule=lambda m, g, bld_yr: (
            m.BuildGen[g, bld_yr] ==
            m.BuildUnits[g, bld_yr] * m.gen_unit_size[g]))
