from __future__ import division
from __future__ import print_function
from collections import defaultdict
from textwrap import dedent
import os
from pyomo.environ import *
import pandas as pd
import time

# This module represents our best forecasts of capacity additions on Oahu as of
# June 2020. There are near-term forecasts through 2025 for all technologies and
# long-term forecasts for DGPV and distributed batteries. These are close to the
# forecasts HECO used for their modeling, but sometimes more up-to-date or
# realistic. The forecasts HECO used for their modeling at this time are in
# heco_plan_2020_06.py


def TODO(note):
    raise NotImplementedError(dedent(note).strip())


def NOTE(note):
    print("=" * 80)
    print("{}:".format(__name__))
    print(dedent(note).strip())
    print("=" * 80)
    print()
    # time.sleep(2)


def define_arguments(argparser):
    argparser.add_argument(
        "--psip-force",
        action="store_true",
        default=False,
        help="Force following of PSIP plans (building exact amounts of certain technologies).",
    )
    argparser.add_argument(
        "--psip-relax",
        dest="psip_force",
        action="store_false",
        help="Relax PSIP plans, to find a more optimal strategy.",
    )
    argparser.add_argument(
        "--psip-minimal-renewables",
        action="store_true",
        default=False,
        help="Use only the amount of renewables shown in PSIP plans, and no more (should be combined with --psip-relax).",
    )
    argparser.add_argument(
        "--force-build",
        nargs=3,
        default=None,
        help="Force construction of at least a certain quantity of a particular technology during certain years. Space-separated list of year, technology and quantity.",
    )
    argparser.add_argument(
        "--psip-relax-after",
        type=float,
        default=None,
        help="Follow the PSIP plan up to and including the specified year, then optimize construction in later years. Should be combined with --psip-force.",
    )

    argparser.add_argument(
        "--psip-allow-more-solar-2025",
        action="store_true",
        default=False,
        help="Treat 2025 target for LargePV as lower limit, not exact target.",
    )
    argparser.add_argument(
        "--psip-no-additional-onshore-wind",
        action="store_true",
        default=False,
        help="Don't allow construction of any onshore wind beyond the current plan.",
    )


def is_renewable(tech):
    return any(txt in tech for txt in ("PV", "Wind", "Solar"))


def is_battery(tech):
    return "battery" in tech.lower()


def define_components(m):
    ###################
    # resource rules to match HECO's forecast as of late 2019 or
    # (optionally) 2016-12 PSIP
    ##################

    # decide whether to enforce the PSIP preferred plan
    # if an environment variable is set, that takes precedence
    # (e.g., on a cluster to override options.txt)
    psip_env_var = os.environ.get("USE_PSIP_PLAN")
    if psip_env_var is None:
        # no environment variable; use the --psip-relax flag
        psip = m.options.psip_force
    elif psip_env_var.lower() in ["1", "true", "y", "yes", "on"]:
        psip = True
    elif psip_env_var.lower() in ["0", "false", "n", "no", "off"]:
        psip = False
    else:
        raise ValueError(
            "Unrecognized value for environment variable USE_PSIP_PLAN={} (should be 0 or 1)".format(
                psip_env_var
            )
        )

    if m.options.verbose:
        if psip:
            print("Using PSIP construction plan.")
        else:
            print(
                "Relaxing PSIP construction plan (optimizing around forecasted adoption)."
            )

    # make sure LNG is turned off
    if (
        psip
        and "LNG" in m.FUELS
        and getattr(m.options, "force_lng_tier", []) != ["none"]
    ):
        raise RuntimeError(
            "To match the PSIP with LNG available, you must use the lng_conversion "
            'module and set "--force-lng-tier none".'
        )

    # use cases:
    # DistPV fixed all the way through for most-likely scenarios and PSIP scenarios but not for general Switch-Oahu
    # Distributed storage fixed all the way through in most-likely and PSIP but not Switch-Oahu
    # Centralized storage Battery_Bulk at lower limit all the way through (representing distributed storage) in
    # Large PV, Onshore Wind, Offshore Wind, centralized storage fixed for some early years in most-likely case and PSIP, maybe in Switch-Oahu
    # Other technologies at fixed levels in PSIP but not most-likely case
    # In most-likely and PSIP scenarios, all renewables already in place plus everything specified in targets gets rebuilt at retirement.

    # Plan:
    # - each year is either fixed or flexible, i.e., early years will have predetermined build or not
    # - when PSIP is in effect, all targets are exact -- no construction possible except what's listed
    # - when PSIP is relaxed, definite targets are applied exactly up until last year for which targets
    #   are specified, then extra capacity can be added freely
    #    - this locks in DistPV forecast and other "definite" construction elements
    #    - this also allows specifying early construction either here or in existing plants tables,
    #      with similar effect
    # - "most-likely" (PBR) targets are listed as "definite" targets, applied when PSIP flag turned off
    # - This module introduces a new treatment of the definite targets compared to the older psip_2012_12:
    #   they are treated as exact targets between the start of the study and the last date specified, but
    #   then more can be added in later years.
    # - Battery_Bulk is cloned as DistBattery and targets are set for that (may be excluded from non-PSIP/PBR scenarios)
    #   - this allows fixed targets for DistBattery in same years as free investment in Battery_Bulk
    # - DistPV and DistBattery are listed as definite targets through 2045
    # - PSIP thermal plants are listed in PSIP targets only
    # - early-years storage and renewables automatically get rebuilt in later years, but we don't consider the
    #   rebuild targets when calculating the fixed-construction period for these technologies, so these are used
    #   as lower limits, not fixed targets.

    # * Alternative strategy (abandoned): start from scratch, modifying gen_predetermined_build
    #   * create input spreadsheet showing forecasted capacity for various technology groups in each zone,
    #     grouped into different adoption forecasts (tech_forecast_scenario)
    #   * store this spreadsheet in a table in the back-end database
    #   * store average cap factor of each project in project table
    #   * scenario_data translates this into construction plans
    #       * rank projects in each technology group by levelized cost
    #       * assign capacity target step-ups first to existing projects, then to lowest-cost project as of that year
    #       * assign reconstruction dates to continue capacity step-ups in later years
    #       * capacity step-downs can't be handled because it's not clear which projects should be retired,
    #         and they may be infeasible; they also don't fit with the idea that these tranches last forever
    #       * write all the construction steps into gen_predetermined_build
    #       * can't create construction plans in import_data because they must avoid rebuilding in occupied
    #         projects, which depends on asset life, which depends on tech_scen_id, not known till scenario_data runs
    #   * this approach could also be used to handle all the existing builds, instead of the current existing projects system
    #   * but we're back to an old problem then -- what about cases where these are floors but not upper limits,
    #     e.g., want to force in one CC plant, but open to having more than that?
    #       * could handle that by moving the predetermined part into a separate project, but then project definitions
    #         must depend on tech_forecast_scenario

    # NOTE: RESOLVE used different wind and solar profiles from Switch.
    # Switch profiles seem to be more accurate, so we optimize against them
    # and show that this may give (small) savings vs. the RESOLVE plan.

    # TODO: Should I use Switch to investigate how much of HECO's poor performance is due
    # to using bad resource profiles (small onshore wind that doesn't rise in the rankings),
    # how much is due to capping PV at 300 MW in 2020,
    # how much is due to non-integrality in RESOLVE (fixed by later jimmying by HECO), and
    # how much is due to forcing in elements before and after the optimization?

    # TODO (maybe): set project-specific targets, so that DistPV targets can be spread among tranches
    # and specific projects in the PSIP can be represented accurately (really just NPM wind). This
    # might also allow reconstruction of exactly the same existing or PSIP project when retired
    # (as specified in the PSIP). Currently the code below lets Switch choose the best project with the
    # same technology when it replaces retired renewable projects.

    # targets for individual generation technologies
    # (year, technology, MW added)
    # For storage technologies with flexible energy value (no
    # gen_storage_energy_to_power_ratio provided), MW added should be replaced
    # by a tuple of (MW, hours).

    # Technologies that are forecasted to be built in "most-likely" scenarios.
    # These apply whenever this module is used, even if rest of PSIP plan is
    # ignored by turning off psip flag. Like PSIP targets, these are assumed
    # to be rebuilt at retirement until the end of the study.
    # NOTE("""
    #     Need to get Switch to model solar+storage using normal storage module;
    #     model AC limit and allow unlimited DC on back side. Then use this to
    #     model RFP PV+BESS and forecasted DGPV+DESS.
    # """)
    NOTE(
        """
        ***** For future work, use the newer start-of-year existing PV capacity
        ***** in Existing Plants.xlsx and smooth the transition from the
        ***** actual value at start of 2020 (674) to the 2020 forecast (562).
        ***** Maybe do the same for large solar, i.e., shift everything that was
        ***** online at start of 2020 into the "existing" category and/or make
        ***** the first optimized year 2021.
    """
    )
    tech_group_targets_definite = [
        # HECO June 2018 forecast, saved on shared drive in PBR docket
        # See the following:
        # email from Doug Codiga 11/19/19: "FW: October RWG and PWG Meeting Follow-Ups"
        # forecasts stored in https://drive.google.com/open?id=1ToL7x-m17M2t0Cfd5k6w8no0rDiPy31l
        # "/s/data/Generator Info/HECO Dist PV Forecast Jun 2018.xlsx"
        # We assume all DistPV and DistBattery are used efficiently/optimally,
        # i.e., we do not attempt to model non-optimal pairing of DistPV with
        # DistBattery or curtailment on self-supply tariffs.
        # NOTE: HECO sent a new forecast on 2020-03-18 (see email from Murray
        # Clay at Ulupono that day), but we don't use it because it seems
        # unrealistic. (See email from Murray Clay (Ulupono) 2020-04-14 13:58
        # and  /s/data/Generator Info/HECO Dist PV Forecast 2018-03-17.xlsx)
        (2020, "DistPV", 15.336, "DER forecast"),  # net of 547 in existing capacity
        (2021, "DistPV", 29.51, "DER forecast"),
        (2022, "DistPV", 22.835, "DER forecast"),
        (2023, "DistPV", 19.168, "DER forecast"),
        (2024, "DistPV", 23.087, "DER forecast"),
        (2025, "DistPV", 24.322, "DER forecast"),
        (2026, "DistPV", 25.888, "DER forecast"),
        (2027, "DistPV", 27.24, "DER forecast"),
        (2028, "DistPV", 28.387, "DER forecast"),
        (2029, "DistPV", 29.693, "DER forecast"),
        (2030, "DistPV", 30.522, "DER forecast"),
        (2031, "DistPV", 31.32, "DER forecast"),
        (2032, "DistPV", 32.234, "DER forecast"),
        (2033, "DistPV", 32.42, "DER forecast"),
        (2034, "DistPV", 32.98, "DER forecast"),
        (2035, "DistPV", 33.219, "DER forecast"),
        (2036, "DistPV", 32.785, "DER forecast"),
        (2037, "DistPV", 33.175, "DER forecast"),
        (2038, "DistPV", 33.011, "DER forecast"),
        (2039, "DistPV", 33.101, "DER forecast"),
        (2040, "DistPV", 33.262, "DER forecast"),
        (2041, "DistPV", 33.457, "DER forecast"),
        (2042, "DistPV", 33.343, "DER forecast"),
        (2043, "DistPV", 34.072, "DER forecast"),
        (2044, "DistPV", 34.386, "DER forecast"),
        (2045, "DistPV", 35.038, "DER forecast"),
        # note: HECO provides a MWh forecast; we assume inverters are large
        # enough to charge in 4h
        (2020, "DistBattery", (31.941, 4), "DER forecast"),
        (2021, "DistBattery", (12.968, 4), "DER forecast"),
        (2022, "DistBattery", (9.693, 4), "DER forecast"),
        (2023, "DistBattery", (3.135, 4), "DER forecast"),
        (2024, "DistBattery", (3.732, 4), "DER forecast"),
        (2025, "DistBattery", (4.542, 4), "DER forecast"),
        (2026, "DistBattery", (5.324, 4), "DER forecast"),
        (2027, "DistBattery", (6.115, 4), "DER forecast"),
        (2028, "DistBattery", (6.719, 4), "DER forecast"),
        (2029, "DistBattery", (7.316, 4), "DER forecast"),
        (2030, "DistBattery", (7.913, 4), "DER forecast"),
        (2031, "DistBattery", (8.355, 4), "DER forecast"),
        (2032, "DistBattery", (8.723, 4), "DER forecast"),
        (2033, "DistBattery", (9.006, 4), "DER forecast"),
        (2034, "DistBattery", (9.315, 4), "DER forecast"),
        (2035, "DistBattery", (9.49, 4), "DER forecast"),
        (2036, "DistBattery", (9.556, 4), "DER forecast"),
        (2037, "DistBattery", (9.688, 4), "DER forecast"),
        (2038, "DistBattery", (9.777, 4), "DER forecast"),
        (2039, "DistBattery", (9.827, 4), "DER forecast"),
        (2040, "DistBattery", (9.874, 4), "DER forecast"),
        (2041, "DistBattery", (9.939, 4), "DER forecast"),
        (2042, "DistBattery", (10.098, 4), "DER forecast"),
        (2043, "DistBattery", (10.238, 4), "DER forecast"),
        (2044, "DistBattery", (10.37, 4), "DER forecast"),
        (2045, "DistBattery", (10.478, 4), "DER forecast"),
        # HECO feed-in tariff (FIT) projects under construction as of 10/22/19, from
        # https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board
        # NOTE: PSIP Figure J-10 says these are in addition to the customer DGPV
        # adoption forecast but they are not in "HECO construction plan 2020-03-17.docx".
        # Samantha Ruiz (Ulupono) recommended in email 5/26/20 to count them as
        # non-DER esp. since HECO's March 2020 DER forecast is flat in early
        # years. Note: these are probably fixed-axis rather than tracking (i.e.,
        # more like DistPV than LargePV), and they are at particular locations.
        # But we include them here as LargePV and put them here  instead of in
        # existing projects because (a) they don't reduce available roof
        # inventory and (b) counting them as existing but built in 2020 would
        # block construction of additional large PV in 2020.
        (
            2020,
            "LargePV",
            5,
            "Aloha Solar II",
        ),  # Aloha Solar Energy Fund II, online 4/2/20
        (2021, "LargePV", 3.5, "Mauka FIT 1"),  # Mauka FIT 1
        # note: Mauka FIT 1 and Na Pua Makani (below) are scheduled to come online
        # in 2020, but they are not online yet as of 6/4/2020, so we model them
        # as starting 1/1/2021.
        # Na Pua Makani (NPM) wind
        # 2018/24 MW in PSIP, but still under construction in late 2019;
        # Reported as 24 MW to be online in 2020 in
        # https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board (accessed 10/22/19)
        # Listed as 27 MW with operation beginning by summer 2020 on https://www.napuamakanihawaii.org/fact-sheet/
        # TODO: Is Na Pua Makani 24 MW or 27 MW?
        (2021, "OnshoreWind", 24, "Na Pua Makani"),
        # PSIP 2016: (2018, 'OnshoreWind', 24),
        # CBRE wind and PV
        # Final order given allowing HECO to proceed with standardized contracts
        # in June 2018: https://cca.hawaii.gov/dca/files/2018/07/Order-No-35560-HECO-CBRE.pdf
        # "At the ten-month milestone [June 2019], three projects have half-executed standard
        # form contracts ("SFCs") and interconnection agreements." None had subscribers or were
        # under construction at this point.
        # https://dms.puc.hawaii.gov/dms/DocumentViewer?pid=A1001001A19G15A93031F00794
        # In Oct. 2019, HECO's website said it had agreement(s) in place for 4990 kW
        # of the 5000 MW solar allowed in Phase 1, with 330 kW in queue. I think the
        # June 2018 D&O said this will roll over to Phase 2. No mention of wind on
        # the HECO program website.
        # https://www.hawaiianelectric.com/products-and-services/customer-renewable-programs/community-solar
        # According to HECO press release, the first phase includes (only) 8 MW
        # of solar on all islands (5 MW on Oahu). Other techs will be included
        # in phase 2, which will begin "about two years" from 7/2018.
        # https://www.hawaiianelectric.com/regulators-approve-community-solar-plans
        # In 11/19/19 data sharing, HECO reported "One project for CBRE Phase 1
        # on O'ahu is slated to be installed by Q4 of 2019.  Five Phase 1
        # projects are estimated to be installed in 2020 (one in Q2 2020 and
        # four in Q4 2020).  Lastly, two projects are estimated to be installed
        # in Q3 of 2021.". In heco_outlook_2019 we broke these up into
        # installations in 2019, 2020 and 2021, but in "HECO construction plan 2020-03-17.docx"
        # they treat them all as being installed in 2020, so we do that now.
        (2020, "LargePV", 5, "CBRE Phase 1"),  # CBRE Phase 1
        # Original CBRE program design had only 72 MW in phase 1 and 2 (leaving
        # 64 MW for phase 2), but HECO suggested increasing this to 235 MW over
        # 5 years. HECO said this was because of projected shortfalls in DER
        # program. Joint Parties say it should be possible to accept all of this
        # earlier and expand the program if it goes quickly, and this should not
        # be used to limit DER adoption.
        # https://dms.puc.hawaii.gov/dms/DocumentViewer?pid=A1001001A19H20B01349C00185
        # **** questions:
        # **** Should we reduce DER forecast in light of HECO's projected shortfall reported in CBRE proceeding?
        # **** How much solar should we expect on Oahu in CBRE Phase 2 and when?
        # **** Do we expect any wind on Oahu in CBRE Phase 2, and if so, when?
        # In heco_outlook_2019, we used 150 MW in 2022 as a placeholder Oahu CBRE Phase 2.
        # In this version, we switch to 43.5 in 2025, as shown in "HECO construction plan 2020-03-17.docx"
        # This is in addition to RFPs noted below.
        # (2025, 'LargePV', 43.5),  # CBRE Phase 2
        # According to Murray Clay email 4/14/20, PUC Order No. 37070 in Docket
        # 2015-0389 specified Oahu Phase 2 as 170 MW. "In tranche 1 there is an
        # RFP process for 75 MW and 15 MW through an expedited (small project
        # process).  Tranche 2 is again 75 MW for RFP and 5 MW for expedited
        # small projects for the 170 MW Oahu total.  I think the tariff for the
        # expedited small projects has to be filed in Sept 2020.  RFP 1 is
        # second half of 2020 and RFP 2 is second half of 2021. ... CBRE often
        # takes a lot of time to be deployed...
        # Based on this and later discussion with Ulupono (Samantha Ruiz email
        # 2020-05-26 23:15), we adopted the CBRE phase 2 forecast below:
        (
            2023,
            "LargePV",
            15,
            "CBRE phase 2, small",
        ),  # small, expedited procurement in order
        (
            2024,
            "LargePV",
            5,
            "CBRE phase 2, small",
        ),  # small, expedited procurement in order
        (2025, "LargePV", 150, "CBRE phase 2"),  # larger, slower
        # 2018-2019 RFPs (docket 2017-0352)
        # These replace large PV and bulk batteries reported in PSIP for 2020 and 2022.
        # TODO: maybe move these to existing plants tables
        # "On March 25, 2019, the commission approved six ... grid-scale,
        # solar-plus-storage projects.... Cumulatively, the projects will add 247
        # megawatts ("MW") of solar energy with almost 1 gigawatt hour of
        # storage to the HECO Companies' grids."
        # -- D&O 36604, https://dms.puc.hawaii.gov/dms/DocumentViewer?pid=A1001001A19J10A90756F00117
        # First 6 approved projects (dockets 2018-0430, -0431, -0432, -0434, -0435, and -0436) are listed at
        # -- https://www.hawaiianelectric.com/six-low-priced-solar-plus-storage-projects-approved-for-oahu-maui-and-hawaii-islands
        # On 8/20/19, PUC approved 7th project, 12.5 MW/50 MWh AES solar+storage (docket 2019-0050, order 36480)
        # -- https://dms.puc.hawaii.gov/dms/DocumentViewer?pid=A1001001A19H21B03929E00301
        # -- https://www.hawaiianelectric.com/puc-approves-grid-scale-solar-project-in-west-oahu
        # As of 10/22/19, 8th project, 15 MW/60 MWh solar+storage on Maui, is still under review (docket 2018-0433)
        # Status of all approved projects and in-service data are listed at
        # https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board
        # They are also shown in "HECO construction plan 2020-03-17.docx".
        # As of 2020-05-25, both sources say the first one will be online in
        # 2021 and the other three will be online in 2022. But in an email to
        # Ulupono May 23, 2020, Rod Aoki (HECO) said all RFP 1 projects would
        # be online at the end of 2022. In an email to M Fripp 5/21/20,
        # Samantha Ruiz (Ulupono) said they would likely come online in 2022.
        # In an email to M Fripp 5/23/20, quoting the Rod Aoki email, Murray
        # Clay (Ulupono) recommended they counting them as coming online at
        # start of 2022, not end. Taking account of all this, we set them all
        # to start in 2022.
        (2022, "LargePV", 12.5, "RFP stage 1"),  # AES West Oahu Solar
        (2022, "LargePV", 52, "RFP stage 1"),  # Hoohana Solar 1
        (2022, "LargePV", 39, "RFP stage 1"),  # Mililani I Solar
        (2022, "LargePV", 36, "RFP stage 1"),  # Waiawa Solar
        # storage associated with large PV projects; we assume this will be used
        # efficiently, so we model it along with other large-scale storage.
        (2022, "Battery_Bulk", (12.5, 4), "RFP stage 1"),  # AES West Oahu Solar
        (2022, "Battery_Bulk", (52, 4), "RFP stage 1"),  # Hoohana Solar 1
        (2022, "Battery_Bulk", (39, 4), "RFP stage 1"),  # Mililani I Solar
        (2022, "Battery_Bulk", (36, 4), "RFP stage 1"),  # Waiawa Solar
        # Oahu RFP Stage 2 projects, retrieved 2020-06-04 from
        # https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board
        # We assume they come online at _end_ of year (start of next year).
        # See "data/Generator Info/HECO RFP Stage 2 summary.xlsx" to generate this code.
        # Also see https://www.hawaiianelectric.com/hawaiian-electric-selects-16-projects-in-largest-quest-for-renewable-energy-energy-storage-for-3-islands
        (2023, "LargePV", 6, "RFP stage 2"),  # Kaukonahua Solar
        (2023, "LargePV", 60, "RFP stage 2"),  # Kupehau Solar
        (2023, "LargePV", 42, "RFP stage 2"),  # Kupono Solar
        (2023, "LargePV", 6.6, "RFP stage 2"),  # Mehana Solar
        (2024, "LargePV", 15, "RFP stage 2"),  # Barbers Point Solar
        (2024, "LargePV", 120, "RFP stage 2"),  # Mahi Solar
        (2024, "LargePV", 7, "RFP stage 2"),  # Mountain View Solar
        (2024, "LargePV", 30, "RFP stage 2"),  # Waiawa Phase 2 Solar
        (2023, "Battery_Bulk", (185, 3.054), "RFP stage 2"),  # Kapolei Energy Storage
        (2023, "Battery_Bulk", (6, 4.233), "RFP stage 2"),  # Kaukonahua Solar
        (2023, "Battery_Bulk", (60, 4), "RFP stage 2"),  # Kupehau Solar
        (2023, "Battery_Bulk", (42, 4), "RFP stage 2"),  # Kupono Solar
        (2023, "Battery_Bulk", (6.6, 4), "RFP stage 2"),  # Mehana Solar
        (2024, "Battery_Bulk", (15, 4), "RFP stage 2"),  # Barbers Point Solar
        (2024, "Battery_Bulk", (120, 4), "RFP stage 2"),  # Mahi Solar
        (2024, "Battery_Bulk", (7, 5), "RFP stage 2"),  # Mountain View Solar
        (2024, "Battery_Bulk", (30, 8), "RFP stage 2"),  # Waiawa Phase 2 Solar
        # NOTE: Samantha Ruiz (Ulupono) email 2020-05-21 and 5/26/20 14:36 says
        # PUC directed HECO  to install these by 2022, but she thinks 2023-24 is
        # more likely. In email to Ulupono 5/23/20, Rod Aoki (HECO) said all RFP
        # 2 projects would come online at end of 2025 (forwarded by Murray Clay,
        # Ulupono, 5/23/20).
        # Note: HECO said in "HECO construction plan 2020-03-17.docx" that RFP 2
        # would add 1,300 GWh/year in 2025; their renewable project status board
        # (10/2019-5/2020) says the same amount in 2022-25. (Proposals were due
        # 11/5/19 for up to this amount.) This would be about 560 GW (calculation
        # below), or 594 GWh according to HECO
        # https://www.hawaiianelectric.com/hawaiis-largest-renewable-energy-push-detailed-in-new-procurement-plan
        # That is larger than what they ended up procuring. Original plan could
        # also have been a mix of wind and solar, but final procurement was only
        # solar.
        # avg. cap factor for 560 MW starting after 390 best MW have been installed
        # (existing projects + FIT + CBRE 1 + half of CBRE 2 + RFP 1) is 26.6%; see
        # "select site, max_capacity, avg(cap_factor) from cap_factor natural join project where technology = 'CentralTrackingPV' group by 1, 2 order by 3 desc;"
        # and (120*.271+247*.265+193*.264)/(120+247+193)
        # Then (1,300,000 MWh/y)/(.266 * 8766 h/y) = 558 MW
        # Apply an extra chunk of PV in 2025. This could be done for either of
        # two reasons:
        # (a) If there is no forecast for 2025,  then Switch would build a lot
        # in 2025 and then we would interpolate that  to 2023-25. This would be
        # an unrealistic installatino rate and would clobber the 2023-24
        # forecasts.
        # (b) If there is a forecast for 2025 that is lower than 2024 and lower
        # than the 2026 value chosen by Switch (0.2 * 2030 value), then that
        # leaves a weird gap that we want to fill. (For now, we handle that case
        # by potentially interpolating back from 2030 to 2025 instead of 2026.)
        # (2025, 'LargePV', 50),
        # PSIP 2016-12-23 Table 4-1 included 90 MW of contingency battery in 2019
        # and https://www.hawaiianelectric.com/documents/clean_energy_hawaii/selling_power_to_the_utility/competitive_bidding/20190207_tri_company_future_procurement.pdf
        # says the 2016-12 plan was to do 70 MW contingency in 2019 and more contingency/regulation in 2020
        # There has been no further discussion of these as of 10/22/19, so we assume they are
        # replaced by storage that comes with the PV systems.
        # PSIP 2016: (2019, 'Battery_Conting', 90),
    ] + [
        # Assume no new distributed generation or batteries after 2045
        # (we need some forecast to avoid picking winners between large PV
        # and dist PV, and forecasting continuous increases in distpv would
        # be redundant with already adequate large-renewables)
        (y, t, 0.0, "late freeze")
        for y in range(2046, 2060)
        for t in ["DistPV", "DistBattery"]
    ]
    # No new generation in early years beyond what's shown above
    # (this will also block construction of these techs in all years if the
    # --psip-force flag is set)
    tech_group_targets_definite += [
        (y, t, 0.0, "early freeze")
        for techs, years in [
            (("OnshoreWind", "OffshoreWind", "LargePV"), range(2020, 2025 + 1)),
            (
                (
                    "IC_Barge",
                    "IC_MCBH",
                    "IC_Schofield",
                    "CC_152",
                    "Battery_Conting",
                    "Battery_Reg",
                ),
                range(2020, 2023 + 1),
            ),
        ]
        for t in techs
        for y in years
    ]

    if m.options.psip_no_additional_onshore_wind:
        tech_group_targets_definite += [
            (y, "OnshoreWind", 0.0, "block onshore wind") for y in range(2020, 2056)
        ]

    # add targets specified on the command line
    # TODO: allow repeated invocation
    if m.options.force_build is not None:
        b = list(m.options.force_build)
        build = (
            int(b[0]),  # year
            b[1],  # tech
            # quantity
            float(b[2]) if len(b) == 3 else (float(b[2]), float(b[3])),
            "manual override",
        )
        print("Forcing build: {}".format(build))
        tech_group_targets_definite.append(build)

    # technologies proposed in "HECO construction plan 2020-03-17.docx" but which may not be built if a better plan is found.
    tech_group_targets_psip = [
        (2026, "CC_152", 150.586, "HECO plan 3/17/20"),
        (2028, "CC_152", 150.586, "HECO plan 3/17/20"),
        (2030, "Battery_Bulk", (165, 4), "HECO plan 3/17/20"),
        (2032, "CC_152", 2 * 150.586, "HECO plan 3/17/20"),
        (2035, "Battery_Bulk", (168, 4), "HECO plan 3/17/20"),
        (2040, "LargePV", 280, "HECO plan 3/17/20"),
        (2040, "Battery_Bulk", (420, 4), "HECO plan 3/17/20"),
        (2045, "LargePV", 1180, "HECO plan 3/17/20"),
        (2045, "Battery_Bulk", (1525, 4), "HECO plan 3/17/20"),
        (
            2045,
            "IC_Barge",
            4 * 16.786392,
            "HECO plan 3/17/20",
        ),  # proxy for 4*17 MW of generic ICE capacity
        # RESOLVE modeled 4-hour batteries as being capable of providing reserves,
        # and didn't model contingency batteries (see data/HECO Plans/PSIP-WebDAV/2017-01-31 Response to Parties IRs/CA-IR-1/Input
        # and Output Files by Case/E3 and Company Defined Cases/Market DGPV (Reference)/OA_NOLNG/technologies.tab).
        # Then HECO added a 90 MW contingency battery (table 4-1 of PSIP 2016-12-23).
        # Note: RESOLVE can get reserves from batteries (they only considered 4-hour batteries), but not
        # from EVs or flexible demand.
        # DR: Looking at RESOLVE inputs, it seems like they take roughly 4% of load, and allow it to be doubled
        # or cut to zero each hour (need to double-check this beyond first day). Maybe this includes EVs?
        # (no separate sign of EVs).
        # TODO: check Resolve load levels against Switch.
        # TODO: maybe I should switch over to using the ABC curves and load profiles that HECO used with PLEXOS
        # (for all islands).
        # TODO: Did HECO assume 4-hour batteries, demand response or EVs could provide reserves when running PLEXOS?
        # - all of these seem unlikely, but we have to ask HECO to find out; PLEXOS files are unclear.
    ]

    if psip:
        if m.options.psip_relax_after is not None:
            # NOTE: this could be moved later, if we want this flag to relax
            # both the definite and psip targets
            psip_targets = [
                t for t in tech_group_targets_psip if t[0] <= m.options.psip_relax_after
            ]
        else:
            psip_targets = tech_group_targets_psip.copy()
        tech_group_targets = tech_group_targets_definite + psip_targets
    else:
        # must make a copy here so that rebuilds will be added to
        # tech_group_targets but not tech_group_targets_definite
        tech_group_targets = tech_group_targets_definite.copy()

    # Show which technologies can contribute to the target for each technology
    # group and which group each technology contributes to
    techs_for_tech_group = {
        "DistPV": ["DistPV", "SlopedDistPV", "FlatDistPV"],
        "LargePV": ["CentralTrackingPV", "CentralFixedPV"],
    }
    # use the rest as-is
    missing_techs = {t for y, t, s, l in tech_group_targets}.difference(
        techs_for_tech_group.keys()
    )
    techs_for_tech_group.update({t: [t] for t in missing_techs})
    # create a reverse mapping
    tech_tech_group = {
        tech: tech_group
        for tech_group, techs in techs_for_tech_group.items()
        for tech in techs
    }

    # Rebuild renewable projects and forecasted technologies at retirement.
    # In the future we may be able to simplify this by enforcing capacity targets
    # instead of construction targets.

    # note: this behavior is consistent with the following:
    # discussion on p. 3-8 of PSIP 2016-12-23 vol. 1.
    # Resolve applied planned wind and solar as set levels through 2045, not set additions in each year.
    # Table 4-1 shows final plans that were sent to Plexos; Plexos input files in
    # data/HECO Plans/PSIP-WebDAV/2017-01-31 Response to Parties IRs/DBEDT-IR-12/Input/Oahu/Oahu E3 Plan Input/CSV files/Theme 5
    # show optional capacity built in 2020 or 2025 (in list below) continuing in service in 2045.
    # and Plexos input files in data/HECO Plans/PSIP-WebDAV/2017-01-31 Response to Parties IRs/DBEDT-IR-12/Input/Oahu/Oahu E3 Plan Input/CSV files/PSIP Max Capacity.csv
    # don't show any retirements of wind and solar included as "planned" in RESOLVE and "existing" in Switch
    # (Waivers PV1, West Loch; Kawailoa may be omitted?)
    # also note: Plexos input files in XX
    # show max battery capacity equal to sum of all prior additions

    # m = lambda: 3; m.options = m; m.options.inputs_dir = '/Users/matthias/Dropbox/Research/Ulupono/Enovation Model/pbr_scenario/inputs'
    gen_info = pd.read_csv(os.path.join(m.options.inputs_dir, "gen_info.csv"))
    gen_info["tech_group"] = gen_info["gen_tech"].map(tech_tech_group)
    gen_info = gen_info[gen_info["tech_group"].notna()]
    # existing technologies are also subject to rebuilding
    existing_techs = (
        pd.read_csv(os.path.join(m.options.inputs_dir, "gen_build_predetermined.csv"))
        .merge(gen_info, how="inner")
        .groupby(["build_year", "tech_group"])["build_gen_predetermined"]
        .sum()
        .reset_index()
    )
    assert not any(
        is_battery(t) for i, y, t, q in existing_techs.itertuples()
    ), "Must update {} to handle pre-existing batteries.".format(__name__)
    ages = gen_info.groupby("tech_group")["gen_max_age"].agg(["min", "max", "mean"])
    assert all(ages["min"] == ages["max"]), "Some psip technologies have mixed ages."
    last_period = pd.read_csv(os.path.join(m.options.inputs_dir, "periods.csv")).iloc[
        -1, 0
    ]

    # rebuild all renewables and batteries in place before the start of the study,
    # plus any technologies with targets specified here
    rebuildable_targets = [
        (y, t, q, "existing")
        for i, y, t, q in existing_techs.itertuples()
        if is_renewable(t) or is_battery(t)
    ] + tech_group_targets
    tech_life = dict()
    for build_year, tech_group, cap, label in rebuildable_targets:
        if tech_group not in ages.index:
            raise ValueError(
                "A target has been specified for {} but there are no matching "
                "technologies in gen_info.csv.".format(tech_group)
            )
        max_age = ages.loc[tech_group, "mean"]
        tech_life[tech_group] = max_age
        rebuild_year = build_year + max_age
        while rebuild_year <= last_period:
            tech_group_targets.append(
                (rebuild_year, tech_group, cap, "rebuild " + label)
            )
            rebuild_year += max_age
    del gen_info, existing_techs, ages, rebuildable_targets

    # we also convert to normal python datatypes to support serialization
    tech_group_power_targets = [
        (int(y), t, float(q[0] if type(q) is tuple else q), l)
        for y, t, q, l in tech_group_targets
    ]
    tech_group_energy_targets = [
        (int(y), t, float(q[0] * q[1]), l)
        for y, t, q, l in tech_group_targets
        if type(q) is tuple
    ]

    m.FORECASTED_TECH_GROUPS = Set(
        dimen=1, initialize=list(techs_for_tech_group.keys())
    )
    m.FORECASTED_TECH_GROUP_TECHS = Set(
        m.FORECASTED_TECH_GROUPS, dimen=1, initialize=techs_for_tech_group
    )
    m.FORECASTED_TECHS = Set(dimen=1, initialize=list(tech_tech_group.keys()))
    m.tech_tech_group = Param(
        m.FORECASTED_TECHS, within=Any, initialize=tech_tech_group
    )

    # make a list of renewable technologies
    m.RENEWABLE_TECH_GROUPS = Set(
        dimen=1,
        initialize=m.FORECASTED_TECH_GROUPS,
        filter=lambda m, tg: is_renewable(tg),
    )

    def tech_group_target(m, per, tech, targets):
        """Find the amount of each technology that is targeted to be built
        between the start of the previous period and the start of the current
        period and not yet retired."""
        start = 0 if per == m.PERIODS.first() else m.PERIODS.prev(per)
        end = per
        target = sum(
            q
            for (tyear, ttech, q, l) in targets
            if ttech == tech
            and start < tyear
            and tyear <= end
            and tyear + tech_life[ttech] > end
        )
        return target

    def rule(m, per, tech):
        return tech_group_target(m, per, tech, tech_group_power_targets)

    m.tech_group_power_target = Param(
        m.PERIODS, m.FORECASTED_TECH_GROUPS, within=Reals, initialize=rule
    )

    def rule(m, per, tech):
        return tech_group_target(m, per, tech, tech_group_energy_targets)

    m.tech_group_energy_target = Param(
        m.PERIODS, m.FORECASTED_TECH_GROUPS, within=Reals, initialize=rule
    )

    def MakeTechGroupDicts_rule(m):
        # get unit sizes of all technologies
        unit_sizes = m.tech_group_unit_size_dict = defaultdict(float)
        for g, unit_size in m.gen_unit_size.items():
            tech = m.gen_tech[g]
            if tech in m.FORECASTED_TECHS:
                tech_group = m.tech_tech_group[tech]
                if tech_group in unit_sizes:
                    if unit_sizes[tech_group] != unit_size:
                        raise ValueError(
                            "Generation technology {} uses different unit sizes for different projects."
                        )
                else:
                    unit_sizes[tech_group] = unit_size
        # get predetermined capacity for all technologies
        m.tech_group_predetermined_power_cap_dict = defaultdict(float)
        for (g, per), cap in m.build_gen_predetermined.items():
            tech = m.gen_tech[g]
            if tech in m.FORECASTED_TECHS:
                tech_group = m.tech_tech_group[tech]
                m.tech_group_predetermined_power_cap_dict[tech_group, per] += cap
        m.tech_group_predetermined_energy_cap_dict = defaultdict(float)
        for (g, per), cap in m.build_gen_predetermined.items():
            tech = m.gen_tech[g]
            if tech in m.FORECASTED_TECHS and g in m.STORAGE_GENS:
                # Need to get predetermined energy capacity here, but there's no
                # param for it yet, so currently these can only be implemented
                # as technologies with fixed gen_storage_energy_to_power_ratio,
                # in which case users should only provide a power target, not
                # an energy target in this file. In the future, there may be
                # a way to provide predetermined power and energy params, so we
                # watch out for that here.
                if m.gen_storage_energy_to_power_ratio[g] == float("inf"):
                    TODO(
                        "Need to lookup predetermined energy capacity for storage technologies."
                    )
                    # m.tech_group_predetermined_energy_cap_dict[tech_group, per] += <predetermined energy cap>

    m.MakeTechGroupDicts = BuildAction(rule=MakeTechGroupDicts_rule)

    # Find last date for which a definite target was specified for each tech group.
    # This sets the last year when construction of a technology is fixed at a
    # predetermined level in the "most-likely" (non-PSIP) cases.
    # This ignores PSIP targets, since _all_ construction is frozen when those are
    # used, and ignores reconstruction targets, because those just follow on from
    # the early-years construction, and we don't want to freeze construction all
    # the way through.
    last_definite_target = dict()
    for y, t, q, l in tech_group_targets_definite:
        last_definite_target[t] = max(y, last_definite_target.get(t, 0))

    # Save targets and group definitions for future reference
    import json

    os.makedirs(m.options.outputs_dir, exist_ok=True)  # avoid errors with new dir
    with open(os.path.join(m.options.outputs_dir, "heco_outlook.json"), "w") as f:
        json.dump(
            {
                "tech_group_power_targets": tech_group_power_targets,
                "tech_group_energy_targets": tech_group_energy_targets,
                "techs_for_tech_group": techs_for_tech_group,
                "tech_tech_group": tech_tech_group,
                "last_definite_target": last_definite_target,
            },
            f,
            indent=4,
        )

    # def build_tech_group_in_period(m, tech_group, period):
    #     """
    #     How much capacity is added in this tech_group in this period?
    #     Returns literal 0 if and only if there are no matching projects.
    #     Otherwise returns a Pyomo expression.
    #     """
    #     return sum(
    #         build_var[g, period]
    #         for g in m.GENERATION_PROJECTS
    #         if m.gen_tech[g] in m.FORECASTED_TECHS
    #             and m.tech_tech_group[m.gen_tech[g]] == tech_group
    #             and (g, period) in build_var,
    #         0
    #     )

    # # allow extra solar in 2025, up to the point of straight-line additions
    # # between 2025 and 2030 (inclusive)
    # ####### We don't do this here, we just interpolate back from 2030 to 2025
    # ####### instead of 2026 (slighly less optimal, but much simpler)
    # if last_definite_target['LargePV'] == 2025:
    #     last_definite_target['LargePV'] = 2024  # use target as lower bound in 2025
    #     print("="*80)
    #     print("NOTE: Using HECO 2025 LargePV plan as lower bound, not fixed target.")
    #     print("="*80)
    #     ##### slack variable to allow 2025 to overshoot 20% of 2030 if needed
    #     m.SolarOvershoot2025 = Var(within=NonNegativeReals)
    #     def rule(m):
    #         build2025 = build_tech_group_in_period['LargePV', 2025]
    #         build2030 = build_tech_group_in_period['LargePV', 2030]
    #         ####### This doesn't work, needs a big-M constraint to force
    #         ####### build2025 to be below the max of the target or 0.2 * build2030
    #         return build2025 - m.SolarOvershoot2025 <= 0.2 * build2030
    #     m.Even_Increment_Solar_2025 = Constraint(rule=rule)
    # else:
    #     raise ValueError(
    #         'Expected last HECO target for LargePV to be in 2025, but it is in {}.'
    #         .format(last_definite_target['LargePV'])
    #     )

    def tech_group_target_rule(m, per, tech_group, build_var, target):
        """
        Enforce targets for each technology.

        with PSIP: build is zero except for tech_group_power_targets
            (sum during each period or before first period)
        without PSIP: build is == definite targets during time range when targets specified
                      build is >= target later;
        Note: in the last case the target is the sum of targets between start of prior period and start of this one
        """
        build = sum(
            build_var[g, per]
            for g in m.GENERATION_PROJECTS
            if m.gen_tech[g] in m.FORECASTED_TECHS
            and m.tech_tech_group[m.gen_tech[g]] == tech_group
            and (g, per) in build_var
        )

        if isinstance(build, int) and build == 0:
            # no matching projects found, left with literal 0
            if target == 0:
                return Constraint.Skip
            else:
                raise ValueError(
                    "Target was set for {} in {}, but no matching projects are available.".format(
                        tech_group, per
                    )
                )

        if psip and (
            m.options.psip_relax_after is None or per <= m.options.psip_relax_after
        ):
            # PSIP in effect: exactly match the target (possibly zero)
            return build == target
        elif per <= last_definite_target.get(tech_group, 0):
            # PSIP not in effect, but a definite target is
            return build == target
        elif (
            m.options.psip_minimal_renewables and tech_group in m.RENEWABLE_TECH_GROUPS
        ):
            # Only build the specified amount of renewables, no more.
            # This is used to apply the definite targets, but otherwise minimize renewable development.
            return build == target
        else:
            # treat the target as a lower bound
            return build >= target

    def rule(m, per, tech_group):
        # get target, including any capacity specified in the predetermined builds,
        # so the target will be additional to those
        target = (
            m.tech_group_power_target[per, tech_group]
            + m.tech_group_predetermined_power_cap_dict[tech_group, per]
        )
        return tech_group_target_rule(m, per, tech_group, m.BuildGen, target)

    m.Enforce_Tech_Group_Power_Target = Constraint(
        m.PERIODS, m.FORECASTED_TECH_GROUPS, rule=rule
    )

    def rule(m, per, tech_group):
        # get target, including any capacity specified in the predetermined builds,
        # so the target will be additional to those
        target = (
            m.tech_group_energy_target[per, tech_group]
            + m.tech_group_predetermined_energy_cap_dict[tech_group, per]
        )
        return tech_group_target_rule(m, per, tech_group, m.BuildStorageEnergy, target)

    m.Enforce_Tech_Group_Energy_Target = Constraint(
        m.PERIODS, m.FORECASTED_TECH_GROUPS, rule=rule
    )

    if psip:

        def rule(m):
            buildable_techs = set(m.gen_tech[g] for (g, y) in m.NEW_GEN_BLD_YRS)
            if buildable_techs - set(m.FORECASTED_TECHS):
                # TODO: automatically add zero-targets
                m.logger.error(
                    "\nERROR: You need to provide at least one zero target for "
                    "each technology without targets in the PSIP to prevent it "
                    "from being built."
                )
                return False
            else:
                return True

        m.Check_For_Buildable_Techs_Under_PSIP = BuildCheck(rule=rule)

        # don't allow construction of other technologies (e.g., pumped hydro, fuel cells)
        advanced_tech_vars = [
            "BuildPumpedHydroMW",
            "BuildAnyPumpedHydro",
            "BuildElectrolyzerMW",
            "BuildLiquifierKgPerHour",
            "BuildLiquidHydrogenTankKg",
            "BuildFuelCellMW",
        ]

        def no_advanced_tech_rule_factory(v):
            return lambda m, *k: (getattr(m, v)[k] == 0)

        for v in advanced_tech_vars:
            try:
                var = getattr(m, v)
                setattr(
                    m,
                    "PSIP_No_" + v,
                    Constraint(var._index, rule=no_advanced_tech_rule_factory(v)),
                )
            except AttributeError:
                pass  # model doesn't have this var
