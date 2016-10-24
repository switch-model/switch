# Copyright 2016 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

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

"""

import os
from pyomo.environ import *

def define_components(mod):
    """
    
    WATER_NODES is the set of nodes of the water system that do not have
    storage capacity. These usually represent confluence and/or divergence
    of different water flows. Members of this set can be abbreviated as 
    wn or wnode.
    
    wn_is_sink[WATER_NODES] is a binary flag indicating whether a water
    node is a sink. These nodes need not obey the law of conservation of 
    mass, so that water flows that go into them may be greater than the
    ones that flow out. The main use case for these is to be the end of a
    water basin (representing the ocean or other sink).
    
    WATER_NODES_BALANCE_POINTS is a set showing all the combinations of
    water nodes and timepoints, in which the conservation of mass law 
    must be enforced. For now it is initialized as the cross product of
    the WATER_NODES and TIMEPOINTS sets, but it should be flexibilized 
    to allow for addition and removal of water nodes in intermediate
    timepoints of the simulation horizon.
    
    WATER_SINKS_BALANCE_POINTS is a set showing all the combinations of
    water sinks and timepoints, in which water "spilling" is allowed when
    enforcing the conservation of mass law. They usually represent water
    intakes in a river (where water that is not extracted just keeps on
    flowing through the river) and actual sinks, such as an ocean or 
    lake (or any point after which the modeling of the hydraulic system
    is irrelevant for the power system).
    
    wnode_constant_inflow[wn] is the value of constant inflow of 
    water at each node of the hydraulic system throughout the whole 
    simulation. Inflow refers to an external source of water that comes 
    into the system at the water node, such as rainfall. Water flows
    that originate from an upstream model component, such as another water
    node or a reservoir, are decided by the model and so must not be
    specified here. This parameter is specified in cubic meters per second 
    (cumec) and defaults to 0.
    
    wnode_constant_consumption[wn] is the value of constant 
    consumption of water at each node of the hydraulic system throughout
    the whole simulation. Consumption refers to any activity that takes
    water out of the modeled hydraulic system, such as crop irrigation,
    human and animal consumption, minimum ecological flow for a sink
    node, etc. This parameter is specified in cubic meters per second 
    (cumec) and defaults to 0.
    
    wnode_tp_inflow[wn, t] and wnode_tp_consumption[wn, t]
    are the values of water inflow and consumption at each node of the
    hydraulic system specified at each timepoint. These are optional 
    parameters that default to wnode_constant_inflow_cumec and
    wnode_constant_consumption_cumec. Depending on data availability,
    these parameters may be used to represent different phenomena. In
    example, the Chilean datasets specify water inflows due to rainfall
    and melting snows at different nodes in a weekly basis. So, all
    simulated timepoints that belong to the same week will have the same
    wnode_tp_inflow_cumec parameter specified for each water node.
    
    SinkSpillage[(wn, t) for (wn, t) in WATER_SINKS_BALANCE_POINTS] are 
    the water spillage decisions at each water sink and timepoint, in 
    cubic meters per second.
    
    
    RESERVOIRS is the set of water reservoirs. These can be thought of as
    nodes where water may be stored, which requires additional 
    characterization. Members of this set may be abbreviated as r or res. 
    
    res_min_vol[r] is a parameter that specifies the minimum
    storage capacity of the reservoir in cubic meters. Usually this will
    be a positive value, since reservoirs cannot be completely emptied
    because of physical limitations, but it is allowed to be 0 in case
    relative volumes want to be used.
    
    res_max_vol[r] is a parameter that specifies the maximum
    storage capacity of the reservoir in cubic meters. If at any
    timepoint the volume of water in the reservoir reaches this limit,
    spillage may occur to mantain the mass balance. This parameter is
    determined by the physical characteristics of the reservoir.
    
    RESERVOIRS_BALANCE_POINTS is a set showing all the combinations of
    reservoirs and timepoints, in which the conservation of mass law 
    must be enforced. For now it is initialized as the cross product of
    the RESERVOIRS and TIMEPOINTS sets, but it should be flexibilized 
    to allow for addition and removal of reservoirs in intermediate
    timepoints of the simulation horizon.
    
    res_min_vol_tp[r, t] and res_max_vol_tp[r, t] are the
    values of allowable minimum and maximum water volume at each 
    reservoir specified at each timepoint. These may be used to represent
    seasonal restrictions in water levels at any reservoir. In example,
    minimum volumes of water must be kept during summer at some reservoirs
    to allow for leisure and tourism activities, such as water sports.
    These parameters are optional and must be specified in cubic meters 
    and default to reservoir_min_vol and reservoir_max_vol.
    
    initial_res_vol[r] is a parameter that states the starting volume
    of stored water in each reservoir. The same value will be used as
    a starting point in each period of the simulation, independent of
    which was the final level at the last timepoint of the previous period.
    This methodology has been used in several expansion planning papers 
    that include reservoir hydro power plants, because it allows decoupling
    the operational subproblems of each period and thus speeding up the
    optimization considerably.
    
    final_res_vol[r] is a parameter that states the final volume of stored
    water in each reservoir. This level is enforced as a minimum for the
    final volume. Usually, this parameter is specified to be the same as 
    the initial volume, so that the reservoir may only arbitrage with the
    water inflows that come into it during the period.
    
    res_tp_inflow[r, t] and res_tp_consumption[r, t] are
    parameters that specify the water inflow and consumption at each
    reservoir in cubic meters per second (cumec). These are indexed by
    timepoint and don't have a constant parameter to default to (they
    default to 0) like water nodes do.

    ReservoirInitialVol[r, t] and ReservoirFinalVol[r, t] are variables
    that determine the initial and final volumes of water at each reservoir
    at each timepoint, specified in cubic meters. These variables are
    determined by the water balance between inflows and outflows at each
    reservoir.
    
    Enforce_Res_Max_Vol[r, t] and Enforce_Res_Min_Vol[r, t] are constraints
    that enforce maximum and minimum volumes of each reservoir for each
    timepoint.
    
    
    WATER_CONNECTIONS is the set of flows that begin and end in different
    water bodies, such as reservoirs and nodes. The model decides how much
    water is "dispatched" through each connection at each timepoint. Water
    may only flow in one direction, so "to" and "from" parameters must be
    inputted. Members of this set may be abbreviated by wc or wcon.
    
    WATER_BODIES is the set resulting from the union of the RESERVOIRS set
    and the WATER_NODES set. It represents all locations that may be
    connected through a water connection.
    
    WCONS_DISPATCH_POINTS is the set of the cross product between 
    TIMEPOINTS and WATER_CONNECTIONS. In the future, this should be 
    flexibilized to allow for new water connections to be created within 
    the simulation horizon (as with WATER_NODES_BALANCE_POINTS and 
    RESERVOIRS_BALANCE_POINTS).
    
    water_body_from[wc] is a parameter that specifies the water body from
    which the connection extracts water.
    
    water_body_to[wc] is a parameter that specifies the water body to which 
    the connection injects water. 
    
    wc_capacity[wc] is a parameter that specifies the limit, in cubic
    meters per second, of the water flow through the connection. This
    datum is difficult to find, but could be relevant in some cases where
    rivers or streams have a defined capacity and greater flows could
    cause them to collapse and/or flood the surrounding area. Defaults
    to 9999 cumec.
    
    min_eco_flow[wc, t] is a parameter that indicates the minimum ecological 
    water flow that must be dispatched through each water connection at each 
    timepoint, specified in cubic meters per second. The parameter is
    indexed by timepoint to allow for representation of seasonal or hourly
    ecological or social constraints. This is an optional parameter that
    defaults to 0. 
    
    DispatchWater[wc, t] is a variable that represents how much water is
    flowing through each water connection at each timepoint. The lower bound is
    m.min_eco_flow[wc, t] and the upper bound is m.wc_capacity[wc].
    
    Enforce_Wnode_Balance[(wn, t) for (wn, t) in WATER_NODES_BALANCE_POINTS]
    is a constraint that enforces conservation of mass at water nodes. This
    accounts for any spills at sink nodes.
    
    Enforce_Reservoir_Balance[r, t] is the constraint that enforces the
    conservation of mass at each reservoir and timepoint, ensuring that
    if there is an imbalance between inflows and outflows to and from a
    reservoir in a timepoint, that will translate into a change in stored
    volume.
    
    Enforce_Reservoir_Vol_Links[r, t] is the constraint that links the
    final volume at each reservoir and timepoint with the initial volume
    at the next timepoint. The initial volume is forced to be equal to
    the initial_res_vol parameter.
    
    Enforce_Final_Vol_Condition[r] is the constraint that forces the
    final volume at each reservoir to be greater than or equal to the 
    final_res_vol parameter. This boundary condition is key to prevent
    an extreme use of water by the model. 
    
    
    HYDRO_PROJECTS is a subset of PROJECTS which are to be linked with the
    hydraulic system. Both reservoir generators as well as hydroelectric
    projects in series must be specified as HYDRO_PROJECTS and will be
    treated the same. Members of this set may be abbreviated as hproj.
    
    HYDRO_PROJ_DISPATCH_POINTS is a subset of PROJ_DISPATCH_POINTS only with
    projects that belong to the HYDRO_PROJECTS set. This set is used to
    index the electricity generation decisions.
    
    hydro_efficiency[hproj] is a parameter that specifies the "hydraulic
    efficiency" of a project, in units of MW/(cubic meters per second). 
    The amount of power generated by a hydroelectric generator with a 
    certain flow depends on the water head. This creates a non linear
    relationship between the generated power per water flow and the volume
    of stored water. In this module, the efficiency is assumed to be a
    constant for each project, to mantain linearity.
    
    hydraulic_location[hproj] is a parameter that specifies the water
    connection in which each hydro project is located. Multiple projects
    may be located at the same connection, which allows modeling of
    cascading generation.
    
    TurbinatedFlow[hproj, t] is a variable that represents the water flow, 
    in cubic meters per second, that is passed through the turbines of each 
    project at each timepoint. This is the flow that is used to generate
    electricity.
    
    SpilledFlow[hproj, t] is a variable that represents the water flow, 
    in cubic meters per second, that is spilled by each project at each
    timepoint. All spilled water is considered to be returned to the same
    water connection from which it was originally extracted. 
        
    Enforce_Hydro_Generation[hproj, t] is the constraint that forces power
    generation at each hydro project to be equal to the flow of water that
    goes through its turbines, times its hydro efficiency. This relation
    is observed at each timepoint.
    
    Enforce_Hydro_Extraction[hproj, t] is the constraint that mantains the
    conservation of mass at each project's water extraction point, so that
    the sum of the flows that go through its turbines and the one that is
    spilled are equal to the water that is flowing at each timepoint through
    the water connection where it is located.
    
    -----------------
    TODO:
    -Flexibilize definition of balance points for water nodes and reservoirs,
    as well as dispatch points for water connections, so that the hydraulic
    system topology may change during the simulation. This would allow
    representation of new connections and reservoirs that may be built.
    
    -Analyze the possibility of merging reservoirs and water nodes into
    a single set of objects. Reservoirs would just then be water nodes
    with the ability of storing water.
    
    -Check if it is faster to skip creation of constraints enforcing
    wcon maximum capacity and minimum ecological flow, or having them
    be created with the default parameters. I'm not sure if the savings
    in time of not creating the constraints and printing them to the LP file
    compensate the time spent checking if the constraint should or shouldn't
    be created.
    
    """
    
    #################
    # Nodes of the water network
    mod.WATER_NODES = Set()
    mod.WATER_NODES_BALANCE_POINTS = Set(
        dimen=2,
        initialize=lambda m: m.WATER_NODES * m.TIMEPOINTS)
    mod.wnode_constant_inflow = Param(
        mod.WATER_NODES,
        within=NonNegativeReals,
        default=0.0)
    mod.wnode_constant_consumption = Param(
        mod.WATER_NODES,
        within=NonNegativeReals,
        default=0.0)
    mod.wnode_tp_inflow = Param(
        mod.WATER_NODES_BALANCE_POINTS,
        within=NonNegativeReals,
        default=lambda m, wn, t: m.wnode_constant_inflow[wn])
    mod.wnode_tp_consumption = Param(
        mod.WATER_NODES_BALANCE_POINTS,
        within=NonNegativeReals,
        default=lambda m, wn, t: m.wnode_constant_consumption[wn])

    #################
    # Sink nodes
    mod.wn_is_sink = Param(
        mod.WATER_NODES,
        within=Boolean)
    mod.min_data_check('wn_is_sink')
    mod.WATER_SINKS_BALANCE_POINTS = Set(
        initialize=mod.WATER_NODES_BALANCE_POINTS,
        filter=lambda m, wn, t: m.wn_is_sink[wn])
    mod.SinkSpillage = Var(
        mod.WATER_SINKS_BALANCE_POINTS,
        within=NonNegativeReals)

    #################
    # Reservoir nodes
    mod.RESERVOIRS = Set()
    mod.res_min_vol = Param(
        mod.RESERVOIRS,
        within=NonNegativeReals)
    mod.res_max_vol = Param(
        mod.RESERVOIRS,
        within=PositiveReals,
        validate=lambda m, val, r: val >= m.res_min_vol[r])
    mod.RESERVOIRS_BALANCE_POINTS = Set(
        dimen=2,
        initialize=lambda m: m.RESERVOIRS * m.TIMEPOINTS)
    mod.res_min_vol_tp = Param(
        mod.RESERVOIRS_BALANCE_POINTS,
        within=NonNegativeReals,
        default=lambda m, r, t: m.res_min_vol[r])
    mod.res_max_vol_tp = Param(
        mod.RESERVOIRS_BALANCE_POINTS,
        within=NonNegativeReals,
        default=lambda m, r, t: m.res_max_vol[r])
    mod.initial_res_vol = Param(
        mod.RESERVOIRS,
        within=NonNegativeReals,
        validate=lambda m, val, r: (
            m.res_min_vol[r] <= val <= m.res_max_vol[r]))
    mod.final_res_vol = Param(
        mod.RESERVOIRS,
        within=NonNegativeReals,
        validate=lambda m, val, r: (
            m.res_min_vol[r] <= val <= m.res_max_vol[r]))
    mod.res_tp_inflow = Param(
        mod.RESERVOIRS_BALANCE_POINTS,
        within=NonNegativeReals,
        default=0.0)
    mod.res_tp_consumption = Param(
        mod.RESERVOIRS_BALANCE_POINTS,
        within=NonNegativeReals,
        default=0.0)    
    mod.min_data_check('res_min_vol', 'res_max_vol', 'initial_res_vol', 'final_res_vol')
    mod.ReservoirInitialVol = Var(
        mod.RESERVOIRS_BALANCE_POINTS,
        within=NonNegativeReals)
    mod.ReservoirFinalVol = Var(
        mod.RESERVOIRS_BALANCE_POINTS,
        within=NonNegativeReals)
    mod.Enforce_Res_Max_Vol = Constraint(
        mod.RESERVOIRS_BALANCE_POINTS,
        rule=lambda m, r, t: (
            m.ReservoirFinalVol[r, t] <= m.res_max_vol_tp[r, t]))
    mod.Enforce_Res_Min_Vol = Constraint(
        mod.RESERVOIRS_BALANCE_POINTS,
        rule=lambda m, r, t: (   
            m.ReservoirFinalVol[r, t] >= m.res_min_vol_tp[r, t]))    
    

    ################
    # Edges of the water network
    mod.WATER_CONNECTIONS = Set()
    mod.WATER_BODIES = Set(
        initialize=lambda m: m.WATER_NODES | m.RESERVOIRS)
    mod.WCONS_DISPATCH_POINTS = Set(
        dimen=2,
        initialize=lambda m: m.WATER_CONNECTIONS * m.TIMEPOINTS)    
    mod.water_body_from = Param(
        mod.WATER_CONNECTIONS, 
        within=mod.WATER_BODIES)
    mod.water_body_to = Param(
        mod.WATER_CONNECTIONS, 
        within=mod.WATER_BODIES)
    mod.wc_capacity = Param(
        mod.WATER_CONNECTIONS,
        within=PositiveReals,
        default=float('inf'))
    mod.min_eco_flow = Param(
        mod.WCONS_DISPATCH_POINTS,
        within=NonNegativeReals,
        default=0.0)    
    mod.min_data_check('water_body_from', 'water_body_to')
    mod.DispatchWater = Var(
        mod.WCONS_DISPATCH_POINTS,
        within=NonNegativeReals,
        bounds=lambda m, wc, t: (m.min_eco_flow[wc, t], m.wc_capacity[wc]))  

    def Enforce_Wnode_Balance_rule(m, wn, t):
        # Cache (inflow, outflow) for all nodes & timepoints in one pass
        if not hasattr(m, '_WaterNodeNet_dict'):
            m._WaterFlows_dict = {(wn2, t2): [0.0, 0.0] \
                                  for (wn2, t2) in m.WATER_NODES_BALANCE_POINTS}
            for wn2 in m.WATER_NODES:
                for wc in m.WATER_CONNECTIONS:
                    if m.water_body_to[wc] == wn2:
                        for t2 in m.TIMEPOINTS:
                            m._WaterFlows_dict[(wn2, t2)][0] += m.DispatchWater[wc, t2]
                    if m.water_body_from[wc] == wn2:
                        for t2 in m.TIMEPOINTS:
                            m._WaterFlows_dict[(wn2, t2)][1] += m.DispatchWater[wc, t2]
        # Use pop to free memory in each loop and delattr to clean up at the end
        [dispatch_inflow, dispatch_outflow] = m._WaterFlows_dict.pop((wn, t))
        if len(m._WaterFlows_dict.keys()) == 0:
            delattr(m, '_WaterFlows_dict')
        # Spill flows: 0 for non-sink nodes
        spill_outflow = 0.0
        if m.wn_is_sink[wn]:
            spill_outflow = m.SinkSpillage[wn, t]
        # Conservation of mass flow
        return (
            m.wnode_tp_inflow[wn, t] + dispatch_inflow == \
            m.wnode_tp_consumption[wn, t] + dispatch_outflow + spill_outflow)
    mod.Enforce_Wnode_Balance = Constraint(
        mod.WATER_NODES_BALANCE_POINTS,
        rule=Enforce_Wnode_Balance_rule)

    mod.Enforce_Reservoir_Balance = Constraint(
        mod.RESERVOIRS_BALANCE_POINTS,
        # Rule: timepoint_duration * Net_flow_rate = Change_in_volume
        rule=lambda m, r, t: (
            m.tp_duration_hrs[t] * 3600 * (
                m.res_tp_inflow[r, t] + 
                sum(m.DispatchWater[wc, t] for wc in m.WATER_CONNECTIONS 
                    if m.water_body_to[wc] == r) -
                sum( m.DispatchWater[wc, t] for wc in m.WATER_CONNECTIONS 
                    if m.water_body_from[wc] == r) -
                m.res_tp_consumption[r, t]
            ) == m.ReservoirFinalVol[r, t] - m.ReservoirInitialVol[r, t]))
    def Enforce_Reservoir_Vol_Links_rule(m, r, t):
        if not hasattr(m, '_first_tps_in_period'):
            m._first_tps_in_period = {p: [] for p in m.PERIODS}
            for ts in m.TIMESERIES:
                p = m.ts_period[ts]
                m._first_tps_in_period[p].append(m.TS_TPS[ts].first())
        tp_p = m.tp_period[t]
        if t == m.PERIOD_TPS[tp_p].first():
            # All reservoirs start with the specified initial volume
            return (m.ReservoirInitialVol[r, t] == m.initial_res_vol[r])
        elif (t in m._first_tps_in_period[tp_p] and 
                t != m.PERIOD_TPS[tp_p].first()):
            # If the timepoint is the first of a series, start with the
            # final volume of the previous series' last timepoint
            previous_ts = m.TIMESERIES.prev(m.tp_ts[t])
            previous_ts_last_tp = m.TS_TPS[previous_ts].last()
            return (m.ReservoirInitialVol[r, t] == 
                m.ReservoirFinalVol[r, previous_ts_last_tp])
        else:
            # In other cases, the initial volume will be equal to the
            # final volume of the previous timepoint
            return (m.ReservoirInitialVol[r, t] == 
                m.ReservoirFinalVol[r, m.tp_previous[t]])
    mod.Enforce_Reservoir_Vol_Links = Constraint(
        mod.RESERVOIRS_BALANCE_POINTS,
        rule=Enforce_Reservoir_Vol_Links_rule)
    mod.Enforce_Final_Vol_Condition = Constraint(
        mod.RESERVOIRS, mod.PERIODS,
        rule=lambda m, r, p: (m.final_res_vol[r] <= 
            m.ReservoirFinalVol[r, m.PERIOD_TPS[p].last()]))
    
    
    mod.HYDRO_PROJECTS = Set(
        validate=lambda m, val: val in m.PROJECTS)
    mod.HYDRO_PROJ_DISPATCH_POINTS = Set(
        initialize=mod.PROJ_DISPATCH_POINTS,
        filter=lambda m, proj, t: proj in m.HYDRO_PROJECTS)
    mod.hydro_efficiency = Param(
        mod.HYDRO_PROJECTS,
        within=PositiveReals,
        validate=lambda m, val, proj: val <= 10)
    mod.hydraulic_location = Param(
        mod.HYDRO_PROJECTS,
        validate=lambda m, val, proj: val in m.WATER_CONNECTIONS)
    mod.TurbinatedFlow = Var(
        mod.HYDRO_PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.SpilledFlow = Var(
        mod.HYDRO_PROJ_DISPATCH_POINTS,
        within=NonNegativeReals)
    mod.Enforce_Hydro_Generation = Constraint(
        mod.HYDRO_PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (m.DispatchProj[proj, t] ==
            m.hydro_efficiency[proj] * m.TurbinatedFlow[proj, t]))
    mod.Enforce_Hydro_Extraction = Constraint(
        mod.HYDRO_PROJ_DISPATCH_POINTS,
        rule=lambda m, proj, t: (m.TurbinatedFlow[proj, t] +
            m.SpilledFlow[proj, t] == 
            m.DispatchWater[m.hydraulic_location[proj], t]))



def load_inputs(mod, switch_data, inputs_dir):
    """
    
    Import hydro data to model hydroelectric projects in reservoirs and
    in series.
    
    The files water_nodes.tab, reservoirs.tab, water_connections.tab and 
    hydro_projects.tab are mandatory, since they specify the hydraulic 
    system's topology and basic characterization. 
    
    Files water_node_tp_flows, reservoir_tp_data.tab and min_eco_flows.tab
    are optional, since they specify information in a timepoint basis that
    has constant values to default to.
    
    Run-of-River hydro projects should not be included in this file; RoR
    hydro is treated like any other variable renewable resource, and
    which expects data in variable_capacity_factors.tab.
    
    """
    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'water_nodes.tab'),
        auto_select=True,
        index=mod.WATER_NODES,
        optional_params=['mod.wnode_constant_inflow',
            'mod.wnode_constant_consumption'],
        param=(mod.wn_is_sink, mod.wnode_constant_inflow, 
            mod.wnode_constant_consumption))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'water_node_tp_flows.tab'),
        auto_select=True,
        optional_params=['mod.wnode_tp_inflow', 'mod.wnode_tp_consumption'],
        param=(mod.wnode_tp_inflow, mod.wnode_tp_consumption))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'reservoirs.tab'),
        auto_select=True,
        index=mod.RESERVOIRS,
        param=(mod.res_min_vol, mod.res_max_vol, 
            mod.initial_res_vol, mod.final_res_vol))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'reservoir_tp_data.tab'),
        optional=True,
        auto_select=True,
        optional_params=['mod.res_tp_inflow', 'mod.res_tp_inflow_consumption', 
            'mod.res_max_vol_tp', 'mod.res_min_vol_tp'],
        param=(mod.res_tp_inflow, mod.res_tp_consumption, 
            mod.res_max_vol_tp, mod.res_min_vol_tp))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'water_connections.tab'),
        auto_select=True,
        index=mod.WATER_CONNECTIONS,
        param=(mod.water_body_from, mod.water_body_to, mod.wc_capacity))
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, 'min_eco_flows.tab'),
        auto_select=True,
        param=(mod.min_eco_flow))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'hydro_projects.tab'),
        auto_select=True,
        index=mod.HYDRO_PROJECTS,
        param=(mod.hydro_efficiency, mod.hydraulic_location))

