# %% IMPORTS AND SCENARIO DEFINITION
import pandas as pd
from matplotlib import pyplot as plt

from switch_model.tools.graph.main import GraphTools
from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    get_scenario,
    set_style,
)

# GET DATA FOR W/S RATIO
STORAGE_BINS = (float("-inf"), 6, 10, 20, float("inf"))
STORAGE_LABELS = GraphTools.create_bin_labels(STORAGE_BINS)
for i in range(len(STORAGE_LABELS)):
    STORAGE_LABELS[i] = STORAGE_LABELS[i] + "h Storage"

# Define tools for wind to solar ratio set
baseline_ws_ratio = 0.187
# Get Graph tools
tools_ws_ratio = GraphTools(
    scenarios=[
        get_scenario("WS10", 0.0909),
        get_scenario("WS018", 0.15),
        get_scenario("1342", baseline_ws_ratio),
        get_scenario("WS027", 0.21),
        get_scenario("WS033", 0.25),
        get_scenario("WS043", 0.3),
        get_scenario("WS066", 0.4),
        get_scenario("WS100", 0.5),
        get_scenario("WS150", 0.6),
        get_scenario("WS233", 0.7),
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

baseline_energy_cost = 22.43

# GET COST DATA
tools_cost = GraphTools(
    scenarios=[
        get_scenario("C21", 0.5),
        get_scenario("C18", 1),
        get_scenario("C22", 2),
        get_scenario("C23", 5),
        get_scenario("C17", 10),
        get_scenario("C24", 15),
        get_scenario("1342", baseline_energy_cost),
        get_scenario("C25", 40),
        get_scenario("C19", 70),
        get_scenario("C20", 102)
    ]
)
tools_cost.pre_graphing(multi_scenario=True)


def get_data(tools):
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
        usecols=["BuildTx", "trans_length_km", "scenario_index"],
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
    tx.index = tx.index.map(tools.get_scenario_name)

    cap = tools.get_dataframe("gen_cap.csv")
    cap = tools.transform.gen_type(cap)
    cap = cap.groupby(["scenario_index", "gen_type"], as_index=False)[
        "GenCapacity"
    ].sum()
    cap = cap.pivot(columns="gen_type", index="scenario_index", values="GenCapacity")
    cap *= 1e-3  # Convert to GW
    cap = cap.rename_axis("Technology", axis=1).rename_axis(None)
    cap = cap[["Wind"]]
    cap.index = cap.index.map(tools.get_scenario_name)

    return storage, tx, cap

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

def create_secondary_y_axis(ax, include_label):
    rax = ax.twinx()
    rax.set_ylim(0, Y_LIM / 2.5)
    if include_label:
        rax.spines["left"].set_position(("axes", -0.2))
        rax.yaxis.set_label_position("left")
        rax.yaxis.tick_left()
        rax.tick_params(top=False, bottom=False, right=False, left=True, which="both")
        rax.spines["left"].set_color("grey")
        rax.set_ylabel("New Transmission Built (millions of MW-km)")
    else:
        rax.tick_params(top=False, bottom=False, right=False, left=False, which="both")
        rax.set_yticklabels([])
    return rax


rax_top_left = create_secondary_y_axis(ax_top_left, True)
rax_top_right = create_secondary_y_axis(ax_top_right, False)
rax_bottom_left = create_secondary_y_axis(ax_bottom_left, True)
rax_bottom_right = create_secondary_y_axis(ax_bottom_right, False)


# %% DEFINE PLOTTING CODE
def plot_panel(ax, rax, storage, tx, cap, x_label=""):
    lw = 2.5
    s = 7.5
    colors = tools_ws_ratio.get_colors()
    storage.index.name = None
    storage.plot(ax=ax, marker=".", colormap="autumn", legend=False, linewidth=lw, markersize=s)
    storage.sum(axis=1).plot(ax=ax, marker=".", color=colors["Storage"], label="All Storage", legend=False, linewidth=lw,
                             markersize=s)
    rax.plot(tx, marker=".", color="purple", label="Built Tx", linewidth=lw, alpha=0.5)
    cap.plot(ax=ax, marker=".", color=colors, legend=False, linewidth=lw, markersize=s, alpha=0.5)
    ax.set_ylabel("Power Capacity (GW)")
    ax.set_title(x_label)


# %% PLOT WIND TO SOLAR PENETRATION

storage_ws, tx_ws, cap_ws = get_data(tools_ws_ratio)

ax = ax_top_left
rax = rax_top_left
ax.tick_params(top=False, bottom=True, right=False, left=True, which="both")

plot_panel(ax, rax, storage_ws, tx_ws, cap_ws, "Set A: Varying Wind-vs-Solar Share")

ax.set_xticks([0.2, 0.5, 0.8])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8], minor=True)
ax.set_xticklabels(["80%\nSolar", "50-50\nWind-Solar", "80%\nWind"])
ax.axvline(baseline_ws_ratio, linestyle="dotted", color="dimgrey")
ax.text(baseline_ws_ratio - 0.04, 125, "Baseline", rotation=90, color="dimgrey")
ax.set_xlim([0.08, 0.86])

fig.legend(loc="lower center", ncol=4)

# %% PLOT HYDRO
storage_hy, tx_hy, cap_hy = get_data(tools_hydro)
ax = ax_top_right
rax = rax_top_right
plot_panel(ax, rax, storage_hy, tx_hy, cap_hy, "Set B: Reducing Hydropower Generation")
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
ax.set_xticks([0, 0.5, 1])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9], minor=True)
ax.set_xticklabels(["No\nhydropower", "50%\nhydropower", "Baseline\nHydropower"])

# %% PLOT TX
ax = ax_bottom_left
rax = rax_bottom_left
storage_tx, tx_tx, cap_tx = get_data(tools_tx)
plot_panel(ax, rax, storage_tx, tx_tx, cap_tx, "Set C: Varying Transmission Build Costs")
# %% PLOT COSTS
ax = ax_bottom_right
rax = rax_bottom_right
storage_cost, tx_cost, cap_cost = get_data(tools_cost)
plot_panel(ax, rax, storage_cost, tx_cost, cap_cost, "Set D: Varying Storage Energy Costs")
ax.set_xscale("log")
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
ax.set_xticks([1, 10, 100])
ax.set_xticks([0.5, 0.6, 0.7, 0.8, 0.9, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 30, 40, 50, 60, 70, 80, 90], minor=True)
ax.set_xticklabels(["1\n$/kWh", "10\n$/kWh", "100\n$/kWh"])
ax.set_xlabel("(log scale)")
ax.axvline(baseline_energy_cost, linestyle="dotted", color="dimgrey")
ax.text(baseline_energy_cost - 6, 125, "Baseline", rotation=90, color="dimgrey")

plt.subplots_adjust()
# %% CALCULATIONS
