from __future__ import division
from __future__ import print_function
from collections import defaultdict
from textwrap import dedent
from math import isnan
import os
from pyomo.environ import *
import pandas as pd
import time

# This module represents HECO's outlook as described in their modeling work in
# March-June 2020. Use the --psip-force flag to apply the plan they specified
# for that work too.

# See psip_2016_12 and heco_outlook_2020_06 for documentation of general structure


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

    tech_group_targets_definite = [
        # HECO seems to have left Pearl City Peninsula Solar Park out of their plan
        # (they call it "other solar"), so we cancel it out here
        # (2021, 'LargePV', -1, 'missing Pearl City Solar'),
        # Actually we don't, because it is uncancellable at this point; we just
        # assume they proceed with the additional solar installations they report, on top of this.
        # HECO March 2020 forecast
        # /s/data/Generator Info/HECO Dist PV Forecast 2020-03-17.xlsx
        # We assume all DistPV and DistBattery are used efficiently/optimally,
        # i.e., we do not attempt to model non-optimal pairing of DistPV with
        # DistBattery or curtailment on self-supply tariffs.
        (2021, "DistPV", 0, "DER forecast"),
        (2022, "DistPV", 0, "DER forecast"),
        (2023, "DistPV", 0, "DER forecast"),
        (2024, "DistPV", 0, "DER forecast"),
        (2025, "DistPV", 0, "DER forecast"),
        (2026, "DistPV", 0, "DER forecast"),
        (2027, "DistPV", 0, "DER forecast"),
        (2028, "DistPV", 7.3, "DER forecast"),
        (2029, "DistPV", 25.8, "DER forecast"),
        (2030, "DistPV", 27.3, "DER forecast"),
        (2031, "DistPV", 28.4, "DER forecast"),
        (2032, "DistPV", 29.7, "DER forecast"),
        (2033, "DistPV", 30.5, "DER forecast"),
        (2034, "DistPV", 31.3, "DER forecast"),
        (2035, "DistPV", 32.2, "DER forecast"),
        (2036, "DistPV", 32.5, "DER forecast"),
        (2037, "DistPV", 32.9, "DER forecast"),
        (2038, "DistPV", 33.3, "DER forecast"),
        (2039, "DistPV", 32.7, "DER forecast"),
        (2040, "DistPV", 33.2, "DER forecast"),
        (2041, "DistPV", 33, "DER forecast"),
        (2042, "DistPV", 33.1, "DER forecast"),
        (2043, "DistPV", 33.3, "DER forecast"),
        (2044, "DistPV", 33.5, "DER forecast"),
        (2045, "DistPV", 33.3, "DER forecast"),
        # note: HECO provides a MWh forecast; we assume inverters are large
        # enough to charge in 4h
        (2021, "DistBattery", (0, 4), "DER forecast"),
        (2022, "DistBattery", (0, 4), "DER forecast"),
        (2023, "DistBattery", (0, 4), "DER forecast"),
        (2024, "DistBattery", (6.812, 4), "DER forecast"),
        (2025, "DistBattery", (9.693, 4), "DER forecast"),
        (2026, "DistBattery", (3.135, 4), "DER forecast"),
        (2027, "DistBattery", (3.732, 4), "DER forecast"),
        (2028, "DistBattery", (4.542, 4), "DER forecast"),
        (2029, "DistBattery", (5.324, 4), "DER forecast"),
        (2030, "DistBattery", (6.115, 4), "DER forecast"),
        (2031, "DistBattery", (6.719, 4), "DER forecast"),
        (2032, "DistBattery", (7.316, 4), "DER forecast"),
        (2033, "DistBattery", (7.913, 4), "DER forecast"),
        (2034, "DistBattery", (8.355, 4), "DER forecast"),
        (2035, "DistBattery", (8.723, 4), "DER forecast"),
        (2036, "DistBattery", (9.006, 4), "DER forecast"),
        (2037, "DistBattery", (9.315, 4), "DER forecast"),
        (2038, "DistBattery", (9.49, 4), "DER forecast"),
        (2039, "DistBattery", (9.556, 4), "DER forecast"),
        (2040, "DistBattery", (9.688, 4), "DER forecast"),
        (2041, "DistBattery", (9.777, 4), "DER forecast"),
        (2042, "DistBattery", (9.827, 4), "DER forecast"),
        (2043, "DistBattery", (9.874, 4), "DER forecast"),
        (2044, "DistBattery", (9.939, 4), "DER forecast"),
        (2045, "DistBattery", (10.098, 4), "DER forecast"),
        # Mauka Fit 1 and Na Pua Makani are scheduled to come online in 2020 but
        # are still under construction as of 8/7/20 according to
        # https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board
        # In the HECO plan (Docket 2018-0088 HECO SOP 2, Exhibit P2), Mauka Fit
        # 1 is online in 2021 and Na Pua Makani and CBRE Phase 1 are online in
        # 2020. Since none of these are online by Aug. 2020, we model them as
        # starting 1/1/2021.
        # NOTE: PSIP Figure J-10 says FIT projects (Mauka FIT and Aloha Solar II (in Existing Plant Data) are in addition to the customer DGPV
        # adoption forecast, but they are not in "HECO construction plan 2020-03-17.docx".
        # Samantha Ruiz (Ulupono) recommended in email 5/26/20 to count them as
        # non-DER esp. since HECO's March 2020 DER forecast is flat in early
        # years. Note: these are probably fixed-axis rather than tracking (i.e.,
        # more like DistPV than LargePV), but we include them as LargePV because
        # they don't reduce available roof inventory.
        # NOTE: Mauka FIT and Na Pua Makani are at particular locations but we
        # include them here because  counting them as existing capacity in 2021
        # would block construction of additional generators in 2021.
        (2021, "LargePV", 3.5, "Mauka FIT 1"),  # Mauka FIT 1
        # Na Pua Makani (NPM) wind
        # Reported as 24 MW in
        # https://www.hawaiianelectric.com/clean-energy-hawaii/our-clean-energy-portfolio/renewable-project-status-board
        # (accessed 10/22/19) but 27 MW on
        # https://www.napuamakanihawaii.org/fact-sheet/. HECO confirmed by email
        # that it is 24 MW.
        (2021, "OnshoreWind", 24, "Na Pua Makani"),
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
        (2021, "LargePV", 5, "CBRE Phase 1"),  # CBRE Phase 1
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
        (2025, "LargePV", 43.5, "CBRE phase 2"),
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
        (2021, "LargePV", 12.5, "RFP stage 1"),  # AES West Oahu Solar
        (2022, "LargePV", 52, "RFP stage 1"),  # Hoohana Solar 1
        (2022, "LargePV", 39, "RFP stage 1"),  # Mililani I Solar
        (2022, "LargePV", 36, "RFP stage 1"),  # Waiawa Solar
        # storage associated with large PV projects; we assume this will be used
        # efficiently, so we model it along with other large-scale storage.
        (2021, "Battery_Bulk", (12.5, 4), "RFP stage 1"),  # AES West Oahu Solar
        (2022, "Battery_Bulk", (52, 4), "RFP stage 1"),  # Hoohana Solar 1
        (2022, "Battery_Bulk", (39, 4), "RFP stage 1"),  # Mililani I Solar
        (2022, "Battery_Bulk", (36, 4), "RFP stage 1"),  # Waiawa Solar
        # 200 MW / 6 hour BESS in HECO Phase 2 SOP Exhibit P2 Attachment 1
        (2022, "Battery_Bulk", (200, 6), "HECO plan"),
        # Note: HECO said in "HECO construction plan 2020-03-17.docx" that RFP 2
        # would add 1,300 GWh/year in 2025; their renewable project status board
        # (10/2019-5/2020) says the same amount in 2022-25.
        # PBR Phase 2 SOP Attachment 1 says this too.
        # We think this would be 560 MW, but they think it is 594 MW (see p. 9 of Exhibit A of Dkt 2018-0088 2020-06-18 HECO Phase 2 SOP.pdf)
        # We use 594 MW, because that meshes better with the total MW reported in their plan.
        (2025, "LargePV", 594, "RFP stage 2"),
        # avg. cap factor for 560 MW starting after 390 best MW have been installed
        # (existing projects + FIT + CBRE 1 + half of CBRE 2 + RFP 1) is 26.6%; see
        # "select site, max_capacity, avg(cap_factor) from cap_factor natural join project where technology = 'CentralTrackingPV' group by 1, 2 order by 3 desc;"
        # and (120*.271+247*.265+193*.264)/(120+247+193)
        # Then (1,300,000 MWh/y)/(.266 * 8766 h/y) = 558 MW
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
        pd.read_csv(
            os.path.join(m.options.inputs_dir, "gen_build_predetermined.csv"),
            na_values=["."],
        )
        .merge(gen_info, how="inner")
        .groupby(["build_year", "tech_group"])[
            ["build_gen_predetermined", "build_gen_energy_predetermined"]
        ]
        .agg(lambda x: x.sum(skipna=False))
        .reset_index()
    )
    ages = gen_info.groupby("tech_group")["gen_max_age"].agg(["min", "max", "mean"])
    assert all(ages["min"] == ages["max"]), "Some psip technologies have mixed ages."
    last_period = pd.read_csv(os.path.join(m.options.inputs_dir, "periods.csv")).iloc[
        -1, 0
    ]

    # rebuild all renewables and batteries in place before the start of the study,
    # plus any technologies with targets specified here
    rebuildable_targets = [
        (y, t, (mw if isnan(mwh) else (mw, mwh / mw)), "existing")
        for i, y, t, mw, mwh in existing_techs.itertuples()
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

    # import pdb; pdb.set_trace()

    m.FORECASTED_TECH_GROUPS = Set(
        dimen=1, initialize=list(techs_for_tech_group.keys())
    )
    m.FORECASTED_TECH_GROUP_TECHS = Set(
        m.FORECASTED_TECH_GROUPS, dimen=1, initialize=techs_for_tech_group
    )
    m.FORECASTED_TECHS = Set(dimen=1, initialize=list(tech_tech_group.keys()))
    m.tech_tech_group = Param(
        m.FORECASTED_TECHS, within=NonNegativeReals, initialize=tech_tech_group
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
        m.PERIODS, m.FORECASTED_TECH_GROUPS, within=NonNegativeReals, initialize=rule
    )

    def rule(m, per, tech):
        return tech_group_target(m, per, tech, tech_group_energy_targets)

    m.tech_group_energy_target = Param(
        m.PERIODS, m.FORECASTED_TECH_GROUPS, within=NonNegativeReals, initialize=rule
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
        for (g, per), cap in m.build_gen_energy_predetermined.items():
            tech = m.gen_tech[g]
            if (
                tech in m.FORECASTED_TECHS
                and g in m.STORAGE_GENS
                and m.gen_storage_energy_to_power_ratio[g] == float("inf")
            ):
                tech_group = m.tech_tech_group[tech]
                m.tech_group_predetermined_energy_cap_dict[tech_group, per] += cap

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
