from __future__ import absolute_import
from __future__ import print_function
from pyomo.environ import *
from .util import get
import time


def define_components(m):
    """
    incorporate the effect of federal subsidies
    """

    m.logger.warning(
        "WARNING: {} module does not account for storage attached to renewable projects.".format(
            __name__
        )
    )
    m.logger.warning(
        "WARNING: {} module should use 10% ITC for FlatDistPV in 2022 and later; see https://www.energy.gov/eere/solar/downloads/residential-and-commercial-itc-factsheets".format(
            __name__
        )
    )

    # note: wind/solar/geothermal production tax credit expires in 2017-2019,
    # so we ignore that (http://programs.dsireusa.org/system/program/detail/734)

    # TODO: move these values into data files
    itc_rates = {
        # DistPV from http://programs.dsireusa.org/system/program/detail/1235
        (2018, "DistPV"): 0.3,
        (2019, "DistPV"): 0.3,
        (2020, "DistPV"): 0.26,
        (2021, "DistPV"): 0.22,
        # Wind, Solar and Geothermal ITC from
        # http://programs.dsireusa.org/system/program/detail/658
        (2018, "CentralTrackingPV"): 0.3,
        (2019, "CentralTrackingPV"): 0.3,
        (2020, "CentralTrackingPV"): 0.26,
        (2021, "CentralTrackingPV"): 0.22,
        (2022, "CentralTrackingPV"): 0.10,
        (2018, "OnshoreWind"): 0.22,
        (2019, "OnshoreWind"): 0.12,
        (2018, "OffshoreWind"): 0.22,
        (2019, "OffshoreWind"): 0.12,
    }
    itc_rates.update({(y, "CentralTrackingPV"): 0.1 for y in range(2023, 2051)})
    itc_rates.update({(y, "Geothermal"): 0.1 for y in range(2018, 2051)})

    # clone entries for similar technologies
    clones = [
        ("DistPV", "FlatDistPV"),
        ("DistPV", "SlopedDistPV"),
        ("CentralTrackingPV", "CentralFixedPV"),
    ]
    for src, dest in clones:
        itc_rates.update(
            {(y, dest): rate for (y, tech), rate in itc_rates.items() if tech == src}
        )

    def rule(m):
        subsidized_techs = {k for (y, k) in itc_rates}
        missing_techs = [
            t
            for t in m.GENERATION_TECHNOLOGIES
            if (
                any(x in t.lower() for x in ["pv", "solar", "wind", "geo"])
                and t not in subsidized_techs
            )
        ]
        if missing_techs:
            print("")
            print("=" * 80)
            print(
                "WARNING: these technologies are not listed in {}\n"
                "but may need to be: \n"
                "{}".format(__name__, ", ".join(missing_techs))
            )
            print("=" * 80)
            print("")
            time.sleep(3)

    m.fed_subsidies_check_techs = BuildAction(rule=rule)

    m.gen_investment_subsidy_fraction = Param(
        m.GEN_BLD_YRS,
        within=Reals,
        rule=lambda m, g, bld_yr: itc_rates.get((bld_yr, m.gen_tech[g]), 0.0),
    )
    # model the renewable investment tax credit as simply prorating the
    # annual capital cost (done per generator to simplify reporting)
    # TODO: apply to storage energy too
    m.GenCapitalCostsSubsidy = Expression(
        m.GEN_PERIODS,
        rule=lambda m, g, p: sum(
            -m.gen_investment_subsidy_fraction[g, bld_yr]
            * m.BuildGen[g, bld_yr]
            * m.gen_capital_cost_annual[g, bld_yr]
            for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, p]
        ),
    )

    m.TotalGenCapitalCostsSubsidy = Expression(
        m.PERIODS,
        rule=lambda m, p: sum(
            m.GenCapitalCostsSubsidy[g, p] for g in m.GENS_IN_PERIOD[p]
        ),
    )
    m.Cost_Components_Per_Period.append("TotalGenCapitalCostsSubsidy")
