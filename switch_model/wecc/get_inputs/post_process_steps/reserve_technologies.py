""" This post-process selects which technologies can provide reserves"""
# Standard packages
import os
import shutil

# Third-party packages
import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process


@register_post_process(
    name="no_fosill_reserve",
    msg="Aggregating candidate projects by load zone for specified technologies",
    only_with_config=True,
    priority=4
)
def post_process(config):
    """ This function sets to zero the column that allows each candidate technology to
    proividee"""

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
