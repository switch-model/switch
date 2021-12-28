# %% IMPORTS AND SCENARIO DEFINITION
import matplotlib.gridspec
import pandas as pd
from matplotlib.ticker import ScalarFormatter
from matplotlib import pyplot as plt

import weightedcalcs

from switch_model.tools.graph.main import GraphTools
from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    get_scenario,
    set_style,
)

quartile_inner = 0.25
quartile = 0.05

# Define tools for wind to solar ratio set
baseline_ws_ratio = 0.187
# Get Graph tools
tools_ws_ratio = GraphTools(
    scenarios=[
        get_scenario("WS10", 0.0909),
        get_scenario("1342", baseline_ws_ratio),
        get_scenario("WS100", 0.5),
        get_scenario("WS500", 0.833),
    ]
)
tools_ws_ratio.pre_graphing(multi_scenario=True)

# Define tools for hydro set
tools_hydro = GraphTools(
    scenarios=[
        get_scenario("H25", 0),
        get_scenario("H26", 0.5),
        get_scenario("1342", 1),
    ]
)
tools_hydro.pre_graphing(multi_scenario=True)

# GET DATA FOR W/S RATIO
STORAGE_BINS = (0, 6, 8, 10, 15, 20, 30, 100, float("inf"))


def get_storage_data(tools):
    storage = tools.get_dataframe("storage_capacity.csv")
    storage = storage[storage["OnlinePowerCapacityMW"] != 0]
    storage["duration"] = (
        storage["OnlineEnergyCapacityMWh"] / storage["OnlinePowerCapacityMW"]
    )
    storage = storage[["scenario_name", "duration", "OnlinePowerCapacityMW"]]
    storage["duration_group"] = pd.cut(storage.duration, bins=STORAGE_BINS)
    storage = storage.groupby(
        ["scenario_name", "duration_group"]
    ).OnlinePowerCapacityMW.sum()
    storage /= 10 ** 3
    storage = storage.unstack()

    # Calculate transmission
    tx = tools.get_dataframe(
        "transmission.csv",
        usecols=["BuildTx", "trans_length_km", "scenario_name"],
        convert_dot_to_na=True,
    ).fillna(0)
    tx["BuildTx"] *= tx["trans_length_km"]
    tx["BuildTx"] *= 1e-6
    tx = (
        tx.groupby("scenario_name", as_index=False)["BuildTx"]
            .sum()
            .set_index("scenario_name")
    )
    tx = tx.rename({"BuildTx": "New Tx"}, axis=1)

    cmap = "viridis"
    cmap = tools.plt.pyplot.get_cmap(cmap)
    n = len(STORAGE_BINS)
    colors = [cmap(x / (n - 2)) for x in range(n - 1)]
    # storage["color"] = tools.pd.cut(storage.duration, bins=STORAGE_BINS, labels=colors)

    return storage, tx


storage_data_ws_ratio, tx = get_storage_data(tools_ws_ratio)

# GET HYDRO DATA
storage_data_hydro = get_storage_data(tools_hydro)

#  GET TX DATA
tools_tx = GraphTools(
    scenarios=[
        get_scenario("T4", "No Tx\nBuild Costs"),
        get_scenario("1342", "Baseline"),
        get_scenario("T5", "10x Tx Build Costs"),
    ]
)
tools_tx.pre_graphing(multi_scenario=True)
storage_data_tx = get_storage_data(tools_tx)

# GET COST DATA
cost_labels = ["50% of\nBaseline", "Baseline", "ATB Costs"]
tools_cost = GraphTools(
    scenarios=[
        get_scenario("C16", "50% of\nBaseline"),
        get_scenario("1342", "Baseline"),
        get_scenario("C12", "ATB Costs"),
    ]
)

tools_cost.pre_graphing(multi_scenario=True)
# %% DEFINE FIGURE AND PLOTTING FUNCTIONS
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(12, 12)


def plot_cap_and_tx_change(ax, cap, colors):
    cap.plot(ax=ax, color=colors["Storage"], marker=".", legend=False)


def plot_storage(ax, df):
    x = df.index.values
    ax.plot(
        x,
        df["max"].values,
        color="black",
        linestyle="dotted",
        marker=".",
        label="Min/Max",
    )
    ax.plot(x, df["min"].values, color="black", linestyle="dotted", marker=".")
    ax.plot(x, df.median_val.values, color="black", label="Median", marker=".")
    ax.fill_between(
        x,
        df.upper_inner.values,
        df["upper"].values,
        alpha=0.2,
        color="black",
        edgecolor=None,
        label=f"{int(quartile * 100)}-{int(100 - quartile * 100)}th percentile",
    )
    ax.fill_between(
        x,
        df["lower"].values,
        df.lower_inner.values,
        alpha=0.2,
        color="black",
        edgecolor=None,
    )
    ax.fill_between(
        x,
        df.lower_inner.values,
        df.upper_inner.values,
        alpha=0.4,
        color="black",
        edgecolor=None,
        label=f"{int(quartile_inner * 100)}-{int(100 - quartile_inner * 100)}th percentile",
    )


# Define axes
gs = matplotlib.gridspec.GridSpec(5, 2, figure=fig, height_ratios=[1, 2, 0.25, 1, 2])
ax_top_left = fig.add_subplot(gs[1, 0])
ax_top_right = fig.add_subplot(gs[1, 1], sharey=ax_top_left)
ax_bottom_left = fig.add_subplot(gs[4, 0])
ax_bottom_right = fig.add_subplot(gs[4, 1], sharey=ax_bottom_left)
cap_top_left = fig.add_subplot(gs[0, 0], sharex=ax_top_left)
cap_top_right = fig.add_subplot(gs[0, 1], sharex=ax_top_right, sharey=cap_top_left)
cap_bottom_left = fig.add_subplot(gs[3, 0], sharex=ax_bottom_left)
cap_bottom_right = fig.add_subplot(gs[3, 1], sharex=ax_bottom_right, sharey=cap_bottom_left)
rax_top_left = cap_top_left.twinx()
rax_top_right = cap_top_right.twinx()
rax_bottom_left = cap_bottom_left.twinx()
rax_bottom_right = cap_bottom_right.twinx()
rax_top_left.get_shared_y_axes().join(rax_top_left, rax_top_right)
rax_bottom_left.get_shared_y_axes().join(rax_bottom_left, rax_bottom_right)
plt.subplots_adjust(wspace=0.01, hspace=0.1)

# Labels
label = "Storage Duration (h)"
ax_top_left.set_ylabel(label)
ax_bottom_left.set_ylabel(label)
label = "Power Capacity (GW)"
cap_top_left.set_ylabel(label)
cap_bottom_left.set_ylabel(label)
ax_bottom_left.set_ylim(0, 70)

# Position axes
rax_top_left.spines["left"].set_position(("axes", -0.2))
rax_top_left.yaxis.set_label_position("left")
rax_bottom_left.spines["left"].set_position(("axes", -0.2))
rax_bottom_left.yaxis.set_label_position("left")

# %% PLOT BOTTOM LEFT

ax = ax_bottom_left
ax.tick_params(top=False, bottom=True, right=False, left=True, which="both")

plot_storage(ax, storage_data_ws_ratio)

ax.set_xlabel("Wind-to-Solar Share")
ax.set_xticks([0.2, 0.5, 0.8])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8], minor=True)
ax.set_xticklabels(["80%\nSolar", "50/50 Wind-Solar", "80%\nWind"])
ax.axvline(baseline_ws_ratio, linestyle="dotted")
ax.set_xlim([0.08, 0.86])
ax.text(baseline_ws_ratio - 0.03, 30, "Baseline Scenario", rotation=90, style="italic")

ax = cap_bottom_left
plot_cap_and_tx_change(ax, cap_ws_ratio, tools_ws_ratio.get_colors())

# %% PLOT BOTTOM RIGHT
ax = ax_bottom_right
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
plot_storage(ax, storage_data_hydro)
ax.set_xlabel("Hydropower Reduction")
ax.set_xticks([0, 0.5, 1])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9], minor=True)
ax.set_xticklabels(["No\nhydro", "50% of baseline", "Baseline"])

ax = cap_bottom_right
plot_cap_and_tx_change(ax, cap_hydro, tools_hydro.get_colors())

# %% PLOT TX
ax = ax_top_left
plot_storage(ax, storage_data_tx)
# ax.set_xticklabels([""])
ax.set_xlabel("Transmission Scenario")

ax = cap_top_left
plot_cap_and_tx_change(ax, cap_tx, tools_tx.get_colors())
# %% PLOT COSTS
ax = ax_top_right
storage_data_costs = storage_data_costs.sort_values(by="median_val")
plot_storage(ax, storage_data_costs)

ax = cap_top_right
plot_cap_and_tx_change(ax, cap_costs, tools_cost.get_colors())
ax.set_xlabel("Cost Scenario")
# %% CALCULATIONS
df = cap_ws_ratio["Storage"].copy()
1 - df.loc[0.5] / df.loc[baseline_ws_ratio]
# %%
df = storage_data_ws_ratio
df.loc[baseline_ws_ratio]
# %%
df.loc[0.5]
# %%

df.loc[0.833]
