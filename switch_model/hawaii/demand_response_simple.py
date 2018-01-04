import os
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf

def define_arguments(argparser):
    argparser.add_argument('--demand-response-share', type=float, default=0.30, 
        help="Fraction of hourly load that can be shifted to other times of day (default=0.30)")

def define_components(m):
    
    # maximum share of hourly load that can be rescheduled
    # this is mutable so various values can be tested
    m.demand_response_max_share = Param(default=m.options.demand_response_share, mutable=True)

    # adjustment to demand during each hour (positive = higher demand)
    m.ShiftDemand = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=Reals, bounds=lambda m, z, t: 
        (
            (-1.0) * m.demand_response_max_share * m.zone_demand_mw[z, t],
            # assume all shiftable load can be concentrated into 3 hours (no less)
            None # 24/3 * m.demand_response_max_share * m.zone_demand_mw[z, t]
        )
    )

    # all changes to demand must balance out over the course of the day
    m.Demand_Response_Net_Zero = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        sum(m.ShiftDemand[z, tp] for tp in m.TPS_IN_TS[ts]) == 0.0
    )

    # add demand response to the zonal energy balance
    m.Zone_Power_Withdrawals.append('ShiftDemand')

    # # calculate up and down reserves (from supply perspective, so "up" means less load)
    # # note: the bids are negative quantities, indicating _production_ of reserves;
    # # they contribute to the reserve requirement with opposite sign
    # m.DemandUpReserves = Expression(m.LOAD_ZONES, m.TIMEPOINTS,
    #     rule=lambda m, z, tp: m.DemandResponse[z, t] -  m.DemandResponse[z, t].lb
    # )
    # m.DemandDownReserves = Expression(m.LOAD_ZONES, m.TIMEPOINTS,
    #     # assume loads could quickly be
    #     rule=lambda m, z, tp: m.DemandResponse[z, t].ub - m.DemandResponse[z, t]
    # )
    
    # Register with spinning reserves if it is available
    if hasattr(m, 'Spinning_Reserve_Up_Provisions'):
        m.HIDemandResponseSimpleSpinningReserveUp = Expression(
            m.BALANCING_AREA_TIMEPOINTS, 
            rule=lambda m, b, t:
                sum(m.DemandResponse[z, t] -  m.DemandResponse[z, t].lb
                    for z in m.ZONES_IN_BALANCING_AREA[b])
        )
        m.Spinning_Reserve_Up_Provisions.append('HIDemandResponseSimpleSpinningReserveUp')
