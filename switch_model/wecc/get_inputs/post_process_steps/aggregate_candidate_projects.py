"""
This get_inputs post-process step aggregates candidate plants of a certain type within the same load zone
to simplify model complexity.

Implementation details:

1. We first aggregate the plants in generation_projects_info.csv.
    - We average the connection costs (weighted by capacity limit)
    - We sum the capacity limit

2. We verify that the build costs are the same for all the aggregated projects and update build_costs.csv

3. We aggregate the variable_capacity_factors.csv depending on the method specified in the parameter 'cf_method'.
    If cf_method="file" we use the variable capacity factors found in an external file.

-----
This file also contains the function create_capacity_factors() which will generate a file
called zonal_capacity_factors.csv that can be consumed by the post process step
with cf_method=file (see point #3 above). Details on how this file is created are available
in the documentation of that function.
"""
import warnings

import numpy as np
import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import post_process_step


@post_process_step(
    msg="Aggregating candidate projects by load zone for specified technologies"
)
def post_process(func_config):
    agg_techs = func_config["agg_techs"]
    cf_method = func_config["cf_method"]
    assert type(agg_techs) == list
    # Don't allow hydro to be aggregated since we haven't implemented how to handle
    # hydro_timeseries.csv
    assert "Hydro_NonPumped" not in agg_techs
    assert "Hydro_Pumped" not in agg_techs

    print(
        f"\t\tAggregating on projects where gen_tech in {agg_techs} with capacity factor method {cf_method}"
    )
    key = "GENERATION_PROJECT"

    #################
    # 1. Aggregate generation_projects_info.csv
    ################
    # Keep only the projects we want to aggregate (must be candidate and in agg_techs)
    # save the projects we're not aggregating into projects_no_agg for later
    filename = "generation_projects_info.csv"
    df = pd.read_csv(filename, index_col=False, dtype={key: str})
    columns = df.columns.values
    predetermined = pd.read_csv(
        "gen_build_predetermined.csv", usecols=[key], dtype={key: str}
    )[key]
    should_agg = df["gen_tech"].isin(agg_techs) & (~df[key].isin(predetermined))
    if cf_method == "file":
        # Filter out projects where we don't have a capacity factor
        try:
            zonal_cf = pd.read_csv("zonal_capacity_factors.csv", index_col=False)
        except FileNotFoundError:
            raise Exception(
                "Post process step 'aggregate_candidate_projects' with method 'file'"
                " requires an external zonal_capacity_factors.csv to exist. This file can be generated"
                " using the scripts in zonal_capacity_factors.csv."
            )
        valid_proj = df.merge(
            zonal_cf[["gen_load_zone", "gen_tech"]].drop_duplicates(),
            on=["gen_load_zone", "gen_tech"],
            how="right",
            validate="many_to_one",
        )[key]
        should_agg &= df[key].isin(valid_proj)
    projects_no_agg = df[~should_agg].copy()
    df = df[should_agg].copy()

    # Reset the dbid since we're creating a new project
    df["gen_dbid"] = "."

    # Specify the new project id (e.g. agg_Wind_CA_SGE) and save a mapping of keys to aggregate keys for later
    df["agg_key"] = "agg_" + df["gen_tech"] + "_" + df["gen_load_zone"]
    keys_to_agg = df[[key, "agg_key", "gen_tech", "gen_load_zone"]]
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
                f"The following columns are not unique and we do not know how to aggregate them: {non_unique_values}"
            )

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
    df = (
        df.merge(
            keys_to_agg[[key, "agg_key"]], on=key, how="left", validate="many_to_one"
        )
        .drop(key, axis=1)
        .rename({"agg_key": key}, axis=1)
    )

    # Aggregate
    def agg_costs(x):
        # Verify that there are no differences among the columns we are not aggregating
        x = x.drop_duplicates()
        if len(x) != 1:
            num_unique = x.nunique()
            non_unique_values = num_unique[num_unique != 1].index.values
            raise Exception(
                f"The following columns are not unique and we do not know how to aggregate them: {non_unique_values}"
            )

        # Return the single row
        return x

    df = df.groupby([key], as_index=False, dropna=False, sort=False).apply(agg_costs)
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
    df = (
        df.merge(keys_to_agg, on=key, how="left", validate="many_to_one")
        .drop(key, axis=1)
        .rename({"agg_key": key}, axis=1)
    )

    # Aggregate by group and timepoint
    dfgroup = df.groupby([key, "timepoint"], as_index=False, dropna=False, sort=False)
    if cf_method == "95_quantile":
        df = dfgroup.quantile(0.95)
    elif cf_method == "weighted_mean":
        # Code to take the weighted average
        df = dfgroup.quantile(
            lambda x: np.average(x["gen_max_capacity_factor"], weights=x["weight"])
        ).rename({None: "gen_max_capacity_factor"}, axis=1)
    elif cf_method == "file":
        df = df.drop(["gen_max_capacity_factor", "weight"], axis=1).drop_duplicates()
        df = df.merge(
            zonal_cf, on=["gen_load_zone", "timepoint", "gen_tech"], how="left"
        )
    else:
        raise NotImplementedError(f"Method '{cf_method}' is not implemented.")
    df = pd.concat([df[columns], df_keep])
    df[columns].to_csv(filename, index=False)


def create_capacity_factors():
    """
    This function creates a zonal_capacity_factors.csv file
    that contains capacity factors aggregated by load_zone, timepoint and technology based on the dispatch
    instructions for *candidate* renewable plants from the results of a previous run. Capacity
    factors are calculated by aggregating all the candidate plants of the same gen_tech within a load
    zone and using the following equation

    capacity factor = (DispatchGen + Curtailment) / (GenCapacity  * (1 - gen_forced_outage_rate))

    This equation is essentially calculating the aggregated variable capacity factor for
    the entire load zone by reversing how DispatchUpperLimit is calculated in the SWITCH model.
    See switch_model.generators.core.no_commit.py

    Note that capacity factors are only calculated for technologies where all the candidate
    plants are variable and not baseload (baseload plants have a different way of calculating the outage rate).

    Further, if the results that are being used don't contain any built candidate plants in a load zone, no
    zonal capacity factor can be created for that zone (since we can't divide by GenCapacity when it's 0).
    This may cause certain load zones to remain un-aggregated when applying this file's post process step.
    A warning will be displayed when this function is run if a capacity factor can't be created for the load zone.

    This function requires the following files
        inputs/generation_projects_info.csv (to get gen_forced_outage_rate)
        inputs/gen_build_predetermined.csv (to know which projects are candidate projects)
        outputs/timestamps.csv (to find which timepoint matches which period)
        outputs/gen_cap.csv (to find the GenCapacity during any period)
        outputs/dispatch.csv (to know the DispatchGen and Curtailment)
    """
    # Read the projects
    projects = pd.read_csv(
        "inputs/generation_projects_info.csv",
        usecols=[
            "GENERATION_PROJECT",
            "gen_tech",
            "gen_is_variable",
            "gen_is_baseload",
            "gen_forced_outage_rate",
        ],
        dtype={"GENERATION_PROJECT": str},
        index_col=False,
    )
    # Filter out predetermined plants
    predetermined = pd.read_csv(
        "inputs/gen_build_predetermined.csv",
        usecols=["GENERATION_PROJECT"],
        dtype={"GENERATION_PROJECT": str},
        index_col=False,
    )["GENERATION_PROJECT"]
    n = len(projects)
    projects = projects[~projects["GENERATION_PROJECT"].isin(predetermined)]
    print(f"Removed {n - len(projects)} projects that were predetermined plants.")
    del predetermined
    # Determine the gen_techs where gen_is_variable is always True and gen_is_baseload is always False.
    # Grouping and summing works since summing Falses gives 0 but summing Trues gives >0.
    projects["gen_is_not_variable"] = ~projects["gen_is_variable"]
    grouped_projects = projects.groupby("gen_tech", as_index=False)[
        ["gen_is_not_variable", "gen_is_baseload"]
    ].sum()
    grouped_projects = grouped_projects[
        (grouped_projects["gen_is_not_variable"] == 0)
        & (grouped_projects["gen_is_baseload"] == 0)
    ]
    gen_tech = grouped_projects["gen_tech"]
    del grouped_projects
    print(f"Aggregating for gen_tech: {gen_tech.values}")

    # Filter out projects that aren't variable or are baseload
    n = len(projects)
    projects = projects[projects["gen_tech"].isin(gen_tech)]
    valid_gens = projects["GENERATION_PROJECT"]
    print(f"Removed {n - len(projects)} projects that aren't of allowed gen_tech.")

    # Calculate the gen_forced_outage_rate and verify it is identical for all the projects within the same group
    outage_rates = projects.groupby("gen_tech", as_index=False)[
        "gen_forced_outage_rate"
    ]
    if (outage_rates.nunique()["gen_forced_outage_rate"] - 1).sum() != 0:
        outage_rates = (
            outage_rates.nunique().set_index("gen_tech")["gen_forced_outage_rate"] - 1
        )
        outage_rates = outage_rates[outage_rates != 0]
        raise Exception(
            f"These generation technologies have different forced outage rates: {outage_rates.index.values}"
        )
    outage_rates = (
        outage_rates.mean()
    )  # They're all the same so mean returns the proper value
    del projects
    print("Check passed: gen_forced_outage_rate is identical.")

    # Read the dispatch instructions
    dispatch = pd.read_csv(
        "outputs/dispatch.csv",
        usecols=[
            "generation_project",
            "timestamp",
            "gen_tech",
            "gen_load_zone",
            "DispatchGen_MW",
            "Curtailment_MW",
        ],
        index_col=False,
        dtype={"generation_project": str},
    )
    # Keep only valid projects
    dispatch = dispatch[dispatch["generation_project"].isin(valid_gens)]
    # Group by timestamp, gen_tech and load_zone
    dispatch = dispatch.groupby(
        ["timestamp", "gen_tech", "gen_load_zone"], as_index=False
    ).sum()
    # Get the DispatchUpperLimit from DispatchGen + Curtailment
    dispatch["DispatchUpperLimit"] = (
        dispatch["DispatchGen_MW"] + dispatch["Curtailment_MW"]
    )
    dispatch = dispatch.drop(["DispatchGen_MW", "Curtailment_MW"], axis=1)

    # Add the period to each row by merging with outputs/timestamp.csv
    timestamps = pd.read_csv(
        "outputs/timestamps.csv",
        usecols=["timestamp", "timepoint", "period"],
        index_col=False,
    )
    dispatch = dispatch.merge(
        timestamps, on="timestamp", how="left", validate="many_to_one"
    )
    del timestamps

    # Read the gen_cap.csv
    cap = pd.read_csv(
        "outputs/gen_cap.csv",
        usecols=[
            "GENERATION_PROJECT",
            "PERIOD",
            "gen_tech",
            "gen_load_zone",
            "GenCapacity",
        ],
        index_col=False,
        dtype={"GENERATION_PROJECT": str},
    ).rename({"PERIOD": "period"}, axis=1)
    # Keep only valid projects
    cap = cap[cap["GENERATION_PROJECT"].isin(valid_gens)].drop(
        "GENERATION_PROJECT", axis=1
    )
    # Sum for the tech, period and load zone
    cap = cap.groupby(["period", "gen_tech", "gen_load_zone"], as_index=False).sum()
    # Merge onto dispatch
    dispatch = dispatch.merge(
        cap,
        on=["period", "gen_tech", "gen_load_zone"],
        how="left",
        validate="many_to_one",
    )
    del cap

    # Filter out zones with no buildout
    is_no_buildout = dispatch["GenCapacity"] == 0
    missing_data = (
        dispatch[is_no_buildout][["period", "gen_tech", "gen_load_zone"]]
        .drop_duplicates()
        .groupby(["period", "gen_tech"], as_index=False)["gen_load_zone"]
        .nunique()
        .rename({"gen_load_zone": "Number of Load Zones"}, axis=1)
    )
    if missing_data["Number of Load Zones"].sum() > 0:
        warnings.warn(
            f"Unable to make capacity factors for the following categories since total capacity in those zones is 0.\n{missing_data}"
        )
    dispatch = dispatch[~is_no_buildout]

    # Merge outage rates onto dispatch
    dispatch = dispatch.merge(outage_rates, on="gen_tech")
    del outage_rates

    dispatch["gen_max_capacity_factor"] = dispatch["DispatchUpperLimit"] / (
        dispatch["GenCapacity"] * (1 - dispatch["gen_forced_outage_rate"])
    )
    dispatch = dispatch[
        [
            "gen_tech",
            "gen_load_zone",
            "timestamp",
            "timepoint",
            "gen_max_capacity_factor",
        ]
    ]
    dispatch.to_csv("zonal_capacity_factors.csv", index=False)


if __name__ == "__main__":
    create_capacity_factors()
