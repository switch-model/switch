import numpy as np
import pandas as pd

from .utils import (
    get_median_days,
    get_peak_days,
    logger,
    get_next_prv_day,
    get_load_data,
)


def sample_timepoints(
    data,
    dates,
    number_tps: int = 6,
    peak=None,
    median=None,
    study_timeframe_id=1,
    time_stample_id=1,
    period_id=1,
):
    if number_tps != 6:
        raise NotImplementedError(f"{number_tps} tps is not yet implemented")
    columns = [
        "raw_timepoint_id",
        "study_timeframe_id",
        "time_sample_id",
        "period_id",
        "timestamp_utc",
        "id",
        "day_no",
    ]
    df = data.set_index("timestamp_utc").copy()
    delta_t = int(24 / number_tps)

    sampled_timepoints_list = []
    for num, date in enumerate(dates):
        if peak:
            subset = df.loc[date].copy()
            # FIXME: Maybe we want to only pass the data with the demand series instead of
            # having all the other columns
            subset_peak = subset["demand_mw"].idxmax()
            prev_day, next_day = get_next_prv_day(subset_peak)
            subset = df.loc[prev_day:next_day].copy()
            tps = subset[
                subset_peak
                - pd.Timedelta(value=delta_t * 2, unit="hours") : subset_peak
                + pd.Timedelta(value=(delta_t * 2 + delta_t), unit="hours") : delta_t
            ].copy()
        else:
            subset = df[date].copy()
            tps = subset[::delta_t].copy()  # raise KeyError("Odd number of timepoints")
            # # raise NotImplementedError("Blame the developer!")
        # # TODO: Add a more robust sampling strategy that is able to check
        # # if the sampling is on the day before and check if the max is in the sampling
        # tps = data_filter.iloc[date_loc::delta_t]
        # if len(tps) != number_tps:
        # # FIXME: There is problem if the day is at the end I need to fix this
        # tps = data_filter.iloc[0::delta_t]
        if peak:
            id_label = "P"
        else:
            id_label = "M"
            breakpoint
        tps.loc[:, "id"] = id_label
        tps.loc[:, "day_no"] = f"{num}_{id_label}"

        sampled_timepoints_list.append(tps)
    data = pd.concat(sampled_timepoints_list)
    data.loc[:, "study_timeframe_id"] = study_timeframe_id
    data.loc[:, "time_sample_id"] = time_stample_id
    data.loc[:, "period_id"] = period_id
    data = data.reset_index()[columns]
    return data


def _get_timeseries(
    data: pd.DataFrame,
    number_tps: int = 6,
    study_timeframe_id=10,
    time_stample_id=7,
    # period_id=1,
    *args,
    **kwargs,
):
    df = data.copy()
    if "id" in data.columns:
        identifier = data["id"].unique()[0]
    else:
        identifier = None
    # TODO: Add a new argument to identify groups of days.
    df.loc[:, "date"] = df.timestamp_utc.dt.date
    # df.loc[:, "date"] = df.timestamp_utc.dt.strftime("%Y-%m").values
    df.loc[:, "days_in_month"] = df.timestamp_utc.dt.days_in_month
    df["year"] = df.timestamp_utc.dt.year
    df["leap_year"] = df["year"] % 4
    df["days_in_year"] = np.where(df["leap_year"] == 0, 366, 365)
    # Get first timepoint for each date
    df["first_timepoint_utc"] = df.groupby(["period_id", "day_no"])[
        "timestamp_utc"
    ].transform("first")
    # Get last timepoint for each date FIXME: This might not work if peak is found in the transition between two dates.
    df["last_timepoint_utc"] = df.groupby(["period_id", "day_no"])[
        "timestamp_utc"
    ].transform("last")

    identifier = df["id"]
    df.loc[:, "name"] = df.timestamp_utc.dt.strftime(f"%Y-%m-%d") + "_" + identifier
    df.loc[:, "num_timepoints"] = number_tps
    df.loc[:, "hours_per_tp"] = int(24 / number_tps)
    df.loc[:, "study_timeframe_id"] = study_timeframe_id
    df.loc[:, "time_sample_id"] = time_stample_id
    # df.loc[:, "period_id"] = period_id
    df = _scaling(df, *args, **kwargs)
    df = df.sort_values("date").reset_index(drop=True)
    df.index = df.index.rename("sampled_timeseries_id")

    # Get only duplicate
    df = df.drop_duplicates(subset=["period_id", "day_no"])
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


def method4(
    demand_scenario_id,
    study_id,
    time_sample_id,
    number_tps,
    period_values,
    db_conn=None,
    **kwargs,
):
    ...


def peak_median(
    demand_scenario_id,
    study_id,
    time_sample_id,
    number_tps,
    period_values,
    db_conn=None,
    **kwargs,
):

    # Get load data
    df = get_load_data(demand_scenario_id, db_conn=db_conn, **kwargs)

    df = df.groupby(["timestamp_utc", "date", "raw_timepoint_id"], as_index=False)[
        "demand_mw"
    ].sum()

    sampled_tps = []
    for row in period_values:
        (study_id, period_id, start_year, label, scale_to_period, _end_year) = row
        if label > 2051:
            raise SystemExit(f"Year {label} does not exist on the DB")
        df_tmp = df[df.timestamp_utc.dt.year == label].reset_index(drop=True)
        median_days = get_median_days(df_tmp)
        if "2040-01-18" in median_days:
            idx = median_days.index("2040-01-18")
            median_days[idx] = "2040-01-16"
        peak_days = get_peak_days(df_tmp)

        assert len(peak_days) == 12
        assert len(median_days) == 12
        sampled_tps.append(
            sample_timepoints(
                df_tmp,
                peak_days,
                number_tps=number_tps,
                study_timeframe_id=study_id,
                time_stample_id=time_sample_id,
                period_id=period_id,
                peak=True,
            )
        )
        sampled_tps.append(
            sample_timepoints(
                df_tmp,
                median_days,
                time_stample_id=time_sample_id,
                study_timeframe_id=study_id,
                period_id=period_id,
            )
        )
    sampled_tps = pd.concat(sampled_tps).sort_values("timestamp_utc")

    # FIXME: For some reasone I grab a duplicated raw_timepoint_id. However, I do not know
    # where it came from. This is a quick fix
    # sampled_tps = sampled_tps.drop_duplicates(subset=["raw_timepoint_id"])
    timeseries = _get_timeseries(
        sampled_tps,
        study_timeframe_id=study_id,
        time_stample_id=time_sample_id,
        scale_to_period=scale_to_period,
    )
    sampled_to_db = sampled_tps.loc[:, ~sampled_tps.columns.isin(["id"])]
    # TODO: Pass this before in the sampled_timepoints function
    sampled_to_db["date"] = sampled_to_db["timestamp_utc"].dt.date
    columns = [
        "raw_timepoint_id",
        "study_timeframe_id",
        "time_sample_id",
        "sampled_timeseries_id",
        "period_id",
        "timestamp_utc",
    ]
    columns_ts = [
        "sampled_timeseries_id",
        "study_timeframe_id",
        "time_sample_id",
        "period_id",
        "name",
        "hours_per_tp",
        "num_timepoints",
        "first_timepoint_utc",
        "last_timepoint_utc",
        "scaling_to_period",
    ]
    sampled_tps_tms = pd.merge(
        sampled_to_db,
        timeseries[["sampled_timeseries_id", "period_id", "day_no"]],
        how="right",
        on=["period_id", "day_no"],
    )

    # FIXME: Overlaping timepoints cause troubles on the DB
    breakpoint()

    return timeseries[columns_ts], sampled_tps_tms[columns]
