from pyomo.environ import *
from util import get

def define_components(m):
    """
    incorporate the effect of federal subsidies
    """

    # note: wind/solar/geothermal production tax credit expires in 2017-2019,
    # so we ignore that (http://programs.dsireusa.org/system/program/detail/734)

    # TODO: move these values into data files
    itc_rates = {
        # DistPV from http://programs.dsireusa.org/system/program/detail/1235
        (2018, 'DistPV'): 0.3,
        (2019, 'DistPV'): 0.3,
        (2020, 'DistPV'): 0.3,
        (2021, 'DistPV'): 0.3,
        # Wind, Solar and Geothermal ITC from
        # http://programs.dsireusa.org/system/program/detail/658
        (2018, 'CentralTrackingPV'): 0.3,
        (2019, 'CentralTrackingPV'): 0.3,
        (2020, 'CentralTrackingPV'): 0.26,
        (2021, 'CentralTrackingPV'): 0.22,
        (2022, 'CentralTrackingPV'): 0.10,
        (2018, 'OnshoreWind'): 0.22,
        (2019, 'OnshoreWind'): 0.12,
        (2018, 'OffshoreWind'): 0.22,
        (2019, 'OffshoreWind'): 0.12,
    }
    itc_rates.update({
        (y, 'CentralTrackingPV'): 0.1
        for y in range(2023, 2051)
    })
    itc_rates.update({  # clone the CentralTrackingPV entries
        (y, 'CentralFixedPV'): itc_rates[y, 'CentralTrackingPV']
        for y in range(2018, 2051)
    })
    itc_rates.update({
        (y, 'Geothermal'): 0.1
        for y in range(2018, 2051)
    })

    # model the renewable investment tax credit as simply prorating the annual capital cost
    m.Federal_Investment_Tax_Credit_Annual = Expression(
        m.PERIODS,
        rule=lambda m, pe: sum(
            -itc_rates[bld_yr, m.gen_tech[g]]
            * m.BuildGen[g, bld_yr]
            * m.gen_capital_cost_annual[g, bld_yr]
            for g in m.NON_FUEL_BASED_GENS
            for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, pe]
            if (bld_yr, m.gen_tech[g]) in itc_rates
        )
    )
    m.Cost_Components_Per_Period.append('Federal_Investment_Tax_Credit_Annual')
