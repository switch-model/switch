import os
from pyomo.environ import *
from switch_mod.financials import capital_recovery_factor as crf

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
            None
        )
    )
    
    # all changes to demand must balance out over the course of the day
    m.Demand_Response_Net_Zero = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        sum(m.ShiftDemand[z, tp] for tp in m.TPS_IN_TS[ts]) == 0.0
    )

    # add the demand response to the model's energy balance
    m.LZ_Energy_Components_Consume.append('ShiftDemand')
