import os
from pyomo.environ import *

def define_arguments(argparser):
    argparser.add_argument("--ev-timing", choices=['bau', 'optimal'], default='optimal',
        help="Rule for when to charge EVs -- business-as-usual (upon arrival), flat around the clock, or optimal (default).")
    argparser.add_argument('--ev-reserve-types', nargs='+', default=['spinning'],
        help=
            "Type(s) of reserves to provide from electric-vehicle charging (e.g., 'contingency' or 'regulation')."
            "Default is generic 'spinning'. Specify 'none' to disable. Only takes effect with '--ev-timing optimal'."
    )

# parameters describing the EV and ICE fleet each year, all indexed by zone,
# vehicle type and period
ev_zone_type_period_params = [
    "n_vehicles",
    "ice_gals_per_year", "ice_fuel", "ev_kwh_per_year",
    "ev_extra_cost_per_vehicle_year"
]

def define_components(m):

    # indexing set for EV bids, decomposed to get sets of EV bid numbers and EV types
    m.EV_ZONE_TYPE_BID_TP = Set(dimen=4)  # load zone, vehicle type, bid number, timepoint
    def rule(m):
        bids = m.EV_BID_NUMS_set = set()
        types = m.EV_TYPES_set = set()
        for z, t, n, tp in m.EV_ZONE_TYPE_BID_TP:
            bids.add(n)
            types.add(t)
    m.Split_EV_Sets = BuildAction(rule=rule)
    m.EV_BID_NUMS = Set(initialize=lambda m: m.EV_BID_NUMS_set)
    m.EV_TYPES = Set(initialize=lambda m: m.EV_TYPES_set)

    # parameters describing the EV and ICE fleet each year

    # fraction of vehicle fleet that will be electrified in each period (0-1)
    # (could eventually be a decision variable)
    m.ev_share = Param(m.LOAD_ZONES, m.PERIODS, within=PercentFraction)
    for p in ev_zone_type_period_params:
        setattr(m, p, Param(m.LOAD_ZONES, m.EV_TYPES, m.PERIODS))

    # calculate the extra annual cost (non-fuel) of having EVs, relative to ICEs,
    # for batteries and chargers
    m.ev_extra_annual_cost = Param(
        m.PERIODS, initialize=lambda m, p:
        sum(
            m.ev_share[z, p]
            * m.n_vehicles[z, t, p]
            * m.ev_extra_cost_per_vehicle_year[z, t, p]
            for z in m.LOAD_ZONES
            for t in m.EV_TYPES
        )
    )

    # calculate total fuel usage, cost and emissions for ICE (non-EV) vehicles
    motor_fuel_mmbtu_per_gallon = {
        # from https://www.eia.gov/Energyexplained/?page=about_energy_units
        "Motor_Gasoline": 0.120476,
        "Motor_Diesel":   0.137452
    }
    m.ice_annual_fuel_mmbtu = Param(
        m.LOAD_ZONES, m.EV_TYPES, m.PERIODS,
        initialize=lambda m, z, evt, p:
            (1.0 - m.ev_share[z, p])
            * m.n_vehicles[z, evt, p]
            * m.ice_gals_per_year[z, evt, p]
            * motor_fuel_mmbtu_per_gallon[m.ice_fuel[z, evt, p]]
    )
    # non-EV fuel cost
    if hasattr(m, "rfm_supply_tier_cost"):
        ice_fuel_cost_func = lambda m, z, p, f: m.rfm_supply_tier_cost[m.zone_rfm[z, f], p, 'base']
    else:
        ice_fuel_cost_func = lambda m, z, p, f: m.fuel_cost[z, f, p]
    m.ice_annual_fuel_cost = Param(m.PERIODS, initialize=lambda m, p:
        sum(
            m.ice_annual_fuel_mmbtu[z, evt, p]
            * ice_fuel_cost_func(m, z, p, m.ice_fuel[z, evt, p])
            for z in m.LOAD_ZONES
            for evt in m.EV_TYPES
        )
    )
    # non-EV annual emissions (currently only used for reporting via
    # --save-expression ice_annual_emissions
    # TODO: find a way to add this to the AnnualEmissions expression (maybe);
    # at present, this doesn't affect the system emissions or emission cost
    m.ice_annual_emissions = Param(m.PERIODS, initialize = lambda m, p:
        sum(
            m.ice_annual_fuel_mmbtu[z, evt, p]
            * (
                m.f_co2_intensity[m.ice_fuel[z, evt, p]]
                + m.f_upstream_co2_intensity[m.ice_fuel[z, evt, p]]
            )
            for z in m.LOAD_ZONES
            for evt in m.EV_TYPES
        )
    )

    # add cost components to account for the vehicle miles traveled via EV or ICE
    # (not used because it interferes with calculation of cost per kWh for electricity)
    m.Cost_Components_Per_Period.append('ev_extra_annual_cost')
    m.Cost_Components_Per_Period.append('ice_annual_fuel_cost')

    # EV bid data -- total MW used by 100% EV fleet, for each zone, veh type,
    # bid number, timepoint
    m.ev_bid_by_type = Param(m.EV_ZONE_TYPE_BID_TP)

    # aggregate across vehicle types (types are only needed for reporting)
    m.ev_bid_mw = Param(
        m.LOAD_ZONES, m.EV_BID_NUMS, m.TIMEPOINTS,
        initialize=lambda m, z, n, tp:
            sum(m.ev_bid_by_type[z, t, n, tp] for t in m.EV_TYPES)
    )

    # find lowest and highest possible charging in each timepoint, used for reserve calcs
    m.ev_charge_min = Param(
        m.LOAD_ZONES, m.TIMEPOINTS,
        initialize=lambda m, z, tp:
            m.ev_share[z, m.tp_period[tp]]
            * min(m.ev_bid_mw[z, n, tp] for n in m.EV_BID_NUMS)
    )
    m.ev_charge_max = Param(
        m.LOAD_ZONES, m.TIMEPOINTS,
        initialize=lambda m, z, tp:
            m.ev_share[z, m.tp_period[tp]]
            * max(m.ev_bid_mw[z, n, tp] for n in m.EV_BID_NUMS)
    )

    # decide which share of the fleet to allocate to each charging bid
    m.EVBidWeight = Var(m.LOAD_ZONES, m.TIMESERIES, m.EV_BID_NUMS, within=PercentFraction)
    m.Charge_Enough_EVs = Constraint(
        m.LOAD_ZONES, m.TIMESERIES,
        rule=lambda m, z, ts:
            sum(m.EVBidWeight[z, ts, n] for n in m.EV_BID_NUMS) == m.ev_share[z, m.ts_period[ts]]
    )

    # calculate total EV charging
    m.ChargeEVs = Expression(
        m.LOAD_ZONES, m.TIMEPOINTS,
        rule=lambda m, z, tp: sum(
            m.EVBidWeight[z, m.tp_ts[tp], n] * m.ev_bid_mw[z, n, tp]
            for n in m.EV_BID_NUMS
        )
    )

    # set rules for when to charge EVs
    # note: this could be generalized to fractions between 0% and 100% BAU
    if m.options.ev_timing == "optimal":
        if m.options.verbose:
            print "Charging EVs at best time each day."
        # no extra code needed
    elif m.options.ev_timing == "bau":
        if m.options.verbose:
            print "Charging EVs at business-as-usual times of day."
        # give full weight to BAU bid (number 0)
        m.ChargeEVs_bau = Constraint(
            m.LOAD_ZONES, m.EV_BID_NUMS, m.TIMESERIES,
            rule=lambda m, z, n, ts: (
                m.EVBidWeight[z, ts, n]
                == (m.ev_share[z, m.ts_period[ts]] if n == 0 else 0)
            )
        )
    else:
        # should never happen
        raise ValueError("Invalid value specified for --ev-timing: {}".format(str(m.options.ev_timing)))

    # add the EV load to the model's energy balance
    m.Zone_Power_Withdrawals.append('ChargeEVs')

    # Register with spinning reserves if it is available and optimal EV charging is enabled.
    if [rt.lower() for rt in m.options.ev_reserve_types] != ['none'] and m.options.ev_timing == "optimal":
        if hasattr(m, 'Spinning_Reserve_Up_Provisions'):
            # calculate available slack from EV charging
            # (from supply perspective, so "up" means less load)
            m.EVSlackUp = Expression(
                m.BALANCING_AREA_TIMEPOINTS,
                rule=lambda m, b, t: sum(
                    m.ChargeEVs[z, t] - m.ev_charge_min[z, t]
                    for z in m.ZONES_IN_BALANCING_AREA[b]
                )
            )
            m.EVSlackDown = Expression(
                m.BALANCING_AREA_TIMEPOINTS,
                rule=lambda m, b, t: sum(
                    m.ev_charge_max[z, t] - m.ChargeEVs[z, t]
                    for z in m.ZONES_IN_BALANCING_AREA[b]
                )
            )
            if hasattr(m, 'GEN_SPINNING_RESERVE_TYPES'):
                # using advanced formulation, index by reserve type, balancing area, timepoint.
                # define variables for each type of reserves to be provided
                # choose how to allocate the slack between the different reserve products
                m.EV_SPINNING_RESERVE_TYPES = Set(
                    initialize=m.options.ev_reserve_types
                )
                m.EVSpinningReserveUp = Var(
                    m.EV_SPINNING_RESERVE_TYPES, m.BALANCING_AREA_TIMEPOINTS,
                    within=NonNegativeReals
                )
                m.EVSpinningReserveDown = Var(
                    m.EV_SPINNING_RESERVE_TYPES, m.BALANCING_AREA_TIMEPOINTS,
                    within=NonNegativeReals
                )
                # constrain reserve provision within available slack
                m.Limit_EVSpinningReserveUp = Constraint(
                    m.BALANCING_AREA_TIMEPOINTS,
                    rule=lambda m, ba, tp:
                        sum(
                            m.EVSpinningReserveUp[rt, ba, tp]
                            for rt in m.EV_SPINNING_RESERVE_TYPES
                        ) <= m.EVSlackUp[ba, tp]
                )
                m.Limit_EVSpinningReserveDown = Constraint(
                    m.BALANCING_AREA_TIMEPOINTS,
                    rule=lambda m, ba, tp:
                        sum(
                            m.EVSpinningReserveDown[rt, ba, tp]
                            for rt in m.EV_SPINNING_RESERVE_TYPES
                        ) <= m.EVSlackDown[ba, tp]
                )
                m.Spinning_Reserve_Up_Provisions.append('EVSpinningReserveUp')
                m.Spinning_Reserve_Down_Provisions.append('EVSpinningReserveDown')
            else:
                # using older formulation, only one type of spinning reserves, indexed by balancing area, timepoint
                if m.options.ev_reserve_types != ['spinning']:
                    raise ValueError(
                        'Unable to use reserve types other than "spinning" with simple spinning reserves module.'
                    )
                m.Spinning_Reserve_Up_Provisions.append('EVSlackUp')
                m.Spinning_Reserve_Down_Provisions.append('EVSlacDown')


def load_inputs(m, switch_data, inputs_dir):
    """
    Import ev data from .tab files.
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ev_share.tab'),
        auto_select=True,
        param=m.ev_share
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ev_fleet_info_advanced.tab'),
        auto_select=True,
        param=[getattr(m, p) for p in ev_zone_type_period_params]
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ev_charging_bids.tab'),
        auto_select=True,
        param=m.ev_bid_by_type,
        index=m.EV_ZONE_TYPE_BID_TP
    )
