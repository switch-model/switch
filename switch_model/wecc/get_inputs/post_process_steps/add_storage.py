"""
This post-process step was created by Martin Staadecker
when studying long duration energy storage. It
allows adding storage technologies from a Google Sheet to
the csvs in the inputs folder.
"""
import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process


def fetch_df(tab_name, key, config):
    """
    Returns a dataframe from the google sheet and filters it by the key
    """
    TAB_NAME_GID = {
        "constants": 0,
        "plants": 889129113,
        "costs": 1401952285,
        "minimums": 1049456965
    }
    SHEET_ID = "1SJrj039T1T95NLTs964VQnsfZgo2QWCo29x2ireVYcU"

    gid = TAB_NAME_GID[tab_name]
    url = f"https://docs.google.com/spreadsheet/ccc?key={SHEET_ID}&output=csv&gid={gid}"

    df: pd.DataFrame = pd.read_csv(url, index_col=False) \
        .replace("FALSE", 0) \
        .replace("TRUE", 1)

    if "description" in df.columns:
        df = df.drop("description", axis=1)

    if key is not None:
        df = filer_by_scenario(df, key, config)
    return df


def filer_by_scenario(df, scenario_column, config):
    """
    Filters a dataframe by a scenario param
    """
    if scenario_column in config:
        scenario = config[scenario_column]
    else:
        scenario = input(f"Which scenario do you want for '{scenario_column}' (default 0) : ")
        scenario = int(scenario) if scenario != "" else 0
    df = df[df[scenario_column] == scenario]
    return df.drop(scenario_column, axis=1)


def cross_join(df1, df2):
    return df1.assign(key=1).merge(
        df2.assign(key=1),
        on="key"
    ).drop("key", axis=1)


def add_to_csv(filename, to_add, primary_key=None, append=True):
    """
    Used to append a dataframe to an input .csv file
    """
    if append:
        try:
            df = pd.read_csv(filename, index_col=False)
            df = pd.concat([df, to_add], ignore_index=True)[df.columns]
        except FileNotFoundError:
            df = to_add
    else:
        df = to_add
    # Confirm that primary_key is unique
    if primary_key is not None:
        assert len(df[primary_key]) == len(df[primary_key].drop_duplicates())
    df.to_csv(filename, index=False)


def drop_previous_candidate_storage():
    """
    Drops all candidate storage from the model
    """
    # Get the generation projects
    STORAGE_TECH = "Battery_Storage"

    gen = pd.read_csv("generation_projects_info.csv", index_col=False)
    # Find generation projects that are both storage and not predetermined (i.e. candidate)
    predetermined_gen = pd.read_csv("gen_build_predetermined.csv", index_col=False)["GENERATION_PROJECT"]
    should_drop = (gen["gen_tech"] == STORAGE_TECH) & ~gen["GENERATION_PROJECT"].isin(predetermined_gen)
    # Find projects that we should drop (candidate storage)
    gen_to_drop = gen[should_drop]["GENERATION_PROJECT"]

    # Drop and write output
    gen = gen[~should_drop]
    gen.to_csv("generation_projects_info.csv", index=False)

    # Drop the dropped generation projects from gen_build_costs.csv
    costs = pd.read_csv("gen_build_costs.csv", index_col=False)
    costs = costs[~costs["GENERATION_PROJECT"].isin(gen_to_drop)]
    costs.to_csv("gen_build_costs.csv", index=False)


@register_post_process(
    name="add_storage",
    msg="Adding storage from Google Sheets",
    only_with_config=True,
    priority=1  # Increased priority (default is 2) so that it always runs before replace_plants_in_zone_all.py
)
def main(config):
    # Drop previous candidate storage from inputs
    drop_previous_candidate_storage()

    # Get the generation storage plants from Google Sheet
    gen_projects = fetch_df("constants", "constant_scenario", config).set_index("param_name").transpose()
    gen_projects = cross_join(gen_projects, fetch_df("plants", "plants_scenario", config))

    # Append the storage plants to the inputs
    add_to_csv("generation_projects_info.csv", gen_projects, primary_key="GENERATION_PROJECT")

    # Create min_per_tech.csv
    min_projects = fetch_df("minimums", "minimums_scenario", config)
    add_to_csv("min_per_tech.csv", min_projects, primary_key=["gen_tech", "period"], append=False)

    # Get the plant costs from GSheets and append to costs
    storage_costs = fetch_df("costs", "costs_scenario", config)
    storage_costs = storage_costs[storage_costs["GENERATION_PROJECT"].isin(gen_projects["GENERATION_PROJECT"])]
    add_to_csv("gen_build_costs.csv", storage_costs, primary_key=["GENERATION_PROJECT", "build_year"])

    # Create add_storage_info.csv
    pd.DataFrame([config]).transpose().to_csv("add_storage_info.csv", header=False)

    # Add the storage types to the graphs
    gen_type = gen_projects[["gen_tech", "gen_energy_source"]].drop_duplicates()
    gen_type.columns = ["gen_tech", "energy_source"]
    gen_type["map_name"] = "default"
    gen_type["gen_type"] = "Storage"
    pd.concat([
        pd.read_csv("graph_tech_types.csv", index_col=False), gen_type
    ]).to_csv("graph_tech_types.csv", index=False)


if __name__ == "__main__":
    main({})
