"""Special dispatch/commitment rules for Kalaeloa plant."""

import os
from pyomo.environ import *

def define_components(m):
    # force Kalaeloa_CC3 offline unless 1&2 are at max (per John Cole e-mail 9/28/16)
    
    # by inspection of figure 8 & 9 in the RPS Study, it appears that Kalaeloa has 3 modes:
    # commit unit 1, run between 65 and 90 MW
    # commit units 1 & 2, run each between 65 and 90 MW
    # run both 1 & 2 at 90 MW, and run 3 at 28 MW

    more_than_kalaeloa_capacity = 220   # used for big-m constraints on individual units

    m.KALAELOA_MAIN_UNITS = Set(
        initialize=["Oahu_Kalaeloa_CC1", "Oahu_Kalaeloa_CC2", "Kalaeloa_CC1", "Kalaeloa_CC2"],
        filter=lambda m, p: p in m.PROJECTS
    )
    m.KALAELOA_DUCT_BURNERS = Set(
        initialize=["Oahu_Kalaeloa_CC3", "Kalaeloa_CC3"],
        filter=lambda m, p: p in m.PROJECTS
    )
    
    m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (p, tp) for p in m.KALAELOA_MAIN_UNITS for tp in m.PROJ_ACTIVE_TIMEPOINTS[p]
        )
    )
    m.KALAELOA_DUCT_BURNER_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (p, tp) for p in m.KALAELOA_DUCT_BURNERS for tp in m.PROJ_ACTIVE_TIMEPOINTS[p]
        )
    )
    m.KALAELOA_ACTIVE_TIMEPOINTS = Set(
        initialize=lambda m: set(tp for p, tp in m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS)
    )
    
    # run kalaeloa at full power or not
    m.RunKalaeloaUnitFull = Var(m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS, within=Binary)
    
    m.Run_Kalaeloa_Unit_Full_Enforce = Constraint(
        m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS,
        rule=lambda m, proj, tp:
            m.DispatchProj[proj, tp] 
            + (1 - m.RunKalaeloaUnitFull[proj, tp]) * more_than_kalaeloa_capacity
            >=
            m.ProjCapacityTP[proj, tp] * m.proj_availability[proj]
    )

    # only run duct burner if all main units are full-on
    m.Run_Kalaeloa_Duct_Burner_Only_When_Full = Constraint(
        m.KALAELOA_DUCT_BURNER_DISPATCH_POINTS, m.KALAELOA_MAIN_UNITS,
        rule=lambda m, p_duct, tp, p_main:
            m.DispatchProj[p_duct, tp]
            <= 
            m.RunKalaeloaUnitFull[p_main, tp] * more_than_kalaeloa_capacity
    )

    # force at least one Kalaeloa unit to run at full power at all times
    # unless they are both on maintenance outage (per John Cole e-mail 9/28/16)
    def Kalaeloa_Must_Run_rule(m, tp):
        try:
            both_units_out = (
                sum(m.proj_max_commit_fraction[p, tp] for p in m.KALAELOA_MAIN_UNITS) 
                == 0
            )
        except AttributeError:
            both_units_out = False

        if both_units_out:
            return Constraint.Skip
        else:
            return (sum(m.RunKalaeloaUnitFull[p, tp] for p in m.KALAELOA_MAIN_UNITS) >= 1)
    m.Kalaeloa_Must_Run = Constraint(m.KALAELOA_ACTIVE_TIMEPOINTS, rule=Kalaeloa_Must_Run_rule)
