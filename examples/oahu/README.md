SYNOPSIS
	switch solve --verbose --log-run

This example illustrates a fairly full-featured capacity expansion model, 
using a number of optional modules from the main switch package, as well
as many modules that have been added to the Hawaii regional package 
(some of these will eventually migrate to the main switch_mod package). 

This is based on the "tiny" version of the "main" Switch-Hawaii model
(2 periods, 1 day per period, 8 hours per day). The full version
of this model can be found at http://github.com/switch-hawaii/main.

Features of this model include:

- spinning reserves (n-1 contingencies plus regulating reserves for 
  renewables) 
- complex fuel markets and the option of expanding these markets
- discrete construction of thermal power plants
- a renewable portfolio standard (RPS)
- complex commitment and dispatch rules for a cogen combined-cycle
  plant (Kalaeloa)
- complex rules for conversion of certain plants to liquified
  natural gas (LNG)
- scheduling the charging of electric vehicles (EVs) and accounting
  for the cost of these vehicles vs. internal combusion vehicles
- a simple pumped-hydro storage facility
- a simple model of lithium-ion batteries with fixed calendar life
  (allowing one cycle per day)
- the option of installing and operating long-term hydrogen 
  electricity storage
- a simple demand-response model (rescheduling a fixed percentage
  of load to any time of day)
- flexible supply and demand components are smoothed out during
  a post-solve step, to avoid "jumpy" charging patterns
- hawaii-specific result reporting
- uses settings stored in modules.txt, options.txt and iterate.txt 
  in the main directory (not an inputs subdir)
  
  