import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process
from switch_model.tools.drop import main as drop


@register_post_process(
    name="only_california",
    msg="Dropping all the zones outside of California",
    priority=3
)
def main(_):
    df = pd.read_csv("load_zones.csv", index_col=False)
    df = df[df["LOAD_ZONE"].str.startswith("CA_")]
    df.to_csv("load_zones.csv", index=False)
    drop(["--silent", "--no-confirm", "--run", "--inputs-dir", "."])
