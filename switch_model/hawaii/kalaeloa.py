"""Special dispatch/commitment rules for Kalaeloa plant."""

import os
from pyomo.environ import *

def define_arguments(argparser):
    argparser.add_argument("--run-kalaeloa-even-with-high-rps", action='store_true', default=False,
        help="Enforce the 75 MW minimum-output rule for Kalaeloa in all years (otherwise relaxed "
             "if RPS or EV share >= 75%%). Mimics behavior from switch 2.0.0b2.")

def define_components(m):
    # force Kalaeloa_CC3 offline unless 1&2 are at max (per John Cole e-mail 9/28/16)

    # by inspection of figure 8 & 9 in the RPS Study, it appears that Kalaeloa has 3 modes:
    # commit unit 1, run between 65 and 90 MW
    # commit units 1 & 2, run each between 65 and 90 MW
    # run both 1 & 2 at 90 MW, and run 3 at 28 MW

    m.KALAELOA_MAIN_UNITS = Set(
        initialize=["Oahu_Kalaeloa_CC1", "Oahu_Kalaeloa_CC2", "Kalaeloa_CC1", "Kalaeloa_CC2"],
        filter=lambda m, g: g in m.GENERATION_PROJECTS
    )
    m.KALAELOA_DUCT_BURNERS = Set(
        initialize=["Oahu_Kalaeloa_CC3", "Kalaeloa_CC3"],
        filter=lambda m, g: g in m.GENERATION_PROJECTS
    )

    m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.KALAELOA_MAIN_UNITS for tp in m.TPS_FOR_GEN[g]
        )
    )
    m.KALAELOA_DUCT_BURNER_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.KALAELOA_DUCT_BURNERS for tp in m.TPS_FOR_GEN[g]
        )
    )
    m.KALAELOA_ACTIVE_TIMEPOINTS = Set(
        initialize=lambda m: set(tp for g, tp in m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS)
    )

    # run kalaeloa at full power or not
    # (if linearized, this is the fraction of capacity that is dispatched)
    m.RunKalaeloaUnitFull = Var(m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS, within=Binary)

    m.Run_Kalaeloa_Unit_Full_Enforce = Constraint( # big-m constraint
        m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS,
        rule=lambda m, g, tp:
            m.DispatchGen[g, tp]
            + (1 - m.RunKalaeloaUnitFull[g, tp]) * m.gen_capacity_limit_mw[g]
            >=
            m.GenCapacityInTP[g, tp] * m.gen_availability[g]
    )

    # only run duct burner if all main units are full-on
    m.Run_Kalaeloa_Duct_Burner_Only_When_Full = Constraint(
        m.KALAELOA_DUCT_BURNER_DISPATCH_POINTS, m.KALAELOA_MAIN_UNITS,
        rule=lambda m, g_duct, tp, g_main:
            m.DispatchGen[g_duct, tp]
            <=
            m.RunKalaeloaUnitFull[g_main, tp] * m.gen_capacity_limit_mw[g_duct]
    )

    # force at least one Kalaeloa unit to run at full power at all times
    # (actually 75 MW, based on fig 9 of RPS Study)
    # unless they are both on maintenance outage (per John Cole e-mail 9/28/16)
    def Kalaeloa_Must_Run_rule(m, tp):
        try:
            both_units_out = (
                sum(m.gen_max_commit_fraction[g, tp] for g in m.KALAELOA_MAIN_UNITS)
                == 0
            )
        except AttributeError:
            both_units_out = False

        # in 2018, fossil fuel consumption was roughly 1M barrels for various
        # taxable uses, 420k barrels for utility, and maybe 500k barrels for
        # non-utility electricity production (Kalaeloa)? (It looks like jet
        # kerosene was brought in directly.) There are two refineries that split
        # the crude oil into LSFO, gasoline and other products. These are co-products,
        # so it's probably not cost-effective to keep running any refinery with the
        # same amount of steam if the demand for either product drops below 25%
        # of the 2018 level. So we assume that Kalaeloa's must-run rule applies
        # only until either consumption is below 25% of the starting level.
        ev_share = m.ev_share['Oahu', m.tp_period[tp]] if hasattr(m, 'ev_share') else 0.0
        rps_level = m.rps_target_for_period[m.tp_period[tp]] if hasattr(m, 'rps_target_for_period') else 0.0

        if both_units_out or (
            (ev_share >= 0.75 or rps_level >= 0.75) and not m.options.run_kalaeloa_even_with_high_rps
        ):
            return Constraint.Skip
        else:
            return (sum(m.DispatchGen[g, tp] for g in m.KALAELOA_MAIN_UNITS) >= 75.0)
    m.Kalaeloa_Must_Run = Constraint(m.KALAELOA_ACTIVE_TIMEPOINTS, rule=Kalaeloa_Must_Run_rule)
