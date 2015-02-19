"""
timescales.py
Defines timescales for investment and dispatch for the SWITCH model.

SYNOPSIS
>>> from coopr.pyomo import *
>>> from timescales import *
>>> switch_model = AbstractModel()
>>> define_timescales(switch_model)
>>> switch_instance = switch_model.create('test_dat/timescale_test_valid.dat')

Note, this can be tested with `python -m doctest -v timescales.py`
"""
from coopr.pyomo import *

def define_timescales(switch):
    """
    Augments a Pyomo abstract model object with sets and parameters that describe timescales of investment and dispatch decisions.
        
    INVEST_PERIODS is the set of multi-year periods describing the timescale of investment decisions.
    Related parameters that are indexed by period p include:
        * period_length_years[p]
        * period_start[p]
        * period_end[p]
    
    DISPATCH_SCENARIOS is the set of conditions in which dispatch may occur within an investment period. Examples include low hydro, high hydro, El Nina, La Nina, etc. In the stochastic version of switch, each investment period may contain multiple dispatch scenarios. For ease of development, the scenarios are assumed to be human-readable text that are unique within a run such as low_hydro_2020 rather than database ids. 
    Related parameters that are indexed by scenario s include:
        * period_of_scenario[s]
        * dbid_of_scenario[s] describes the external database id for a dispatch scenario
        * hours_in_scenario[s] = [Sum of weights of all timepoints within a scenario]
            Currently, the hours_in_scenario must be within 1% of the expected length of the period. Period length is calculated by multiplying the average number of hours in a year rounded to the nearest integer (8766) by the number of years per period. I implemented this rule because these are used as weights for variable costs of dispatch and operations, and I think it is important for those costs to reflect those expected costs over an entire period or else the levelized costs of power that is being optimized will not make sense. 
 
    TIMESERIES denote blocks of consecutive timepoints within a dispatch scenario. An individual time series could represent a single day, a week, a month or an entire year. This replaces the DATE construct in the old SWITCH code and is meant to be more versatile. TIMESERIES ids need to be unique across dispatch scenarios. 
    Related parameters indexed by TIMESERIES include
        * scenario_of_timeseries[timeseries] = [dispatch scenario that timeseries belongs to]
    
    TIMEPOINTS describe unique timepoints within a time series and typically index exogenous variables such as electricity demand and variable renewable energy output. This replaces the HOURS construct in some of the old versions of SWITCH. Timepoints need ids that are unique across dispatch scenarios rather than a simple timestamp that may be replicated across dispatch scenarios. Timepoint ids should also indicate their relative ordering within a timeseries.
    Related parameters indexed by timepoint t include:
        * timepoint_weight_in_hours[t] The "weight" of a timepoint within an investment period in units of hours
        * timepoint_label[t] = YYYYMMDDHH These human-readable timestamp label should be unique within a dispatch scenario
        * scenario_of_timepoint[t] = [scenario this timepoint belongs to]
        * timeseries_of_timepoint[t] = [timeseries this timepoint belongs to]
    
    Other indexed sets describe memberships of dispatch scenarios to investment periods, timeseries to dispatch scenarios, etc.    These include:
        * DISPATCH_SCENARIOS_IN_PERIOD[period] = [set of dispatch scenarios within that period]
        * TIMESERIES_IN_SCENARIO[scenario] = [set of timeseries within that scenario]
        * TIMEPOINTS_IN_TIMESERIES[timeseries] = [ordered set of timepoints within that timeseries]
        * TIMEPOINTS_IN_SCENARIO[scenario] = [set of timepoints in that dispatch scenario]
    
    """

    switch.INVEST_PERIODS = Set(ordered=True)
    switch.period_length_years = Param(switch.INVEST_PERIODS, 
        within=PositiveReals)
    switch.period_start = Param(switch.INVEST_PERIODS, within=PositiveReals)
    switch.period_end = Param(switch.INVEST_PERIODS, within=PositiveReals)

    switch.DISPATCH_SCENARIOS = Set() 
    switch.period_of_scenario = Param(switch.DISPATCH_SCENARIOS, 
        within=switch.INVEST_PERIODS)
    switch.dbid_of_scenario = Param(switch.DISPATCH_SCENARIOS, 
        within=PositiveIntegers)

    """
    Most of the primary data will come from an extensive timepoints table.
    Timeseries, scenarios and their memberships will be derived from this data.
    Currently, the code does not validate data integrity of timeseries and 
    and scenarios
    """
    switch.TIMEPOINTS = Set()
    switch.timepoint_weight_in_hours = Param(switch.TIMEPOINTS, 
        within=NonNegativeReals)
    switch.timepoint_label = Param(switch.TIMEPOINTS, within=PositiveIntegers)
    switch.scenario_of_timepoint = Param(switch.TIMEPOINTS, 
        within=switch.DISPATCH_SCENARIOS)
    switch.timeseries_of_timepoint = Param(switch.TIMEPOINTS)

    def init_TIMESERIES (switch):
        return set(switch.timeseries_of_timepoint[t] for t in switch.TIMEPOINTS)
    switch.TIMESERIES = Set( initialize=init_TIMESERIES) 

    def init_scenario_of_timeseries (switch, timeseries):
        for t in switch.TIMEPOINTS:
            if switch.timeseries_of_timepoint[t] == timeseries:
                return switch.scenario_of_timepoint[t]
    switch.scenario_of_timeseries = Param(switch.TIMESERIES, 
        within=switch.DISPATCH_SCENARIOS, 
        initialize=init_scenario_of_timeseries)

    # I may need to define period_of_timeseries at some point, but it doesn't look like I need it for now. 

    ####################
    # "Helper" sets that are indexed for convenient look-up

    def init_TIMESERIES_IN_SCENARIO (switch, scenario):
        return set(ts for ts in switch.TIMESERIES if switch.scenario_of_timeseries[ts] == scenario)
    switch.TIMESERIES_IN_SCENARIO = Set(switch.DISPATCH_SCENARIOS, 
        ordered=True, within=switch.TIMESERIES, 
        initialize=init_TIMESERIES_IN_SCENARIO)

    def init_TIMEPOINTS_IN_TIMESERIES (switch, timeseries):
        return (t for t in switch.TIMEPOINTS if switch.timeseries_of_timepoint[t] == timeseries)
    switch.TIMEPOINTS_IN_TIMESERIES = Set(switch.TIMESERIES, ordered=True, 
        within=switch.TIMEPOINTS, initialize=init_TIMEPOINTS_IN_TIMESERIES)

    def init_TIMEPOINTS_IN_SCENARIO (switch, scenario):
        return (t for t in switch.TIMEPOINTS if switch.scenario_of_timepoint[t] == scenario)
    switch.TIMEPOINTS_IN_SCENARIO = Set(switch.DISPATCH_SCENARIOS, 
        within=switch.TIMEPOINTS, initialize=init_TIMEPOINTS_IN_SCENARIO)

    def init_DISPATCH_SCENARIOS_IN_PERIOD (switch, period):
        return (s for s in switch.DISPATCH_SCENARIOS if switch.period_of_scenario[s] == period)
    switch.DISPATCH_SCENARIOS_IN_PERIOD = Set(switch.INVEST_PERIODS, 
        within=switch.DISPATCH_SCENARIOS, 
        initialize=init_DISPATCH_SCENARIOS_IN_PERIOD)

    def init_hours_in_scenario (switch, scenario):
        return sum(switch.timepoint_weight_in_hours[t] for t in switch.TIMEPOINTS_IN_SCENARIO[scenario])
    # Validate time weights: Total timepoint weights in a scenario must be within 1% of the expected length of the period
    def validate_hours_in_scenario (switch, hours_in_scenario, scenario):
        p = switch.period_of_scenario[scenario]
        expected_hours_in_period = switch.period_length_years[p] * 8766
        return (hours_in_scenario < 1.01 * expected_hours_in_period and 
                hours_in_scenario > 0.99 * expected_hours_in_period)
    switch.hours_in_scenario = Param(switch.DISPATCH_SCENARIOS, 
        initialize=init_hours_in_scenario, 
        validate=validate_hours_in_scenario)
