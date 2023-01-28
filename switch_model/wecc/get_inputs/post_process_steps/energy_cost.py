# Standard packages
import os
import shutil

# Third-party packages
import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import post_process_step


@post_process_step(
    msg="Change energy cost for storage candidate",
)
def post_process(func_config):

    percentage = int(func_config["percentage"]) / 100
    dtype = {"GENERATION_PROJECT": str}
    df = pd.read_csv("generation_projects_info.csv", dtype=dtype)
    costs = pd.read_csv("gen_build_costs.csv", dtype=dtype)
    predetermined = pd.read_csv("gen_build_predetermined.csv", dtype=dtype)

    gen_projects = df.merge(
        costs,
        on="GENERATION_PROJECT",
    )

    gen_projects = gen_projects.merge(
        predetermined,
        on=["GENERATION_PROJECT", "build_year"],
        how="left",  # Makes a left join
    )

    # Get candiate technology only
    candidate = gen_projects.query("build_year == 2050").query(
        "gen_tech =='Battery_Storage'"
    )

    # Get canidate generation project id
    candidate_ids = candidate["GENERATION_PROJECT"].values

    gen_cost_mwh = costs.loc[
        costs["GENERATION_PROJECT"].isin(candidate_ids),
        "gen_storage_energy_overnight_cost",
    ].astype(float)

    # Set to zero column that allows technology to provide reserves
    costs.loc[
        costs["GENERATION_PROJECT"].isin(candidate_ids),
        "gen_storage_energy_overnight_cost",
    ] = (
        gen_cost_mwh * percentage
    )

    # Save file again
    costs.to_csv("gen_build_costs.csv", index=False)
