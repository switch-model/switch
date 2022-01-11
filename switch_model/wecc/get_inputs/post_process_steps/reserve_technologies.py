""" This post-process selects which technologies can provide reserves"""
# Standard packages
import os
import shutil

# Third-party packages
import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import post_process_step


@post_process_step(
    msg="Removing fossil fuels from reserves.",
)
def post_process(_):
    """This function sets to zero the column that allows each candidate technology to
    provide"""

    fname = "generation_projects_info.csv"
    df = pd.read_csv(fname)

    # Energy sources to exclude from reserves
    filter_techs = ["ResidualFuelOil", "Gas", "DistillateFuelOil", "Coal"]

    # Set to zero column that allows technology to provide reserves
    df.loc[
        df["gen_energy_source"].isin(filter_techs), "gen_can_provide_cap_reserves"
    ] = 0

    # Save file again
    df.to_csv(fname, index=False)
