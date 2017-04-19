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
    m.NEW_GENECTS = Set(initialize=lambda m: set(p for (p, y) in m.NEW_GEN_BLD_YRS))
    
    # model the wind production tax credit 
    m.Wind_Subsidy_Hourly = Expression(
        m.TIMEPOINTS,
        rule=lambda m, t: -wind_prod_tax_credit * sum(
            m.DispatchGen[p, t] 
                for p in m.GENERATION_PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[wind_energy_source]
                    if p in m.NEW_GENECTS and (p, t) in m.GEN_TPS
        )
    )
    m.Cost_Components_Per_TP.append('Wind_Subsidy_Hourly')
    
    # model the solar tax credit as simply prorating the annual capital cost
    m.Solar_Credit_Annual = Expression(m.PERIODS, rule=lambda m, pe: 
        -solar_invest_tax_credit * sum(
            m.BuildGen[g, bld_yr] * m.gen_capital_cost_annual[g, bld_yr]
                for g in m.GENERATION_PROJECTS_BY_NON_FUEL_ENERGY_SOURCE[solar_energy_source]
                    if g in m.NEW_GENECTS
                        for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, pe]))
    # # another version:
    # m.Solar_Credit_Annual = Expression(m.PERIODS, rule=lambda m, pe:
    #     -solar_invest_tax_credit * sum(
    #         m.BuildGen[g, bld_yr] * m.gen_capital_cost_annual[g, bld_yr]
    #             for (g, bld_yr) in m.NEW_GEN_BLD_YRS
    #                 if (pe in m.PERIODS_FOR_GEN_BLD_YR[g, bld_yr]
    #                     and m.gen_energy_source[g] == solar_energy_source)))
    m.Cost_Components_Per_Period.append('Solar_Credit_Annual')
