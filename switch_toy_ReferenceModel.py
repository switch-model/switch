#!/usr/local/bin/python

# Simple multi-period investment & dispatch toy switch..
# Investments must be made before the start of each period
# Each investment plan must satisfy multiple dispatch scenarios
# For simplicity, each dispatch scenario is a few timepoints scaled up to represent an entire year

from coopr.pyomo import *
switch = AbstractModel()

# INVEST_PERIODS is the set of multi-year periods describing the timescale of investment decisions. 
switch.INVEST_PERIODS = Set(ordered=True)

switch.period_length_years = Param(switch.INVEST_PERIODS, within=PositiveReals)
switch.period_start = Param(switch.INVEST_PERIODS, within=PositiveReals)
switch.period_end = Param(switch.INVEST_PERIODS, within=PositiveReals)


# DISPATCH_SCENARIOS is the set of conditions in which dispatch may occur within an investment period. Examples include low hydro, high hydro, El Nina, La Nina, etc. In the stochastic version of the switch, each investment period may contain multiple dispatch scenarios. For ease of development, the scenarios are assumed to be human-readable text that are unique within a run such as low_hydro_2020 rather than database ids. 
switch.DISPATCH_SCENARIOS = Set() 
switch.period_of_scenario = Param(switch.DISPATCH_SCENARIOS, within=switch.INVEST_PERIODS)
switch.dbid_of_scenario = Param(switch.DISPATCH_SCENARIOS, within=PositiveIntegers)

# TIMEPOINTS within dispatch don't have an inherent ordering except within a timeseries within a dispatch scenario. Timepoints need ids that are unique across dispatch scenarios rather than a simple timestamp that may be replicated across dispatch scenarios. The ids of timepoints should also indicate the ordering within their timeseries.
switch.TIMEPOINTS = Set()
switch.timepoint_weight_in_hours = Param(switch.TIMEPOINTS, within=NonNegativeReals)

# timepoint_label[t] = YYYYMMDDHH
# These human-readable timestamp label should be unique within a dispatch scenario. 
switch.timepoint_label = Param(switch.TIMEPOINTS, within=PositiveIntegers)

# scenario_of_timepoint[t] = [scenario this timepoint belongs to]
switch.scenario_of_timepoint = Param(switch.TIMEPOINTS, within=switch.DISPATCH_SCENARIOS)

# timeseries_of_timepoint[t] = [timeseries this timepoint belongs to]
switch.timeseries_of_timepoint = Param(switch.TIMEPOINTS)

# TIMESERIES denote blocks of consecutive timepoints within a dispatch scenario. 
# TIMESERIES replaces the DATE construct in the old SWITCH code and is meant to be more versatile. A TIMESERIES could represent a single day or an entire month. TIMESERIES ids need to be unique across dispatch scenarios. 
def init_TIMESERIES (switch):
  return set(switch.timeseries_of_timepoint[t] for t in switch.TIMEPOINTS)
switch.TIMESERIES = Set( initialize=init_TIMESERIES) 

# scenario_of_timeseries[timeseries] = [dispatch scenario that timeseries belongs to]
def init_scenario_of_timeseries (switch, timeseries):
  for t in switch.TIMEPOINTS:
    if switch.timeseries_of_timepoint[t] == timeseries:
      return switch.scenario_of_timepoint[t]
switch.scenario_of_timeseries = Param(switch.TIMESERIES, within=switch.DISPATCH_SCENARIOS, initialize=init_scenario_of_timeseries)


####################
# "Helper" sets that are indexed for convenient look-up

# switch.TIMESERIES_IN_SCENARIO[scenario] = [set of timeseries within that scenario]
def init_TIMESERIES_IN_SCENARIO (switch, scenario):
  return set(ts for ts in switch.TIMESERIES if switch.scenario_of_timeseries[ts] == scenario)
switch.TIMESERIES_IN_SCENARIO = Set(switch.DISPATCH_SCENARIOS, ordered=True, within=switch.TIMESERIES, initialize=init_TIMESERIES_IN_SCENARIO)

# switch.TIMEPOINTS_IN_TIMESERIES[timeseries] = [ordered set of timepoints within that timeseries]
def init_TIMEPOINTS_IN_TIMESERIES (switch, timeseries):
  return (t for t in switch.TIMEPOINTS if switch.timeseries_of_timepoint[t] == timeseries)
switch.TIMEPOINTS_IN_TIMESERIES = Set(switch.TIMESERIES, ordered=True, \
  within=switch.TIMEPOINTS, initialize=init_TIMEPOINTS_IN_TIMESERIES)

# switch.TIMEPOINTS_IN_SCENARIO[scenario] = [set of timepoints in that dispatch scenario]
def init_TIMEPOINTS_IN_SCENARIO (switch, scenario):
  return (t for t in switch.TIMEPOINTS if switch.scenario_of_timepoint[t] == scenario)
switch.TIMEPOINTS_IN_SCENARIO = Set(switch.DISPATCH_SCENARIOS, within=switch.TIMEPOINTS, initialize=init_TIMEPOINTS_IN_SCENARIO)

# switch.DISPATCH_SCENARIOS_IN_PERIOD[period] = [set of dispatch scenarios within that period]
def init_DISPATCH_SCENARIOS_IN_PERIOD (switch, period):
  return (s for s in switch.DISPATCH_SCENARIOS if switch.period_of_scenario[s] == period)
switch.DISPATCH_SCENARIOS_IN_PERIOD = Set(switch.INVEST_PERIODS, within=switch.DISPATCH_SCENARIOS, initialize=init_DISPATCH_SCENARIOS_IN_PERIOD)

# Validate time weights: Total timepoint weights in a scenario must be within 1% of the expected length of the period
def init_hours_in_scenario (switch, scenario):
  return sum( switch.timepoint_weight_in_hours[t] for t in switch.TIMEPOINTS_IN_SCENARIO[scenario])
def validate_hours_in_scenario (switch, hours_in_scenario, scenario):
  expected_hours_in_period = switch.period_length_years[switch.period_of_scenario[scenario]] * 8766.0
  return (hours_in_scenario < 1.01 * expected_hours_in_period and hours_in_scenario > 0.99 * expected_hours_in_period)
switch.hours_in_scenario = Param(switch.DISPATCH_SCENARIOS, initialize=init_hours_in_scenario, validate=validate_hours_in_scenario)

# def InvestCostRule(switch):
#     return sum(
#       switch.fixed_cost_per_mw_h_gas * switch.BuildGas 
#       + switch.variable_cost_per_mwh_gas * switch.DispatchGas[h]
#       + switch.carbon_cost_per_mwh_gas * switch.DispatchGas[h]
#       + sum(switch.fixed_cost_per_mw_h_re[t] * switch.BuildRE[t, s] for (t, s) in switch.RE_PROJECTS)
#       for h in switch.HOURS)
# 
# def DispatchCostRule(switch):
#     return sum(
#       switch.fixed_cost_per_mw_h_gas * switch.BuildGas 
#       + switch.variable_cost_per_mwh_gas * switch.DispatchGas[h]
#       + switch.carbon_cost_per_mwh_gas * switch.DispatchGas[h]
#       + sum(switch.fixed_cost_per_mw_h_re[t] * switch.BuildRE[t, s] for (t, s) in switch.RE_PROJECTS)
#       for h in switch.HOURS)
# 
# switch_toy_model.TotalCost = Objective(rule=PowerCostRule, sense=minimize)

instance = switch.create('timescale_test.dat')
instance.pprint()
