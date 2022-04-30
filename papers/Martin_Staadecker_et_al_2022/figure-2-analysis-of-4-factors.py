# %% IMPORTS AND SCENARIO DEFINITION
import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import PercentFormatter

from switch_model.tools.graph.main import GraphTools
from papers.Martin_Staadecker_et_al_2022.util import (
    get_scenario,
    set_style, save_figure,
)

custom_color_map = LinearSegmentedColormap.from_list(
    "custom_color_map", ["#E0A4AA", "#B9646B", "#4D0409"]
)

# GET DATA FOR W/S RATIO
STORAGE_BINS = (float("-inf"), 10, 20, float("inf"))
STORAGE_LABELS = GraphTools.create_bin_labels(STORAGE_BINS)
for i in range(len(STORAGE_LABELS)):
    STORAGE_LABELS[i] = STORAGE_LABELS[i] + "h Storage (GW)"

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
        # get_scenario("WS233", 0.7), # Removed since results are invalid
        # get_scenario("WS500", 0.833), # Removed since results are misleading
    ], set_style=False
)
tools_ws_ratio.pre_graphing(multi_scenario=True)

# Define tools for hydro set
tools_hydro = GraphTools(
    scenarios=[
        get_scenario("H25", 1),
        get_scenario("H025", 0.75),
        get_scenario("H050", 0.5),
        get_scenario("H065", 0.35),
        get_scenario("H085", 0.15),
        get_scenario("1342", 0),
    ], set_style=False
)
tools_hydro.pre_graphing(multi_scenario=True)

#  GET TX DATA
tools_tx = GraphTools(
    scenarios=[
        get_scenario("T4", "No Tx Build Costs\n(No Tx Congestion)"),
        get_scenario("1342", "Baseline"),
        get_scenario("T5", "10x Tx\nBuild Costs"),
    ], set_style=False
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
        get_scenario("C26", 7),
        get_scenario("C17", 10),
        get_scenario("C24", 15),
        get_scenario("1342", baseline_energy_cost),
        get_scenario("C25", 40),
        get_scenario("C19", 70),
        get_scenario("C20", 102)
    ], set_style=False
)
tools_cost.pre_graphing(multi_scenario=True)


def get_data(tools, normalize_to_baseline=None):
    storage = tools.get_dataframe("storage_capacity.csv")
    duration = storage.copy()
    duration = duration[duration["OnlinePowerCapacityMW"] != 0]
    duration["duration"] = (
            duration["OnlineEnergyCapacityMWh"] / duration["OnlinePowerCapacityMW"]
    )
    duration = duration[["scenario_index", "duration", "OnlinePowerCapacityMW"]]
    duration["Duration (h)"] = pd.cut(
        duration.duration, bins=STORAGE_BINS, labels=STORAGE_LABELS
    )
    duration = duration.groupby(
        ["scenario_index", "Duration (h)"]
    ).OnlinePowerCapacityMW.sum()
    duration /= 10 ** 3
    duration = duration.unstack()
    duration.index = duration.index.map(tools.get_scenario_name)

    storage = storage[["scenario_index", "OnlineEnergyCapacityMWh"]]
    storage = storage.groupby("scenario_index").sum()
    storage.index = storage.index.map(tools.get_scenario_name)
    storage *= 1e-6
    storage.columns = ["Storage Energy Capacity (TWh)"]

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
    cap = cap[["Wind", "Solar"]]
    cap.index = cap.index.map(tools.get_scenario_name)

    # Make it a percent change compared to the baseline
    if normalize_to_baseline is not None:
        tx = (tx / tx.loc[normalize_to_baseline])
        cap = (cap / cap.loc[normalize_to_baseline])
        storage = (storage / storage.loc[normalize_to_baseline])
        duration = (duration / duration.sum(axis=1).loc[normalize_to_baseline])

    return duration, tx, cap, storage


# %% DEFINE FIGURE AND PLOTTING FUNCTIONS
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(6.850394, 6.850394)

# Define axes
ax_tl = fig.add_subplot(2, 2, 1)
ax_tr = fig.add_subplot(2, 2, 2, sharey=ax_tl)
ax_bl = fig.add_subplot(2, 2, 3)
ax_br = fig.add_subplot(2, 2, 4, sharey=ax_bl)
Y_LIM_BASE = 1.85
ax_tl.set_ylim(0, Y_LIM_BASE)
ax_bl.set_ylim(0, Y_LIM_BASE)
ax_tl.yaxis.set_major_formatter(PercentFormatter(xmax=1))
ax_bl.yaxis.set_major_formatter(PercentFormatter(xmax=1))


# def create_secondary_y_axis(ax, include_label, y_lim, y_label, color="grey", offset=-0.25):
#     rax = ax.twinx()
#     rax.set_ylim(0, y_lim)
#     if include_label:
#         rax.spines["left"].set_position(("axes", offset))
#         rax.yaxis.set_label_position("left")
#         rax.yaxis.tick_left()
#         rax.tick_params(top=False, bottom=False, right=False, left=True, which="both")
#         rax.spines["left"].set_color(color)
#         rax.set_ylabel(y_label)
#     else:
#         rax.tick_params(top=False, bottom=False, right=False, left=False, which="both")
#         rax.set_yticklabels([])
#     return rax


# y_lim = (Y_LIM_BASE) * 200
# y_label = "Storage Power Capacity (GW)"
# c = "tab:red"
# rax_top_left = create_secondary_y_axis(ax_tl, True, y_lim, y_label, c)
# rax_top_right = create_secondary_y_axis(ax_tr, False, y_lim, y_label, c)
# rax_bottom_left = create_secondary_y_axis(ax_bl, True, y_lim, y_label, c)
# rax_bottom_right = create_secondary_y_axis(ax_br, False, y_lim, y_label, c)


# y_lim = Y_LIM_BASE / 50
# y_label = "Energy Capacity (TWh)"
# c = "green"
# rrax_tl = create_secondary_y_axis(ax_tl, True, y_lim, y_label, c, offset=-0.4)
# rrax_tr = create_secondary_y_axis(ax_tr, False, y_lim, y_label, c, offset=-0.4)
# rrax_bl = create_secondary_y_axis(ax_bl, True, y_lim, y_label, c, offset=-0.4)
# rrax_br = create_secondary_y_axis(ax_br, False, y_lim, y_label, c, offset=-0.4)
#
# y_lim = Y_LIM_BASE * 2
# y_label = "Solar Power Capacity (GW)"
# c = tools_ws_ratio.get_colors()["Solar"]
# rrrax_tl = create_secondary_y_axis(ax_tl, True, y_lim, y_label, c, offset=-0.6)
# rrrax_tr = create_secondary_y_axis(ax_tr, False, y_lim, y_label, c, offset=-0.6)
# rrrax_bl = create_secondary_y_axis(ax_bl, True, y_lim, y_label, c, offset=-0.6)
# rrrax_br = create_secondary_y_axis(ax_br, False, y_lim, y_label, c, offset=-0.6)


# %% DEFINE PLOTTING CODE
def plot_panel(ax, rax, rrax, rrrax, data, title=""):
    duration, tx, cap, storage = data
    lw = 1
    s = 3
    colors = tools_ws_ratio.get_colors()
    duration.index.name = None
    storage.index.name = None
    duration.plot(ax=ax, colormap=custom_color_map, legend=False, kind="area", zorder=1.5, alpha=0.5, linewidth=0)
    # duration.sum(axis=1).plot(ax=ax, marker=".", color="red", label="All Storage (GW)", legend=False,
    #                           linewidth=lw,
    #                           markersize=s)
    ax.plot(tx, marker=".", color="tab:red", label="Built Transmission", linewidth=lw, markersize=s)
    cap["Wind"].plot(ax=ax, marker=".", color=colors, legend=False, linewidth=lw, markersize=s)
    cap["Solar"].plot(ax=ax, marker=".", color=colors, legend=False, linewidth=lw, markersize=s)
    storage.plot(ax=ax, marker=".", color="green", linewidth=lw, markersize=s,
                 legend=False)
    ax.set_ylabel("Percent of baseline capacity")
    ax.set_title(title)


# %% PLOT WIND TO SOLAR PENETRATION

data_ws = get_data(tools_ws_ratio, normalize_to_baseline=baseline_ws_ratio)

ax = ax_tl
# rax = rax_top_left
ax.tick_params(top=False, bottom=True, right=False, left=True, which="both")

plot_panel(ax, None, None, None, data_ws, "Set A: Varying Wind-vs-Solar Share")

ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
ax.set_xticklabels(["90% Solar\n10% Wind", "", "70% Solar\n30% Wind", "", "50% Solar\n50% Wind", ""])
ax.set_xlabel("Solar-Wind ratio")
ax.axvline(baseline_ws_ratio, linestyle="dotted", color="dimgrey")
ax.text(baseline_ws_ratio - 0.02, 0.1, "Baseline", rotation=90, color="dimgrey")

fig.legend(loc="lower center", ncol=4)

# %% PLOT HYDRO
data_hy = get_data(tools_hydro, normalize_to_baseline=0)
ax = ax_tr
# rax = rax_top_right
plot_panel(ax, None, None, None, data_hy, "Set B: Reducing Hydropower Generation")
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
ax.set_xticks([0, 0.5, 1])
ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9], minor=True)
ax.set_xticklabels(["0%\n(Baseline)", "50%", "100%\n(No Hydro)"])
ax.set_xlabel("Hydropower reduction")

# %% PLOT TX
ax = ax_bl
# rax = rax_bottom_left
data_tx = get_data(tools_tx, normalize_to_baseline="Baseline")
ax.set_xticks([0, 1, 2])
plot_panel(ax, None, None, None, data_tx, "Set C: Varying Transmission Build Costs")
# %% PLOT COSTS
ax = ax_br
# rax = rax_bottom_right
data_cost = get_data(tools_cost, normalize_to_baseline=baseline_energy_cost)
plot_panel(ax, None, None, None, data_cost, "Set D: Varying Storage Energy Costs")
ax.set_xscale("log")
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
ax.set_xticks([1, 10, 100])
ax.set_xticks(
    [
        0.5,
        0.6,
        0.7,
        0.8,
        0.9,
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        20,
        30,
        40,
        50,
        60,
        70,
        80,
        90,
    ],
    minor=True,
)
ax.set_xticklabels(["1\n$/kWh", "10\n$/kWh", "100\n$/kWh"])
ax.set_xlabel("(log scale)")
ax.axvline(baseline_energy_cost, linestyle="dotted", color="dimgrey")
ax.text(baseline_energy_cost - 4, 0.1, "Baseline", rotation=90, color="dimgrey")

plt.subplots_adjust(left=0.08, right=0.97, top=0.95, wspace=0.05, hspace=0.25)

# %% SAVE FIGURE
save_figure("figure-2-analysis-of-4-factors.png")
# %% MAX POWER DURATION
df = tools_ws_ratio.get_dataframe("storage_capacity.csv")
df = df[df.scenario_name == 0.833]
df["duration"] = df["duration"] = (
        df["OnlineEnergyCapacityMWh"] / df["OnlinePowerCapacityMW"]
)
df = df[["load_zone", "duration", "OnlinePowerCapacityMW"]]
df.sort_values("duration")
# %% HYDRO POWER impact
en = data_hy[3].copy() * 1000
pw = data_hy[0].sum(axis=1).copy()
pw, en

# %% HYDRO power total capacity
df = tools_hydro.get_dataframe("dispatch_annual_summary.csv")
scenario = 1
# scenario = 0.5
df = df[df.scenario_name == scenario]
df = tools_hydro.transform.gen_type(df)
df = df[df.gen_type != "Storage"]
df = df.groupby("gen_type").Energy_GWh_typical_yr.sum()
df *= 1e-3
df
df.loc["Hydro"] / df.sum()
# %%
data_tx
# %% Storage duration in 50% hydro
df = tools_hydro.get_dataframe("dispatch_zonal_annual_summary.csv")
df = df[df.scenario_name == 1]
df = tools_hydro.transform.gen_type(df)
df = df[["gen_load_zone", "gen_type", "Energy_GWh_typical_yr"]].set_index("gen_load_zone")
df_sum = df.groupby("gen_load_zone").Energy_GWh_typical_yr.sum()
df_sum = df_sum.rename("total")
df = df.join(df_sum)
cutoff = 0.5
df["percent"] = df["Energy_GWh_typical_yr"] / df["total"]
df = df[["percent", "gen_type"]].reset_index()
df = df[df.gen_type == "Hydro"]
df = df[df.percent > cutoff]
valid_load_zones = df["gen_load_zone"]

df = tools_hydro.get_dataframe("storage_capacity.csv")
# df = df[df.scenario_name == 0.5]
df = df[["load_zone", "scenario_name", "OnlinePowerCapacityMW", "OnlineEnergyCapacityMWh"]]
df = df[df.load_zone.isin(valid_load_zones)]
df = df.groupby("scenario_name").sum()
df["OnlineEnergyCapacityMWh"] / df["OnlinePowerCapacityMW"]
# valid_load_zones

# %% TX Change
df = data_tx[2]
df
# %% COSTS
df = data_cost
table = 1
df[table], (data_cost[table] / data_cost[table].loc[22.43] - 1) * 100
# %%
df = tools_cost.get_dataframe("storage_capacity.csv")
df["duration"] = df["OnlineEnergyCapacityMWh"] / df["OnlinePowerCapacityMW"]
df = df.groupby("scenario_name").duration.max()
df
# %%
df = tools_cost.get_dataframe("storage_capacity.csv")
df["duration"] = df["OnlineEnergyCapacityMWh"] / df["OnlinePowerCapacityMW"]
total_power = df.groupby("scenario_name").OnlinePowerCapacityMW.sum()
total_energy = df.groupby("scenario_name").OnlineEnergyCapacityMWh.sum()
total_energy / total_power
# %% California only costs
df = tools_cost.get_dataframe("storage_capacity.csv")
df = tools_cost.transform.load_zone(df)
df = df[df.region == "CA"]
df["duration"] = df["OnlineEnergyCapacityMWh"] / df["OnlinePowerCapacityMW"]
print("max duration", df.groupby("scenario_name").duration.max())
print("median duration", df.groupby("scenario_name").duration.median())
print("total capacity", df.groupby("scenario_name").OnlineEnergyCapacityMWh.sum() / 1e6)

cap = tools_cost.get_dataframe("gen_cap.csv")
cap = tools_cost.transform.gen_type(cap)
cap = cap.groupby(["scenario_index", "gen_type"], as_index=False)[
    "GenCapacity"
].sum()
cap = cap.pivot(columns="gen_type", index="scenario_index", values="GenCapacity")
cap *= 1e-3  # Convert to GW
cap = cap.rename_axis("Technology", axis=1).rename_axis(None)
cap = cap[["Solar"]]
cap.index = cap.index.map(tools_cost.get_scenario_name)
cap
