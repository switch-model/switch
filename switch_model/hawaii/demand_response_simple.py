from __future__ import division
import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf

from switch_model.balancing.demand_response.iterative import (
    register_demand_response_reserves,
)


def define_arguments(argparser):
    argparser.add_argument(
        "--demand-response-share",
        type=float,
        default=0.30,
        help="Fraction of hourly load that can be shifted to other times of day (default=0.30)",
    )
    argparser.add_argument(
        "--demand-response-reserve-types",
        nargs="+",
        default=[],
        help="Type(s) of reserves to provide from demand response (e.g., 'contingency' or 'regulation'). "
        "Specify 'none' to disable. Default is 'spinning' if an operating reserve module is used, "
        "otherwise it is 'none'.",
    )


def define_components(m):

    # maximum share of hourly load that can be rescheduled
    # this is mutable so various values can be tested
    m.demand_response_max_share = Param(
        default=m.options.demand_response_share, mutable=True, within=PercentFraction
    )

    # maximum amount of load that can be _added_ each hour; we assume
    # it is 8x the maximum reduction, which is roughly equivalent to
    # concentrating the shifted load into a 3-hour period.
    # Note: before 9/12/18, we didn't enforce this for scheduling, but did
    # apply it when calculating down reserve provision, which meant we would
    # give negative down reserves when shifted demand exceeded this quantity,
    # which would have to come from somewhere else.
    m.demand_response_max_increase = Param(
        within=NonNegativeReals, rule=lambda m: m.demand_response_max_share * 24 / 3
    )

    # adjustment to demand during each hour (positive = higher demand)
    m.ShiftDemand = Var(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        within=Reals,
        bounds=lambda m, z, t: (
            (-1.0) * m.demand_response_max_share * m.zone_demand_mw[z, t],
            m.demand_response_max_increase * m.zone_demand_mw[z, t],
        ),
    )

    # all changes to demand must balance out over the course of the day
    m.Demand_Response_Net_Zero = Constraint(
        m.LOAD_ZONES,
        m.TIMESERIES,
        rule=lambda m, z, ts: sum(m.ShiftDemand[z, tp] for tp in m.TPS_IN_TS[ts])
        == 0.0,
    )

    # add demand response to the zonal energy balance
    m.Zone_Power_Withdrawals.append("ShiftDemand")

    if hasattr(m, "ZONES_IN_BALANCING_AREA"):
        # calculate available slack from demand response
        # (from supply perspective, so "up" means less load)
        m.DemandResponseSlackUp = Expression(
            m.BALANCING_AREA_TIMEPOINTS,
            rule=lambda m, b, t: sum(
                m.ShiftDemand[z, t] - m.ShiftDemand[z, t].lb
                for z in m.ZONES_IN_BALANCING_AREA[b]
            ),
        )
        m.DemandResponseSlackDown = Expression(
            m.BALANCING_AREA_TIMEPOINTS,
            rule=lambda m, b, tp: sum(
                # difference between scheduled load and max allowed
                m.demand_response_max_increase * m.zone_demand_mw[z, tp]
                - m.ShiftDemand[z, tp]
                for z in m.ZONES_IN_BALANCING_AREA[b]
            ),
        )
    register_demand_response_reserves(m)
