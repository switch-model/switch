SYNOPSIS
	switch solve --verbose --log-run

This example illustrates the use of using the hydro_simple module. 

Reservoir hydro (or hydro for short) is treated as a dispatchable
resource with the added constraints of maintaining minimum run levels
for every timepoint (for streamflow) and average run levels over the
course of each timeseries. Both minimum and average levels are defined
per timeseries.

Run of river hydro (or RoR for short) is treated as any other variable
renewable resource, with capacity factors defined for each timepoint.
