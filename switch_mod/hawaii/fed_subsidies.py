from pyomo.environ import *
from util import get

def define_components(m):
    """
    incorporate the effect of federal subsidies
    """
    
    # TODO: move these values into data files
    wind_energy_source = 'WND'
    # approx lifetime average credit, based on 2014$ 0.023/kWh for first 10 years of project
    wind_prod_tax_credit = 0.015 * 1000  # $/MWh
    solar_energy_source = 'SUN'
    solar_invest_tax_credit = 0.3   # fraction of capital cost

    # note: wind PTC expired at end of 2014; solar expires at end of 2016, 
    # except for continuing 10% business investment tax credit.
    
    # note: here we assume that existing projects and new (unbuilt) projects
    # are defined separately
    m.NEW_PROJECTS = Set(initialize=lambda m: set(p for (p, y) in m.NEW_PROJ_BUILDYEARS))
    
    # model the wind production tax credit 
    m.Wind_Subsidy_Hourly = Expression(
        m.TIMEPOINTS,
        rule=lambda m, t: -wind_prod_tax_credit * sum(
            m.DispatchProj[p, t] 
                for p in m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[wind_energy_source]
                    if p in m.NEW_PROJECTS and (p, t) in m.PROJ_DISPATCH_POINTS
        )
    )
    m.cost_components_tp.append('Wind_Subsidy_Hourly')
    
    # model the solar tax credit as simply prorating the annual capital cost
    m.Solar_Credit_Annual = Expression(m.PERIODS, rule=lambda m, pe: 
        -solar_invest_tax_credit * sum(
            m.BuildProj[pr, bld_yr] * m.proj_capital_cost_annual[pr, bld_yr]
                for pr in m.PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[solar_energy_source]
                    if pr in m.NEW_PROJECTS
                        for bld_yr in m.PROJECT_PERIOD_ONLINE_BUILD_YRS[pr, pe]))
    # # another version:
    # m.Solar_Credit_Annual = Expression(m.PERIODS, rule=lambda m, pe:
    #     -solar_invest_tax_credit * sum(
    #         m.BuildProj[pr, bld_yr] * m.proj_capital_cost_annual[pr, bld_yr]
    #             for (pr, bld_yr) in m.NEW_PROJECT_BUILDYEARS
    #                 if (pe in m.PROJECT_BUILDS_OPERATIONAL_PERIODS[pr, bld_yr]
    #                     and m.g_energy_source[m.p_gen_tech[pr]] == solar_energy_source)))
    m.cost_components_annual.append('Solar_Credit_Annual')
