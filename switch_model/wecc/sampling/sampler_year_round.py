import pandas as pd

from .utils import read_from_db


def sample_year_round(
        method_config,
        period_values,
        db_conn=None,
        **kwargs
):
    hours_per_tp = method_config["hours_per_tp"]
    first_hour = method_config["first_hour"]
    last_hour = first_hour + 24 - hours_per_tp
    tp_per_day = 24 / hours_per_tp
    time_delta = pd.Timedelta(hours_per_tp, unit="hours")

    timeseries = []
    timepoints = []

    for i, period in enumerate(period_values):
        # Extract important values from the period values
        (_, period_id, _, label, length_yrs, _) = period

        # Create a timeseries row
        sampled_timeseries_id = i + 1  # sampled_timeseries_id start ids at 1 for consistency with db
        first_timepoint_utc = pd.Timestamp(year=label, month=1, day=1, hour=first_hour)
        last_timepoint_utc = pd.Timestamp(year=label, month=12, day=31, hour=last_hour)
        num_days = 366 if first_timepoint_utc.is_leap_year else 365
        timeseries.append((
            sampled_timeseries_id,
            period_id,  # period_id
            f"{label}-year-round",  # ts_name
            hours_per_tp,
            num_days * tp_per_day,  # number of timepoints per ts
            first_timepoint_utc,
            last_timepoint_utc,
            length_yrs  # scaling_to_period (In a 10 year period, there's 10 timeseries per period)
        ))

        # Create the timepoints row
        timepoint_timestamp = first_timepoint_utc
        while timepoint_timestamp <= last_timepoint_utc:
            timepoints.append((
                sampled_timeseries_id,
                period_id,
                timepoint_timestamp
            ))
            timepoint_timestamp += time_delta

    timeseries = pd.DataFrame(timeseries, columns=[
        "sampled_timeseries_id",
        "period_id",
        "name",
        "hours_per_tp",
        "num_timepoints",
        "first_timepoint_utc",
        "last_timepoint_utc",
        "scaling_to_period"
    ])

    timepoints = pd.DataFrame(timepoints, columns=[
        "sampled_timeseries_id",
        "period_id",
        "timestamp_utc"
    ])

    raw_timepoints = read_from_db(
        table_name="raw_timepoint",
        db_conn=db_conn,
        columns=["raw_timepoint_id", "timestamp_utc"],
        **kwargs
    )

    timepoints = timepoints.merge(
        raw_timepoints,
        how="left",
        on="timestamp_utc",
        validate="one_to_one"
    )

    return timeseries, timepoints
