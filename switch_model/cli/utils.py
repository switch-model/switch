import time
import numpy as np
from loguru import logger
import psycopg2.extras as extras
import os
import pandas as pd


# TODO: Move this function to utils
def timeit(func):
    def wrapped(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        logger.debug("Function '{}' executed in {:f} s", func.__name__, end - start)
        return result

    return wrapped


@timeit
def get_load_data(
    demand_scenario_id: int,
    year: int = 2006,
    table: str = "demand_timeseries",
    db_conn=None,
    verbose=None,
    force_download=False,
    *args,
    **kwargs,
):
    """Query the load data from the database"""
    # Safety check if no DB connection is passed
    if not db_conn:
        raise SystemExit(
            "No connection to DB provided. Check if you passed it correctly"
        )

    logger.debug(f"Getting load data from {table}")

    fname = f"{demand_scenario_id}.csv"

    query = f"""
        SELECT * FROM switch.demand_timeseries
        WHERE
            demand_scenario_id = '{demand_scenario_id}';
        """
    if verbose:
        print(query)
    if not os.path.exists(fname) or force_download:
        df = pd.read_sql_query(query, db_conn)
        df = df.sort_values(["load_zone_id", "raw_timepoint_id"])
        df["date"] = df["timestamp_utc"].dt.strftime("%Y-%m-%d").values
        df.to_csv(fname, index=False)
    else:
        df = pd.read_csv(fname, parse_dates=["timestamp_utc"])
    return df


def insert_to_db(
    table_name: str,
    columns: list,
    values,
    db_conn=None,
    schema="switch",
    id_column=None,
    id_var=None,
    overwrite=False,
    verbose=None,
    **kwargs,
):
    # Safety check if no DB connection is passed
    if not db_conn:
        raise SystemExit(
            "No connection to DB provided. Check if you passed it correctly"
        )
    # Convert columns to a single string to pass it into the query
    columns = ",".join(columns)

    # Default queries.
    # NOTE: We can add new queries on this section
    search_query = f"""
        select {id_column} from {schema}.{table_name} where {id_column} = {id_var};
    """
    default_query = f"""
        insert into {schema}.{table_name}({columns}) values %s;
    """
    clear_query = f"""
        delete from {schema}.{table_name} where {id_column} = {id_var};
    """

    # Start transaction with DB
    with db_conn:
        with db_conn.cursor() as curs:

            # Check if ID is in database
            curs.execute(search_query)
            data = curs.fetchall()

            if data and overwrite:
                if verbose:
                    print(data)
                    print(values)
                print("Data exists. Overwritting data")
                curs.execute(clear_query)
                extras.execute_values(curs, default_query, values)
            elif not data:
                print("Inserting new data to DB.")
                extras.execute_values(curs, default_query, values)
            else:
                raise SystemExit(
                    f"Value {id_var} for {id_column} already exists on table {table_name}. Use another one."
                )

    ...


def get_peak_days(data, freq: str = "MS", verbose: bool = False):
    df = data.copy()

    # Get timestamp of monthly peak
    df = df.set_index("timestamp_utc")
    peak_idx = df.groupby(pd.Grouper(freq="MS")).idxmax()["demand_mw"]

    # Get date of peak timestamp
    datetime_idx = pd.to_datetime(peak_idx.values).strftime("%Y-%m-%d").values

    # Get all days where monthly peak demand is observed
    # peak_days = df.loc[df.date.isin(datetime_idx)]

    # Return dataframe with peak days with hourly resolution
    return datetime_idx


def get_median_days(data, number=6, freq="MS", identifier="M"):
    """Calculate median day giving a timeseries

    Args:
        data (pd.DataFrame): data to filter,
        number (float): number of days to return.

    Note(s):
        * Month start is to avoid getting more timepoints in a even division
    """
    df = data.copy()
    df = df.set_index("timestamp_utc")
    years = []
    for _, group in df.groupby([pd.Grouper(freq="A"), pd.Grouper(freq=freq)]):
        # Calculate the daily mean
        grouper = group.groupby(pd.Grouper(freq="D")).mean()["demand_mw"]
        if len(grouper) & 1:
            # Odd number of days
            index_median = grouper.loc[grouper == grouper.median()].index[0]
        else:
            # Even number of days
            index_median = (np.abs(grouper - grouper.median())).idxmin()
        # years.append(group.loc[index_median.strftime("%Y-%m-%d")].reset_index())
        years.append(index_median.strftime("%Y-%m-%d"))
    # output_data = pd.concat(years, sort=True)
    return np.array(years)
