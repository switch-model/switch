SYNOPSIS
	switch solve --verbose --log-run

This example illustrates the use of the hydro_system module. The input set does not consider new investments; this is only a production costing example.

This module creates a hydraulic system parallel to the electric one. The hydro system consists in water nodes, where conservation of mass must be obeyed at every timepoint, and connections, that transport water between nodes. The two systems are linked at hydroelectric generators, where water flow is used to produce electricity.

Reservoir hydroelectric projects are treated as dispatchable generators.
Run of river projects located in hydro basins (located up or downstream
other hydro generators) are also treated as dispatchable generators. Their generation is constrained by the water flow through the location and by a hydraulic efficiency factor. Water that is not passed through the turbines may be spilled as desired to be used by downstream generators to produce electricity as well.

The system state -stored water volumes at each reservoir- is linked throughout all timepoints. Border conditions are implemented for the first and last timepoint of the time horizon to prevent excessive water usage.

Transit times for water flow are not implemented, so water dispatched from one node reaches the next node downstream at the next timepoint.

Hydraulic efficiencies are assumed to be constant values, which implies assuming that turbine efficiencies do not change with different flows and that the water head is constant.
