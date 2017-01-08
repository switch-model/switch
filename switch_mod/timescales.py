# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""
Defines timescales for investment and dispatch for the SWITCH-Pyomo model.

SYNOPSIS
>>> from switch_mod.utilities import define_AbstractModel
>>> model = define_AbstractModel('timescales')
>>> instance = model.load_inputs(inputs_dir='test_dat')

"""

import os
from pyomo.environ import *
import utilities

hours_per_year = 8766


def define_components(mod):
    """
    Augments a Pyomo abstract model object with sets and parameters that
    describe timescales of investment and dispatch decisions.

    PERIODS is the set of multi-year periods describing the timescale of
    investment decisions. The following parameters describe attributes
    of a period.

    period_start[p]: The first complete year of an investment period.

    period_end[p]: The last complete year of an investment period.

    period_length_years[p]: The number of years in an investment
    period; derived from period_start and period_end.

    period_length_hours[p]: The number of hours in an investment
    period; derived from period_length_years with an average of   8766
    hours per year.

    TIMESERIES denote blocks of consecutive timepoints within a period.
    An individual time series could represent a single day, a week, a
    month or an entire year. This replaces the DATE construct in the old
    SWITCH code and is meant to be more versatile. The following parameters
    describe attributes of a timeseries.

    ts_period[ts]: The period a timeseries falls in.

    ts_num_tps[ts]: The number of timepoints in a timeseries.

    ts_duration_of_tp[ts]: The duration in hours of each timepoint
    within a timeseries. This is used for calculations that ensure a
    storage project has a sufficient energy charge when it is
    dedicated to providing reserves.

    ts_duration_hrs[ts]: The total duration of a timeseries in hours.
        = ts_duration_of_tp[ts] * ts_num_tps[ts]

    ts_scale_to_period[ts]: The number of times this representative
    timeseries is expected to occur in a period. Used as a scaling
    factor   to adjust the weight from ts_duration_hrs up to a period.
    See examples below.

    ts_scale_to_year[ts]: The number of times this representative
    timeseries is expected to occur in a year.

    TIMEPOINTS describe unique timepoints within a time series and
    typically index exogenous variables such as electricity demand and
    variable renewable energy output. The duration of a timepoint is
    typically on the order of one or more hours, so costs associated
    with timepoints are specified in hourly units, and the weights of
    timepoints are specified in units of hours. TIMEPOINTS replaces the
    HOURS construct in some of the old versions of SWITCH. The order of
    timepoints is provided by their ordering in their input file
    according to the standard Pyomo/AMPL conventions. To maintain
    sanity, we recommend sorting your input file by timestamp. Each
    timepoint within a series has the same duration to simplify
    statistical calculations. The following parameters describe
    attributes of timepoints.

    tp_weight[t]: The weight of a timepoint within an investment
    period in units of hours per period.
        = ts_duration_of_tp[ts] * ts_scale_to_period[ts]

    tp_weight_in_year[t]: The weight of a timepoint within a year
    in units of hours per year.
         = tp_weight[t] / period_length_years[p]

    tp_timestamp[t]: The timestamp of the future time represented by
    this timepoint. This is only used as a label and can follow any
    format you wish. Although we highly advise populating this
    parameter, it is optional and will default to t.

    tp_ts[t]: This timepoint's timeseries.

    tp_period[t]: This timepoint's period.

    tp_duration_hrs[t]: The duration of this timepoint in hours,
    taken directly from the timeseries specification ts_duration_of_tp.

    tp_previous[t]: The timepoint that is previous to t in its
    timeseries. Timeseries are treated circularly, so previous of the
    first timepoint will be the last timepoint in the series instead of
    being None or invalid. In the degenerate case of a timeseries with a
    single timepoint, tp_previous[t] will be t.

    PERIOD_TPS[period]: The set of timepoints in a period.

    TS_TPS[timeseries]: The ordered set of timepoints in a timeseries.

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

    EXAMPLE
    >>> from switch_mod.utilities import define_AbstractModel
    >>> model = define_AbstractModel('timescales')
    >>> if hasattr(model, 'create_instance'):
    ...     instance = model.create_instance('test_dat/timescales.dat')
    ... else:
    ...     instance = model.create('test_dat/timescales.dat')
    >>> if hasattr(model, 'create_instance'):
    ...     instance = model.create_instance('test_dat/timescales_bad_weights.dat')
    ... else:
    ...     instance = model.create('test_dat/timescales_bad_weights.dat')
    Traceback (most recent call last):
        ...
    ValueError: BuildCheck 'validate_time_weights' identified error with index '2020'

    """

    mod.PERIODS = Set(ordered=True)
    mod.period_start = Param(mod.PERIODS, within=PositiveReals)
    mod.period_end = Param(mod.PERIODS, within=PositiveReals)
    mod.min_data_check('PERIODS', 'period_start', 'period_end')

    mod.TIMESERIES = Set(ordered=True)
    mod.ts_period = Param(mod.TIMESERIES, within=mod.PERIODS)
    mod.ts_duration_of_tp = Param(mod.TIMESERIES, within=PositiveReals)
    mod.ts_num_tps = Param(mod.TIMESERIES, within=PositiveIntegers)
    mod.ts_scale_to_period = Param(mod.TIMESERIES, within=PositiveReals)
    mod.min_data_check(
        'TIMESERIES', 'ts_period', 'ts_duration_of_tp', 'ts_num_tps',
        'ts_scale_to_period')

    mod.TIMEPOINTS = Set(ordered=True)
    mod.tp_ts = Param(mod.TIMEPOINTS, within=mod.TIMESERIES)
    mod.min_data_check('TIMEPOINTS', 'tp_ts')
    mod.tp_timestamp = Param(mod.TIMEPOINTS, default=lambda m, t: t)

    # Derived sets and parameters
    # note: the first four are calculated early so they
    # can be used for the add_one_to_period_end_rule
    
    mod.tp_weight = Param(
        mod.TIMEPOINTS,
        within=PositiveReals,
        initialize=lambda m, t: (
            m.ts_duration_of_tp[m.tp_ts[t]] *
            m.ts_scale_to_period[m.tp_ts[t]]))
    mod.TS_TPS = Set(
        mod.TIMESERIES,
        ordered=True,
        within=mod.TIMEPOINTS,
        initialize=lambda m, ts: [
            t for t in m.TIMEPOINTS if m.tp_ts[t] == ts])
    mod.tp_period = Param(
        mod.TIMEPOINTS,
        within=mod.PERIODS,
        initialize=lambda m, t: m.ts_period[m.tp_ts[t]])
    mod.PERIOD_TS = Set(
        mod.PERIODS,
        ordered=True,
        within=mod.TIMESERIES,
        initialize=lambda m, p: [
            ts for ts in m.TIMESERIES if m.ts_period[ts] == p])
    mod.PERIOD_TPS = Set(
        mod.PERIODS,
        ordered=True,
        within=mod.TIMEPOINTS,
        initialize=lambda m, p: [
            t for t in m.TIMEPOINTS if m.tp_period[t] == p])
    
    # Decide whether period_end values have been given as exact points in time
    # (e.g., 2020.0 means 2020-01-01 00:00:00), or as a label for a full
    # year (e.g., 2020 means 2020-12-31 12:59:59). We use whichever one gives
    # a better correspondence between the timepoint weights and the period length.
    # NOTE: we can't just check whether period_end[p] + 1 = period_start[p+1],
    # because that is undefined for single-period models.
    def add_one_to_period_end_rule(m):
        hours_in_period = {p: sum(m.tp_weight[t] for t in m.PERIOD_TPS[p]) for p in m.PERIODS}
        err_plain = sum(
            (m.period_end[p] - m.period_start[p]) * hours_per_year - hours_in_period[p]
                for p in m.PERIODS)
        err_add_one = sum(
            (m.period_end[p] + 1 - m.period_start[p]) * hours_per_year - hours_in_period[p]
                for p in m.PERIODS)
        add_one = (abs(err_add_one) < abs(err_plain))
        # print "add_one: {}".format(add_one)
        return add_one
    mod.add_one_to_period_end = Param(within=Boolean, initialize=add_one_to_period_end_rule)

    mod.period_length_years = Param(
        mod.PERIODS,
        initialize=lambda m, p: m.period_end[p] - m.period_start[p] + (1 if m.add_one_to_period_end else 0))
    mod.period_length_hours = Param(
        mod.PERIODS,
        initialize=lambda m, p: m.period_length_years[p] * hours_per_year)

    mod.ts_scale_to_year = Param(
        mod.TIMESERIES,
        initialize=lambda m, ts: (
            m.ts_scale_to_period[ts] / m.period_length_years[m.ts_period[ts]]))
    mod.ts_duration_hrs = Param(
        mod.TIMESERIES,
        initialize=lambda m, ts: (
            m.ts_num_tps[ts] * m.ts_duration_of_tp[ts]))

    mod.tp_weight_in_year = Param(
        mod.TIMEPOINTS,
        within=PositiveReals,
        initialize=lambda m, t: (
            m.tp_weight[t] / m.period_length_years[m.tp_period[t]]))
    mod.tp_duration_hrs = Param(
        mod.TIMEPOINTS,
        initialize=lambda m, t: m.ts_duration_of_tp[m.tp_ts[t]])
    # Identify previous step for each timepoint, for use in tracking
    # unit commitment or storage. We use circular indexing (.prevw() method) 
    # for the timepoints within a timeseries to give consistency between the 
    # start and end state. (Note: separate timeseries are assumed to be 
    # disconnected from each other.)
    mod.tp_previous = Param(
        mod.TIMEPOINTS,
        within=mod.TIMEPOINTS,
        initialize=lambda m, t: m.TS_TPS[m.tp_ts[t]].prevw(t))

    def validate_time_weights_rule(m, p):
        hours_in_period = sum(m.tp_weight[t] for t in m.PERIOD_TPS[p])
        tol = 0.01
        if(hours_in_period > (1 + tol) * m.period_length_hours[p] or
           hours_in_period < (1 - tol) * m.period_length_hours[p]):
            print ("validate_time_weights_rule failed for period " +
                   "'{period:.0f}'. Expected {period_h:0.2f}, based on " +
                   "length in years, but the sum of timepoint weights " +
                   "is {ds_h:0.2f}.\n"
                   ).format(period=p, period_h=m.period_length_hours[p],
                            ds_h=hours_in_period)
            return 0
        return 1
    mod.validate_time_weights = BuildCheck(
        mod.PERIODS,
        rule=validate_time_weights_rule)

    def validate_period_lengths_rule(m, p):
        tol = 0.01
        if p != m.PERIODS.last():
            p_end = m.period_start[p] + m.period_length_years[p]
            p_next = m.period_start[m.PERIODS.next(p)]
            if abs(p_next - p_end) > tol:
                print (
                    "validate_period_lengths_rule failed for period"
                    + "'{p:.0f}'. Period ends at {p_end}, but next period"
                    + "begins at {p_next}."
                ).format(p=p, p_end=p_end, p_next=p_next)
                return False
        return True
    mod.validate_period_lengths = BuildCheck(
        mod.PERIODS, 
        rule=validate_period_lengths_rule)


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import data for timescales from .tab files.  The inputs_dir
    should contain the following files with these columns. The
    columns may be in any order and extra columns will be ignored.

    periods.tab
        INVESTMENT_PERIOD, period_start, period_end

    timeseries.tab
        TIMESERIES, period, ts_duration_of_tp, ts_num_tps,
        ts_scale_to_period

    The order of rows in timepoints.tab indicates the order of the
    timepoints per Pyomo and AMPL convention. To maintain your sanity,
    we highly recommend that you sort your input file chronologically by
    timestamp. Note: timestamp is solely used as a label and be in any
    format.

    timepoints.tab
        timepoint_id, timestamp, timeseries

    EXAMPLE:
    >>> from switch_mod.utilities import define_AbstractModel
    >>> model = define_AbstractModel('timescales')
    >>> instance = model.load_inputs(inputs_dir='test_dat')
    >>> instance.tp_weight_in_year.pprint()
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
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'periods.tab'),
        select=('INVESTMENT_PERIOD', 'period_start', 'period_end'),
        index=mod.PERIODS,
        param=(mod.period_start, mod.period_end))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'timeseries.tab'),
        select=('TIMESERIES', 'ts_period', 'ts_duration_of_tp',
                'ts_num_tps', 'ts_scale_to_period'),
        index=mod.TIMESERIES,
        param=(mod.ts_period, mod.ts_duration_of_tp,
               mod.ts_num_tps, mod.ts_scale_to_period))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'timepoints.tab'),
        select=('timepoint_id', 'timestamp', 'timeseries'),
        index=mod.TIMEPOINTS,
        param=(mod.tp_timestamp, mod.tp_ts))
