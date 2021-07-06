import os
import shutil

import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process


@register_post_process("Creating graph files")
def create_graph_files():
    graph_config = os.path.join(os.path.dirname(__file__), "graph_config")
    shutil.copy(os.path.join(graph_config, "graph_tech_colors.csv"), "graph_tech_colors.csv")
    shutil.copy(os.path.join(graph_config, "graph_tech_types.csv"), "graph_tech_types.csv")
    create_graph_timestamp_map()

def create_graph_timestamp_map():
    timepoints = pd.read_csv("timepoints.csv", index_col=False)
    timeseries = pd.read_csv("timeseries.csv", index_col=False)

    timepoints = timepoints.merge(
        timeseries,
        how='left',
        left_on='timeseries',
        right_on='TIMESERIES',
        validate="many_to_one"
    )

    timepoints["time_column"] = timepoints["timeseries"].apply(lambda c: c.partition("-")[2])

    timestamp_map = timepoints[["timestamp", "ts_period", "time_column"]]
    timestamp_map.columns = ["timestamp", "time_row", "time_column"]
    timestamp_map.to_csv("graph_timestamp_map.csv", index=False)