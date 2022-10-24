"""Special operating rules for individual plants on Oahu."""

import os
from pyomo.environ import *
from switch_model.utilities import unique_list


def define_arguments(argparser):
    argparser.add_argument(
        "--run-kalaeloa-even-with-high-rps",
        action="store_true",
        default=False,
        help="Enforce the 75 MW minimum-output rule for Kalaeloa in all years (otherwise relaxed "
        "if RPS or EV share >= 75%%). Mimics behavior from switch 2.0.0b2.",
    )


def define_components(m):
    refineries_closed(m)
    kalaeloa(m)
    schofield(m)
    cogen(m)


def refineries_closed(m):
    """
    Define the REFINERIES_CLOSED_TPS set, which identifies timepoints when
    oil refineries are assumed to be closed.

    In 2018, fossil fuel consumption was roughly 1M barrels for various
    taxable uses, 420k barrels for utility, and maybe 500k barrels for
    non-utility electricity production (Kalaeloa)? (It looks like jet
    kerosene was brought in directly.) There are two refineries that split
    the crude oil into LSFO, gasoline and other products. These are co-products,
    so it's probably not cost-effective to keep running any refinery with the
    same amount of steam if the demand for either product drops too far.
    We shut these down if fossil fuel is used for less than 25% of total power
    or vehicles. (Maybe 50% would be better?)
    """

    def filter(m, tp):
        ev_share = (
            m.ev_share["Oahu", m.tp_period[tp]] if hasattr(m, "ev_share") else 0.0
        )
        rps_level = (
            m.rps_target_for_period[m.tp_period[tp]]
            if hasattr(m, "rps_target_for_period")
            else 0.0
        )
        return ev_share >= 0.75 or rps_level >= 0.75

    m.REFINERIES_CLOSED_TPS = Set(dimen=1, initialize=m.TIMEPOINTS, filter=filter)


def kalaeloa(m):
    """Special dispatch/commitment rules for Kalaeloa plant."""
    # force Kalaeloa_CC3 offline unless 1&2 are at max (per John Cole e-mail 9/28/16)

    # by inspection of figure 8 & 9 in the RPS Study, it appears that Kalaeloa has 3 modes:
    # commit unit 1, run between 65 and 90 MW
    # commit units 1 & 2, run each between 65 and 90 MW
    # run both 1 & 2 at 90 MW, and run 3 at 28 MW

    m.KALAELOA_MAIN_UNITS = Set(
        dimen=1,
        initialize=[
            "Oahu_Kalaeloa_CC1",
            "Oahu_Kalaeloa_CC2",
            "Kalaeloa_CC1",
            "Kalaeloa_CC2",
        ],
        filter=lambda m, g: g in m.GENERATION_PROJECTS,
    )
    m.KALAELOA_DUCT_BURNERS = Set(
        dimen=1,
        initialize=["Oahu_Kalaeloa_CC3", "Kalaeloa_CC3"],
        filter=lambda m, g: g in m.GENERATION_PROJECTS,
    )

    m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.KALAELOA_MAIN_UNITS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    m.KALAELOA_DUCT_BURNER_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.KALAELOA_DUCT_BURNERS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    m.KALAELOA_ACTIVE_TIMEPOINTS = Set(
        dimen=1,
        initialize=lambda m: unique_list(
            tp for g, tp in m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS
        ),
    )

    # run kalaeloa at full power or not
    # (if linearized, this is the fraction of capacity that is dispatched)
    m.RunKalaeloaUnitFull = Var(m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS, within=Binary)

    m.Run_Kalaeloa_Unit_Full_Enforce = Constraint(  # big-m constraint
        m.KALAELOA_MAIN_UNIT_DISPATCH_POINTS,
        rule=lambda m, g, tp: m.DispatchGen[g, tp]
        + (1 - m.RunKalaeloaUnitFull[g, tp]) * m.gen_capacity_limit_mw[g]
        >= m.GenCapacityInTP[g, tp] * m.gen_availability[g],
    )

    # only run duct burner if all main units are full-on
    m.Run_Kalaeloa_Duct_Burner_Only_When_Full = Constraint(
        m.KALAELOA_DUCT_BURNER_DISPATCH_POINTS,
        m.KALAELOA_MAIN_UNITS,
        rule=lambda m, g_duct, tp, g_main: m.DispatchGen[g_duct, tp]
        <= m.RunKalaeloaUnitFull[g_main, tp] * m.gen_capacity_limit_mw[g_duct],
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

        # We assume that Kalaeloa's must-run rule applies only until the
        # refineries close, as specified in the m.oahu_refineries_closed parameter
        if both_units_out or (
            tp in m.REFINERIES_CLOSED_TPS
            and not m.options.run_kalaeloa_even_with_high_rps
        ):
            return Constraint.Skip
        else:
            return sum(m.DispatchGen[g, tp] for g in m.KALAELOA_MAIN_UNITS) >= 75.0

    m.Kalaeloa_Must_Run = Constraint(
        m.KALAELOA_ACTIVE_TIMEPOINTS, rule=Kalaeloa_Must_Run_rule
    )


def schofield(m):
    """
    Require Schofield to run on at least 50% biodiesel (as required by Army). We
    generalize that to 50% renewable fuel.
    See https://www.power-eng.com/2017/08/21/schofield-generating-station-highlights-value-of-reciprocating-engines/
    and pp. 18-19 of https://dms.puc.hawaii.gov/dms/DocumentViewer?pid=A1001001A15I30B50504F50301
    and https://www.govtech.com/fs/Power-Plant-in-Hawaii-to-Run-Partly-on-Biofuel.html
    """

    m.SCHOFIELD_GENS = Set(
        dimen=1,
        initialize=m.GENERATION_PROJECTS,
        filter=lambda m, g: "schofield" in g.lower(),
    )
    m.One_Schofield = BuildCheck(rule=lambda m: len(m.SCHOFIELD_GENS) == 1)

    if not hasattr(m, "f_rps_eligible"):
        raise RuntimeError(
            "The {} module requires the hawaii.rps module.".format(__name__)
        )

    def rule(m, g, t):
        if (g, t) not in m.GEN_TPS:
            return Constraint.Skip  # beyond retirement date
        all_fuel = sum(m.GenFuelUseRate[g, t, f] for f in m.FUELS_FOR_GEN[g])
        renewable_fuel = sum(
            m.GenFuelUseRate[g, t, f] for f in m.FUELS_FOR_GEN[g] if m.f_rps_eligible[f]
        )
        return renewable_fuel >= 0.5 * all_fuel

    m.Schofield_50_Percent_Renewable = Constraint(
        m.SCHOFIELD_GENS, m.TIMEPOINTS, rule=rule
    )


def cogen(m):
    """
    Shutdown small cogen plants when refineries are closed.
    Don't burn biodiesel in cogen plants.
    """
    m.REFINERY_GENS = Set(
        dimen=1,
        initialize=m.GENERATION_PROJECTS,
        filter=lambda m, g: any(rg in g for rg in ["Hawaii_Cogen", "Tesoro_Hawaii"]),
    )
    m.Two_Refinery_Gens = BuildCheck(rule=lambda m: len(m.REFINERY_GENS) == 2)

    # relax commitment requirement when refineries are closed
    def rule(m, g, tp):
        if (g, tp) in m.Enforce_Commit_Lower_Limit:
            print("relaxing commitment for {}, {}".format(g, tp))
            m.Enforce_Commit_Lower_Limit[g, tp].deactivate()

    m.Relax_Refinery_Cogen_Baseload_Constraint = BuildAction(
        m.REFINERY_GENS, m.REFINERIES_CLOSED_TPS, rule=rule
    )
    # force 0 production when refineries are closed
    def rule(m, g, t):
        if (g, t) not in m.GEN_TPS:
            return Constraint.Skip  # beyond retirement date
        else:
            return m.DispatchGen[g, tp] == 0

    m.Shutdown_Refinery_Cogens = Constraint(
        m.REFINERY_GENS, m.REFINERIES_CLOSED_TPS, rule=rule
    )

    m.REFINERY_BIOFUELS = Set(
        dimen=1,
        initialize=lambda m: unique_list(
            f
            for g in m.REFINERY_GENS
            for f in m.FUELS_FOR_GEN[g]
            if m.f_rps_eligible[f]
        ),
    )
    # don't burn biofuels in cogen plants
    def rule(m, g, t, f):
        if (g, t, f) not in m.GenFuelUseRate:
            return Constraint.Skip  # beyond retirement date or wrong fuel
        else:
            return m.GenFuelUseRate[g, t, f] == 0.0

    m.Cogen_No_Biofuel = Constraint(
        m.REFINERY_GENS, m.TIMEPOINTS, m.REFINERY_BIOFUELS, rule=rule
    )
