import time
import numpy as np
from loguru import logger
import psycopg2.extras as extras
import os
import pandas as pd
import functools

logger.remove(0)
logger.add("sampling.log", level="DEBUG", enqueue=True, mode="w")


def timeit(f_py=None, to_log=None):
    assert callable(f_py) or f_py is None

    def _decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            if to_log:
                logger.debug(
                    "Function '{}' executed in {:f} s", func.__name__, end - start
                )
            else:
                print(f"|  Finished in {end-start:.2f}s.")
            return result

        return wrapper

    return _decorator(f_py) if callable(f_py) else _decorator

@timeit(to_log=True)
def get_load_data(
    demand_scenario_id: int,
    force_download=False,
    **kwargs,
):
    """ Query the load data from the database"""
    fname = f"load_data-{demand_scenario_id}.csv"

    if not os.path.exists(fname) or force_download:
        df = read_from_db(
            table_name="demand_timeseries",
            where_clause=f"demand_scenario_id = '{demand_scenario_id}'",
            **kwargs
        )
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
    db_conn,
    schema,
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

    print(f"+ {table_name}: ")

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
                print("|  Data exists. Overwritting data")
                curs.execute(clear_query)
                extras.execute_values(curs, default_query, values)
            elif not data:
                print("|  Inserting new data to DB.")
                if verbose:
                    print(values)
                extras.execute_values(curs, default_query, values)
            else:
                raise SystemExit(
                    f"\nValue {id_var} for {id_column} already exists on table {table_name}. Use another one."
                )
    ...


def read_from_db(
        table_name: str,
        db_conn,
        schema,
        where_clause: str = None,
        columns: list = None,
        verbose=False,
        **kwargs
):
    if not db_conn:
        raise SystemExit(
            "No connection to DB provided. Check if you passed it correctly"
        )

    print(f" | Reading from {table_name}")

    columns = "*" if columns is None else ",".join(columns)
    query = f"""
        SELECT {columns} 
        FROM {schema}.{table_name}
        """
    if where_clause is not None:
        query += f" WHERE {where_clause}"
    query += ";"

    if verbose:
        print(query)

    return pd.read_sql_query(query, db_conn)


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
    # Loop through every group of year and freq (normally month start)
    for _, group in df.groupby([pd.Grouper(freq="A"), pd.Grouper(freq=freq)]):
        # Calculate the daily mean
        grouper = group.groupby(pd.Grouper(freq="D")).mean()["demand_mw"]
        if len(grouper) & 1:
            # if Odd number of days find middle element and get index
            index_median = grouper.loc[grouper == grouper.median()].index[0]
        else:
            # Even number of days
            index_median = (np.abs(grouper - grouper.median())).idxmin()
        # years.append(group.loc[index_median.strftime("%Y-%m-%d")].reset_index())
        years.append(index_median.strftime("%Y-%m-%d"))
    # output_data = pd.concat(years, sort=True)
    return years


def get_next_prv_day(date):
    if not isinstance(date, pd.Timestamp):
        date = pd.to_datetime(date)
    prev_day = date + pd.Timedelta(value=-1, unit="day")
    next_day = date + pd.Timedelta(value=1, unit="day")
    return prev_day, next_day
