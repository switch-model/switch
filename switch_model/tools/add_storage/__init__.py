"""
This package was created by Martin Staadecker
when studying long duration energy storage. It
allows adding storage technologies from a csv file to
the csvs in the inputs folder.
"""
import os

import pandas as pd
from switch_model.wecc.get_inputs import replace_plants_in_zone_all

scenario_params = {}

def fetch_df(tab_name):
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
    return df


def filer_by_scenario(df, column_name):
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


def append_to_csv(filename, to_add):
    df = pd.read_csv(filename, index_col=False)
    col = df.columns
    df = pd.concat([df, to_add], ignore_index=True)[col]
    df.to_csv(filename, index=False)


def get_gen_constants():
    df = fetch_df("constants")
    df = filer_by_scenario(df, "constant_scenario")
    df = df.set_index("param_name")
    return df.transpose()


def main(run_post_solve=True, scenario_config=None, change_dir=True):
    print("Adding candidate storage from GSheets...")
    global scenario_params
    # If a config is passed use it when filtering by scenario
    if scenario_config is not None:
        scenario_params = scenario_config

    # Move to input directory
    if change_dir:
        os.chdir("inputs")

    # Get the generation storage plants from Google Sheet
    gen_constants = get_gen_constants()
    gen_plants = fetch_df("plants")
    gen_plants = cross_join(gen_plants, gen_constants)

    # Append the storage plants to the inputs
    append_to_csv("generation_projects_info.csv", gen_plants)

    # Get the plant costs from GSheets and append to costs
    storage_costs = filer_by_scenario(fetch_df("costs"), "costs_scenario")
    append_to_csv("gen_build_costs.csv", storage_costs)

    # Change plants with _ALL_ZONES to a plant in every zone
    if run_post_solve:
        replace_plants_in_zone_all()

    # Create add_storage_info.csv
    pd.DataFrame([scenario_params]).transpose().to_csv("add_storage_info.csv", header=False)


if __name__ == "__main__":
    main()
