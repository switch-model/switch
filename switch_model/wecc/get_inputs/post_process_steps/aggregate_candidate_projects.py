"""
This get_inputs post-process step aggregates candidate plants of a certain type within the same load zone
to simplify model complexity.

Implementation details:

1. We first aggregate the plants in generation_projects_info.csv.
    - We average the connection costs (weighted by capacity limit)
    - We sum the capacity limit

2. We verify that the build costs are the same for all the aggregated projects and update build_costs.csv

3. We aggregate the variable_capacity_factors.csv by averaging the values for each timepoint
"""
import numpy as np
import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process


@register_post_process(
    name="aggregate_projects_by_zone",
    msg="Aggregating candidate projects by load zone for specified technologies",
    only_with_config=True,
    priority=4
)
def main(config):
    agg_techs = config["agg_techs"]
    cf_quantile = config["cf_quantile"]
    assert type(agg_techs) == list
    # Don't allow hydro to be aggregated since we haven't implemented how to handle
    # hydro_timeseries.csv
    assert "Hydro_NonPumped" not in agg_techs
    assert "Hydro_Pumped" not in agg_techs

    print(f"\t\tAggregating on projects where gen_tech in {agg_techs}")
    key = "GENERATION_PROJECT"

    #################
    # 1. Aggregate generation_projects_info.csv
    ################
    # Keep only the projects we want to aggregate (must be candidate and in agg_techs)
    # save the projects we're not aggregating into projects_no_agg for later
    filename = "generation_projects_info.csv"
    df = pd.read_csv(filename, index_col=False, dtype={key: str})
    columns = df.columns.values
    predetermined = pd.read_csv("gen_build_predetermined.csv", usecols=[key], dtype={key: str})[key]
    should_agg = df["gen_tech"].isin(agg_techs) & (~df[key].isin(predetermined))
    projects_no_agg = df[~should_agg]
    df = df[should_agg]

    # Drop the db_id column since we're creating a new project
    df = df.drop("gen_dbid", axis=1)

    # Specify the new project id (e.g. agg_Wind_CA_SGE) and save a mapping of keys to aggregate keys for later
    df["agg_key"] = "agg_" + df["gen_tech"] + "_" + df["gen_load_zone"]
    keys_to_agg = df[[key, "agg_key"]]
    df = df.astype({"gen_capacity_limit_mw": float})
    keys_to_agg["weight"] = df["gen_capacity_limit_mw"]
    df[key] = df.pop("agg_key")

    # Aggregate
    def agg_projects(x):
        x = x.copy()
        connect_cost = x.pop("gen_connect_cost_per_mw")
        capacity_limit = x.pop("gen_capacity_limit_mw")

        # Verify that there are no differences among the columns we are not aggregating
        x = x.drop_duplicates()
        if len(x) != 1:
            num_unique = x.nunique()
            non_unique_values = num_unique[num_unique != 1].index.values
            raise Exception(
                f"The following columns are not unique and we do not know how to aggregate them: {non_unique_values}")

        # Set the aggregated columns
        x["gen_capacity_limit_mw"] = capacity_limit.sum()
        x["gen_connect_cost_per_mw"] = np.average(connect_cost, weights=capacity_limit)
        return x

    df = df.groupby(key, as_index=False).apply(agg_projects)

    # Add back the non aggregate projects and write to csv
    df = pd.concat([df, projects_no_agg])
    df[columns].to_csv(filename, index=False)

    ############
    # 2. Update gen_build_costs.csv
    ############
    # Read the file and filter aggregated
    filename = "gen_build_costs.csv"
    df = pd.read_csv(filename, index_col=False, dtype={key: str})
    columns = df.columns.values
    should_agg = df[key].isin(keys_to_agg[key])
    df_keep = df[~should_agg]
    df = df[should_agg]
    # Replace the plant id with the aggregated plant id
    df = df \
        .merge(keys_to_agg,
               on=key,
               how='left',
               validate="many_to_one") \
        .drop([key, "weight"], axis=1) \
        .rename({"agg_key": key}, axis=1)

    # Aggregate
    def agg_costs(x):
        # Verify that there are no differences among the columns we are not aggregating
        x = x.drop_duplicates()
        if len(x) != 1:
            num_unique = x.nunique()
            non_unique_values = num_unique[num_unique != 1].index.values
            raise Exception(
                f"The following columns are not unique and we do not know how to aggregate them: {non_unique_values}")

        # Return the single row
        return x
    df = df \
        .groupby([key], as_index=False, dropna=False, sort=False) \
        .apply(agg_costs)
    df = pd.concat([df, df_keep])
    df[columns].to_csv(filename, index=False)


    #########
    # 3. Average the variable capacity factors
    #########
    # Fetch the capacity factors for the projects of interest
    filename = "variable_capacity_factors.csv"
    df = pd.read_csv(filename, index_col=False, dtype={key: str})
    columns = df.columns.values
    should_agg = df[key].isin(keys_to_agg[key])
    df_keep = df[~should_agg]
    df = df[should_agg]
    # Replace the plant id with the aggregated plant id
    df = df \
        .merge(keys_to_agg,
               on=key,
               how='left',
               validate="many_to_one") \
        .drop([key, "weight"], axis=1) \
        .rename({"agg_key": key}, axis=1)

    # Aggregate by group and key
    dfgroup = df.groupby([key, "timepoint"], as_index=False, dropna=False, sort=False)
    df = dfgroup.quantile(cf_quantile)
    # Code to take the weighted average
    # df = dfgroup \
    #     .quantile(lambda x: np.average(x["gen_max_capacity_factor"], weights=x["weight"])) \
    #     .rename({None: "gen_max_capacity_factor"}, axis=1)
    df = pd.concat([df, df_keep])
    df[columns].to_csv(filename, index=False)
