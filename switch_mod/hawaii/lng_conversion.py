"""Don't allow use of LNG unless the cost of conversion is paid."""

# TODO: store source data in a .dat file and read it in here

# TODO: change fuel_markets_expansion to support more complex supply chains,
# e.g., a regional facility (LNG switch) in line with a market upgrade (bulk LNG),
# and possibly additional upgrades beyond (e.g., adding a second FSRU).
# For now, we include the cost of the LNG switch via ad-hoc constraints 

from pyomo.environ import *
from switch_mod.financials import capital_recovery_factor

def define_arguments(argparser):
    argparser.add_argument('--force-lng-tier', default=None, 
        help="LNG tier to use for the full study or 'none' to use no LNG; optimal choice will be made if not specified.")

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
    m.LNG_REGIONAL_FUEL_MARKET = Set(
        initialize=lambda m: {rfm for rfm, per, tier in m.LNG_RFM_SUPPLY_TIERS}
    )
    m.LNG_TIERS = Set(
        initialize=lambda m: {tier for rfm, per, tier in m.LNG_RFM_SUPPLY_TIERS}
    )
    
    # should each tier be activated?
    m.ActivateLNGTier = Var(m.LNG_TIERS, within=Binary)

    # if any tier is activated, all the corresponding markets should be activated
    # TODO: allow different activation periods (for studies longer than 10 years), 
    # and recover all capital costs during the active period(s) (currently lumped 
    # into the first 10 years)
    # This may mean defining a tier upgrade as a project with a certain capital cost
    # and fixed O&M. Or maybe for LNG upgrades, we require full recovery during the
    # online period? i.e., lump the cost on the first day of use? or amortize it over
    # all fuel that passes through the project? maybe just allow specification of 
    # capital cost and project life for LNG upgrades, and allow deactivation (avoiding
    # fixed O&M) after a certain period of time. Then PSIP module could force longer
    # activation if needed.
    
    m.Activate_All_Markets_And_Periods = Constraint(
        m.LNG_RFM_SUPPLY_TIERS,
        rule = lambda m, rfm, per, tier: 
            m.RFMSupplyTierActivate[rfm, per, tier] == m.ActivateLNGTier[tier]
    )
    
    # force use of a particular LNG tier
    def Force_LNG_Tier_rule(m, tier):
        if m.options.force_lng_tier is None:
            # just let the model choose the tier to activate
            return Constraint.Skip
        elif m.options.force_lng_tier.lower() == 'none':
            print "Blocking use of LNG tier: {}".format(tier)
            return (m.ActivateLNGTier[tier] == 0)
        elif tier == m.options.force_lng_tier:
            print "Forcing use of LNG tier: {}".format(tier)
            return (m.ActivateLNGTier[tier] == 1)
        elif m.options.force_lng_tier in m.LNG_TIERS:
            # specified a valid tier, but not the current one
            print "Blocking use of LNG tier: {}".format(tier)
            return (m.ActivateLNGTier[tier] == 0)
        else:
            raise ValueError(
                "--force-lng-tier argument '{}' does not match any LNG market tier.".format(m.options.force_lng_tier)
            )
    m.Force_LNG_Tier = Constraint(m.LNG_TIERS, rule=Force_LNG_Tier_rule)
    
    # list of all projects and timepoints when LNG could potentially be used
    m.LNG_PROJECT_TIMEPOINTS = Set(dimen=2, initialize = lambda m: 
        ((p, t) for p in m.PROJECTS_BY_FUEL['LNG'] for t in m.TIMEPOINTS 
            if (p, t) in m.PROJ_DISPATCH_POINTS)
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
            'Oahu_Kahe_K5', 'Oahu_Kahe_K6', 'Oahu_Kalaeloa_CC1_CC2', 
            'Oahu_CC_383', 'Oahu_CC_152', 'Oahu_CT_100'
        ]
    )
    m.LNG_In_Converted_Plants_Only = Constraint(m.LNG_PROJECT_TIMEPOINTS, 
        rule=lambda m, proj, tp:
            Constraint.Skip if proj in m.LNG_CONVERTED_PLANTS
            else (m.ProjFuelUseRate[proj, tp, 'LNG'] == 0)
    )
    
    # largest amount of LNG that might be consumed per year (should be at least
    # equal to the amount that might be activated and left unused, but
    # not too much bigger); this is 2 million tons per year * 52 MMBtu/ton
    big_market_lng = 2e6 * 52   # MMbtu/year
    
    # LNG converted plants must use LNG unless the supply is exhausted
    # note: in this formulation, FuelConsumptionInMarket can be low,
    # unless LNG_Has_Slack is zero, in which case all available fuel
    # must be consumed. (Conversely, LNG_Has_Slack cannot be set to zero
    # unless all available fuel is consumed.)
    # note: if we create multiple LNG regional fuel markets, this will
    # need to be changed, rather than naming the market directly.
    m.LNG_Has_Slack = Var(m.LNG_REGIONAL_FUEL_MARKET, m.PERIODS, within=Binary)
    def LNG_Slack_Calculation_rule(m, rfm, per):
        if any(
            value(m.rfm_supply_tier_limit[r, p, tier]) == float('inf')
                for r, p, tier in m.RFM_P_SUPPLY_TIERS[rfm, per]
        ):
            # there's an infinite LNG tier in this market (which is activated by default)
            return m.LNG_Has_Slack[rfm, per] == 1
        else:
            # ensure m.LNG_Has_Slack is 1 unless all active tiers are fully used
            return (
                m.FuelConsumptionInMarket[rfm, per] 
                + big_market_lng * m.LNG_Has_Slack[rfm, per]
                >= 
                sum(
                    m.RFMSupplyTierActivate[r, p, tier] * m.rfm_supply_tier_limit[r, p, tier]
                        for r, p, tier in m.RFM_P_SUPPLY_TIERS[rfm, per]
                )
            )
    m.LNG_Slack_Calculation = Constraint(
        m.LNG_REGIONAL_FUEL_MARKET, m.PERIODS,
        rule=LNG_Slack_Calculation_rule
    )

    # force LNG-capable plants to use only LNG until they exhaust all active tiers
    # note: we assume no single project can produce more than 
    # 1500 MW from LNG at 10 MMBtu/MWh heat rate
    big_project_mw = 1500 # MW
    big_project_lng = big_project_mw * 10 # MMBtu/hour
    def Only_LNG_In_Converted_Plants_rule(m, proj, tp):
        if proj not in m.LNG_CONVERTED_PLANTS:
            return Constraint.Skip
        # otherwise force non-LNG fuel to zero if there's LNG available
        non_lng_fuel = sum(
            m.ProjFuelUseRate[proj, tp, f] 
                for f in m.G_FUELS[m.proj_gen_tech[proj]] 
                    if f != 'LNG'
        )
        rfm = m.lz_rfm[m.proj_load_zone[proj], 'LNG']
        lng_market_exhausted = 1 - m.LNG_Has_Slack[rfm, m.tp_period[tp]]
        return (non_lng_fuel <= big_project_lng * lng_market_exhausted)
    m.Only_LNG_In_Converted_Plants = Constraint(
        m.LNG_PROJECT_TIMEPOINTS, 
        rule=Only_LNG_In_Converted_Plants_rule
    )
    
    # If the 'container' tier is forced on, then
    # force LNG-capable plants to run at max power, or up to the
    # point where they exhaust all active LNG tiers. Combined with the 
    # Only_LNG_In_Converted_Plants constraint, this forces plants to burn
    # as much LNG as possible, until they use up the available quota. 
    # This is needed because containerized LNG sometimes costs more than
    # oil, so without the constraint the model would avoid running LNG-capable
    # plants in order to save money.
    # Note: this shouldn't be applied if LNG is cheaper than oil, because
    # then it will force LNG plants on when they would otherwise be off
    # to avoid curtailment.
    if m.options.force_lng_tier == 'container':
        print "Forcing LNG-capable plants to use the full LNG supply if possible."
        def Force_Converted_Plants_On_rule(m, proj, tp):
            if proj in m.LNG_CONVERTED_PLANTS:
                return Constraint.Skip
            # otherwise force production up to the maximum if market has slack
            rfm = m.lz_rfm[m.proj_load_zone[proj], 'LNG']
            lng_market_exhausted = 1 - m.LNG_Has_Slack[rfm, m.tp_period[tp]]
            rule = (
                m.DispatchProj[proj, tp]
                >= 
                m.DispatchUpperLimit[proj, tp]
                - big_project_mw * lng_market_exhausted
            )
            return rule
        m.Force_Converted_Plants_On = Constraint(
            m.LNG_PROJECT_TIMEPOINTS,
            rule=Force_Converted_Plants_On_rule
        )
            
    # # force consumption up to the limit if the 'container' tier is activated,
    # # because this tier sometimes costs more than oil, in which case it will
    # # be avoided without this rule. (this also models HECO's commitment to LNG in PSIP)
    # # (not used because it would make the model infeasible if available plants
    # # can't consume the target quantity, e.g., if the CC_483 is not built)
    # m.LNG_Use_All_Containerized_LNG = Constraint(
    #     m.LNG_REGIONAL_FUEL_MARKET, m.PERIODS
    #     rule = lambda rfm, per:
    #         m.FuelConsumptionInMarket[rfm, per]
    #         ==
    #         sum(
    #             m.RFMSupplyTierActivate[r, p, tier] * m.rfm_supply_tier_limit[r, p, tier]
    #                 for r, p, tier in m.RFM_P_SUPPLY_TIERS[rfm, per]
    #         )
    # )
