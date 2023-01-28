import argparse
import sys

import yaml

from switch_model.utilities import query_yes_no
from switch_model.wecc.get_inputs.scenario import load_scenario_from_config
from switch_model.wecc.utilities import connect, load_config


def main():
    # Start CLI
    parser = argparse.ArgumentParser(
        description="Creates a new scenario in the database by using the values in"
        " config.yaml. Therefore the new scenario will have the same values"
        " as the base scenario but you can override specific columns by "
        " specifying them in config.yaml."
    )
    parser.add_argument(
        "scenario_id", type=int, help="The id of the new scenario to add to db."
    )
    parser.add_argument(
        "--name", required=True, help="The name of the new scenario to add in db."
    )
    parser.add_argument(
        "--description",
        required=True,
        help="The new scenario description to add in db.",
    )
    parser.add_argument(
        "--db-env-var", default="DB_URL", help="The connection environment variable."
    )

    # Optional arguments
    parser.add_argument(
        "--config_file",
        default="config.yaml",
        type=str,
        help="Configuration file to use.",
    )

    args = parser.parse_args()

    # Start db connection
    db_conn = connect(connection_env_var=args.db_env_var)
    db_cursor = db_conn.cursor()

    # # Exit if you are not sure if you want to overwrite
    # if args.overwrite:

    config = load_config()
    scenario_params = load_scenario_from_config(config, db_cursor)

    # Override the given parameters
    scenario_params.name = args.name
    scenario_params.description = args.description
    scenario_params.scenario_id = args.scenario_id

    ordered_params = list(
        filter(lambda v: v[1] is not None, scenario_params.__dict__.items())
    )
    columns = ",".join(v[0] for v in ordered_params)
    values = ",".join(
        f"'{v[1]}'" if type(v[1]) == str else str(v[1]) for v in ordered_params
    )

    query = f"""INSERT INTO scenario({columns}) VALUES  ({values});"""

    print(f"\n{query}\n")

    if not query_yes_no(
        f"Are you sure you want to run the above query.?", default="no"
    ):
        sys.exit()

    db_cursor.execute(query)
    db_conn.commit()
    db_cursor.close()
    db_conn.close()

    print(f"Ran query.")
