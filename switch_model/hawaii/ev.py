from __future__ import print_function
from __future__ import division
import os
from pyomo.environ import *
from switch_model import timescales


def define_arguments(argparser):
    argparser.add_argument(
        "--ev-timing",
        default=["optimal"],
        nargs="+",
        help="Rule(s) for when to charge EVs -- bau=business-as-usual (upon arrival), "
        "flat=around the clock, or optimal (default). You may also specify "
        "multiple options in the form --ev-timing bau=0.32 optimal=0.68 to "
        "use more than one mode. Modes without shares assigned will receive "
        "equal fractions of the unallocated charging.",
    )
    argparser.add_argument(
        "--ev-reserve-types",
        nargs="+",
        default=["spinning"],
        help="Type(s) of reserves to provide from electric-vehicle charging (e.g., 'contingency' or 'regulation')."
        "Default is generic 'spinning'. Specify 'none' to disable. Only takes effect with '--ev-timing optimal'.",
    )


def define_components(m):
    # setup various parameters describing the EV and ICE fleet each year
    m.ev_share = Param(m.LOAD_ZONES, m.PERIODS, within=PercentFraction)
    m.ice_miles_per_gallon = Param(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.ev_miles_per_kwh = Param(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.ev_extra_cost_per_vehicle_year = Param(m.LOAD_ZONES, m.PERIODS, within=Reals)
    m.n_all_vehicles = Param(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)
    m.vmt_per_vehicle = Param(m.LOAD_ZONES, m.PERIODS, within=NonNegativeReals)

    m.ev_bau_mw = Param(m.LOAD_ZONES, m.TIMEPOINTS, within=Reals)

    # calculate the extra annual cost (non-fuel) of having EVs, relative to ICEs (mostly for batteries, could also be chargers)
    m.ev_extra_annual_cost = Param(
        m.PERIODS,
        within=Reals,
        initialize=lambda m, p: sum(
            m.ev_extra_cost_per_vehicle_year[z, p]
            * m.ev_share[z, p]
            * m.n_all_vehicles[z, p]
            for z in m.LOAD_ZONES
        ),
    )

    # calculate total fuel cost for ICE (non-EV) VMTs
    if hasattr(m, "rfm_supply_tier_cost"):
        # using fuel_costs.markets
        ice_fuel_cost_func = lambda m, z, p: m.rfm_supply_tier_cost[
            "Hawaii_Motor_Gasoline", p, "base"
        ]
    elif hasattr(m, "ZONE_FUEL_PERIODS"):
        # using fuel_costs.simple
        ice_fuel_cost_func = lambda m, z, p: m.fuel_cost[z, "Motor_Gasoline", p]
    elif hasattr(m, "ZONE_FUEL_TIMEPOINTS"):
        # using fuel_costs.simple_per_timepoint
        ice_fuel_cost_func = (
            lambda m, z, p: sum(
                m.tp_weight[t] * m.fuel_cost_per_timepoint[z, "Motor_Gasoline", t]
                for t in m.TPS_IN_PERIOD[p]
            )
            / m.period_length_hours[p]
        )
    m.ice_annual_fuel_cost = Param(
        m.PERIODS,
        within=NonNegativeReals,
        initialize=lambda m, p: sum(
            (1.0 - m.ev_share[z, p])
            * m.n_all_vehicles[z, p]
            * m.vmt_per_vehicle[z, p]
            / m.ice_miles_per_gallon[z, p]
            * 0.114  # 0.114 MBtu/gal gasoline
            * ice_fuel_cost_func(m, z, p)
            for z in m.LOAD_ZONES
        ),
    )

    # add cost components to account for the vehicle miles traveled via EV or ICE
    # (not used because it interferes with calculation of cost per kWh for electricity)
    # m.Cost_Components_Per_Period.append('ev_extra_annual_cost')
    # m.Cost_Components_Per_Period.append('ice_annual_fuel_cost')

    # calculate the amount of energy used during each timeseries under business-as-usual charging
    m.ev_mwh_ts = Param(
        m.LOAD_ZONES,
        m.TIMESERIES,
        within=NonNegativeReals,
        initialize=lambda m, z, ts: sum(m.ev_bau_mw[z, tp] for tp in m.TPS_IN_TS[ts])
        * m.ts_duration_of_tp[ts],
    )

    # decide when to provide the EV energy
    m.ChargeEVs = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)

    # make sure to charge all EVs at some point during the day
    # (they must always consume the same amount per day as under business-as-usual,
    # but there may be some room to reschedule it.)
    m.ChargeEVs_min = Constraint(
        m.LOAD_ZONES,
        m.TIMESERIES,
        rule=lambda m, z, ts: sum(m.ChargeEVs[z, tp] for tp in m.TPS_IN_TS[ts])
        * m.ts_duration_of_tp[ts]
        == m.ev_mwh_ts[z, ts],
    )

    # set rules for when to charge EVs
    mode_shares = {"optimal": 0.0, "flat": 0.0, "bau": 0.0}
    for tag in m.options.ev_timing:
        try:
            mode, share = tag.split("=", 2)
            try:
                share = float(share)
            except:
                print(
                    "\nInvalid share for EV charging mode {}: ({}).".format(mode, share)
                )
                raise
        except ValueError:
            mode = tag
            share = None
        if mode in mode_shares:
            mode_shares[mode] = share
        else:
            raise ValueError(
                "Invalid EV charging mode specified for --ev-timing: {}".format(mode)
            )
    fillers = [mode for (mode, share) in mode_shares.items() if share is None]
    allocated_shares = sum(share for share in mode_shares.values() if share is not None)
    if allocated_shares >= 1.00001:
        raise ValueError(
            "Shares assigned with --ev-timing flag add up to {}. "
            "They must sum to 1.0 (or less if a catch-all mode is specified).".format(
                allocated_shares
            )
        )
    if allocated_shares <= 0.99999 and not fillers:
        raise ValueError(
            "Shares assigned with --ev-timing flag add up to {}. "
            "They must sum to 1.0 if no catch-all mode is specified.".format(
                allocated_shares
            )
        )
    for mode in fillers:
        mode_shares[mode] = (1 - allocated_shares) / len(fillers)

    if m.options.verbose:
        for mode, tag in [
            ("optimal", "at best time each day"),
            ("flat", "round the clock each day"),
            ("bau", "at business-as-usual times each day"),
        ]:
            if mode_shares[mode] > 0:
                print("Charging {:.1%} of EVs {}.".format(mode_shares[mode], tag))

    # force the minimum amount of charging required for the bau and flat modes;
    # all other charging will be allocated optimally among hours
    m.Min_EV_Charging = Expression(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, tp: mode_shares["flat"]
        * (m.ev_mwh_ts[z, m.tp_ts[tp]] / m.ts_duration_hrs[m.tp_ts[tp]])
        + mode_shares["bau"] * m.ev_bau_mw[z, tp],
    )
    m.Enforce_EV_Charging_Modes = Constraint(
        m.LOAD_ZONES,
        m.TIMEPOINTS,
        rule=lambda m, z, tp: m.ChargeEVs[z, tp] >= m.Min_EV_Charging[z, tp],
    )

    # add the EV load to the model's energy balance
    m.Zone_Power_Withdrawals.append("ChargeEVs")

    # Register with spinning reserves if it is available and any optimal EV charging is enabled.
    if [rt.lower() for rt in m.options.ev_reserve_types] != ["none"] and mode_shares[
        "optimal"
    ] > 0:
        if hasattr(m, "Spinning_Reserve_Up_Provisions"):
            # calculate available slack from EV charging
            # (from supply perspective, so "up" means less load)
            m.EVSlackUp = Expression(
                m.BALANCING_AREA_TIMEPOINTS,
                rule=lambda m, b, t: sum(
                    m.ChargeEVs[z, t] - m.Min_EV_Charging[z, t]
                    for z in m.ZONES_IN_BALANCING_AREA[b]
                ),
            )
            # note: we currently ignore down-reserves (option of increasing consumption)
            # from EVs since it's not clear how high they could go; we could revisit this if
            # down-reserves have a positive price at equilibrium (probabably won't)
            # print("\n\nNeed to define Spinning_Reserve_Down_Provisions for EVs.\n")
            # import time; time.sleep(3)
            if hasattr(m, "GEN_SPINNING_RESERVE_TYPES"):
                # using advanced formulation, index by reserve type, balancing area, timepoint
                # define variables for each type of reserves to be provided
                # choose how to allocate the slack between the different reserve products
                m.EV_SPINNING_RESERVE_TYPES = Set(
                    dimen=1, initialize=m.options.ev_reserve_types
                )
                m.EVSpinningReserveUp = Var(
                    m.EV_SPINNING_RESERVE_TYPES,
                    m.BALANCING_AREA_TIMEPOINTS,
                    within=NonNegativeReals,
                )
                # constrain reserve provision within available slack
                m.Limit_EVSpinningReserveUp = Constraint(
                    m.BALANCING_AREA_TIMEPOINTS,
                    rule=lambda m, ba, tp: sum(
                        m.EVSpinningReserveUp[rt, ba, tp]
                        for rt in m.EV_SPINNING_RESERVE_TYPES
                    )
                    <= m.EVSlackUp[ba, tp],
                )
                m.Spinning_Reserve_Up_Provisions.append("EVSpinningReserveUp")
            else:
                # using older formulation, only one type of spinning reserves, indexed by balancing area, timepoint
                if m.options.ev_reserve_types != ["spinning"]:
                    raise ValueError(
                        'Unable to use reserve types other than "spinning" with simple spinning reserves module.'
                    )
                m.Spinning_Reserve_Up_Provisions.append("EVSlackUp")


def load_inputs(m, switch_data, inputs_dir):
    """
    Import ev data from .csv files.
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_fleet_info.csv"),
        param=[
            getattr(m, p)
            for p in [
                "ev_share",
                "ice_miles_per_gallon",
                "ev_miles_per_kwh",
                "ev_extra_cost_per_vehicle_year",
                "n_all_vehicles",
                "vmt_per_vehicle",
            ]
        ],
    )
    # print "loading ev_bau_load.csv"
    # import pdb; pdb.set_trace()
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_bau_load.csv"), param=m.ev_bau_mw
    )
