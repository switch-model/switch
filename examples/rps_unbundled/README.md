SYNOPSIS
	switch solve --verbose

This example illustrates the use of Switch to construct and run a
model with three load zones and two investment periods where the first
investment period has more temporal resolution than the second. A
simple Renewable Portfolio Standard (RPS) policy is enforced with the
use of the generators.no_commit module.

This example is built on the same system as the 3zone_toy example.
It can be observed that more biomass (considered an RPS-elegible fuel
in this example) capacity is built on the first period to provide
enough renewable energy to meet the RPS goals.
