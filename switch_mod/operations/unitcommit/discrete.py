# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines model components to force discrete unit commitment for
generation technologies that have g_unit_size specified.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel(
...     'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
...     'investment.proj_build', 'investment.proj_discrete_build', 
...     'operations.proj_dispatch', 'operations.unitcommit', 
...     'operations.unitcommit.discrete')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

from pyomo.environ import *


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to force discrete
    builds for generation technologies that have g_unit_size specified.
    Unless otherwise stated, all power capacity is specified in units of
    MW and all sets and parameters are mandatory.

    PROJ_DISPATCH_POINTS_DISCRETE is a subset of PROJ_DISPATCH_POINTS
    that only includes projects that have g_unit_size defined for their
    technology.

    CommitUnits[(proj, bld_yr) in PROJECT_BUILDYEARS_DISCRETE] is an
    integer decision variable of how many units to commit.

    Commit_Units_Consistency[(proj, bld_yr) in
    PROJECT_BUILDYEARS_DISCRETE] is a constraint that forces the
    continous decision variable CommitProject to be equal to CommitUnits
    * g_unit_size * proj_availability. The use of proj_availability here
    is a rough estimation to approximate forced or scheduled outages as
    a linear derating factor.

    Josiah's note: I have trouble wrapping my head around this
    estimation method of dealing with outages. It seems reasonable if
    you are describing average annual energy production from a project,
    but if you are modeling discrete unit commitment, it seems like you
    need discrete outage events instead of derating unit size based on
    avearge annual outage rates. In my mind, you would want to include
    discrete unit commitment to significantly increase operational
    detail and realism, a goal which also requires discrete modeling of
    outages. In my mind, mixing a continuous outage derating with a
    discrete unit commitment does not significantly add resolution to an
    operational model. But maybe that's just me.

    """

    mod.PROJ_DISPATCH_POINTS_DISCRETE = Set(
        initialize=mod.PROJ_DISPATCH_POINTS,
        filter=lambda m, pr, t: (
            m.proj_gen_tech[pr] in m.GEN_TECH_WITH_UNIT_SIZES))
    mod.CommitUnits = Var(
        mod.PROJ_DISPATCH_POINTS_DISCRETE,
        within=NonNegativeIntegers)
    mod.Commit_Units_Consistency = Constraint(
        mod.PROJ_DISPATCH_POINTS_DISCRETE,
        rule=lambda m, pr, t: (
            m.CommitProject[pr, t] ==
            m.CommitUnits[pr, t] * m.g_unit_size[m.proj_gen_tech[pr]] *
            m.proj_availability[pr]))
