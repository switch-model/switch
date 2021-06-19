"""
This package was created by Martin Staadecker
when studying long duration energy storage. It
allows adding storage technologies from a Google Sheet to
the csvs in the inputs folder.
"""
import os

import pandas as pd
from switch_model.wecc.get_inputs import replace_plants_in_zone_all

# Parameters picked for Google Sheet
scenario_params = {}

def fetch_df(tab_name, key=None):
    """
    Returns a dataframe from the google sheet
    """
    tab_name_to_gid = {
        "constants": 0,
        "plants": 889129113,
        "costs": 1401952285
    }
    gid = tab_name_to_gid[tab_name]
    sheet_id = "1SJrj039T1T95NLTs964VQnsfZgo2QWCo29x2ireVYcU"
    url = f"https://docs.google.com/spreadsheet/ccc?key={sheet_id}&output=csv&gid={gid}"
    df = pd.read_csv(url, index_col=False) \
        .replace("FALSE", 0) \
        .replace("TRUE", 1)
    if key is not None:
        df = filer_by_scenario(df, key)
    return df


def filer_by_scenario(df, column_name):
    """
    Filters a dataframe by a scenario param
    """
    if column_name not in scenario_params:
        scenario = input(f"Which scenario do you want for '{column_name}' (default 0) : ")
        if scenario == "":
            scenario = 0
        scenario_params[column_name] = int(scenario)
    df = df[df[column_name] == scenario_params[column_name]]
    return df.drop(column_name, axis=1)


def cross_join(df1, df2):
    return df1.assign(key=1).merge(
        df2.assign(key=1),
        on="key"
    ).drop("key", axis=1)


def append_to_csv(filename, to_add, primary_key=None):
    """
    Used to append a dataframe to an input .csv file
    """
    df = pd.read_csv(filename, index_col=False)
    col = df.columns
    df = pd.concat([df, to_add], ignore_index=True)[col]
    # Confirm that primary_key is unique
    if primary_key is not None:
        assert len(df[primary_key]) == len(df[primary_key].drop_duplicates())
    df.to_csv(filename, index=False)


def get_gen_constants():
    df = fetch_df("constants", "constant_scenario")
    df = df.set_index("param_name")
    return df.transpose()

def drop_previous_candidate_storage():
    """
    Drops all candidate storage from the model
    """
    # Get the generation projects
    gen = pd.read_csv("generation_projects_info.csv", index_col=False)
    # Find generation projects that are both storage and not predetermined (i.e. candidate)
    predetermined_gen = pd.read_csv("gen_build_predetermined.csv", index_col=False)["GENERATION_PROJECT"]
    should_drop = (gen["gen_tech"] == "Battery_Storage") & ~gen["GENERATION_PROJECT"].isin(predetermined_gen)
    # Find projects that we should drop (candidate storage)
    gen_to_drop = gen[should_drop]["GENERATION_PROJECT"]
    # Verify we're dropping the right amount
    assert len(gen_to_drop) == 50 # 50 is the number of load zones. we expect one candidate per load zone

    # Drop and write output
    gen = gen[~should_drop]
    gen.to_csv("generation_projects_info.csv", index=False)

    # Drop the dropped generation projects from gen_build_costs.csv
    costs = pd.read_csv("gen_build_costs.csv", index_col=False)
    costs = costs[~costs["GENERATION_PROJECT"].isin(gen_to_drop)]
    costs.to_csv("gen_build_costs.csv", index=False)

def main(run_post_solve=True, scenario_config=None, change_dir=True):
    print("Adding candidate storage from GSheets...")
    global scenario_params
    # If a config is passed use it when filtering by scenario
    if scenario_config is not None:
        scenario_params = scenario_config

    # Move to input directory
    if change_dir:
        os.chdir("inputs")

    # Drop previous candidate storage from inputs
    drop_previous_candidate_storage()

    # Get the generation storage plants from Google Sheet
    gen_constants = get_gen_constants()
    gen_plants = fetch_df("plants", "plants_scenario")
    gen_plants = cross_join(gen_plants, gen_constants)

    # Append the storage plants to the inputs
    append_to_csv("generation_projects_info.csv", gen_plants, primary_key="GENERATION_PROJECT")

    # Get the plant costs from GSheets and append to costs
    storage_costs = fetch_df("costs", "costs_scenario")
    append_to_csv("gen_build_costs.csv", storage_costs, primary_key=["GENERATION_PROJECT", "build_year"])

    # Change plants with _ALL_ZONES to a plant in every zone
    if run_post_solve:
        replace_plants_in_zone_all()

    # Create add_storage_info.csv
    pd.DataFrame([scenario_params]).transpose().to_csv("add_storage_info.csv", header=False)


if __name__ == "__main__":
    main()
