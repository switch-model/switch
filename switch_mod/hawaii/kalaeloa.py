"""Special dispatch/commitment rules for Kalaeloa plant."""

import os
from pyomo.environ import *

def define_components(m):
    # force Kalaeloa_CC3 offline unless 1&2 are at max (per John Cole e-mail 9/28/16)
    
    # by inspection of figure 8 & 9 in the RPS Study, it appears that Kalaeloa has 3 modes:
    # commit unit 1, run between 65 and 90 MW
    # commit units 1 & 2, run each between 65 and 90 MW
    # run both 1 & 2 at 90 MW, and run 3 at 28 MW

    # run kalaeloa at full power or not
    m.RunKalaeloaFull = Var(m.TIMEPOINTS, within=Binary)
    
    more_than_kalaeloa_capacity = 220   # used for big-m constraints on individual units
    
    m.Run_Kalaeloa_Full_Enforce = Constraint(
        ["Oahu_Kalaeloa_CC1", "Oahu_Kalaeloa_CC2"], m.TIMEPOINTS, 
        rule=lambda m, g, tp:
            m.DispatchGen[g, tp] + (1-m.RunKalaeloaFull[tp]) * more_than_kalaeloa_capacity
            >=
            m.GenCapacityPerTP[g, tp] * m.gen_availability[g]
    )
    if hasattr(m, 'CommitGenUnits'):
        # using unit commitment
        m.Run_Kalaeloa_CC3_Only_When_Full = Constraint(m.TIMEPOINTS, rule=lambda m, tp:
            m.CommitGenUnits["Oahu_Kalaeloa_CC3", tp]
            <= 
            m.RunKalaeloaFull[tp]
        )
    else:
        # simple model (probably doesn't work well with Kalaeloa!)
        m.Run_Kalaeloa_CC3_Only_When_Full = Constraint(m.TIMEPOINTS, rule=lambda m, tp:
            m.DispatchGen["Oahu_Kalaeloa_CC3", tp]
            <= 
            m.RunKalaeloaFull[tp] * more_than_kalaeloa_capacity
        )
