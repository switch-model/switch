SYNOPSIS
    python -m switch_mod.solve

This example illustrates the use of the hydro_system module.

This module creates a hydraulic system parallel to the electric one. In
the former, the conservation of mass law must be obeyed at every timepoint
and location. The module is flexible enough to model most hydraulic
phenomena.

Reservoir hydroelectric projects are treated as dispatchable generators.
Run of river projects located in hydro basins (located up or downstream
other hydro generators) are also treated as dispatchable generators. Their generation is constrained by the water flow through the location and by the 
efficiency of the generator, and treatment allows to spill as much water 
as is desired. Spilled water may be used by downstream generators to 
produce electricity.

All hydro basins must end in a sink node.
