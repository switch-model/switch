""" Command-line interphase for SWITCH-WECC Database

"""

# Standard packages
import argparse
from pathlib import Path
import sys
import time
import typing

# Third-party packages
from loguru import logger
import numpy as np
import pandas as pd
import psycopg2.extras as extras

# Local imports
from .db_connect import connect
from .utils import insert_to_db
from .utils import get_load_data
from .utils import timeit
from .sampling import peak_median

# The schema is general for the script
SCHEMA = "switch"
OVERWRITE = True

# Start db connection
db_conn = connect()


def insert_study_timeframe_id(study_id, name, description, db_conn=db_conn, **kwargs):
    table_name = "study_timeframe"
    columns = ["study_timeframe_id", "name", "description"]
    id_column = "study_timeframe_id"

    # TODO: Maybe find a better way to do this on a general function for all the tables.
    # This works for the moment for each table
    values = [(study_id, name, description)]

    if kwargs.get("verbose"):
        print(values)

    # Calling insert function
    insert_to_db(
        table_name,
        columns,
        values,
        schema=SCHEMA,
        db_conn=db_conn,
        id_column=id_column,
        id_var=study_id,
        **kwargs,
    )

    return values


def insert_periods(
    study_id, start_year, end_year, period_length, db_conn=db_conn, **kwargs
):
    table_name = "period"
    columns = [
        "study_timeframe_id",
        "period_id",
        "start_year",
        "label",
        "length_yrs",
        "end_year",
    ]
    id_column = "study_timeframe_id"

    # Get values to insert
    period_range = range(start_year, end_year, period_length)
    values = [
        (
            study_id,
            period_id + 1,  # Period ID
            period_start,
            int(
                round((period_start + (period_start + period_length - 1)) / 2)
            ),  # Period label is middle point round to nearest integer
            period_length,
            period_start
            + period_length
            - 1,  # Remove one from last period to match previous runs
        )
        for period_id, period_start in enumerate(period_range)
    ]

    if kwargs.get("verbose"):
        print(values)

    # Calling insert function
    insert_to_db(
        table_name,
        columns,
        values,
        schema=SCHEMA,
        db_conn=db_conn,
        id_column=id_column,
        id_var=study_id,
        **kwargs,
    )
    return values


def insert_time_sample(study_id, time_sample_id, name, method, description, **kwargs):
    table_name = "time_sample"
    columns = [
        "time_sample_id",
        "study_timeframe_id",
        "name",
        "method",
        "description",
    ]
    # TODO: Ask paty what makes sense here. If using study_timeframe_id or time_sample_id
    id_column = "time_sample_id"

    values = [(time_sample_id, study_id, name, method, description)]

    if kwargs.get("verobse"):
        print(values)
    insert_to_db(
        table_name,
        columns,
        values,
        db_conn=db_conn,
        id_column=id_column,
        id_var=time_sample_id,
        **kwargs,
    )

    return values


def insert_timeseries_tps(
    demand_scenario_id,
    study_id,
    time_sample_id,
    number_tps,
    period_values,
    method=None,
    db_conn=db_conn,
    verbose=None,
    **kwargs,
):
    # import modulelib
    # get(method) from module lib
    # Run method(demand_scenario_id)
    timeseries, sampled_tps = peak_median(
        demand_scenario_id,
        study_id,
        time_sample_id,
        number_tps,
        period_values,
        db_conn=db_conn,
        **kwargs,
    )

    tps_table_name = "sampled_timepoint"
    ts_table_name = "sampled_timeseries"

    id_column = "time_sample_id"

    if kwargs.get("verobse"):
        pass
    # print(values)

    insert_to_db(
        ts_table_name,
        timeseries.columns,
        [tuple(r) for r in timeseries.to_numpy()],
        db_conn=db_conn,
        id_column=id_column,
        id_var=time_sample_id,
        **kwargs,
    )
    insert_to_db(
        tps_table_name,
        sampled_tps.columns,
        [tuple(r) for r in sampled_tps.to_numpy()],
        db_conn=db_conn,
        id_column=id_column,
        id_var=time_sample_id,
        **kwargs,
    )
    ...


# def insert_timepoints(period_values, study_id, time_sample_id,


def cli():

    # TODO: Neet to figure out if we need to pass this as an input
    # Timeframe
    study_id = 10
    name = "Sampling study timeframe"
    description = "Pedro was here"

    insert_study_timeframe_id(
        study_id, name, description, overwrite=OVERWRITE, verbose=True
    )

    # Periods
    start_year = 2016  # args.get("start_year")
    end_year = 2055  # args.get("end_year")
    period_length = 10  # args.get("periods")

    period_values = insert_periods(
        study_id, start_year, end_year, period_length, overwrite=OVERWRITE, verbose=True
    )


    # Timesample
    time_sample_id = 7
    name = "Peak and median"
    method = "peak_median"
    description = "This is the method for peak and median"

    insert_time_sample(
        study_id,
        time_sample_id,
        name,
        method,
        description,
        overwrite=OVERWRITE,
        verobse=True,
    )


    demand_scenario_id = 115
    number_tps = 6

    insert_timeseries_tps(
        demand_scenario_id,
        study_id,
        time_sample_id,
        number_tps,
        period_values,
        overwrite=OVERWRITE,
        verobse=True,
    )

if __name__ == "__main__":
    li()