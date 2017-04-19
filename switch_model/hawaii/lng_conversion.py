"""Don't allow use of LNG unless the cost of conversion is paid."""

# TODO: store source data in a .dat file and read it in here

# TODO: change fuel_markets_expansion to support more complex supply chains,
# e.g., a regional facility (LNG switch) in line with a market upgrade (bulk LNG),
# and possibly additional upgrades beyond (e.g., adding a second FSRU).
# For now, we include the cost of the LNG switch via ad-hoc constraints 

from pyomo.environ import *
from switch_model.financials import capital_recovery_factor

def define_arguments(argparser):
    argparser.add_argument('--force-lng-tier', nargs='*', default=None, 
        help="LNG tier to use or 'none' to use no LNG; can also specify start and end date to use this tier; optimal choices will be made if nothing specified.")

def define_components(m):

    # all conversion costs have been lumped into the tier prices,
    # so all periods must use the same tier, to get the cost recovery right
    # (this reflects the nature of the choice anyway - an early decision
    # on which path to follow with LNG, if any)
    # Note: if we activate a tier in any market, we activate it in all markets
    # (e.g., bringing in containerized LNG for all islands)
    
    m.LNG_RFM_SUPPLY_TIERS = Set(
        initialize=m.RFM_SUPPLY_TIERS, 
        filter=lambda m, rfm, per, tier: m.rfm_fuel[rfm].upper() == 'LNG'
    )
    m.LNG_REGIONAL_FUEL_MARKETS = Set(
        initialize=lambda m: {rfm for rfm, per, tier in m.LNG_RFM_SUPPLY_TIERS}
    )
    m.LNG_TIERS = Set(
        initialize=lambda m: {tier for rfm, per, tier in m.LNG_RFM_SUPPLY_TIERS}
    )
    
    # force LNG to be deactivated when RPS is 100%; 
    # this forces recovery of all costs before the 100% RPS takes effect
    # (otherwise the model sometimes tries to postpone recovery beyond the end of the study)
    if hasattr(m, 'RPS_Enforce'):
        m.No_LNG_In_100_RPS = Constraint(m.LNG_RFM_SUPPLY_TIERS, 
            rule=lambda m, rfm, per, tier:
                (m.RFMSupplyTierActivate[rfm, per, tier] == 0) 
                    if m.rps_target_for_period[per] >= 1.0 
                        else Constraint.Skip
        )
    
    # user can study different LNG durations by specifying a tier to activate and 
    # a start and end date. Both the capital recovery and fixed costs for this tier are
    # bundled into the market's fixed cost, which means a different fuel_supply_curves.tab
    # file is needed for each LNG duration (i.e., the tiers must be forced on or off
    # for a particular duration which matches the fuel_supply_curves.tab). This is
    # brittle and requires trying all permutations to find the optimum, which is not
    # good. A better way would be to specify capital costs separately from fixed costs, 
    # and add a flag to force the model to recover capital costs completely within the 
    # study period if desired. (Another flag could set a minimum duration for LNG
    # infrastructure to be activated.)
    
    # This may mean defining a tier upgrade as a project with a certain capital cost
    # and fixed O&M. Or maybe for LNG upgrades, we require full recovery during the
    # online period? i.e., lump the cost on the first day of use? or amortize it over
    # all fuel that passes through the project? maybe just allow specification of 
    # capital cost and project life for LNG upgrades, and allow deactivation (avoiding
    # fixed O&M) after a certain period of time. Then PSIP module could force longer
    # activation if needed.
    
    # In the end, this was resolved by having the user specify multiple tiers with
    # different lifetimes and corresponding fixed costs per year; then the model
    # (or user) can choose a tier with a particular lifetime.
    
    # force use of a particular LNG tier in particular periods
    def Force_LNG_Tier_rule(m, rfm, per, tier):
        if m.options.force_lng_tier is None:
            # let the model choose the tier(s) to activate
            action = Constraint.Skip
        else:
            # user specified a tier to activate and possibly a date range
            # force that active and deactivate all others.
            force_tier = m.options.force_lng_tier[0]
            force_tier_start = float(m.options.force_lng_tier[1]) if len(m.options.force_lng_tier) > 1 else m.PERIODS.first()
            force_tier_end = float(m.options.force_lng_tier[2]) if len(m.options.force_lng_tier) > 2 else m.PERIODS.last()
            if force_tier.lower() == 'none':
                action = 0
            elif force_tier not in m.LNG_TIERS:
                raise ValueError(
                    "--force-lng-tier argument '{}' does not match any LNG market tier.".format(force_tier)
                )
            elif tier == force_tier and force_tier_start <= per <= force_tier_end:
                # force tier on
                action = 1
            else:
                # specified a valid tier, but not the current one or not the current period
                action = 0
        if action == Constraint.Skip:
            # if m.options.verbose:
            #     print "Model will optimize activation of tier {}.".format((rfm, per, tier))
            result = action
        else:
            if m.options.verbose:
                print "{} activation of tier {}.".format('Forcing' if action else 'Blocking', (rfm, per, tier))
            result = (m.RFMSupplyTierActivate[rfm, per, tier] == action)
        return result
    m.Force_LNG_Tier = Constraint(m.LNG_RFM_SUPPLY_TIERS, rule=Force_LNG_Tier_rule)


    # list of all projects and timepoints when LNG could potentially be used
    m.LNG_GENECT_TIMEPOINTS = Set(dimen=2, initialize = lambda m: 
        ((p, t) for p in m.GENERATION_PROJECTS_BY_FUEL['LNG'] for t in m.TIMEPOINTS 
            if (p, t) in m.GEN_TPS)
    )

    # HECO PSIP 2016-04 has only Kahe 5, Kahe 6, Kalaeloa and CC_383 burning LNG,
    # but we assume other new CC/CT plants could also burn it if they are built (at Kahe site).
    # However, no other plants can use LNG, since the conversion costs only cover the
    # Kahe and Kalealoa sites.
    # TODO: change the multi-fuel data inputs to control this, not here
    # Note: previously there was additional code to prevent these plants from burning
    # LNG if we didn't explicitly do the conversions; however, now the conversion costs
    # are included in the LNG supply tiers, so we don't need to worry about that.
    m.LNG_CONVERTED_PLANTS = Set(
        initialize=[
            'Oahu_Kahe_K5', 'Oahu_Kahe_K6', 
            'Oahu_Kalaeloa_CC1_CC2', # used in some older models
            'Oahu_Kalaeloa_CC1', 'Oahu_Kalaeloa_CC2', 'Oahu_Kalaeloa_CC3',
            'Oahu_CC_383', 'Oahu_CC_152', 'Oahu_CT_100'
        ]
    )
    m.LNG_In_Converted_Plants_Only = Constraint(m.LNG_GENECT_TIMEPOINTS, 
        rule=lambda m, g, tp:
            Constraint.Skip if g in m.LNG_CONVERTED_PLANTS
            else (m.GenFuelUseRate[g, tp, 'LNG'] == 0)
    )
    
    # CODE BELOW IS DISABLED because we have abandoned the 'container' tier which cost
    # more than LSFO, and because we would rather show the choice that is made if LNG 
    # is more expensive (i.e., stick with LSFO)

    # NOTE: all the code below works together to force the model to meet an LNG quota - or try as
    # hard as possible - if LNG has been activated and the variable cost is higher than LSFO. 
    # These constraints could potentially be replaced with simpler code that forces the power 
    # system to meet the LNG quota, but then that could be infeasible if there is not enough 
    # LNG-capable generation capacity to meet that quota.
 
    # # largest amount of LNG that might be consumed per year (should be at least
    # # equal to the amount that might be activated and left unused, but
    # # not too much bigger); this is 2 million tons per year * 52 MMBtu/ton
    # big_market_lng = 2e6 * 52   # MMbtu/year
    
    # # LNG converted plants must use LNG unless the supply is exhausted
    # # note: in this formulation, FuelConsumptionInMarket can be low,
    # # unless LNG_Has_Slack is zero, in which case all available fuel
    # # must be consumed. (Conversely, LNG_Has_Slack cannot be set to zero
    # # unless all available fuel is consumed.)
    # # note: if we create multiple LNG regional fuel markets, this will
    # # need to be changed, rather than naming the market directly.
    # m.LNG_Has_Slack = Var(m.LNG_REGIONAL_FUEL_MARKETS, m.PERIODS, within=Binary)
    # def LNG_Slack_Calculation_rule(m, rfm, per):
    #     if any(
    #         value(m.rfm_supply_tier_limit[r, p, tier]) == float('inf')
    #             for r, p, tier in m.SUPPLY_TIERS_FOR_RFM_PERIOD[rfm, per]
    #     ):
    #         # there's an infinite LNG tier in this market (which is activated by default)
    #         return m.LNG_Has_Slack[rfm, per] == 1
    #     else:
    #         # ensure m.LNG_Has_Slack is 1 unless all active tiers are fully used
    #         return (
    #             m.FuelConsumptionInMarket[rfm, per]
    #             + big_market_lng * m.LNG_Has_Slack[rfm, per]
    #             >=
    #             sum(
    #                 m.RFMSupplyTierActivate[r, p, tier] * m.rfm_supply_tier_limit[r, p, tier]
    #                     for r, p, tier in m.SUPPLY_TIERS_FOR_RFM_PERIOD[rfm, per]
    #             )
    #         )
    # m.LNG_Slack_Calculation = Constraint(
    #     m.LNG_REGIONAL_FUEL_MARKETS, m.PERIODS,
    #     rule=LNG_Slack_Calculation_rule
    # )

    # # force LNG-capable plants to use only LNG until they exhaust all active tiers
    # # note: we assume no single project can produce more than
    # # 1500 MW from LNG at 10 MMBtu/MWh heat rate
    # big_gect_mw = 1500 # MW
    # big_gect_lng = big_gect_mw * 10 # MMBtu/hour
    # def Only_LNG_In_Converted_Plants_rule(m, g, tp):
    #     if g not in m.LNG_CONVERTED_PLANTS:
    #         return Constraint.Skip
    #     # otherwise force non-LNG fuel to zero if there's LNG available
    #     non_lng_fuel = sum(
    #         m.GenFuelUseRate[g, tp, f]
    #             for f in m.FUELS_FOR_GEN[g]
    #                 if f != 'LNG'
    #     )
    #     rfm = m.zone_rfm[m.gen_load_zone[g], 'LNG']
    #     lng_market_exhausted = 1 - m.LNG_Has_Slack[rfm, m.tp_period[tp]]
    #     return (non_lng_fuel <= big_gect_lng * lng_market_exhausted)
    # m.Only_LNG_In_Converted_Plants = Constraint(
    #     m.LNG_GENECT_TIMEPOINTS,
    #     rule=Only_LNG_In_Converted_Plants_rule
    # )
    
    # # If the 'container' tier is forced on, then
    # # force LNG-capable plants to run at max power, or up to the
    # # point where they exhaust all active LNG tiers. Combined with the
    # # Only_LNG_In_Converted_Plants constraint, this forces plants to burn
    # # as much LNG as possible, until they use up the available quota.
    # # This is needed because containerized LNG sometimes costs more than
    # # oil, so without the constraint the model would avoid running LNG-capable
    # # plants in order to save money.
    # # Note: this shouldn't be applied if LNG is cheaper than oil, because
    # # then it will force LNG plants on when they would otherwise be off
    # # to avoid curtailment.
    # if m.options.force_lng_tier == 'container':
    #     print "Forcing LNG-capable plants to use the full LNG supply if possible."
    #     def Force_Converted_Plants_On_rule(m, g, tp):
    #         if g in m.LNG_CONVERTED_PLANTS:
    #             return Constraint.Skip
    #         # otherwise force production up to the maximum if market has slack
    #         rfm = m.zone_rfm[m.gen_load_zone[g], 'LNG']
    #         lng_market_exhausted = 1 - m.LNG_Has_Slack[rfm, m.tp_period[tp]]
    #         rule = (
    #             m.DispatchGen[g, tp]
    #             >=
    #             m.DispatchUpperLimit[g, tp]
    #             - big_gect_mw * lng_market_exhausted
    #         )
    #         return rule
    #     m.Force_Converted_Plants_On = Constraint(
    #         m.LNG_GENECT_TIMEPOINTS,
    #         rule=Force_Converted_Plants_On_rule
    #     )
            
    # # force consumption up to the limit if the 'container' tier is activated,
    # # because this tier sometimes costs more than oil, in which case it will
    # # be avoided without this rule. (this also models HECO's commitment to LNG in PSIP)
    # # (not used because it would make the model infeasible if available plants
    # # can't consume the target quantity, e.g., if the CC_483 is not built)
    # m.LNG_Use_All_Containerized_LNG = Constraint(
    #     m.LNG_REGIONAL_FUEL_MARKETS, m.PERIODS
    #     rule = lambda rfm, per:
    #         m.FuelConsumptionInMarket[rfm, per]
    #         ==
    #         sum(
    #             m.RFMSupplyTierActivate[r, p, tier] * m.rfm_supply_tier_limit[r, p, tier]
    #                 for r, p, tier in m.SUPPLY_TIERS_FOR_RFM_PERIOD[rfm, per]
    #         )
    # )
