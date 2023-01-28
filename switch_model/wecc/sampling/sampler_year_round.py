import pandas as pd

from .utils import read_from_db

# TODO: The created data is in UTC which means in PST our timeseries starts at
#   4pm and ends at 12pm on the 31st. We probably want first_hour to default to 8am with
#   skip_day_one = False. We also probably want to rename first_hour to first_hour_utc.
#   Finally we likely want to add a parameter called last_hour_utc and set it to 8am by default.
def sample_year_round(method_config, period_values, db_conn=None, **kwargs):
    hours_per_tp = method_config["hours_per_tp"]
    first_hour = method_config["first_hour"]
    skip_day_one = method_config["skip_day_one"]
    # Note later in the code we skip Feb 29th for consistency across periods.
    # We also allow skipping Jan. 1st since we don't have all the capacity factors for that year.
    # As such there's either 364 or 365 days
    days_per_year = 364 if skip_day_one else 365
    first_day = 2 if skip_day_one else 1
    last_hour = first_hour + 24 - hours_per_tp
    tp_per_year = 24 * days_per_year / hours_per_tp
    time_delta = pd.Timedelta(hours_per_tp, unit="hours")

    timeseries = []
    timepoints = []

    for i, period in enumerate(period_values):
        # Extract important values from the period values
        (_, period_id, _, label, length_yrs, _) = period

        # Create a timeseries row
        sampled_timeseries_id = (
            i + 1
        )  # sampled_timeseries_id start ids at 1 for consistency with db
        first_timepoint_utc = pd.Timestamp(
            year=label, month=1, day=first_day, hour=first_hour
        )
        last_timepoint_utc = pd.Timestamp(year=label, month=12, day=31, hour=last_hour)
        timeseries.append(
            (
                sampled_timeseries_id,
                period_id,
                f"{label}-year-round",  # ts_name
                hours_per_tp,
                tp_per_year,
                first_timepoint_utc,
                last_timepoint_utc,
                # scaling_to_period factor is number of timeseries in a period
                # that is equal to the number of days in a period / number of days in a timeseries
                # On average there are 365.25 days per year
                (length_yrs * 365.25) / days_per_year,
            )
        )

        # Create the timepoints row
        timepoint_timestamp = first_timepoint_utc
        while timepoint_timestamp <= last_timepoint_utc:
            # We skip Feb. 29th to ensure that all our periods have the same number of days.
            # This guarantees consistency across periods so that comparisons are accurate.
            if not (timepoint_timestamp.month == 2 and timepoint_timestamp.day == 29):
                timepoints.append(
                    (sampled_timeseries_id, period_id, timepoint_timestamp)
                )
            timepoint_timestamp += time_delta

    timeseries = pd.DataFrame(
        timeseries,
        columns=[
            "sampled_timeseries_id",
            "period_id",
            "name",
            "hours_per_tp",
            "num_timepoints",
            "first_timepoint_utc",
            "last_timepoint_utc",
            "scaling_to_period",
        ],
    )

    timepoints = pd.DataFrame(
        timepoints, columns=["sampled_timeseries_id", "period_id", "timestamp_utc"]
    )

    raw_timepoints = read_from_db(
        table_name="raw_timepoint",
        db_conn=db_conn,
        columns=["raw_timepoint_id", "timestamp_utc"],
        **kwargs,
    )

    timepoints = timepoints.merge(
        raw_timepoints, how="left", on="timestamp_utc", validate="one_to_one"
    )

    return timeseries, timepoints
