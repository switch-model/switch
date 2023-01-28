import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import post_process_step


@post_process_step(msg="Reducing hydro average flows")
def post_process(derate_ratio):
    filename = "hydro_timeseries.csv"
    df = pd.read_csv(filename, index_col=False, na_values=".")
    df["hydro_avg_flow_mw"] *= derate_ratio
    df["hydro_min_flow_mw"] = df[["hydro_min_flow_mw", "hydro_avg_flow_mw"]].min(axis=1)
    df.to_csv(filename, index=False, na_rep=".")
