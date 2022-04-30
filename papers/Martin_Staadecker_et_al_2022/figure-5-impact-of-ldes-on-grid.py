# %% GET TOOLS

# Imports
import matplotlib.gridspec
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import cm
from matplotlib.ticker import PercentFormatter
from matplotlib.colors import Normalize
import labellines

from papers.Martin_Staadecker_et_al_2022.util import (
    set_style,
    get_set_e_scenarios, save_figure,
)
from switch_model.tools.graph.main import GraphTools

# Prepare graph tools
tools = GraphTools(scenarios=get_set_e_scenarios(), set_style=False)
tools.pre_graphing(multi_scenario=True)

# %% CREATE FIGURE
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(6.850394, 6.850394)
gs = matplotlib.gridspec.GridSpec(2, 2, figure=fig)
ax1 = fig.add_subplot(gs[0, 0])
ax2 = fig.add_subplot(gs[0, 1])
ax3 = fig.add_subplot(gs[1, :])

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
buildout = (
    buildout.groupby("scenario_name")["BuildGen"].sum().rename("Built Generation")
)

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

# dotted_tx = df.loc[[1.94, 3, 20, 64], ["Built Transmission"]]

# Plot
colors = tools.get_colors()
colors["Built Transmission"] = "y"
colors["Built Generation"] = "r"
# dotted_tx.plot(ax=ax, linestyle="dashed", color="y", alpha=0.8)
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
curtailment["value"] = (
    curtailment["Curtailment_MW"] * curtailment["tp_weight_in_year_hrs"] / 1000
)
curtailment = curtailment.groupby(
    ["scenario_name", "gen_type"], as_index=False
).value.sum()
curtailment = curtailment.pivot(
    index="scenario_name", columns="gen_type", values="value"
)
curtailment /= 1000
curtailment = curtailment.rename_axis("Technology", axis=1)
curtailment.plot(ax=ax, color=tools.get_colors(), marker=".")
ax.set_ylabel("Yearly curtailment (GWh)")
ax.set_xlabel("WECC-wide storage capacity (TWh)")
ax.set_title("A. Impact of LDES on curtailment")
ax.tick_params(top=False, bottom=False, right=False, left=False)
# %% State of charge
ax = ax3
ax.clear()
axr = ax.twinx()
axr.grid(False)

freq = "1D"

state_of_charge = tools.get_dataframe("StateOfCharge.csv")
state_of_charge = state_of_charge.rename(
    {"STORAGE_GEN_TPS_2": "timepoint", "StateOfCharge": "value"}, axis=1
)
state_of_charge = state_of_charge.groupby(
    ["scenario_name", "timepoint"], as_index=False
).value.sum()
state_of_charge.value *= 1e-6  # Convert from MWh to TWh
state_of_charge = tools.transform.timestamp(state_of_charge, use_timepoint=True)
state_of_charge = state_of_charge.set_index("datetime")
state_of_charge = state_of_charge.groupby("scenario_name").resample(freq).value.mean()
state_of_charge = state_of_charge.unstack("scenario_name").rename_axis(
    "Storage Capacity (TWh)", axis=1
)

demand = tools.get_dataframe("loads.csv", from_inputs=True).rename(
    {"TIMEPOINT": "timepoint", "zone_demand_mw": "value"}, axis=1
)
demand = demand[demand.scenario_name == 1.94]
demand = demand.groupby("timepoint", as_index=False).value.sum()
demand = tools.transform.timestamp(demand, use_timepoint=True)
demand = demand.set_index("datetime")["value"]
demand *= 4 * 1e-6  # Each timestep is 4 hours, converting to TWh
total_demand = demand.sum()
print(total_demand)
demand = demand.resample(freq).sum()

state_of_charge.plot(
    ax=ax,
    cmap="viridis",
    ylabel="WECC-wide stored energy (TWh, 24h mean)",
    xlabel="Time of year",
    legend=False,
)


lines = ax.get_lines()
x_label = {
    # 4.0: 135,
    8.0: 150,
    20.0: 170,
    24.0: 230,
    32.0: 245,
    48.0: 260,
    64.0: 285
}
for line in lines:
    label = float(line.get_label())
    if label not in x_label.keys():
        continue
    labellines.labelLine(line, state_of_charge.index[x_label[label]], linespacing=1, outline_width=1, label=str(int(label))+"TWh", align=False, color='k', fontsize="small")

demand = demand.iloc[1:-1]
demand_lines = axr.plot(demand, c="dimgray", linestyle="--", alpha=0.5)
axr.legend(demand_lines, [f"Demand ({total_demand:.0f} TWh/year)"])

ax.set_ylim(0, 65)
axr.set_ylim(0, 65 / 10)
axr.set_ylabel("Demand (TWh/day)")

ax.set_title("C. State of charge throughout the year")

plt.tight_layout()

plt.colorbar(
    cm.ScalarMappable(norm=Normalize(1.94, 64), cmap="viridis"),
    ax=ax,
    label="Storage Capacity (TWh)",
    fraction=0.1,
    pad=0.1
)
# %% SAVE FIGURE
save_figure("figure-5-impact-of-ldes-on-grid.png")

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
1 - cap / cap.loc[20]  # wind decrease %
cap / cap.loc[20] - 1  # solar increase %
(cap - cap.loc[20]) / 1000
# %% transmission
100 - tx / tx.iloc[0] * 100
# (3 - 1.94) * 1000 / ((1 - tx.loc[3] / tx.iloc[0]) * 100)

