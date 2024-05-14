SYNOPSIS
	switch solve --verbose --log-run

These examples illustrate the use of the
`switch_model.generators.extensions.hydro_system module`. The input sets do not
consider new investments; these are only a production costing examples. Hydro
data are provided in `water_nodes.csv`, `water_connections.csv`,
`hydro_generation_projects.csv`, `water_node_tp_flows.csv`, `reservoirs.csv`,
`reservoir_ts_data.csv`, `spillage_penalty.csv` and `gen_info.csv` (standard
generator info plus `gen_storage_efficiency` column for pumped storage). If
using pumped storage hydro, you should also add
`switch_model.generators.extensions.storage` somewhere above
`switch_model.generators.extensions.hydro_system` in `modules.txt`.

The hydro_system module creates a hydraulic system parallel to the electric one.
The hydro system consists of water nodes and connections that transport water
between nodes. There may also be a reservoir at each node. Switch optimizes
water flows through the network, including in and out of reservoirs, subject to
conservation of mass at each node, exogenous water inflows and consumption at
each node, minimum and maximum levels for each reservoir and minimum and maximum
flows through each connection. All flows are specified in cubic meters per
second and reservoir levels are specified in millions of cubic meters.

The water and electric systems are linked by hydroelectric generators attached
to water connections, where water flow is used to produce electricity. The
connection is often a dam downstream of a reservoir, and flow through the dam is
controlled as needed to produce electricity. Alternatively, the connection can
be a waterway with no reservoir nearby, in which case electric production is
restricted by flows from further upstream. Hydroelectric projects with no
reservoirs between them experience the same water flow in series. This can occur
either if they are on the same connection or along a series of connections with
no reservoirs at the nodes in between.

Hydroelectric generators are treated as dispatchable generators. Their
generation is constrained by the water flow through the location and by a
hydraulic efficiency factor (MW produced per m3/s of flow). Water that is not
passed through the turbines may be spilled as desired to be used by downstream
generators to produce electricity as well.

Hydroelectric projects can also be designated as providing pumped storage, in
which case they can pump water from the node below the dam to the one above it
with the specified round-trip efficiency.

The system state - water volume in each reservoir - is linked through all
timepoints in each timeseries. Border conditions are implemented for the first
and last timepoint of each timeseries to prevent excessive water usage.

Transit times for water flow are not implemented, so water dispatched from one
node reaches the next node downstream at the next timepoint.

Hydraulic efficiencies are assumed to be constant values, which assumes that
turbine efficiencies do not change with different flows and that the water head
is constant.

See the code of the `switch_model.generators.extensions.hydro_system` module for
more complete documentation.