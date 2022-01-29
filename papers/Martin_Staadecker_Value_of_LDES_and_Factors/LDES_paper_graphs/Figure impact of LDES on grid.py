# %% GET TOOLS

# Imports
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import PercentFormatter

from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    get_scenario,
    set_style,
)
from switch_model.tools.graph.main import GraphTools


# Prepare graph tools
tools = GraphTools(
    scenarios=[
        get_scenario("1342", name=1.94),
        get_scenario("M7", name=2),
        get_scenario("M10", name=2.5),
        get_scenario("M9", name=3),
        get_scenario("M6", name=4),
        get_scenario("M5", name=8),
        get_scenario("M11", name=12),
        get_scenario("M4", name=16),
        get_scenario("M14", name=18),
        get_scenario("M13", name=20),
        get_scenario("M8", name=24),
        get_scenario("M3", name=32),
        get_scenario("M12", name=48),
        get_scenario("M2", name=64),
    ]
)
tools.pre_graphing(multi_scenario=True)

# %% CREATE FIGURE
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(12, 12)
ax1 = fig.add_subplot(2, 2, 1)
ax2 = fig.add_subplot(2, 2, 2)
ax3 = fig.add_subplot(2, 2, 3)
ax4 = fig.add_subplot(2, 2, 4)

# %% Daily LMP

ax = ax3
ax.clear()
time_mapping = {
    0: "Midnight",
    4: "4am",
    8: "8am",
    12: "Noon",
    16: "4pm",
    20: "8pm"
}
daily_lmp = tools.get_dataframe(
    "load_balance.csv",
    usecols=[
        "timestamp",
        "normalized_energy_balance_duals_dollar_per_mwh",
        "scenario_name",
    ],
).rename(columns={"normalized_energy_balance_duals_dollar_per_mwh": "value"})
daily_lmp = tools.transform.timestamp(daily_lmp)
daily_lmp = daily_lmp.groupby(["scenario_name", "hour"], as_index=False)["value"].mean()
daily_lmp = daily_lmp.pivot(index="scenario_name", columns="hour", values="value")
daily_lmp *= 0.1  # Convert from $/MWh to cents/kWh
daily_lmp = daily_lmp.rename(time_mapping, axis=1).rename_axis("Time of day (PST)", axis=1)
daily_lmp.plot(
    ax=ax,
    xlabel="WECC-wide storage capacity (TWh)",
    marker=".",
    ylabel=u"Estimated LMP (\xa2/kWh)",
    # cmap="tab10"
)
ax.set_title("C. Average estimated LMP by time of day")
# %% YEARLY LMP
ax = ax4
ax.clear()
scenarios_for_yearly_lmp = [5, 7, 8, 11, 12]

cap = tools.get_dataframe(
    "load_balance.csv",
    usecols=[
        "timestamp",
        "normalized_energy_balance_duals_dollar_per_mwh",
        "scenario_name",
    ],
).rename(columns={"normalized_energy_balance_duals_dollar_per_mwh": "value"})
cap = cap.groupby(["scenario_name", "timestamp"], as_index=False).mean()
cap = tools.transform.timestamp(cap)
cap = cap.set_index("datetime")
cap["month"] = cap.index.month
cap = cap.groupby(["scenario_name", "month"]).value.mean()
cap = cap.unstack("month").rename_axis("Storage Capacity (TWh)", axis=1)
# Convert from $/MWh to cents/kWh
cap *= 0.1
cap = cap[scenarios_for_yearly_lmp]
cap = cap.rename({
    5: "May",
    7: "July",
    8: "August",
    11: "November",
    12: "December",
}, axis=1)
cap.plot(
    ax=ax,
    xlabel="WECC-wide storage capacity (TWh)",
    marker=".",
    ylabel=u"Monthly-average estimated LMP (\xa2/kWh)",
    # cmap="tab10"
)
ax.set_title("D. Average estimated LMP during key months")
# %% IMPACT ON TX AND GEN

ax = ax2
ax.clear()
# Calculate transmission
tx = tools.get_dataframe(
    "transmission.csv",
    usecols=["BuildTx", "trans_length_km", "scenario_name"],
    convert_dot_to_na=True,
).fillna(0)
tx["BuildTx"] *= tx["trans_length_km"]
tx = tx.groupby("scenario_name")["BuildTx"].sum().rename("Built Transmission")

# Get new buildout
buildout = tools.get_dataframe("BuildGen.csv").rename(
    columns={"GEN_BLD_YRS_1": "GENERATION_PROJECT"}
)
# Keep only latest year
buildout = buildout[buildout["GEN_BLD_YRS_2"] == 2050]
# Merge with projects to get gen_type
projects = tools.get_dataframe(
    "generation_projects_info.csv",
    from_inputs=True,
    usecols=["GENERATION_PROJECT", "gen_tech", "gen_energy_source", "scenario_name"],
)
buildout = buildout.merge(
    projects,
    on=["GENERATION_PROJECT", "scenario_name"],
    validate="one_to_one",
    how="left",
)
del projects
buildout = tools.transform.gen_type(buildout)
# Filter out storage since it's not considered generation
buildout = buildout[buildout["gen_type"] != "Storage"]
# Sum across the entire scenario
buildout = buildout.groupby("scenario_name")["BuildGen"].sum().rename("Built Generation")

cap = tools.get_dataframe(
    "gen_cap.csv",
    usecols=["gen_tech", "gen_energy_source", "GenCapacity", "scenario_name"],
).rename({"GenCapacity": "value"}, axis=1)
cap = tools.transform.gen_type(cap)
cap = cap.groupby(["scenario_name", "gen_type"], as_index=False).value.sum()
cap = cap[cap["gen_type"].isin(("Wind", "Solar", "Biomass"))]
cap = cap.pivot(index="scenario_name", columns="gen_type", values="value")

# Merge into same dataframe
df = pd.concat([tx, buildout, cap], axis=1)

# Convert to percent against baseline
df = (df / df.iloc[0] - 1) * 100

dotted_tx = df.loc[[1.94,3,20,64], ["Built Transmission"]]

# Plot
colors = tools.get_colors()
colors["Built Transmission"] = "y"
colors["Built Generation"] = "r"
dotted_tx.plot(ax=ax, linestyle="dashed", color="y", alpha=0.8)
df.plot(ax=ax, marker=".", color=colors)
ax.set_ylabel("Change in capacity compared to baseline")
ax.yaxis.set_major_formatter(PercentFormatter())
ax.set_xlabel("WECC-wide storage capacity (TWh)")
ax.set_title("B. Impact of LDES on transmission and generation capacity")
ax.set_ylim(-100, None)
# %% CURTAILMENT

# Read dispatch.csv
ax = ax1
curtailment = tools.get_dataframe(
    "dispatch.csv",
    usecols=[
        "gen_tech",
        "gen_energy_source",
        "Curtailment_MW",
        "is_renewable",
        "tp_weight_in_year_hrs",
        "scenario_name",
    ],
    na_filter=False,  # For performance
)
# Keep only renewable
curtailment = curtailment[curtailment["is_renewable"]]
# Add the gen_type column
curtailment = tools.transform.gen_type(curtailment)
# Convert to GW
curtailment["value"] = curtailment["Curtailment_MW"] * curtailment["tp_weight_in_year_hrs"] / 1000
curtailment = curtailment.groupby(["scenario_name", "gen_type"], as_index=False).value.sum()
curtailment = curtailment.pivot(index="scenario_name", columns="gen_type", values="value")
curtailment /= 1000
curtailment = curtailment.rename_axis("Technology", axis=1)
curtailment.plot(ax=ax, color=tools.get_colors(), marker=".")
ax.set_ylabel("Yearly curtailment (GWh)")
ax.set_xlabel("WECC-wide storage capacity (TWh)")
ax.set_title("A. Impact of LDES on curtailment")
ax.tick_params(top=False, bottom=False, right=False, left=False)
# %%
plt.subplots_adjust(hspace=0.2, wspace=0.25, left=0.07, right=0.97, top=0.95, bottom=0.07)

# %% CALCULATIONS
cap_total = cap["Solar"] + cap["Wind"]
1 - (cap_total / cap_total.iloc[0])
# %%
cap_total
# %%
1 - buildout / buildout.iloc[0]
# %% biomass decrease
1 - cap / cap.iloc[0]
cap - cap.iloc[0]
# %% change from 20 to 64
1 - cap / cap.loc[20] # wind decrease %
cap / cap.loc[20] - 1 # solar increase %
(cap - cap.loc[20]) / 1000
# %% transmission
tx / tx.iloc[0] * 100
(3 - 1.94) * 1000 / ((1 - tx.loc[3] / tx.iloc[0]) * 100)
# %% night time vs day time
df = daily_lmp.divide(daily_lmp["Noon"], axis=0) * 100 - 100
df.min()
df.max()
# %% average drop in daily duals
df = daily_lmp.mean(axis=1)
df / df.iloc[0] - 1
daily_lmp / daily_lmp.iloc[0] - 1
