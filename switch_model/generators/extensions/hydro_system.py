# Copyright (c) 2015-2024 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""

This module defines hydroelectric system components. It creates a hydraulic
system that works in parallel with the electric one. They are linked through
the power generation process at hydroelectric generators. The module builds
on top of generic generators, adding components linking power generation
with water use and availability. It requires the specification of the
water system topology, such as water nodes, reservoirs, water connections
and hydroelectric projects.

The hydraulic system is expected to be operational throughout the whole
time horizon of the simulation.

The water network is a graph composed of nodes and connections. Nodes
represent rivers, lakes or reservoirs, while connections represent flows
between nodes where generating stations may be located. All nodes can have
inflows and consumption that are independent of the hydrological network and
are specified with external data. All connections can control flow between
nodes, potentially limited by minimum flow constraints, or dictated by
geological filtration. All flow is currently downstream, but pumped hydro may
be implemented at a later date. Sink nodes have the ability to spill outside
of the hydraulic system. Reservoir nodes track their water levels during
investment periods, and have their levels externally determined at the
beginning and end of investment periods.

"""
import os
from pyomo.environ import *
from switch_model.utilities import unique_list

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties.properties",
    "switch_model.generators.core.build",
    "switch_model.generators.core.dispatch",
)


def define_components(mod):
    """

    WATER_NODES is the set of nodes of the water system that do not have storage
    capacity. These usually represent confluence and/or divergence of different
    water flows. Members of this set can be abbreviated as wn or wnode.

    WNODE_TPS is a set showing all the combinations of water nodes and
    timepoints, in which the conservation of mass law must be enforced. For now
    it is initialized as the cross product of the WATER_NODES and TIMEPOINTS
    sets, but it should be flexibilized to allow for addition and removal of
    water nodes in intermediate timepoints of the simulation horizon.

    wnode_constant_inflow[wn] is the value of constant inflow of water at each
    node of the hydraulic system throughout the whole simulation. Inflow refers
    to an external source of water that comes into the system at the water node,
    such as rainfall. Water flows that originate from an upstream model
    component, such as another water node or a reservoir, are decided by the
    model and so must not be specified here. This parameter is specified in
    cubic meters per second (cumec) and defaults to 0.

    wnode_constant_consumption[wn] is the value of constant consumption of water
    at each node of the hydraulic system throughout the whole simulation.
    Consumption refers to any activity that takes water out of the modeled
    hydraulic system, such as crop irrigation, human and animal consumption,
    minimum ecological flow for a sink node, etc. This parameter is specified in
    cubic meters per second (cumec) and defaults to 0.

    wnode_tp_inflow[wn, t] and wnode_tp_consumption[wn, t] are the values of
    water inflow and consumption at each node of the hydraulic system specified
    at each timepoint. These are optional parameters that default to
    wnode_constant_inflow and wnode_constant_consumption. Depending on data
    availability, these parameters may be used to represent different phenomena.
    In example, the Chilean datasets specify water inflows due to rainfall and
    melting snows at different nodes in a weekly basis. So, all simulated
    timepoints that belong to the same week will have the same wnode_tp_inflow
    parameter specified for each water node.

    wn_is_sink[WATER_NODES] is a binary flag indicating whether a water node is
    a sink. These nodes need not obey the law of conservation of mass, so that
    water flows that go into them may be greater than the ones that flow out.
    The main use case for these is to be the end of a water basin (such as the
    ocean or a lake).

    node_spillage_cost is the parameter that sets the cost in $/(cubic meters)
    of spilling water out of the water network. This is equivalent to relaxing
    the conservation of mass law when balancing flows in each node and
    timepoint, so cost is set to a high default value. This parameter lets the
    model spill water freely in sink nodes, but relaxes the equality constraint
    for mass balance. This aids the solver in obtaining optimal solutions
    significantly faster and with small water spillages.

    SpillWaterAtNode[WNODE_TPS] are  the decisions of water spillage out of the
    water network at each node and timepoint in  cubic meters per second.

    RESERVOIRS is a subset of water nodes that are reservoirs. These require
    additional characterization. Members of this set may be abbreviated as r or
    res.

    res_min_vol[r] is a parameter that specifies the minimum storage capacity of
    the reservoir in millions of cubic meters. Usually this will be a positive
    value, since reservoirs cannot be completely emptied because of physical
    limitations, but it is allowed to be 0 in case relative volumes want to be
    used.

    res_max_vol[r] is a parameter that specifies the maximum storage capacity of
    the reservoir in millions of cubic meters. If at any timepoint the volume of
    water in the reservoir reaches this limit, spillage may occur to mantain the
    mass balance. This parameter is determined by the physical characteristics
    of the reservoir.

    RESERVOIR_TPS is a set showing all the combinations of reservoirs and
    timepoints, in which the conservation of mass law must be enforced. For now
    it is initialized as the cross product of the RESERVOIRS and TIMEPOINTS
    sets, but it should be flexibilized to allow for addition and removal of
    reservoirs in intermediate timepoints of the simulation horizon.

    res_min_vol_tp[r, t] and res_max_vol_tp[r, t] are the values of allowable
    minimum and maximum water volume at each reservoir specified at each
    timepoint. These may be used to represent seasonal restrictions in water
    levels at any reservoir. For example, minimum volumes of water must be kept
    during summer at some reservoirs to allow for leisure and tourism
    activities, such as water sports. These parameters are optional and default
    to reservoir_min_vol and reservoir_max_vol. They must be specified in
    millionis of cubic meters.

    res_initial_vol[r, ts] is a parameter that states the starting volume of
    stored water in each reservoir for each timeseries in millions of cubic
    meters. If not provided, Switch will assume operators adjust to an optimal
    level before each timeseries.

    res_final_vol[r, ts] is a parameter that states the final volume of stored
    water in each reservoir for each timeseries in millions of cubic meters. If
    not provided, Switch will assume the reservoir must return to the starting
    level at the end of each timeseries. It is recommended to omit res_final_vol
    for most models or set it equal to res_initial_vol, to ensure that the
    system could function with an arbitrary number of repetitions of each
    timeseries, either sequentially or at random times of the year.

    ReservoirVol[r, t] is a variable that tracks the volume of water at each
    reservoir at the beginging of each timepoint, specified in millions of cubic
    meters. This variable is determined by the volume in the previous timepoint,
    the inflows and the outflows.

    WATER_CONNECTIONS is the set of flows that begin and end in different water
    bodies, such as reservoirs and nodes. The model decides how much water is
    "dispatched" through each connection at each timepoint. Water may only flow
    in one direction, so "to" and "from" parameters must be inputted. Members of
    this set may be abbreviated by wc or wcon.

    WCON_TPS is the set of the cross product between TIMEPOINTS and
    WATER_CONNECTIONS. In the future, this should be flexibilized to allow for
    new water connections to be created within the simulation horizon (as with
    WNODE_TPS and RESERVOIR_TPS).

    water_node_from[wc] is a parameter that specifies the water body from which
    the connection extracts water.

    water_node_to[wc] is a parameter that specifies the water body to which the
    connection injects water.

    wc_capacity[wc] is a parameter that specifies the limit, in cubic meters per
    second, of the water flow through the connection. This datum is difficult to
    find, but could be relevant in some cases where rivers or streams have a
    defined capacity and greater flows could cause them to collapse and/or flood
    the surrounding area. Defaults to infinity.

    min_eco_flow[wc, t] is a parameter that indicates the minimum ecological
    water flow that must be dispatched through each water connection at each
    timepoint, specified in cubic meters per second. The parameter is indexed by
    timepoint to allow for representation of seasonal or hourly ecological or
    social constraints. This is an optional parameter that defaults to 0.

    DispatchWater[wc, t] is a variable that represents how much water is flowing
    through each water connection at each timepoint, in cubic meters per second.
    The lower bound is m.min_eco_flow[wc, t] and the upper bound is
    m.wc_capacity[wc].

    Enforce_Wnode_Balance[(wn, t) for (wn, t) in WNODE_TPS] is a constraint that
    enforces conservation of mass at water nodes. This accounts for any spills
    at sink nodes, or any change in reservoir volume between one timepoint and
    the next. This also links the reservoir volumes between timepoints, and
    enforces the final reservoir volume constraint.

    HYDRO_GENS is a subset of GENERATION_PROJECTS which are to be linked with
    the hydraulic system. Both reservoir generators as well as hydroelectric
    projects in series must be specified as HYDRO_GENS and will be treated the
    same. Members of this set may be abbreviated as hproj.

    HYDRO_GEN_TPS is a subset of GEN_TPS only with projects that belong to the
    HYDRO_GENS set. This set is used to index the electricity generation
    decisions.

    hydro_efficiency[hproj] is a parameter that specifies the hydraulic
    efficiency of a project, in units of MW/(cubic meters per second). The
    amount of power generated by a hydroelectric generator with a certain flow
    depends on the water head. This creates a non linear relationship between
    the generated power per water flow and the volume of stored water. In this
    module the efficiency is assumed to be a constant for each project, to keep
    the problem linear.

    hydraulic_location[hproj] is a parameter that specifies the water connection
    in which each hydro project is located. Multiple projects may be located at
    the same connection, which allows modeling of cascading generation.

    TurbinateFlow[hg, t] is a variable that represents the water flow, in cubic
    meters per second, that is passed through the turbines of each project at
    each timepoint. This is the flow that is used to generate electricity.

    SpillFlow[hg, t] is a variable that represents the water flow, in cubic
    meters per second, that is spilled by each project at each timepoint. All
    spilled water is considered to be returned to the same water connection from
    which it was originally extracted.

    Enforce_Hydro_Generation[hg, t] is the constraint that forces power
    generation at each hydro project to be equal to the flow of water that goes
    through its turbines, times its hydro efficiency. This relation is observed
    at each timepoint.

    Enforce_Hydro_Extraction[hg, t] is the constraint that mantains the
    conservation of mass at each project's water extraction point, so that the
    sum of the flows that go through its turbines and the one that is spilled
    are equal to the water that is flowing at each timepoint through the water
    connection where it is located.

    -----
    TODO:
    -Implement pumped storage

    -Allow setting the water spillage cost as a parameter. The default of 10000
    US$/cumec should prevent significant water spillage in non-sink nodes in
    most cases. Nonetheless, some users could want to lower the penalties for
    some nodes in order to get faster solution times, and others could want to
    raise them to avoid spilling completely.

    """
    #################
    # Nodes of the water network
    mod.WATER_NODES = Set(dimen=1)
    mod.WNODE_TPS = Set(dimen=2, initialize=lambda m: m.WATER_NODES * m.TIMEPOINTS)
    mod.wnode_constant_inflow = Param(
        mod.WATER_NODES, within=NonNegativeReals, default=0.0
    )
    mod.wnode_constant_consumption = Param(
        mod.WATER_NODES, within=NonNegativeReals, default=0.0
    )
    mod.wnode_tp_inflow = Param(
        mod.WNODE_TPS,
        within=NonNegativeReals,
        default=lambda m, wn, t: m.wnode_constant_inflow[wn],
    )
    mod.wnode_tp_consumption = Param(
        mod.WNODE_TPS,
        within=NonNegativeReals,
        default=lambda m, wn, t: m.wnode_constant_consumption[wn],
    )
    mod.wn_is_sink = Param(mod.WATER_NODES, within=Boolean)
    mod.min_data_check("wn_is_sink")
    mod.spillage_penalty = Param(within=NonNegativeReals, default=100)
    mod.SpillWaterAtNode = Var(mod.WNODE_TPS, within=NonNegativeReals)

    #################
    # Reservoir nodes
    mod.RESERVOIRS = Set(within=mod.WATER_NODES, dimen=1)
    mod.RESERVOIR_TPS = Set(dimen=2, initialize=lambda m: m.RESERVOIRS * m.TIMEPOINTS)
    mod.res_min_vol = Param(mod.RESERVOIRS, within=NonNegativeReals, default=0.0)
    mod.res_max_vol = Param(
        mod.RESERVOIRS,
        within=NonNegativeReals,
        validate=lambda m, val, r: val >= m.res_min_vol[r],
    )
    mod.res_min_vol_tp = Param(
        mod.RESERVOIR_TPS,
        within=NonNegativeReals,
        default=lambda m, r, t: m.res_min_vol[r],
        validate=lambda m, val, r, t: val >= m.res_min_vol[r],
    )
    mod.res_max_vol_tp = Param(
        mod.RESERVOIR_TPS,
        within=NonNegativeReals,
        default=lambda m, r, t: m.res_max_vol[r],
        validate=lambda m, val, r, t: val <= m.res_max_vol[r],
    )

    mod.res_initial_vol = Param(
        mod.RESERVOIRS,
        mod.TIMESERIES,
        within=NonNegativeReals,
        default=float("inf"),
        validate=lambda m, val, r, ts: val == float("inf")
        or (
            m.res_min_vol_tp[r, m.TPS_IN_TS[ts].first()]
            <= val
            <= m.res_max_vol_tp[r, m.TPS_IN_TS[ts].first()]
        ),
    )
    mod.res_final_vol = Param(
        mod.RESERVOIRS,
        mod.TIMESERIES,
        within=NonNegativeReals,
        default=float("inf"),
        validate=lambda m, val, r, ts: val == float("inf")
        or (
            m.res_min_vol_tp[r, m.TPS_IN_TS[ts].last()]
            <= val
            <= m.res_max_vol_tp[r, m.TPS_IN_TS[ts].last()]
        ),
    )
    mod.min_data_check("res_max_vol")

    # make sure they don't set a final reservoir volume without also setting
    # a starting volume, because then Switch would just set the starting
    # volume as high as it wants, then run down to the final volume.
    mod.Set_res_initial_vol_If_Setting_res_final_vol = BuildCheck(
        mod.TIMESERIES,
        rule=lambda m, ts: m.res_final_vol == float("inf")
        or m.res_initial_vol != float("inf"),
    )

    mod.ReservoirVol = Var(
        mod.RESERVOIR_TPS,
        within=NonNegativeReals,
        bounds=lambda m, r, tp: (m.res_min_vol_tp[r, tp], m.res_max_vol_tp[r, tp]),
    )

    # apply res_initial_vol if provided
    mod.Enforce_res_initial_vol = Constraint(
        mod.RESERVOIRS,
        mod.TIMESERIES,
        rule=lambda m, r, ts: (
            Constraint.Skip
            if (m.res_initial_vol[r, ts] == float("inf"))  # not specified
            else (
                m.ReservoirVol[r, m.TPS_IN_TS[ts].first()] == m.res_initial_vol[r, ts]
            )
        ),
    )

    ################
    # Edges of the water network
    mod.WATER_CONNECTIONS = Set(dimen=1)
    mod.WCON_TPS = Set(dimen=2, initialize=lambda m: m.WATER_CONNECTIONS * m.TIMEPOINTS)
    mod.water_node_from = Param(mod.WATER_CONNECTIONS, within=mod.WATER_NODES)
    mod.water_node_to = Param(mod.WATER_CONNECTIONS, within=mod.WATER_NODES)
    mod.wc_capacity = Param(
        mod.WATER_CONNECTIONS, within=NonNegativeReals, default=float("inf")
    )
    mod.min_eco_flow = Param(mod.WCON_TPS, within=NonNegativeReals, default=0.0)
    mod.min_data_check("water_node_from", "water_node_to")
    mod.DispatchWater = Var(
        mod.WCON_TPS,
        within=NonNegativeReals,
        bounds=lambda m, wc, t: (m.min_eco_flow[wc, t], m.wc_capacity[wc]),
    )

    ################
    # Hydro and pumping projects and available timepoints
    mod.HYDRO_GENS = Set(dimen=1, within=mod.GENERATION_PROJECTS)
    mod.HYDRO_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: ((g, tp) for g in m.HYDRO_GENS for tp in m.TPS_FOR_GEN[g]),
    )

    mod.hydro_efficiency = Param(mod.HYDRO_GENS, within=NonNegativeReals)
    mod.hydraulic_location = Param(mod.HYDRO_GENS, within=mod.WATER_CONNECTIONS)
    mod.TurbinateFlow = Var(mod.HYDRO_GEN_TPS, within=NonNegativeReals)
    mod.SpillFlow = Var(mod.HYDRO_GEN_TPS, within=NonNegativeReals)
    mod.Enforce_Hydro_Generation = Constraint(
        mod.HYDRO_GEN_TPS,
        rule=lambda m, g, t: (
            m.DispatchGen[g, t] == m.hydro_efficiency[g] * m.TurbinateFlow[g, t]
        ),
    )
    mod.Enforce_Hydro_Extraction = Constraint(
        mod.HYDRO_GEN_TPS,
        rule=lambda m, g, t: (
            m.TurbinateFlow[g, t] + m.SpillFlow[g, t]
            == m.DispatchWater[m.hydraulic_location[g], t]
        ),
    )

    mod.PUMPED_HYDRO_GENS = Set(
        dimen=1,
        initialize=lambda m: (
            (m.HYDRO_GENS & m.ALL_STORAGE_GENS)
            if hasattr(m, "ALL_STORAGE_GENS")
            else []
        ),
    )
    mod.PUMPED_HYDRO_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: [
            (g, tp) for g in m.PUMPED_HYDRO_GENS for tp in m.TPS_FOR_GEN[g]
        ],
    )

    # all timepoints when pumping is possible
    mod.PUMPED_WCON_TPS = Set(
        dimen=2,
        initialize=lambda m: unique_list(
            (m.hydraulic_location[g], tp) for (g, tp) in m.PUMPED_HYDRO_GEN_TPS
        ),
    )
    # Amount of water pumped upstream along each connection. This has to be a
    # Var rather than an Expression, because it may be tied to the ChargeStorage
    # choice for multiple gens/pumps on this connection.
    mod.PumpWater = Var(
        mod.PUMPED_WCON_TPS,
        within=NonNegativeReals,
        bounds=lambda m, wc, t: (0, m.wc_capacity[wc]),
    )

    # Amount of water pumped upstream when the storage is charged must be
    # correct. If a gen/pump had 100% round-trip efficiency, we would have
    # ChargeStorage = DispatchGen = TurbinateFlow * hydro_efficiency = PumpWater
    # * hydro_efficiency but with lower round-trip efficiency, we get less water
    # per MWh used for charging.
    # This applies the constraint separately for each gen, so if there are
    # multiple pumps on the same water connection, they all must pump the same
    # amount (cascading, to match the generators).
    mod.Enforce_Hydro_Pumping = Constraint(
        mod.PUMPED_HYDRO_GEN_TPS,
        rule=lambda m, g, t: (
            m.ChargeStorage[g, t] * m.gen_storage_efficiency[g]
            == m.PumpWater[m.hydraulic_location[g], t] * m.hydro_efficiency[g]
        ),
    )

    ##############
    # Hydro flow balance
    mod.INWARD_WCONS_TO_WNODE = Set(
        mod.WATER_NODES,
        dimen=1,
        initialize=lambda m, wn: [
            wc for wc in m.WATER_CONNECTIONS if m.water_node_to[wc] == wn
        ],
    )
    mod.OUTWARD_WCONS_FROM_WNODE = Set(
        mod.WATER_NODES,
        dimen=1,
        initialize=lambda m, wn: [
            wc for wc in m.WATER_CONNECTIONS if m.water_node_from[wc] == wn
        ],
    )

    def Enforce_Wnode_Balance_rule(m, wn, tp):
        # Sum inflows and outflows from and to other nodes
        dispatch_inflow = sum(
            m.DispatchWater[wc, tp]
            - (m.PumpWater[wc, tp] if (wc, tp) in m.PUMPED_WCON_TPS else 0)
            for wc in m.INWARD_WCONS_TO_WNODE[wn]
        )
        dispatch_outflow = sum(
            m.DispatchWater[wc, tp]
            - (m.PumpWater[wc, tp] if (wc, tp) in m.PUMPED_WCON_TPS else 0)
            for wc in m.OUTWARD_WCONS_FROM_WNODE[wn]
        )

        # calculate reservoir_fill_rate rate during this timepoint in m3/s
        if wn in m.RESERVOIRS:
            ts = m.tp_ts[tp]
            if tp == m.TPS_IN_TS[ts].last() and m.res_final_vol[wn, ts] != float("inf"):
                # reach res_final_vol if specified
                end_of_tp_volume = m.res_final_vol[wn, ts]
            else:
                # otherwise use next timepoint (possibly wrapping back to the first)
                end_of_tp_volume = m.ReservoirVol[wn, m.TPS_IN_TS[ts].nextw(tp)]

            # fill rate in m3/s (based on volumes given in million m3)
            reservoir_fill_rate = (
                (end_of_tp_volume - m.ReservoirVol[wn, tp])
                * 1000000.0
                / (m.tp_duration_hrs[tp] * 3600)
            )
        else:
            # not a reservoir: fill rate is 0 m3/s
            reservoir_fill_rate = 0.0

        # Conservation of mass flow
        return (
            # inflows (m3/s)
            m.wnode_tp_inflow[wn, tp] + dispatch_inflow
            # less outflows (m3/s)
            - m.wnode_tp_consumption[wn, tp]
            - dispatch_outflow
            - m.SpillWaterAtNode[wn, tp]
            # net change in volume (m3/s)
            == reservoir_fill_rate
        )

    mod.Enforce_Wnode_Balance = Constraint(
        mod.WNODE_TPS, rule=Enforce_Wnode_Balance_rule
    )

    # TODO: maybe allow creation of water at sink nodes? For now, users must
    # specify the size of the lower reservoir for pumped storage systems and
    # Switch will respect that limit when pumping.
    mod.NodeSpillageCosts = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.SpillWaterAtNode[wn, t] * 3600 * m.tp_duration_hrs[t] * m.spillage_penalty
            for wn in m.WATER_NODES
            if not m.wn_is_sink[wn]
        ),
    )
    mod.Cost_Components_Per_TP.append("NodeSpillageCosts")


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import hydro data to model hydroelectric projects in reservoirs and
    in series.

    The files water_nodes.csv, reservoirs.csv, water_connections.csv and
    hydro_generation_projects.csv are mandatory, since they specify the hydraulic
    system's topology and basic characterization.

    Files water_node_tp_flows, reservoir_tp_data.csv and min_eco_flows.csv
    are optional, since they specify information in a timepoint basis that
    has constant values to default to.

    Run-of-River hydro projects should not be included in this file; RoR
    hydro is treated like any other variable renewable resource, and
    expects data in variable_capacity_factors.csv.

    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "water_nodes.csv"),
        index=mod.WATER_NODES,
        optional_params=["mod.wnode_constant_inflow", "mod.wnode_constant_consumption"],
        param=(
            mod.wn_is_sink,
            mod.wnode_constant_inflow,
            mod.wnode_constant_consumption,
        ),
    )
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "water_node_tp_flows.csv"),
        optional_params=["wnode_tp_inflow", "wnode_tp_consumption"],
        param=(mod.wnode_tp_inflow, mod.wnode_tp_consumption),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "reservoirs.csv"),
        index=mod.RESERVOIRS,
        param=(
            mod.res_min_vol,
            mod.res_max_vol,
        ),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "reservoir_tp_data.csv"),
        optional=True,
        param=(mod.res_max_vol_tp, mod.res_min_vol_tp),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "reservoir_ts_data.csv"),
        optional=True,
        param=(mod.res_initial_vol, mod.res_final_vol),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "water_connections.csv"),
        index=mod.WATER_CONNECTIONS,
        param=(mod.water_node_from, mod.water_node_to, mod.wc_capacity),
    )
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "min_eco_flows.csv"),
        param=(mod.min_eco_flow),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "hydro_generation_projects.csv"),
        index=mod.HYDRO_GENS,
        param=(mod.hydro_efficiency, mod.hydraulic_location),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "spillage_penalty.csv"),
        optional=True,
        param=(mod.spillage_penalty,),
    )
