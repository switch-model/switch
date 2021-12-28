# %% IMPORTS AND SCENARIO DEFINITION
import pandas as pd
from matplotlib import pyplot as plt

from switch_model.tools.graph.main import GraphTools
from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    get_scenario,
    set_style,
    create_bin_labels,
)

# GET DATA FOR W/S RATIO
STORAGE_BINS = (float("-inf"), 6, 8, 10, 15, float("inf"))
STORAGE_LABELS = create_bin_labels(STORAGE_BINS)

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

#  GET TX DATA
tools_tx = GraphTools(
    scenarios=[
        get_scenario("T4", "No Tx\nBuild Costs"),
        get_scenario("1342", "Baseline"),
        get_scenario("T5", "10x Tx\nBuild Costs"),
    ]
)
tools_tx.pre_graphing(multi_scenario=True)

# GET COST DATA
tools_cost = GraphTools(
    scenarios=[
        get_scenario("C16", "50% of\nBaseline"),
        get_scenario("1342", "Baseline"),
        get_scenario("C12", "ATB Costs"),
    ]
)
tools_cost.pre_graphing(multi_scenario=True)


def get_storage_data(tools):
    storage = tools.get_dataframe("storage_capacity.csv")
    storage = storage[storage["OnlinePowerCapacityMW"] != 0]
    storage["duration"] = (
            storage["OnlineEnergyCapacityMWh"] / storage["OnlinePowerCapacityMW"]
    )
    storage = storage[["scenario_index", "duration", "OnlinePowerCapacityMW"]]
    storage["Duration (h)"] = pd.cut(
        storage.duration, bins=STORAGE_BINS, labels=STORAGE_LABELS
    )
    storage = storage.groupby(
        ["scenario_index", "Duration (h)"]
    ).OnlinePowerCapacityMW.sum()
    storage /= 10 ** 3
    storage = storage.unstack()
    storage.index = storage.index.map(tools.get_scenario_name)

    # Calculate transmission
    tx = tools.get_dataframe(
        "transmission.csv",
        usecols=["BuildTx", "trans_length_km", "scenario_name", "scenario_index"],
        convert_dot_to_na=True,
    ).fillna(0)
    tx["BuildTx"] *= tx["trans_length_km"]
    tx["BuildTx"] *= 1e-6
    tx = (
        tx.groupby("scenario_index", as_index=False)["BuildTx"]
        .sum()
        .set_index("scenario_index")
    )

    tx = tx.rename({"BuildTx": "New Tx"}, axis=1)

    return storage, tx


# %% DEFINE FIGURE AND PLOTTING FUNCTIONS
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(12, 12)

# Define axes
ax_top_left = fig.add_subplot(2, 2, 1)
ax_top_right = fig.add_subplot(2, 2, 2, sharey=ax_top_left)
ax_bottom_left = fig.add_subplot(2, 2, 3)
ax_bottom_right = fig.add_subplot(2, 2, 4, sharey=ax_bottom_left)
Y_LIM = 325
ax_top_left.set_ylim(0, Y_LIM)
ax_bottom_left.set_ylim(0, Y_LIM)


# %% DEFINE PLOTTING CODE
def plot_panel(ax, storage, x_label=""):
    lw = 2.5
    s = 7.5
    storage.index.name = None
    storage.plot(ax=ax, marker=".", colormap="viridis", legend=False, linewidth=lw, markersize=s)
    storage.sum(axis=1).plot(ax=ax, marker=".", color="k", label="All durations", legend=False, linewidth=lw,
                             markersize=s)
    ax.set_ylabel("Storage Power Capacity (GW)")
    ax.set_title(x_label)


# %% PLOT WIND TO SOLAR PENETRATION

storage_ws, tx_ws = get_storage_data(tools_ws_ratio)

ax = ax_top_left
ax.tick_params(top=False, bottom=True, right=False, left=True, which="both")

plot_panel(ax, storage_ws, "Set A: Varying Wind-vs-Solar Share")

ax.set_xticks([0.2, 0.5, 0.8])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8], minor=True)
ax.set_xticklabels(["80%\nSolar", "50-50\nWind-Solar", "80%\nWind"])
ax.axvline(baseline_ws_ratio, linestyle="dotted", color="dimgrey")
ax.set_xlim([0.08, 0.86])
ax.text(baseline_ws_ratio - 0.04, 50, "Baseline", rotation=90, color="dimgrey")

# %% PLOT HYDRO
storage_hy, tx_hy = get_storage_data(tools_hydro)
ax = ax_top_right
plot_panel(ax, storage_hy, "Set B: Reducing Hydropower Generation")
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
ax.set_xticks([0, 0.5, 1])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9], minor=True)
ax.set_xticklabels(["No\nhydropower", "50%\nhydropower", "Baseline\nHydropower"])
ax.legend(title="Duration (h)")

# %% PLOT TX
ax = ax_bottom_left
storage_tx, tx_tx = get_storage_data(tools_tx)
plot_panel(ax, storage_tx, "Set C: Varying Transmission Build Costs")
# %% PLOT COSTS
ax = ax_bottom_right
storage_cost, tx_cost = get_storage_data(tools_cost)
plot_panel(ax, storage_cost, "Set D: Varying Storage Costs")

plt.subplots_adjust()
# %% CALCULATIONS
