import numpy as np
import pandas as pd
from typing import List

from .utils import (
    get_median_days,
    get_peak_days,
    logger,
    get_next_prv_day,
    get_load_data,
)


def sample_timepoints(
    load_data,
    dates,
    peak,
    period_id,
    number_tps: int = 6,
):
    """
    Returns a dataframe of timepoints for the given dates
    """
    if number_tps != 6:
        raise NotImplementedError(f"{number_tps} tps is not yet implemented")
    columns_to_return = [
        "date",
        "raw_timepoint_id",
        "period_id",
        "timestamp_utc",
        "id",
    ]
    df = load_data.set_index("timestamp_utc").copy()
    delta_t = int(24 / number_tps)

    sampled_timepoints_list = []
    for date in dates:
        if peak:
            prev_day, next_day = get_next_prv_day(date)
            subset = df.loc[prev_day:next_day].copy()
            # FIXME: Maybe we want to only pass the data with the demand series instead of
            # having all the other columns
            # Find timepoint with peak load
            subset_peak = subset["demand_mw"].idxmax()
            # Get a range of timepoints around the peak
            start_timepoint = subset_peak - pd.Timedelta(value=delta_t * 2, unit="hours")
            end_timepoint = subset_peak + pd.Timedelta(value=(delta_t * 2 + delta_t), unit="hours")
            # Return the timepoints in that range
            tps = subset[start_timepoint: end_timepoint: delta_t]
        else:
            # Get all the timepoints in that day
            subset = df.loc[date].copy()
            tps = subset[::delta_t]  # raise KeyError("Odd number of timepoints")
            # # raise NotImplementedError("Blame the developer!")
        # # TODO: Add a more robust sampling strategy that is able to check
        # # if the sampling is on the day before and check if the max is in the sampling
        # tps = data_filter.iloc[date_loc::delta_t]
        # if len(tps) != number_tps:
        # # FIXME: There is problem if the day is at the end I need to fix this
        # tps = data_filter.iloc[0::delta_t]
        sampled_timepoints_list.append(tps)
    # Merge all the sampled timepoints
    data = pd.concat(sampled_timepoints_list)
    # Add info columns
    data["period_id"] = period_id
    data["id"] = "P" if peak else "M"
    data = data.reset_index()
    data["date"] = data["timestamp_utc"].dt.date
    return data[columns_to_return]


def _get_timeseries(
    data: pd.DataFrame,
    number_tps: int = 6,
    *args,
    **kwargs,
):
    df = data.copy()
    # TODO: Add a new argument to identify groups of days.
    df.loc[:, "date"] = df.timestamp_utc.dt.date
    df.loc[:, "days_in_month"] = df.timestamp_utc.dt.days_in_month
    df["year"] = df.timestamp_utc.dt.year
    df["leap_year"] = df["year"] % 4
    df["days_in_year"] = np.where(df["leap_year"] == 0, 366, 365)
    # Get first timepoint for each date
    df["first_timepoint_utc"] = df.groupby("date")["timestamp_utc"].transform("first")
    # Get last timepoint for each date FIXME: This might not work if peak is found in the transition between two dates.
    df["last_timepoint_utc"] = df.groupby("date")["timestamp_utc"].transform("last")

    # Get only duplicate
    df = df.drop_duplicates("date")

    identifier = df["id"]
    df.loc[:, "name"] = df.timestamp_utc.dt.strftime(f"%Y-%m-%d") + "_" + identifier
    df.loc[:, "num_timepoints"] = number_tps
    df.loc[:, "hours_per_tp"] = int(24 / number_tps)
    # df.loc[:, "period_id"] = period_id
    df = _scaling(df, *args, **kwargs)
    df = df.sort_values("date").reset_index(drop=True)
    df.index = df.index.rename("sampled_timeseries_id")
    return df.reset_index()


def _scaling(data, scale_to_period=10, days_in_month=31, scaling_dict=None):

    df = data.copy()

    # FIXME: Add a function that handle better any days with different weights
    df.loc[df["id"] == "P", "no_days"] = 2
    df.loc[df["id"] == "M", "no_days"] = df.loc[df["id"] == "M", "days_in_month"] - 2

    df["scaling_to_period"] = (
        scale_to_period
        * df["days_in_year"]
        * df["no_days"]  # df["no_days"]
        / (12 * df["days_in_month"])  # (df["hours_per_tp"] * df["num_timepoints"])
    )
    return df


def peak_median(
    period_values,
    method_config,
    db_conn=None,
    **kwargs,
):
    number_tps = method_config.get("number_tps")
    demand_scenario_id = method_config.get("demand_scenario_id")

    # Get load data
    df = get_load_data(demand_scenario_id, db_conn=db_conn, **kwargs)

    # Get total load across the WECC during each timepoint
    df = df.groupby(["timestamp_utc", "date", "raw_timepoint_id"], as_index=False)[
        "demand_mw"
    ].sum()

    sampled_tps = []
    # For each period
    for row in period_values:
        (study_id, period_id, _start_year, label, scale_to_period, _end_year) = row
        if label > 2051:
            raise SystemExit(f"Year {label} does not exist on the DB")
        # Get load for that year
        df_tmp = df[df.timestamp_utc.dt.year == label].reset_index(drop=True)
        # Get days with median load
        median_days: List[str] = get_median_days(df_tmp)
        # Get days of peak load
        peak_days: List[str] = get_peak_days(df_tmp)
        # Add the peak day timepoints
        sampled_tps.append(
            sample_timepoints(
                df_tmp,
                peak_days,
                number_tps=number_tps,
                period_id=period_id,
                peak=True,
            )
        )
        # Add the median day timepoints
        sampled_tps.append(
            sample_timepoints(
                df_tmp,
                median_days,
                period_id=period_id,
                peak=False
            )
        )

    # Merge our dataframes together and sort by time
    sampled_tps = pd.concat(sampled_tps).sort_values("timestamp_utc")

    # FIXME: For some reasone I grab a duplicated raw_timepoint_id. However, I do not know
    # where it came from. This is a quick fix
    sampled_tps = sampled_tps.drop_duplicates(subset=["raw_timepoint_id"])
    # Get the timeseries for the given timepoints
    timeseries = _get_timeseries(
        sampled_tps,
        scale_to_period=scale_to_period,
    )
    # Filter out the id column
    sampled_to_db = sampled_tps.loc[:, ~sampled_tps.columns.isin(["id"])]
    sampled_tps_tms = pd.merge(
        sampled_to_db,
        timeseries[["sampled_timeseries_id", "date"]],
        how="right",
        on="date",
    )
    columns = [
        "raw_timepoint_id",
        "sampled_timeseries_id",
        "period_id",
        "timestamp_utc",
    ]
    columns_ts = [
        "sampled_timeseries_id",
        "period_id",
        "name",
        "hours_per_tp",
        "num_timepoints",
        "first_timepoint_utc",
        "last_timepoint_utc",
        "scaling_to_period",
    ]

    return timeseries[columns_ts], sampled_tps_tms[columns]
