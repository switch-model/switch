# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines model components to force discrete unit commitment for
generation technologies that have gen_unit_size specified.
"""

from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials', 'switch_model.energy_sources.properties',\
    'switch_model.generators.core.build', 'switch_model.investment.gen_discrete_build',\
    'switch_model.generators.core.dispatch', 'switch_model.operations.unitcommit'

def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to force discrete
    builds for generation technologies that have gen_unit_size specified.
    Unless otherwise stated, all power capacity is specified in units of
    MW and all sets and parameters are mandatory.

    GEN_TPS_DISCRETE is a subset of GEN_TPS
    that only includes projects that have gen_unit_size defined.

    CommitGenUnits[(g, bld_yr) in GEN_BLD_YRS_DISCRETE] is an
    integer decision variable of how many units to commit.

    Commit_Units_Consistency[(g, bld_yr) in
    GEN_BLD_YRS_DISCRETE] is a constraint that forces the
    continous decision variable CommitGen to be equal to CommitGenUnits
    * gen_unit_size * gen_availability. The use of gen_availability here
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

    mod.GEN_TPS_DISCRETE = Set(
        initialize=mod.GEN_TPS,
        filter=lambda m, g, t: (
            g in m.DISCRETELY_SIZED_GENS))
    mod.CommitGenUnits = Var(
        mod.GEN_TPS_DISCRETE,
        within=NonNegativeIntegers)
    mod.Commit_Units_Consistency = Constraint(
        mod.GEN_TPS_DISCRETE,
        rule=lambda m, g, t: (
            m.CommitGen[g, t] == m.CommitGenUnits[g, t] * 
            m.gen_unit_size[g] * m.gen_availability[g]))
