"""
Defines timescales for investment and dispatch for the SWITCH-Pyomo model.
This code can be tested with `python -m doctest -v timescales.py`

SYNOPSIS
>>> from pyomo.environ import *
>>> import timescales

Switch-pyomo is licensed under Apache License 2.0 More info at switch-model.org
"""

import os
from pyomo.environ import *
import utilities

hours_per_year = 8766


def define_components(mod):
    """
    Augments a Pyomo abstract model object with sets and parameters that
    describe timescales of investment and dispatch decisions.

    INVEST_PERIODS is the set of multi-year periods describing the
    timescale of investment decisions.

    Related parameters that are indexed by period p include:
    * period_start[p]: The starting year of an investment period.
    * period_end[p]: The last year of an investment period.
    * period_length_years[p]: The number of years in an investment
      period; derived from period_start and period_end.
    * period_length_hours[p]: The number of hours in an investment
      period; derived from period_length_years with an average of
      8766 hours per year.

    TIMESERIES denote blocks of consecutive timepoints within a period.
    An individual time series could represent a single day, a week, a
    month or an entire year. This replaces the DATE construct in the old
    SWITCH code and is meant to be more versatile. TIMESERIES ids need
    to be unique across different periods.

    Related parameters indexed by ts in TIMESERIES include:
    * ts_period[ts]: The period a timeseries falls in.
    * ts_num_tps[ts]: The number of timepoints in a timeseries.
    * ts_duration_of_tp[ts]: The duration in hours of each timepoint
      within a timeseries. This is used for calculations that ensure a
      storage project has a sufficient energy charge when it is
      dedicated to providing reserves.
    * ts_duration_hrs[ts]: The total duration of a timeseries in hours.
        = ts_duration_of_tp[ts] * ts_num_tps[ts]
    * ts_scale_to_period[ts]: Scaling factor to adjust the weight from
      ts_duration_hrs up to a period. See examples below.

    TIMEPOINTS describe unique timepoints within a time series and
    typically index exogenous variables such as electricity demand and
    variable renewable energy output. The duration of a timepoint is
    typically on the order of one or more hours, so costs associated
    with timepoints are specified in hourly units, and the weights of
    timepoints are specified in units of hours. TIMEPOINTS replaces the
    HOURS construct in some of the old versions of SWITCH. Timepoints
    need ids that are unique across periods. Timepoint ids should also
    indicate their relative ordering within a timeseries. Each timepoint
    within a series needs to have the same duration to simplify
    calculations.

    Related parameters indexed by t in TIMEPOINTS include:
    * tp_weight[t]: The weight of a timepoint within an investment
      period in units of hours per period.
         = ts_duration_of_tp[ts] * ts_scale_to_period[ts]
    * tp_weight_in_year[t]: The weight of a timepoint within a year
      in units of hours per year.
         = tp_weight[t] / period_length_years[p]
    * tp_label[t]: These human-readable timestamp labels should be
      unique within a single period. Expected format is YYYYMMDDHH
    * tp_ts[t]: This timepoint's timeseries.
    * tp_period[t]: This timepoint's period.

    Other indexed sets list timepoints within each timeseries or
    period. These include:
    * PERIOD_TPS[period]: The set of timepoints in a period.
    * TS_TPS[timeseries]: The ordered set of timepoints in a timeseries.

    Data validity check:
    Currently, the sum of tp_weight for all timepoints in a period
    must be within 1 percent of the expected length of the investment
    period period. Period length is calculated by multiplying the
    average number of hours in a year rounded to the nearest integer
    (8766) by the number of years per period. I implemented this rule
    because these are used as weights for variable costs of dispatch and
    operations, and I think it is important for those costs to reflect
    those expected costs over an entire period or else the levelized
    costs of power that is being optimized will not make sense.


    EXAMPLES

    These hypothetical examples illustrate differential weighting of
    timepoints and timeseries. Each timepoint adds additional
    computational complexity, and you may wish to reduce the time
    resolution in low-stress periods and increase the time resolution in
    high-stress periods. These examples are probably not the resolutions
    you would choose, but are meant to illustrate calculations. When
    calculating these for your own models, you may check your
    calculations by adding all of the tp_weights in a period and
    ensuring that it is equal to the length of the period in years times
    8766, the average number of hours per year. That weighting ensures
    an accurate depiction of variable costs and dispatch relative to
    fixed costs such as capital. This check is also performed when
    loading a model and will generate an error if the sum of weights of
    all timepoints in a period are more than 1 percent different than
    the expected number of hours.

    Example 1: The month of January is described by two timeseries: one
    to represent a median load day (example 1) and one to represent a
    peak day (example 2). In these examples, the timeseries for the
    median load day has a much larger weight than the timeseries for the
    peak load day.

    January median timeseries: A timeseries describing a median day in
    January is composed of 6 timepoints, each representing a 4-hour
    block. This is scaled up by factor of 30 to represent all but 1 day
    in January, then scaled up by a factor of 10 to represent all
    Januaries in a 10-year period.
    * ts_num_tps = 6 tp/ts
    * ts_duration_of_tp = 4 hr/tp
    * ts_duration_hrs = 24 hr/ts
        = 6 tp/ts * 4 hr/tp
    * ts_scale_to_period = 300 ts/period
        = 1 ts/24 hr * 24 hr/day * 30 day/yr * 10 yr/period
        24 hr/day is a conversion factor. 30 day/yr indicates this
        timeseries is meant to represent 30 days out of every year. If
        it represented every day in January instead of all but one day,
        this term would be 31 day/hr.
    * tp_weight[t] = 1200 hr/period
        = 4 hr/tp * 1 tp/ts * 300 ts/period

    January peak timeseries: This timeseries describing a peak day in
    January is also composed of 6 timepoints, each representing a 4-hour
    block. This is scaled up by factor of 1 to represent a single peak
    day of the month January, then scaled up by a factor of 10 to
    represent all peak January days in a 10-year period.
    * ts_num_tps = 6 tp/ts
    * ts_duration_of_tp = 4 hr/tp
    * ts_duration_hrs = 24 hr/ts
        = 6 tp/ts * 4 hr/tp
    * ts_scale_to_period = 10 ts/period
        = 1 ts/24 hr * 24 hr/day * 1 day/yr * 10 yr/period
        24 hr/day is a conversion factor. 1 day/yr indicates this
        timeseries is meant to represent a single day out of the year.
    * tp_weight[t] = 40 hr/period
        = 4 hr/tp * 1 tp/ts * 10 ts/period

    Example 2: The month of July is described by one timeseries that
    represents an entire week because July is a high-stress period for
    the grid and needs more time resolution to capture capacity and
    storage requirements.

    This timeseries describing 7 days in July is composed of 84
    timepoints, each representing 2 hour blocks. These are scaled up to
    represent all 31 days of July, then scaled by another factor of 10
    to represent a 10-year period.
    * ts_num_tps = 84 tp/ts
    * ts_duration_of_tp = 2 hr/tp
    * ts_duration_hrs = 168 hr/ts
        = 84 tp/ts * 2 hr/tp
    * ts_scale_to_period = 44.29 ts/period
        = 1 ts/168 hr * 24 hr/day * 31 days/yr * 10 yr/period
        24 hr/day is a conversion factor. 31 day/yr indicates this
        timeseries is meant to represent 31 days out of every year (31
        days = duration of July).
    * tp_weight[t] = 88.58 hr/period
        = 2 hr/tp * 1 tp/ts * 44.29 ts/period

    Example 3: The windy season of March & April are described with a
    single timeseries spanning 3 days because this is a low-stress
    period on the grid with surplus wind power and frequent
    curtailments.

    This timeseries describing 3 days in Spring is composted of 72
    timepoints, each representing 1 hour. The timeseries is scaled up by
    a factor of 21.3 to represent the 61 days of March and April, then
    scaled by another factor of 10 to represent a 10-year period.
    * ts_num_tps = 72 tp/ts
    * ts_duration_of_tp = 1 hr/tp
    * ts_duration_hrs = 72 hr/ts
        = 72 tp/ts * 1 hr/tp
    * ts_scale_to_period = 203.3 ts/period
        = 1 ts/72 hr * 24 hr/day * 61 days/yr * 10 yr/period
        24 hr/day is a conversion factor. 6a day/yr indicates this
        timeseries is meant to represent 61 days out of every year (31
        days in March + 30 days in April).
    * tp_weight[t] = 203.3 hr/period
        = 1 hr/tp * 1 tp/ts * 203.3 ts/period

    SYNOPSIS
    >>> from pyomo.environ import *
    >>> import timescales
    >>> switch_mod = AbstractModel()
    >>> timescales.define_components(switch_mod)
    >>> switch_inst = switch_mod.create('test_dat/timescales.dat')
    >>> switch_inst = switch_mod.create('test_dat/timescales_bad_weights.dat')
    Traceback (most recent call last):
        ...
    ValueError: BuildCheck 'validate_time_weights' identified error with index '2020'

    """

    # This will add a min_data_check() method to the model
    utilities.add_min_data_check(mod)

    mod.INVEST_PERIODS = Set(ordered=True)
    mod.period_start = Param(mod.INVEST_PERIODS, within=PositiveReals)
    mod.period_end = Param(mod.INVEST_PERIODS, within=PositiveReals)
    mod.min_data_check('INVEST_PERIODS', 'period_start', 'period_end')
    mod.period_length_years = Param(
        mod.INVEST_PERIODS,
        initialize=lambda mod, p: mod.period_end[p] - mod.period_start[p] + 1)
    mod.period_length_hours = Param(
        mod.INVEST_PERIODS,
        initialize=lambda mod, p: mod.period_length_years[p] * hours_per_year)

    mod.TIMESERIES = Set()
    mod.ts_period = Param(mod.TIMESERIES, within=mod.INVEST_PERIODS)
    mod.ts_duration_of_tp = Param(mod.TIMESERIES, within=PositiveReals)
    mod.ts_num_tps = Param(mod.TIMESERIES, within=PositiveIntegers)
    mod.ts_scale_to_period = Param(mod.TIMESERIES, within=PositiveReals)
    mod.min_data_check(
        'TIMESERIES', 'ts_period', 'ts_duration_of_tp', 'ts_num_tps')
    mod.ts_duration_hrs = Param(
        mod.TIMESERIES,
        initialize=lambda mod, ts: (
            mod.ts_num_tps[ts] * mod.ts_duration_of_tp[ts]))

    mod.TIMEPOINTS = Set()
    mod.tp_ts = Param(mod.TIMEPOINTS, within=mod.TIMESERIES)
    mod.min_data_check('TIMEPOINTS', 'tp_ts')
    mod.tp_label = Param(mod.TIMEPOINTS, default=lambda mod, t: t)
    mod.tp_period = Param(
        mod.TIMEPOINTS,
        within=mod.INVEST_PERIODS,
        initialize=lambda mod, t: mod.ts_period[mod.tp_ts[t]])
    mod.tp_weight = Param(
        mod.TIMEPOINTS,
        within=PositiveReals,
        initialize=lambda mod, t: (
            mod.ts_duration_of_tp[mod.tp_ts[t]] *
            mod.ts_scale_to_period[mod.tp_ts[t]]))
    mod.tp_weight_in_year = Param(
        mod.TIMEPOINTS,
        within=PositiveReals,
        initialize=lambda mod, t: (
            mod.tp_weight[t] / mod.period_length_years[mod.tp_period[t]]))

    ############################################################
    # "Helper" sets that are indexed for convenient look-up.
    # I can't use the filter option to construct these because
    # filter isn't currently implemented for indexed sets.
    mod.TS_TPS = Set(
        mod.TIMESERIES,
        ordered=True,
        within=mod.TIMEPOINTS,
        initialize=lambda m, ts: set(
            t for t in m.TIMEPOINTS if m.tp_ts[t] == ts))
    mod.PERIOD_TPS = Set(
        mod.INVEST_PERIODS,
        within=mod.TIMEPOINTS,
        initialize=lambda m, p: set(
            t for t in m.TIMEPOINTS if m.tp_period[t] == p))

    def validate_time_weights_rule(m, p):
        hours_in_period = sum(m.tp_weight[t] for t in m.PERIOD_TPS[p])
        tol = 0.01
        if(hours_in_period > (1 + tol) * m.period_length_hours[p] or
           hours_in_period < (1 - tol) * m.period_length_hours[p]):
            print "validate_time_weights_rule failed for period " + \
                  "'{period:s}'. Expected {period_h:0.2f}, based on" + \
                  "length in years, but the sum of timepoint weights " + \
                  "is {ds_h:0.2f}.\n"\
                  .format(period=p, period_h=m.period_length_hours[p],
                          ds_h=hours_in_period)
            return 0
        return 1
    mod.validate_time_weights = BuildCheck(
        mod.INVEST_PERIODS,
        rule=validate_time_weights_rule)


def load_data(mod, switch_data, inputs_directory):
    """
    Import data for timescales from .tab files.  The inputs_directory
    should contain the following files with these columns:

    periods.tab
        INVESTMENT_PERIOD, period_start, period_end
    timeseries.tab
        TIMESERIES, period, ts_duration_of_tp, ts_num_tps,
        ts_scale_to_period
    timepoints.tab
        timepoint_id, timepoint_label, timeseries

    This function does not yet perform detailed error checking on the
    incoming files for things like column names, column counts, etc. If
    you make a mistake with column format, you may get an unhelpful
    error message pointing you to some line in this function. If that
    happens, look at the relevant line to see which file is being read
    in, and you'll probably find that you have some kind of error in
    that file.

    Unfortunately, not all errors will be caught while these files are
    read in, and some may only appear during the model.create(data)
    stage. In the future, it would be good to write some basic error
    checking into this import function.

    EXAMPLE:
    >>> from pyomo.environ import *
    >>> import timescales
    >>> switch_mod = AbstractModel()
    >>> timescales.define_components(switch_mod)
    >>> switch_data = DataPortal(model=switch_mod)
    >>> timescales.load_data(switch_mod, switch_data, 'test_dat')
    >>> switch_instance = switch_mod.create(switch_data)
    >>> switch_instance.tp_weight_in_year.pprint()
    tp_weight_in_year : Size=7, Index=TIMEPOINTS, Domain=PositiveReals, Default=None, Mutable=False
        Key : Value
          1 : 1095.744
          2 : 1095.744
          3 : 1095.744
          4 : 1095.744
          5 :   2191.5
          6 :   2191.5
          7 :   8766.0

    """
    # Include select in each load() function so that it will check out column
    # names, be indifferent to column order, and throw an error message if
    # some columns are not found.
    switch_data.load(
        filename=os.path.join(inputs_directory, 'periods.tab'),
        select=('INVESTMENT_PERIOD', 'period_start', 'period_end'),
        index=mod.INVEST_PERIODS,
        param=(mod.period_start, mod.period_end))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'timeseries.tab'),
        select=('TIMESERIES', 'ts_period', 'ts_duration_of_tp',
                'ts_num_tps', 'ts_scale_to_period'),
        index=mod.TIMESERIES,
        param=(mod.ts_period, mod.ts_duration_of_tp,
               mod.ts_num_tps, mod.ts_scale_to_period))
    switch_data.load(
        filename=os.path.join(inputs_directory, 'timepoints.tab'),
        select=('timepoint_id', 'timepoint_label', 'timeseries'),
        index=mod.TIMEPOINTS,
        param=(mod.tp_label, mod.tp_ts))
