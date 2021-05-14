""" Command-line interphase for SWITCH-WECC Database

This is script handles the inputs for the sampling scripts.
"""

# Standard packages
import argparse
import sys

# Third-party packages
import yaml

# Local imports
from switch_model.utilities import query_yes_no
from switch_model.wecc.utilities import connect
from .utils import insert_to_db, timeit
from .sampling import peak_median

# The schema is general for the script
SCHEMA = "switch"
OVERWRITE = True


@timeit
def insert_study_timeframe_id(study_id, name, description, **kwargs):
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
        id_column=id_column,
        id_var=study_id,
        **kwargs,
    )

    return values


@timeit
def insert_periods(study_id, start_year, end_year, period_length, **kwargs):
    # Get values to insert
    # TODO specify number of periods instead of end year
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
        table_name="period",
        columns=[
            "study_timeframe_id",
            "period_id",
            "start_year",
            "label",
            "length_yrs",
            "end_year",
        ],
        values=values,
        schema=SCHEMA,
        id_column="study_timeframe_id",
        id_var=study_id,
        **kwargs,
    )
    return values


@timeit
def insert_time_sample(study_id, time_sample_id, name, method, description, **kwargs):
    # TODO: Ask paty what makes sense here. If using study_timeframe_id or time_sample_id
    values = [(time_sample_id, study_id, name, method, description)]

    if kwargs.get("verbose"):
        print(values)
    insert_to_db(
        table_name="time_sample",
        columns=[
            "time_sample_id",
            "study_timeframe_id",
            "name",
            "method",
            "description",
        ],
        values=values,
        id_column="time_sample_id",
        id_var=time_sample_id,
        **kwargs,
    )

    return values


@timeit
def insert_timeseries_tps(
    demand_scenario_id,
    study_id,
    time_sample_id,
    number_tps,
    period_values,
    method=None,
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
        id_column=id_column,
        id_var=time_sample_id,
        **kwargs,
    )
    insert_to_db(
        tps_table_name,
        sampled_tps.columns,
        [tuple(r) for r in sampled_tps.to_numpy()],
        id_column=id_column,
        id_var=time_sample_id,
        **kwargs,
    )
    ...


# def insert_timepoints(period_values, study_id, time_sample_id,


def main():
    # Start CLI
    parser = argparse.ArgumentParser()

    # Optional arguments
    parser.add_argument(
        "--config_file",
        default="sampling.yaml",
        type=str,
        help="Configuration file to use",
    )

    # General commands
    parser.add_argument("-v", "--verbose", default=False, action="store_true")
    parser.add_argument("--overwrite", default=False, action="store_true")

    args = parser.parse_args()

    # Start db connection
    db_conn = connect()

    # Exit if you are not sure if you want to overwrite
    if args.overwrite:
        if not query_yes_no("You are about to overwrite some data from the Database! Confirm?"):
            sys.exit()

    with open(args.config_file) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    # NOTE: This is a safety measure. Maybe unnecesary?
    if not query_yes_no(f"Do you want to run the sampling with {args.config_file}?"):
        sys.exit()

    print("\nStarting Sampling Script\n")

    # TODO: We are doing this for the moment. We can make a more intelligent or elegant
    # pass to each of the function with a more standarized name schema.
    study_id = data["study_timeframe"].get("id")
    name = data["study_timeframe"].get("name")
    description = data["study_timeframe"].get("description")

    insert_study_timeframe_id(
        study_id, name, description, overwrite=args.overwrite, verbose=args.verbose, db_conn=db_conn
    )

    # Read period configuration
    start_year = data["periods"].get("start_year")
    end_year = data["periods"].get("end_year")
    period_length = data["periods"].get("length")

    period_values = insert_periods(
        study_id,
        start_year,
        end_year,
        period_length,
        overwrite=args.overwrite,
        verbose=args.verbose,
        db_conn=db_conn
    )

    # Timesample
    time_sample_id = data["sampling"].get("id")
    name = data["sampling"].get("name")
    method = data["sampling"].get("method")
    description = data["sampling"].get("description")
    demand_scenario_id = data["load"].get("scenario_id")
    number_tps = data["sampling"].get("number_tps")

    insert_time_sample(
        study_id,
        time_sample_id,
        name,
        method,
        description,
        overwrite=args.overwrite,
        verbose=args.verbose,
        db_conn=db_conn
    )

    insert_timeseries_tps(
        demand_scenario_id,
        study_id,
        time_sample_id,
        number_tps,
        period_values,
        overwrite=args.overwrite,
        verbose=args.verbose,
        db_conn=db_conn
    )
    print("+ Done.")


if __name__ == "__main__":
    main()