import os
from pyomo.environ import *
from switch_model import timescales

def define_arguments(argparser):
    argparser.add_argument("--ev-timing", choices=['bau', 'flat', 'optimal'], default='optimal',
        help="Rule for when to charge EVs -- business-as-usual (upon arrival), flat around the clock, or optimal (default).")

def define_components(m):
    # setup various parameters describing the EV and ICE fleet each year
    for p in ["ev_share", "ice_miles_per_gallon", "ev_miles_per_kwh", "ev_extra_cost_per_vehicle_year", "n_all_vehicles", "vmt_per_vehicle"]:
        setattr(m, p, Param(m.LOAD_ZONES, m.PERIODS))
    
    m.ev_bau_mw = Param(m.LOAD_ZONES, m.TIMEPOINTS)
    
    # calculate the extra annual cost (non-fuel) of having EVs, relative to ICEs (mostly for batteries, could also be chargers)
    m.ev_extra_annual_cost = Param(m.PERIODS, initialize=lambda m, p:
        sum(m.ev_extra_cost_per_vehicle_year[z, p] * m.ev_share[z, p] * m.n_all_vehicles[z, p] for z in m.LOAD_ZONES)
    )

    # calculate total fuel cost for ICE (non-EV) VMTs
    # We assume gasoline for the ICE vehicles costs the same as diesel
    # note: this is the utility price, which is actually lower than retail gasoline
    if hasattr(m, "rfm_supply_tier_cost"):
        ice_fuel_cost_func = lambda m, z, p: m.rfm_supply_tier_cost['Hawaii_Diesel', p, 'base']
    else:
        ice_fuel_cost_func = lambda m, z, p: m.fuel_cost[z, "Diesel", p]

    m.ice_annual_fuel_cost = Param(m.PERIODS, initialize=lambda m, p:
        sum(
            (1.0 - m.ev_share[z, p]) * m.n_all_vehicles[z, p] * m.vmt_per_vehicle[z, p]
            / m.ice_miles_per_gallon[z, p]
            * 0.114   # 0.114 MBtu/gal gasoline
            * ice_fuel_cost_func(m, z, p)
                for z in m.LOAD_ZONES
        )
    )

    # add cost components to account for the vehicle miles traveled via EV or ICE
    # (not used because it interferes with calculation of cost per kWh for electricity)
    # m.Cost_Components_Per_Period.append('ev_extra_annual_cost')
    # m.Cost_Components_Per_Period.append('ice_annual_fuel_cost')

    # calculate the amount of energy used during each timeseries under business-as-usual charging
    m.ev_mwh_ts = Param(m.LOAD_ZONES, m.TIMESERIES, initialize=lambda m, z, ts:
        sum(m.ev_bau_mw[z, tp] for tp in m.TPS_IN_TS[ts]) * m.ts_duration_of_tp[ts]
    )

    # decide when to provide the EV energy
    m.ChargeEVs = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    
    # make sure to charge all EVs at some point during the day
    # (they must always consume the same amount per day as under business-as-usual,
    # but there may be some room to reschedule it.)
    m.ChargeEVs_min = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        sum(m.ChargeEVs[z, tp] for tp in m.TPS_IN_TS[ts]) * m.ts_duration_of_tp[ts] 
        == m.ev_mwh_ts[z, ts]
    )

    # set rules for when to charge EVs
    if m.options.ev_timing == "optimal":
        if m.options.verbose:
            print "Charging EVs at best time each day."
        # no extra code needed
    elif m.options.ev_timing == "flat":
        if m.options.verbose:
            print "Charging EVs as baseload."
        m.ChargeEVs_flat = Constraint(
            m.LOAD_ZONES, m.TIMEPOINTS, 
            rule=lambda m, z, tp:
                m.ChargeEVs[z, tp] == m.ev_mwh_ts[z, m.tp_ts[tp]] / m.ts_duration_hrs[m.tp_ts[tp]]
        )
    elif m.options.ev_timing == "bau":
        if m.options.verbose:
            print "Charging EVs at business-as-usual times of day."
        m.ChargeEVs_bau = Constraint(
            m.LOAD_ZONES, m.TIMEPOINTS, 
            rule=lambda m, z, tp:
                m.ChargeEVs[z, tp] == m.ev_bau_mw[z, tp]
        )
    else:
        # should never happen
        raise ValueError("Invalid value specified for --ev-timing: {}".format(str(m.options.ev_timing)))

    # add the EV load to the model's energy balance
    m.Zone_Power_Withdrawals.append('ChargeEVs')

    # Register with spinning reserves if it is available and optimal EV
    # charging is enabled.
    if('Spinning_Reserve_Up_Provisions' in dir(m) and 
       m.options.ev_timing == "optimal"):
        m.EVSpinningReserveUp = Expression(
            m.BALANCING_AREA_TIMEPOINTS, 
            rule=lambda m, b, t:
                sum(m.ChargeEVs[z, t]
                    for z in m.ZONES_IN_BALANCING_AREA[b])
        )
        m.Spinning_Reserve_Up_Provisions.append('EVSpinningReserveUp')


def load_inputs(m, switch_data, inputs_dir):
    """
    Import ev data from .tab files. 
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ev_fleet_info.tab'),
        auto_select=True,
        param=[
            getattr(m, p) 
                for p in 
                ["ev_share", "ice_miles_per_gallon", "ev_miles_per_kwh", "ev_extra_cost_per_vehicle_year", "n_all_vehicles", "vmt_per_vehicle"]
        ]
    )
    # print "loading ev_bau_load.tab"
    # import pdb; pdb.set_trace()
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ev_bau_load.tab'),
        auto_select=True,
        param=m.ev_bau_mw
    )
