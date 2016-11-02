# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Defines model components to enforce a minimum value for new project build-outs.
This module incorporates binary variables into the model.

"""

from pyomo.environ import *

def define_components(mod):
    """
    
    NEW_PROJ_WITH_MIN_BUILD_YEARS is the subset of NEW_PROJ_BUILDYEARS for
    which minimum capacity build-out constraints will be enforced.
    
    ProjCommitToMinBuild[proj, build_year] is a binary variable that indicates
    whether a project will build capacity in a period or not. If the model is
    committing to building capacity, then the minimum must be enforced.
    
    Enforce_Min_Build_Lower[proj, build_year]  and
    Enforce_Min_Build_Upper[proj, build_year] are a pair of constraints that
    force project build-outs to meet the minimum build requirements for
    generation technologies that have those requirements. They force BuildProj
    to be 0 when ProjCommitToMinBuild is 0, and to be greater than
    g_min_build_capacity when ProjCommitToMinBuild is 1. In the latter case,
    the upper constraint should be non-binding. The total demand over all
    periods and load zones is used as  a limit, as in the extreme case where
    all energy should have to be served in one hour.
    
    """
        
    mod.NEW_PROJ_WITH_MIN_BUILD_YEARS = Set(
        initialize=mod.NEW_PROJ_BUILDYEARS,
        filter=lambda m, pr, p: (
            m.g_min_build_capacity[m.proj_gen_tech[pr]] > 0))
    
    mod.ProjCommitToMinBuild = Var(
        mod.NEW_PROJ_WITH_MIN_BUILD_YEARS, within=Binary)
    
    mod.Enforce_Min_Build_Lower = Constraint(
        mod.NEW_PROJ_WITH_MIN_BUILD_YEARS,
        rule=lambda m, proj, p: (
            m.ProjCommitToMinBuild[proj, p] * 
            m.g_min_build_capacity[m.proj_gen_tech[proj]] <= 
            m.BuildProj[proj, p]))
    
    mod.Enforce_Min_Build_Upper = Constraint(
        mod.NEW_PROJ_WITH_MIN_BUILD_YEARS,
        rule=lambda m, proj, p: (
            m.BuildProj[proj, p] <=
            m.ProjCommitToMinBuild[proj, p] *
            sum(m.lz_demand_mw[lz, tp] * m.tp_weight[tp]
                for lz in m.LOAD_ZONES
                for tp in m.TIMEPOINTS)))
