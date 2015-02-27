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
        * period_start[p]: The starting year of an investment period.
        * period_end[p]: The last year of an investment period.
        * period_length_years[p]: The number of years in an investment period; derived from period_start and period_end.
        * period_length_hours[p]: The number of hours in an investment period; derived from period_length_years with an average of 8766 hours per year. 
    
    DISPATCH_SCENARIOS is the set of conditions in which dispatch may occur within an investment period. Examples include low hydro, high hydro, El Nina, La Nina, etc. In the stochastic version of switch, each investment period may contain multiple dispatch scenarios. For ease of development, the scenarios are assumed to be human-readable text that are unique within a run such as low_hydro_2020 rather than database ids. 
    Related parameters that are indexed by dispatch scenario ds include:
        * scenario_period[ds]: The investment period of a dispatch scenario. 
        * scenario_dbid[ds]: The external database id for a dispatch scenario.
  
    TIMESERIES denote blocks of consecutive timepoints within a dispatch scenario. An individual time series could represent a single day, a week, a month or an entire year. This replaces the DATE construct in the old SWITCH code and is meant to be more versatile. TIMESERIES ids need to be unique across dispatch scenarios. 
    Related parameters indexed by ts in TIMESERIES include
        * ts_scenario[ts]: The dispatch scenario of a timeseries.
        * ts_num_tps[ts]: The number of timepoints in a timeseries.
        * ts_duration_of_tp[ts]: The duration in hours of each timepoint within a timeseries.
            This is used for calculations that ensure a storage project has a sufficient energy charge when it is dedicated to providing reserves.
        * ts_duration_hrs[ts]: The total duration of a timeseries in hours. 
            = ts_duration_of_tp[ts] * ts_num_tps[ts]
        * ts_scale_to_period[ts]: Scaling factor to adjust the weight from ts_duration_hrs up to a period. See examples below. 

    TIMEPOINTS describe unique timepoints within a time series and typically index exogenous variables such as electricity demand and variable renewable energy output. This replaces the HOURS construct in some of the old versions of SWITCH. Timepoints need ids that are unique across dispatch scenarios rather than a simple timestamp that may be replicated across dispatch scenarios. Timepoint ids should also indicate their relative ordering within a timeseries. Each timepoint within a series needs to have the same duration to simplify calculations. 
     Related parameters indexed by t in TIMEPOINTS include: 
        * tp_weight[t]: The weight of a timepoint within an investment period in units of hours per period. 
             = ts_duration_of_tp[ts] * ts_scale_to_period[ts]
        * tp_label[t]: These human-readable timestamp labels should be unique within a dispatch scenario. Expected format is YYYYMMDDHH
        * tp_scenario[t]: The dispatch scenario of this timepoint
        * tp_ts[t]: The timeseries of this timepoint

    Other indexed sets describe memberships of dispatch scenarios to investment periods, timeseries to dispatch scenarios, etc. These include:
        * PERIOD_SCENARIOS[period]: The set of dispatch scenarios in a period.
        * SCENARIO_TS[scenario]: The set of timeseries in a dispatch scenario.
        * TS_TPS[timeseries]: The ordered set of timepoints in a timeseries.
        * SCENARIO_TPS[scenario]: The set of timepoints in a dispatch scenario.
    
    Data validity check:
        Currently, the sum of tp_weight for all timepoints in a scenario must be within 1% of the expected length of the investment period period. Period length is calculated by multiplying the average number of hours in a year rounded to the nearest integer (8766) by the number of years per period. I implemented this rule because these are used as weights for variable costs of dispatch and operations, and I think it is important for those costs to reflect those expected costs over an entire period or else the levelized costs of power that is being optimized will not make sense. 


    EXAMPLES
    These hypothetical examples illustrate differential weighting of timepoints and timeseries. Each timepoint adds additional computational complexity, and you may wish to reduce the time resolution in low-stress periods and increase the time resolution in high-stress periods. These examples are probably not the resolutions you would choose, but are meant to illustrate calculations. When calculating these for your own models, you may check your caluclations by adding all of the tp_weights in a dispatch scenario and ensuring that it yields the number of hours you expect in an entire investment period. That weighting ensures an accurate depiction of fixed and variable costs. 

    Example 1: The month of January is described by two timeseries: one to represent a median load day (example 1) and one to represent a peak day (example 2). In these examples, the timeseries for the median load day has a much larger weight than the timeseries for the peak load day. 
    January median timeseries:
        A timeseries describing a median day in January is composed of 6 timepoints, each representing a 4-hour block. This is scaled up by factor of 30 to represent all but 1 day in January, then scaled up by a factor of 10 to represent all Januaries in a 10-year period. 
        * ts_num_tps = 6 tp/ts
        * ts_duration_of_tp = 4 hr/tp
        * ts_duration_hrs = 24 hr/ts 
            = 6 tp/ts * 4 hr/tp
        * ts_scale_to_period = 300 ts/period
            = 1 ts/24 hr * 24 hr/day * 30 day/yr * 10 yr/period
            24 hr/day is a conversion factor. 30 day/yr indicates this timeseries is meant to represent 30 days out of every year. If it represented every day in January instead of all but one day, this term would be 31 day/hr
        * tp_weight[t] = 1200 hr/period
            = 4 hr/tp * 1 tp/ts * 300 ts/period
    January peak timeseries: 
        This timeseries describing a peak day in January is also composed of 6 timepoints, each representing a 4-hour block. This is scaled up by factor of 1 to represent a single peak day of the month January, then scaled up by a factor of 10 to represent all peak January days in a 10-year period. 
        * ts_num_tps = 6 tp/ts
        * ts_duration_of_tp = 4 hr/tp
        * ts_duration_hrs = 24 hr/ts 
            = 6 tp/ts * 4 hr/tp
        * ts_scale_to_period = 10 ts/period
            = 1 ts/24 hr * 24 hr/day * 1 day/yr * 10 yr/period
            24 hr/day is a conversion factor. 1 day/yr indicates this timeseries is meant to represent a single day out of the year. 
        * tp_weight[t] = 40 hr/period
            = 4 hr/tp * 1 tp/ts * 10 ts/period

    Example 2: The month of July is described by one timeseries that represents an entire week because July is a high-stress period for the grid and needs more time resolution to capture capacity and storage requirements. 
        This timeseries describing 7 days in July is composed of 84 timepoints, each representing 2 hour blocks. These are scaled up to represent all 31 days of July, then scaled by another factor of 10 to represent a 10-year period. 
        * ts_num_tps = 84 tp/ts
        * ts_duration_of_tp = 2 hr/tp
        * ts_duration_hrs = 168 hr/ts
            = 84 tp/ts * 2 hr/tp
        * ts_scale_to_period = 44.29 ts/period
            = 1 ts/168 hr * 24 hr/day * 31 days/yr * 10 yr/period
            24 hr/day is a conversion factor. 31 day/yr indicates this timeseries is meant to represent 31 days out of every year (31 days = duration of July). 
        * tp_weight[t] = 88.58 hr/period
            = 2 hr/tp * 1 tp/ts * 44.29 ts/period

    Example 3: The windy season of March & April are described with a single timeseries spanning 3 days because this is a low-stress period on the grid with surplus wind power and frequent curtailments. 
        This timeseries describing 3 days in Spring is composted of 72 timepoints, each representing 1 hour. The timeseries is scaled up by a factor of 21.3 to represent the 61 days of March and April, then scaled by another factor of 10 to represent a 10-year period. 
        * ts_num_tps = 72 tp/ts
        * ts_duration_of_tp = 1 hr/tp
        * ts_duration_hrs = 72 hr/ts
            = 72 tp/ts * 1 hr/tp
        * ts_scale_to_period = 203.3 ts/period
            = 1 ts/72 hr * 24 hr/day * 61 days/yr * 10 yr/period
            24 hr/day is a conversion factor. 6a day/yr indicates this timeseries is meant to represent 61 days out of every year (31 days in March + 30 days in April).
        * tp_weight[t] = 203.3 hr/period
            = 1 hr/tp * 1 tp/ts * 203.3 ts/period

    """

    # Investment Periods table has columns: period, period_length_years, period_start, period_end
    switch.INVEST_PERIODS = Set(ordered=True)
    switch.period_start = Param(switch.INVEST_PERIODS, within=PositiveReals)
    switch.period_end = Param(switch.INVEST_PERIODS, within=PositiveReals)
    switch.period_length_years = Param(switch.INVEST_PERIODS, within=PositiveReals,
        initialize=lambda mod, p: mod.period_end[p] - mod.period_start[p] + 1)
    switch.period_length_hours = Param(switch.INVEST_PERIODS, within=PositiveReals,
        initialize=lambda mod, p: mod.period_length_years[p] * 8766)

    # Dispatch scenarios table has columns: dispatch scenario, period, scenario_dbid
    switch.DISPATCH_SCENARIOS = Set() 
    switch.scenario_period = Param(switch.DISPATCH_SCENARIOS, 
        within=switch.INVEST_PERIODS)
    switch.scenario_dbid = Param(switch.DISPATCH_SCENARIOS, 
        within=PositiveIntegers)

    # Timeseries table has columns: timeseries, dispatch scenario, ts_duration_of_tp, ts_num_tps, ts_scale_to_period. The last parameter is used to double-check the timepoints table
    switch.TIMESERIES = Set()
    switch.ts_scenario = Param(switch.TIMESERIES, within=switch.DISPATCH_SCENARIOS)
    switch.ts_duration_of_tp = Param(switch.TIMESERIES, within=PositiveReals)
    switch.ts_num_tps = Param(switch.TIMESERIES, within=PositiveIntegers)
    switch.ts_scale_to_period = Param(switch.TIMESERIES, within=PositiveReals)
    switch.ts_duration_hrs = Param(switch.TIMESERIES, 
        initialize=lambda mod, ts: mod.ts_num_tps[ts] * mod.ts_duration_of_tp[ts] )

    # Timepoints table has columns: timepoint_id, timepoint_label, timeseries    
    switch.TIMEPOINTS = Set()
    switch.tp_label = Param(switch.TIMEPOINTS)
    switch.tp_ts = Param(switch.TIMEPOINTS, within=switch.TIMESERIES)
    switch.tp_scenario = Param(switch.TIMEPOINTS, within=switch.DISPATCH_SCENARIOS,
        initialize=lambda mod,t: mod.ts_scenario[mod.tp_ts[t]])
    switch.tp_weight = Param(switch.TIMEPOINTS, within=PositiveReals,
        initialize=lambda mod, t: 
            mod.ts_duration_of_tp[mod.tp_ts[t]] * mod.ts_scale_to_period[mod.tp_ts[t]] )

    ############################################################
    # "Helper" sets that are indexed for convenient look-up. 
    # I can't use the filter option to construct these because 
    # filter isn't currently implemented for indexed sets. 

    switch.SCENARIO_TS = Set(switch.DISPATCH_SCENARIOS, ordered=True, within=switch.TIMESERIES, 
        initialize=lambda mod, ds: 
            set(ts for ts in mod.TIMESERIES if mod.ts_scenario[ts] == ds))
    switch.TS_TPS = Set(switch.TIMESERIES, ordered=True, within=switch.TIMEPOINTS, 
        initialize=lambda mod, ts: 
            set(t for t in mod.TIMEPOINTS if mod.tp_ts[t] == ts))
    switch.SCENARIO_TPS = Set(switch.DISPATCH_SCENARIOS, within=switch.TIMEPOINTS, 
        ordered=True,
        initialize=lambda mod, ds:
            set(t for t in mod.TIMEPOINTS if mod.tp_scenario[t] == ds))
    switch.PERIOD_SCENARIOS = Set(switch.INVEST_PERIODS, within=switch.DISPATCH_SCENARIOS, 
        initialize=lambda mod, p:
            [s for s in mod.DISPATCH_SCENARIOS if mod.scenario_period[s] == p])

 
    # Validate time weights: Total timepoint weights in a scenario must be within 1% of the expected length of the period
    def validate_time_weights_rule (mod):
        for ds in mod.DISPATCH_SCENARIOS:
            expected_hours = mod.period_length_hours[mod.scenario_period[ds]]
            # If I use the indexed set SCENARIO_TPS for this sum, I get an error "ValueError: Error retrieving component SCENARIO_TPS[high_hydro_2020]: The component has not been constructed"
            # hours_in_scenario = sum(mod.tp_weight[t] for t in switch.SCENARIO_TPS[s])
            # Filtering the set TIMEPOINTS like I do when I create SCENARIO_TPS avoids this problem. So does defining this rule after I have created an instance from a .dat file. 
            hours_in_scenario = sum(mod.tp_weight[t] for t in mod.TIMEPOINTS if mod.tp_scenario[t] == ds)
            if (hours_in_scenario > 1.01 * expected_hours or
                hours_in_scenario < 0.99 * expected_hours):
                print "validate_time_weights_rule failed for dispatch scenario '{ds:s}'. The number of hours in the period is {period_h:0.2f}, but the number of hours in the scenario is {ds_h:0.2f}.\n".format(ds=ds, period_h=expected_hours, ds_h=hours_in_scenario)
                return 0
        return 1
    switch.validate_time_weights = BuildCheck(rule=validate_time_weights_rule)
    