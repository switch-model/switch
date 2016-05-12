"""Don't allow use of LNG unless the cost of conversion is paid."""

# TODO: store source data in a .dat file and read it in here

from pyomo.environ import *
from switch_mod.financials import capital_recovery_factor

def define_arguments(argparser):
    argparser.add_argument('--lng-conversion-year', type=int, default=None, 
        help="Year to force conversion to LNG.")

def define_components(m):
    # prorate the cost of LNG conversion among the islands
    # data from 2016-04-01 PSIP, p. 2.9.
    all_zone_conversion_cost = 340e6
    oahu_mw = 140+140+208+383
    maui_mw = 58+58
    hawaii_mw = 60+60
    all_zone_mw = oahu_mw + maui_mw + hawaii_mw
    zone_conversion_costs = {
        'Oahu': all_zone_conversion_cost * oahu_mw / all_zone_mw,
        'Maui': all_zone_conversion_cost * maui_mw / all_zone_mw,
        'Hawaii': all_zone_conversion_cost * hawaii_mw / all_zone_mw,
    }

    # will the system be converted to LNG?
    m.ConvertToLNG = Var(m.LOAD_ZONES, m.PERIODS, within=Binary)

    # force conversion in a particular year
    if m.options.lng_conversion_year is not None:
        print "Forcing conversion to LNG in all zones in {}.".format(m.options.lng_conversion_year)
        m.Force_LNG_Conversion = Constraint(m.LOAD_ZONES, rule=lambda m, z: 
            m.ConvertToLNG[z, m.options.lng_conversion_year] == 1
        )

    # list of all projects and timepoints when LNG could potentially be used
    m.LNG_PROJECT_TIMEPOINTS = Set(dimen=2, initialize = lambda m: 
        ((p, t) for p in m.PROJECTS_BY_FUEL['LNG'] for t in m.TIMEPOINTS 
            if (p, t) in m.PROJ_DISPATCH_POINTS)
    )
    # restrict LNG usage by each plant
    # note: we assume no single project can produce more than 1500 MW from LNG at 10 MMBtu/MWh heat rate
    m.Enforce_LNG_Conversion = Constraint(m.LNG_PROJECT_TIMEPOINTS, rule=lambda m, proj, tp:
        m.ProjFuelUseRate[proj, tp, 'LNG'] 
        <= 1500 * 10 * sum(
            m.ConvertToLNG[m.proj_load_zone[proj], per] 
                for per in m.CURRENT_AND_PRIOR_PERIODS[m.tp_period[tp]]
        )
    )
    # Only Kahe 5, Kahe 6, Kalaeloa and CC_383 can burn LNG 
    # TODO: change the multi-fuel data inputs to control this, not here
    m.LNG_CONVERTED_PLANTS = Set(
        initialize=['Oahu_Kahe_K5', 'Oahu_Kahe_K6', 'Oahu_Kalaeloa_CC1_CC2', 'Oahu_CC_383']
    )
    m.LNG_In_Converted_Plants_Only = Constraint(m.LNG_PROJECT_TIMEPOINTS, 
        rule=lambda m, proj, tp:
            Constraint.Skip if proj in m.LNG_CONVERTED_PLANTS
            else (m.ProjFuelUseRate[proj, tp, 'LNG'] == 0)
    )


    # add the cost of LNG conversion; for now we assume complete recovery in one period,
    # to avoid any stranded costs (this slightly inflates kWh costs during this particular
    # period, but the amount is fairly small compared to other costs, and it may be followed
    # by lower costs in later periods)
    m.LNGConversionAnnualCost = Expression(m.PERIODS, rule=lambda m, p: sum(
        m.ConvertToLNG[z, p] * zone_conversion_costs[z]
        * capital_recovery_factor(m.interest_rate, m.period_length_years[p])
            for z in m.LOAD_ZONES
    ))
    m.cost_components_annual.append('LNGConversionAnnualCost')

    # we could do cost recovery up till 2045 or in one period, whichever comes later,
    # but that gets complicated (have to set to crf to zero after 2045, unless this 
    # period starts after 2045)
    # m.LNGConversionAnnualCost = Expression(m.PERIODS, rule=lambda m, p: sum(
    #     m.ConvertToLNG[z, cnvrt_yr] * m.zone_conversion_costs[z]
    #     * crf(m.interest_rate, max(2045 - p, m.period_length_years[p]))
    #         for cnvrt_yr in m.CURRENT_AND_PRIOR_PERIODS[p]
    #             for z in m.LOAD_ZONES
    # ))
    