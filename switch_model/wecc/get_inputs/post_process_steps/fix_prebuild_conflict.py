import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process


@register_post_process("Shifting 2020 pre-build years to 2019")
def fix_prebuild_conflict_bug():
    """
    This post-processing step is necessary to pass the no_predetermined_bld_yr_vs_period_conflict BuildCheck.
    Basically we are moving all the 2020 predetermined build years to 2019 to avoid a conflict with the 2020 period.
    See generators.core.build.py for details.
    """
    periods = pd.read_csv("periods.csv", index_col=False)
    if 2020 not in periods["INVESTMENT_PERIOD"].values:
        return

    # Read two files that need modification
    gen_build_costs = pd.read_csv("gen_build_costs.csv", index_col=False)
    gen_build_predetermined = pd.read_csv("gen_build_predetermined.csv", index_col=False)
    # Save their size
    rows_prior = gen_build_costs.size, gen_build_predetermined.size
    # Save columns of gen_build_costs
    gen_build_costs_col = gen_build_costs.columns
    # Merge to know which rows are prebuild
    gen_build_costs = gen_build_costs.merge(
        gen_build_predetermined,
        on=["GENERATION_PROJECT", "build_year"],
        how='left'
    )

    # If row is prebuild and in 2020, replace it with 2019
    gen_build_costs.loc[
        (~gen_build_costs["gen_predetermined_cap"].isna()) & (gen_build_costs["build_year"] == 2020),
        "build_year"] = 2019
    # If row is in 2020 replace it with 2019
    gen_build_predetermined.loc[gen_build_predetermined["build_year"] == 2020, "build_year"] = 2019
    # Go back to original column set
    gen_build_costs = gen_build_costs[gen_build_costs_col]

    # Ensure the size is still the same
    rows_post = gen_build_costs.size, gen_build_predetermined.size
    assert rows_post == rows_prior

    # Write the files back out
    gen_build_costs.to_csv("gen_build_costs.csv", index=False)
    gen_build_predetermined.to_csv("gen_build_predetermined.csv", index=False)