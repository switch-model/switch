from __future__ import division
from collections import defaultdict
from textwrap import dedent
import os
from pyomo.environ import *

def TODO(note):
    raise NotImplementedError(dedent(note))

def define_arguments(argparser):
    argparser.add_argument('--psip-force', action='store_true', default=True,
        help="Force following of PSIP plans (retiring AES and building certain technologies).")
    argparser.add_argument('--psip-relax', dest='psip_force', action='store_false',
        help="Relax PSIP plans, to find a more optimal strategy.")
    argparser.add_argument('--psip-minimal-renewables', action='store_true', default=False,
        help="Use only the amount of renewables shown in PSIP plans, and no more (should be combined with --psip-relax).")
    argparser.add_argument('--force-build', nargs=3, default=None,
        help="Force construction of at least a certain quantity of a particular technology during certain years. Space-separated list of year, technology and quantity.")
    argparser.add_argument('--psip-relax-after', type=float, default=None,
        help="Follow the PSIP plan up to and including the specified year, then optimize construction in later years. Should be combined with --psip-force.")

def is_renewable(tech):
    return any(txt in tech for txt in ("PV", "Wind", "Solar"))
def is_battery(tech):
    return 'battery' in tech.lower()

def define_components(m):
    ###################
    # resource rules to match HECO's 2016-04-01 PSIP
    ##################

    # decide whether to enforce the PSIP preferred plan
    # if an environment variable is set, that takes precedence
    # (e.g., on a cluster to override options.txt)
    psip_env_var = os.environ.get('USE_PSIP_PLAN')
    if psip_env_var is None:
        # no environment variable; use the --psip-relax flag
        psip = m.options.psip_force
    elif psip_env_var.lower() in ["1", "true", "y", "yes", "on"]:
        psip = True
    elif psip_env_var.lower() in ["0", "false", "n", "no", "off"]:
        psip = False
    else:
        raise ValueError('Unrecognized value for environment variable USE_PSIP_PLAN={} (should be 0 or 1)'.format(psip_env_var))

    if m.options.verbose:
        if psip:
            print "Using PSIP construction plan."
        else:
            print "Relaxing PSIP construction plan."

    # don't allow addition of anything other than those specified here
    # force retirement of AES at end of 2022

    # these plants are all multi-fuel; will automatically convert to biodiesel in 2045:
    # CIP CT-1, W9, W10, Airport DSG, Schofield, IC_Barge, IC_MCBH, Kalaeloa

    # no use of LNG

    # force battery installations directly (since they're not currently a standard tech)

    # NOTE: RESOLVE used different wind and solar profiles from SWITCH.
    # SWITCH profiles seem to be more accurate, so we optimize against them
    # and show that this may give (small) savings vs. the RESOLVE plan.

    # TODO: Should I use Switch to investigate how much of HECO's poor performance is due
    # to using bad resource profiles (small onshore wind that doesn't rise in the rankings),
    # how much is due to capping PV at 300 MW in 2020,
    # how much is due to non-integrality in RESOLVE (fixed by later jimmying by HECO), and
    # how much is due to forcing in elements before and after the optimization?

    # NOTE: I briefly moved future DistPV to the existing plants workbook, with the idea that
    # we assume the same forecasted adoption occurs with or without the PSIP. That approach
    # also spread the DistPV adoption among the top half of tranches, rather than allowing
    # Switch to cherry-pick the best tranches. However, that approach was ineffective because
    # Switch was still able to add (and did add) DistPV from the lower tranches. That could
    # have been fixed up in import_data.py, or the DistPV could have been moved here, into
    # technology_targets_definite. However, on further reflection, forcing DistPV installations
    # to always match the PSIP forecast seems artificial -- it might be better to do DistPV
    # than utility-scale PV, and there's no reason to preclude that in the non-PSIP plans.
    # (Although it's probably not worth dwelling long on differences if they arise, since they
    # won't make a huge difference in cost.) So now the DistPV is treated as just another optional
    # part of the PSIP plan. Note that this allows Switch to cherry-pick among the best DistPV
    # tranches to meet the PSIP, but that is a little conservative (favorable to HECO), because
    # Switch can also do that for the non-PSIP scenarios. Also, these targets are roughly equal
    # to the top half of the DistPV tranches, so there's not much cherry-picking going on anyway.
    # This could be resolved by setting (optional) project-specific targets in this module,
    # or by making the DistPV tranches coarser (e.g., upper half, third quartile, fourth quartile),
    # which seems like a good idea for representing the general precision of DistPV policies
    # anyway.

    # TODO (maybe): set project-specific targets, so that DistPV targets can be spread among tranches
    # and specific projects in the PSIP can be represented accurately (really just NPM wind). This
    # might also allow reconstruction of exactly the same existing or PSIP project when retired
    # (as specified in the PSIP). Currently the code below lets Switch choose the best project with the
    # same technology when it replaces retired renewable projects.

    # targets for individual generation technologies
    # (year, technology, MW added)
    # TODO: allow either CentralFixedPV or CentralTrackingPV for utility-scale solar
    # (not urgent now, since CentralFixedPV is not currently in the model)

    # Technologies that are definitely being built (at least have permits already.)
    # (Note: these have all been moved into the existing plants workbook.)
    technology_targets_definite = []

    # add targets specified on the command line
    if m.options.force_build is not None:
        b = list(m.options.force_build)
        b[0] = int(b[0])    # year
        b[2] = float(b[2])  # quantity
        b = tuple(b)
        print "Forcing build: {}".format(b)
        technology_targets_definite.append(b)

    # technologies proposed in PSIP but which may not be built if a better plan is found.
    # All from final plan in Table 4-1 of PSIP 2016-12-23 sometimes cross-referenced with PLEXOS inputs.
    # These differ somewhat from inputs to RESOLVE or the RESOLVE plans in Table 3-1 and 3-4, but
    # they represent HECO's final plan as reported in the PSIP.
    technology_targets_psip = [
        # Na Pua Makani (NPM) wind (still awaiting approval as of Feb. 2018) note: this is at a
        # specific location (21.668 -157.956), but since it isn't in the existing plants
        # workbook, we represent it as a generic technology target.
        # note: Resolve modeled 134 MW of planned onshore wind, 30 MW of optional onshore
        # and 800 MW of optional offshore; See "data/HECO Plans/PSIP-WebDAV/2017-01-31 Response to Parties IRs/CA-IR-1/Input
        # and Output Files by Case/E3 and Company Defined Cases/Market DGPV (Reference)/OA_NOLNG/capacity_limits.tab".
        # 'planned' seems to correspond to Na Pua Makani (24), CBRE (10), Kahuku (30), Kawailoka (69);
        # Resolve built 273 MW offshore in 2025-45 (including 143 MW rebuilt in 2045),
        # and 30 MW onshore in 2045 (tables 3-1 and 3-4).
        # Not clear why it picked offshore before onshore (maybe bad resource profiles?). But
        # in their final plan (table 4-1), HECO changed it to 200 MW offshore in 2025
        # (presumably rebuilt in 2045) and 30 MW onshore in 2045.
        (2018, 'OnshoreWind', 24), # Na Pua Makani (NPM) wind
        (2018, 'OnshoreWind', 10), # CBRE wind
        # note: 109.6 MW SunEdison replacements are in Existing Plants workbook.

        # note: RESOLVE had 53.6 MW of planned PV, which is probably Waianae (27.6), Kalaeloa (5)
        # and West Loch (20). Then it added these (table 3-1): 2020: 300 MW (capped, see "renewable_limits.tab"),
        # 2022: 48 MW, 2025: 193 MW, 2040: 541 (incl. 300 MW rebuild), 2045: 1400 MW (incl. 241 MW rebuild).
        # HECO converted this to 109.6 MW of replacement SunEdison waiver projects in 2018
        # (we list those as "existing") and other additions shown below.
        (2018, 'CentralTrackingPV', 15),  # CBRE PV
        (2020, 'CentralTrackingPV', 180),
        (2022, 'CentralTrackingPV', 40),
        (2022, 'IC_Barge', 100.0),         # JBPHH plant
        # note: we moved IC_MCBH one year earlier than PSIP to reduce infeasibility in 2022
        (2022, 'IC_MCBH', 54.0),
        (2025, 'CentralTrackingPV', 200),
        (2025, 'OffshoreWind', 200),
        (2040, 'CentralTrackingPV', 280),
        (2045, 'CentralTrackingPV', 1180),
        (2045, 'IC_MCBH', 68.0), # proxy for 68 MW of generic ICE capacity

        # batteries (MW)
        # from PSIP 2016-12-23 Table 4-1; also see energy ("capacity") and power files in
        # "data/HECO Plans/PSIP-WebDAV/2017-01-31 Response to Parties IRs/DBEDT-IR-12/Input/Oahu/Oahu E3 Plan Input/CSV files/Battery"
        # (note: we mistakenly treated these as MWh quantities instead of MW before 2018-02-20)
        (2019, 'Battery_Conting', 90),
        (2022, 'Battery_4', 426),
        (2025, 'Battery_4', 29),
        (2030, 'Battery_4', 165),
        (2035, 'Battery_4', 168),
        (2040, 'Battery_4', 420),
        (2045, 'Battery_4', 1525),
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

        # installations based on changes in installed capacity shown in
        # data/HECO Plans/PSIP-WebDAV/2017-01-31 Response to Parties IRs/CA-IR-1/Input and Output Files by Case/E3 Company Defined Cases/Market DGPV (Reference)/OA_NOLNG/planned_installed_capacities.tab
        # Also see Figure J-10 of 2016-12-23 PSIP (Vol. 3), which matches these levels (excluding FIT(?)).
        # Note: code further below adds in reconstruction of early installations
        (2020, "DistPV", 606.3-444),  # net of 444 installed as of 2016 (in existing generators workbook)
        (2022, "DistPV", 680.3-606.3),
        (2025, "DistPV", 744.9-680.3),
        (2030, "DistPV", 868.7-744.9),
        (2035, "DistPV", 1015.4-868.7),
        (2040, "DistPV", 1163.4-1015.4),
        (2045, "DistPV", 1307.9-1163.4),
    ]

    # Rebuild renewable projects at retirement (20 years), as specified in the PSIP
    # note: this doesn't include DistPV, because those are part of a forecast, not a plan, so they already
    # get reconstructed in the existing generators workbook, whether or not the PSIP plan is used.

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

    # projects from existing plants workbook (pasted in)
    existing_techs = [
        (2011, "OnshoreWind", 30),
        (2012, "OnshoreWind", 69),
        (2012, "CentralTrackingPV", 5),
        (2016, "CentralTrackingPV", 27.6),
        (2016, "DistPV", 444),
        (2018, "IC_Schofield", 54.98316),
        (2018, "CentralTrackingPV", 49),
        (2018, "CentralTrackingPV", 14.7),
        (2018, "CentralTrackingPV", 46),
        (2018, "CentralTrackingPV", 20),
    ]
    existing_techs += technology_targets_definite
    existing_techs += technology_targets_psip
    # rebuild all renewables at retirement (20 years for RE, 15 years for batteries)
    rebuild_targets = [
        (y+20, tech, cap) for y, tech, cap in existing_techs if is_renewable(tech)
    ] + [
        (y+15, tech, cap) for y, tech, cap in existing_techs if is_battery(tech)
    ] # note: early batteries won't quite need 2 replacements
    # don't schedule rebuilding past end of study
    rebuild_targets = [t for t in rebuild_targets if t[0] <= 2045]
    technology_targets_psip += rebuild_targets

    # make sure LNG is turned off
    if psip and getattr(m.options, "force_lng_tier", []) != ["none"]:
        raise RuntimeError('You must use the lng_conversion module and set "--force-lng-tier none" to match the PSIP.')

    if psip:
        if m.options.psip_relax_after is not None:
            psip_targets = [t for t in technology_targets_psip if t[0] <= m.options.psip_relax_after]
        else:
            psip_targets = technology_targets_psip
        technology_targets = technology_targets_definite + psip_targets
    else:
        technology_targets = technology_targets_definite

    # make a special list including all standard generation technologies plus "LoadShiftBattery"
    m.GEN_TECHS_AND_BATTERIES = Set(initialize=lambda m: [g for g in m.GENERATION_TECHNOLOGIES] + ["LoadShiftBattery"])

    # make a list of renewable technologies
    m.RENEWABLE_TECHNOLOGIES = Set(
        initialize=m.GENERATION_TECHNOLOGIES,
        filter=lambda m, tech: is_renewable(tech)
    )

    def technology_target_init(m, per, tech):
        """Find the amount of each technology that is targeted to be built between the start of the
        previous period and the start of the current period."""
        start = 2000 if per == m.PERIODS.first() else m.PERIODS.prev(per)
        end = per
        target = sum(
            mw for (tyear, ttech, mw) in technology_targets
                if ttech == tech and start < tyear and tyear <= end
        )
        return target
    m.technology_target = Param(m.PERIODS, m.GEN_TECHS_AND_BATTERIES, initialize=technology_target_init)

    def MakeGenTechDicts_rule(m):
        # get unit sizes of all technologies
        unit_sizes = m.gen_tech_unit_size_dict = defaultdict(float)
        for g, unit_size in m.gen_unit_size.iteritems():
            tech = m.gen_tech[g]
            if tech in unit_sizes:
                if unit_sizes[tech] != unit_size:
                    raise ValueError("Generation technology {} uses different unit sizes for different projects.")
            else:
                unit_sizes[tech] = unit_size
        # get predetermined capacity for all technologies
        predet_cap = m.gen_tech_predetermined_cap_dict = defaultdict(float)
        for (g, per), cap in m.gen_predetermined_cap.iteritems():
            tech = m.gen_tech[g]
            predet_cap[tech, per] += cap
    m.MakeGenTechDicts = BuildAction(rule=MakeGenTechDicts_rule)

    # with PSIP: BuildGen is zero except for technology_targets
    #     (sum during each period or before first period)
    # without PSIP: BuildGen is >= definite targets
    def Enforce_Technology_Target_rule(m, per, tech):
        """Enforce targets for each technology; exact target for PSIP cases, minimum target for non-PSIP."""

        # get target, including any capacity specified in the predetermined builds,
        # so the target will be additional to those
        target = m.technology_target[per, tech] + m.gen_tech_predetermined_cap_dict[tech, per]

        # convert target to closest integral number of units
        # (some of the targets are based on nominal unit sizes rather than actual max output)
        if m.gen_tech_unit_size_dict[tech] > 0.0:
            target = round(target / m.gen_tech_unit_size_dict[tech]) * m.gen_tech_unit_size_dict[tech]

        if tech == "LoadShiftBattery":
            # special treatment for batteries, which are not a standard technology
            if hasattr(m, 'BuildBattery'):
                # note: BuildBattery is in MWh, so we convert to MW
                build = sum(m.BuildBattery[z, per] for z in m.LOAD_ZONES) / m.battery_min_discharge_time
            else:
                build = 0
        else:
            build = sum(
                m.BuildGen[g, per]
                for g in m.GENERATION_PROJECTS
                if m.gen_tech[g] == tech and (g, per) in m.GEN_BLD_YRS
            )

        if type(build) is int and build == 0:
            # no matching projects found
            if target == 0:
                return Constraint.Skip
            else:
                print(
                    "WARNING: target was set for {} in {}, but no matching projects are available. "
                    "Model will be infeasible.".format(tech, per)
                )
                return Constraint.Infeasible
        elif psip and per <= m.options.psip_relax_after:
            return (build == target)
        elif m.options.psip_minimal_renewables and tech in m.RENEWABLE_TECHNOLOGIES:
            # only build the specified amount of renewables, no more
            return (build == target)
        else:
            # treat the target as a lower bound
            return (build >= target)
    m.Enforce_Technology_Target = Constraint(
        m.PERIODS, m.GEN_TECHS_AND_BATTERIES, rule=Enforce_Technology_Target_rule
    )

    aes_g = 'Oahu_AES'
    aes_size = 180
    aes_bld_year = 1992
    m.AES_OPERABLE_PERIODS = Set(initialize = lambda m:
        m.PERIODS_FOR_GEN_BLD_YR[aes_g, aes_bld_year]
    )
    m.OperateAES = Var(m.AES_OPERABLE_PERIODS, within=Binary)
    m.Enforce_AES_Deactivate = Constraint(m.TIMEPOINTS, rule=lambda m, tp:
        Constraint.Skip if (aes_g, tp) not in m.GEN_TPS
        else (m.DispatchGen[aes_g, tp] <= m.OperateAES[m.tp_period[tp]] * aes_size)
    )
    m.AESDeactivateFixedCost = Expression(m.PERIODS, rule=lambda m, per:
        0.0 if per not in m.AES_OPERABLE_PERIODS
        else - m.OperateAES[per] * aes_size * m.gen_fixed_om[aes_g, aes_bld_year]
    )
    m.Cost_Components_Per_Period.append('AESDeactivateFixedCost')

    if psip:
        # keep AES active until 9/2022; deactivate after that
        # note: since a period starts in 2022, we retire before that
        m.PSIP_Retire_AES = Constraint(m.AES_OPERABLE_PERIODS, rule=lambda m, per:
            (m.OperateAES[per] == 1) if per + m.period_length_years[per] <= 2022
            else (m.OperateAES[per] == 0)
        )

        # before 2040: no biodiesel, and only 100-300 GWh of non-LNG fossil fuels
        # period including 2040-2045: <= 300 GWh of oil; unlimited biodiesel or LNG

        # no biodiesel before 2040 (then phased in fast enough to meet the RPS)
        m.EARLY_BIODIESEL_MARKETS = Set(dimen=2, initialize=lambda m: [
            (rfm, per)
                for per in m.PERIODS if per + m.period_length_years[per] <= 2040
                    for rfm in m.REGIONAL_FUEL_MARKETS if m.rfm_fuel == 'Biodiesel'
        ])
        m.NoEarlyBiodiesel = Constraint(m.EARLY_BIODIESEL_MARKETS, rule=lambda m, rfm, per:
            m.FuelConsumptionInMarket[rfm, per] == 0
        )

        # # 100-300 GWh of non-LNG fuels in 2021-2040 (based on 2016-04 PSIP fig. 5-5)
        # # Note: this is needed because we assume HECO plans to burn LNG in the future
        # # even in scenarios where it costs more than oil.
        # m.PSIP_HIGH_LNG_PERIODS = Set(initialize=lambda m:
        #     [per for per in m.PERIODS if per + m.period_length_years[per] > 2021 and per < 2045]
        # )
        # m.OilProductionGWhPerYear = Expression(m.PERIODS, rule=lambda m, per:
        #     sum(
        #         m.DispatchGenByFuel[g, tp, f] * m.tp_weight_in_year[tp] * 0.001 # convert from MWh to GWh
        #             for f in ['Diesel', 'LSFO', 'LSFO-Diesel-Blend']
        #                 for g in m.GENS_BY_FUEL[f]
        #                     for tp in m.TPS_IN_PERIOD[per] if (g, tp) in m.GEN_TPS
        #     )
        # )
        # m.Upper_Limit_Oil_Power = Constraint(m.PERIODS, rule=lambda m, per:
        #     (m.OilProductionGWhPerYear[per] <= 300)
        #         if per + 0.5 * m.period_length_years[per] >= 2021
        #     else
        #         Constraint.Skip
        # )
        # # lower limit is in place to roughly reflect HECO's plan
        # m.Lower_Limit_Oil_Power = Constraint(m.PERIODS, rule=lambda m, per:
        #     (m.OilProductionGWhPerYear[per] >= 100)
        #         if per + m.period_length_years[per] < 2040  # relax constraint if period ends after 2040
        #     else
        #         Constraint.Skip
        # )

        # force LNG conversion in 2021 (modeled on similar constraint in lng_conversion.py)
        # This could have extra code to skip the constraint if there are no periods after 2021,
        # but it is unlikely ever to be run that way.
        # Note: this is not needed if some plants are forced to run on LNG
        # NOTE: this is no longer used; use '--force-lng-tier container' instead
        # m.PSIP_Force_LNG_Conversion = Constraint(m.LOAD_ZONES, rule=lambda m, z:
        #         m.ConvertToLNG[
        #             z,
        #             min(per for per in m.PERIODS if per + m.period_length_years[per] > 2021)
        #         ] == 1
        #     )

        # # Kahe 5, Kahe 6, Kalaeloa and CC_383 only burn LNG after 2021
        # # This is not used because it creates a weird situation where HECO runs less-efficient non-LNG
        # # plants instead of more efficient LNG-capable plants on oil.
        # # there may be a faster way to build this, but it's not clear what
        # m.PSIP_Force_LNG_Use = Constraint(m.GEN_TP_FUELS, rule=lambda m, g, tp, fuel:
        #     (m.GenFuelUseRate[g, tp, fuel] == 0)
        #         if g in m.LNG_CONVERTED_PLANTS
        #             and fuel != 'LNG'
        #             and m.tp_period[tp] + m.period_length_years[m.tp_period[tp]] > 2021
        #     else
        #         Constraint.Skip
        # )

        # don't allow construction of other technologies (e.g., pumped hydro, fuel cells)
        advanced_tech_vars = [
            "BuildPumpedHydroMW", "BuildAnyPumpedHydro",
            "BuildElectrolyzerMW", "BuildLiquifierKgPerHour", "BuildLiquidHydrogenTankKg",
            "BuildFuelCellMW",
        ]
        def no_advanced_tech_rule_factory(v):
            return lambda m, *k: (getattr(m, v)[k] == 0)
        for v in advanced_tech_vars:
            try:
                var = getattr(m, v)
                setattr(m, "PSIP_No_"+v, Constraint(var._index, rule=no_advanced_tech_rule_factory(v)))
            except AttributeError:
                pass    # model doesn't have this var

        # # don't allow any changes to the fuel market, including bulk LNG
        # # not used now; use "--force-lng-tier container" instead
        # m.PSIP_Deactivate_Limited_RFM_Supply_Tiers = Constraint(m.RFM_SUPPLY_TIERS,
        #     rule=lambda m, r, p, st:
        #         Constraint.Skip if (m.rfm_supply_tier_limit[r, p, st] == float('inf'))
        #         else (m.RFMSupplyTierActivate[r, p, st] == 0)
        # )
