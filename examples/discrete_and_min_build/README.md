SYNOPSIS
	switch solve --verbose --log-run

This example illustrates the use of Switch to construct and run a very
simple model with a single load zone, one investment period, and two
timepoints. Minimum capacity builds are implemented, as well as discrete
builds according to unit size. This result is less optimal than the
discrete_build example, since at least 5 NG_CC units must be built when
the model wants to invest in that technology.
