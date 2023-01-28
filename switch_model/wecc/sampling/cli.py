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
from .sampler_peak_median import peak_median
from .sampler_year_round import sample_year_round

# The schema is general for the script
SCHEMA = "switch"

sampling_methods = {"peak_median": peak_median, "year_round": sample_year_round}


def get_period_values(study_id, start_year, end_year, period_length):
    values = []
    for period_id, period_start in enumerate(
        range(start_year, end_year, period_length)
    ):
        period_end = period_start + period_length - 1
        values.append(
            (
                study_id,
                period_id + 1,  # Period ID, start at 1
                period_start,
                int(
                    round((period_start + period_end) / 2)
                ),  # Period label is middle point round to nearest integer
                period_length,
                period_end,
            )
        )
    return values


def main():
    # Start CLI
    parser = argparse.ArgumentParser()

    # Optional arguments
    parser.add_argument(
        "--config_file",
        default="sampling.yaml",
        type=str,
        help="Configuration file to use.",
    )

    # General commands
    parser.add_argument("-v", "--verbose", default=False, action="store_true")
    parser.add_argument("--overwrite", default=False, action="store_true")

    args = parser.parse_args()

    # Start db connection
    db_conn = connect()

    # Exit if you are not sure if you want to overwrite
    if args.overwrite:
        if not query_yes_no(
            "You are about to overwrite some data from the Database! Confirm?"
        ):
            sys.exit()

    # Load the config file
    with open(args.config_file) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    # Read all the values from the config file. We do this first to ensure they're all there before
    # running queries

    # TODO: We are doing this for the moment. We can make a more intelligent or elegant
    #       pass to each of the function with a more standarized name schema.

    # study_timeframe configuration
    study_timeframe_config = data["study_timeframe"]
    study_id = study_timeframe_config.get("id")
    study_name = study_timeframe_config.get("name")
    study_description = study_timeframe_config.get("description")

    # period configuration
    periods_config = data["periods"]
    start_year = periods_config.get("start_year")
    end_year = periods_config.get("end_year")
    period_length = periods_config.get("length")

    # time_sample configuration
    sampling_config = data["sampling"]
    time_sample_id = sampling_config.get("id")
    name = sampling_config.get("name")
    method = sampling_config.get("method")
    description = sampling_config.get("description")
    method_config = sampling_config[method]

    # arguments to pass to queries
    kwargs = {
        "overwrite": args.overwrite,
        "verbose": args.verbose,
        "db_conn": db_conn,
        "schema": SCHEMA,
    }

    # NOTE: This is a safety measure. Maybe unnecesary?
    if not query_yes_no(f"Do you want to run the sampling with {args.config_file}?"):
        sys.exit()

    print("\nStarting Sampling Script\n")

    # Create a row for the study timeframe in table study_timeframe
    insert_to_db(
        table_name="study_timeframe",
        columns=["study_timeframe_id", "name", "description"],
        values=[(study_id, study_name, study_description)],
        id_column="study_timeframe_id",
        id_var=study_id,
        **kwargs,
    )

    # Get rows for the periods
    period_values = get_period_values(study_id, start_year, end_year, period_length)

    # Insert rows for the periods into the period table
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
        values=period_values,
        id_column="study_timeframe_id",
        id_var=study_id,
        **kwargs,
    )

    # Insert new scenario in time_sample table
    insert_to_db(
        table_name="time_sample",
        columns=[
            "time_sample_id",
            "study_timeframe_id",
            "name",
            "method",
            "description",
        ],
        values=[(time_sample_id, study_id, name, method, description)],
        id_column="time_sample_id",
        id_var=time_sample_id,
        **kwargs,
    )

    # Get the sampler for the given method
    sampler = sampling_methods[method]
    # Get the sampled timeseries and sampled_tps rows
    timeseries, sampled_tps = sampler(
        method_config=method_config,
        period_values=period_values,
        **kwargs,
    )

    # Add the time_sample_id and study_timeframe_id columns
    timeseries["study_timeframe_id"] = study_id
    timeseries["time_sample_id"] = time_sample_id
    sampled_tps["study_timeframe_id"] = study_id
    sampled_tps["time_sample_id"] = time_sample_id

    # Insert the sampled_timeseries into the database
    insert_to_db(
        table_name="sampled_timeseries",
        columns=timeseries.columns,
        values=[tuple(r) for r in timeseries.to_numpy()],
        id_column="time_sample_id",
        id_var=time_sample_id,
        **kwargs,
    )

    # Insert the sampled_timepoints into the database
    insert_to_db(
        table_name="sampled_timepoint",
        columns=sampled_tps.columns,
        values=[tuple(r) for r in sampled_tps.to_numpy()],
        id_column="time_sample_id",
        id_var=time_sample_id,
        **kwargs,
    )

    print("+ Done.")


if __name__ == "__main__":
    main()
