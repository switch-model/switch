import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import post_process_step
from switch_model.tools.drop import main as drop


@post_process_step(msg="Dropping all the zones outside of California")
def post_process(_):
    df = pd.read_csv("load_zones.csv", index_col=False)
    df = df[df["LOAD_ZONE"].str.startswith("CA_")]
    df.to_csv("load_zones.csv", index=False)
    drop(["--silent", "--no-confirm", "--run", "--inputs-dir", "."])
