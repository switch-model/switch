# %% IMPORTS AND SCENARIO DEFINITION

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


# %% GET DATA FOR W/S RATIO


def get_change_in_tx_and_capacity(tools):
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

    cap = tools.get_dataframe("gen_cap.csv")
    cap = tools.transform.gen_type(cap)
    cap = cap.groupby(["scenario_name", "gen_type"], as_index=False)[
        "GenCapacity"
    ].sum()
    cap = cap.pivot(columns="gen_type", index="scenario_name", values="GenCapacity")
    cap *= 1e-3  # Convert to GW
    cap = cap.rename_axis("Technology", axis=1).rename_axis("Scenario")
    # Remove columns that don't change
    s = cap.std()
    cap = cap[[c for c in cap.columns if c not in s[s == 0]]]
    # df -= df.loc[0.23] # Make it as change compared to baseline
    return cap, tx


def get_storage_data(tools):
    storage = tools.get_dataframe("storage_capacity.csv")
    storage = storage[storage["OnlinePowerCapacityMW"] != 0]
    storage["duration"] = (
        storage["OnlineEnergyCapacityMWh"] / storage["OnlinePowerCapacityMW"]
    )
    storage = storage[["scenario_name", "duration", "OnlinePowerCapacityMW"]]
    storage_group = storage.groupby(["scenario_name"])
    calc = weightedcalcs.Calculator("OnlinePowerCapacityMW")
    #     mean = storage_group.mean().rename("mean_val")
    median = calc.quantile(storage_group, "duration", 0.5).rename("median_val")
    lower_inner = calc.quantile(storage_group, "duration", quartile_inner).rename(
        "lower_inner"
    )
    upper_inner = calc.quantile(storage_group, "duration", 1 - quartile_inner).rename(
        "upper_inner"
    )
    lower = calc.quantile(storage_group, "duration", quartile).rename("lower")
    upper = calc.quantile(storage_group, "duration", 1 - quartile).rename("upper")
    maxi = storage_group["duration"].max().rename("max")
    mini = storage_group["duration"].min().rename("min")
    df = pd.concat([mini, lower, lower_inner, median, upper_inner, upper, maxi], axis=1)
    return df


storage_data_ws_ratio = get_storage_data(tools_ws_ratio)
cap_ws_ratio, tx_ws_ratio = get_change_in_tx_and_capacity(tools_ws_ratio)

# %% GET HYDRO DATA
cap_hydro, tx_hydro = get_change_in_tx_and_capacity(tools_hydro)
storage_data_hydro = get_storage_data(tools_hydro)

# %% DEFINE FIGURE AND PLOTTING FUNCTIONS
set_style()
fig = plt.figure()
fig.set_size_inches(12, 12)


def set_ws_ratio_axis(ax):
    ax.set_xlabel("Wind-to-Solar Share")
    ax.set_xticks([0.2, 0.5, 0.8])
    ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8], minor=True)
    ax.set_xticklabels(["80%\nSolar", "50/50 Wind-Solar", "80%\nWind"])
    ax.axvline(baseline_ws_ratio, linestyle="dotted")
    ax.set_xlim([0.08, 0.86])


def set_hydro_axis(ax):
    ax.set_xlabel("Hydropower Reduction")
    ax.set_xticks([0, 0.5, 1])
    ax.set_xticks([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9], minor=True)
    ax.set_xticklabels(["No\nhydro", "50% of baseline", "Baseline"])


def plot_cap_and_tx_change(ax, rax, cap, tx, colors):
    tx.plot(ax=rax, marker=".", linestyle="dashdot", legend=False, color="grey")
    rax.set_ylim(0, 120)
    cap.plot(ax=ax, color=colors, marker=".", legend=False)


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
    ax.set_ylim(3.5, 900)
    ax.set_yscale("log")


def set_capacity_ax(ax):
    ax.set_ylim(0, 600)


storage_ticks = [4, 10, 50, 100, 500]

# Define axes
ax_top_left = fig.add_subplot(2, 2, 1)
ax_top_right = fig.add_subplot(2, 2, 2)  # , sharey=ax1)
ax_bottom_left = fig.add_subplot(2, 2, 3, sharex=ax_top_left)
ax_bottom_right = fig.add_subplot(2, 2, 4, sharex=ax_top_right)  # , sharey=ax3)
rax_top_left = ax_top_left.twinx()
rax_top_right = ax_top_right.twinx()
plt.subplots_adjust(wspace=0.01, hspace=0.01)

# %% PLOT TOP LEFT
ax = ax_top_left
rax = rax_top_left
ax.clear()
rax.clear()
rax.spines["left"].set_position(("axes", -0.2))
rax.yaxis.set_label_position("left")
rax.yaxis.tick_left()
rax.tick_params(top=False, bottom=False, right=False, left=True, which="both")
ax.tick_params(top=False, bottom=False, right=False, left=True, which="major")
ax.tick_params(top=False, bottom=False, right=False, left=False, which="minor")
# ax.spines["left"].set_color("black")
rax.spines["left"].set_color("grey")
rax.set_ylabel("New Transmission Built (millions of MW-km)")

plot_cap_and_tx_change(ax, rax, cap_ws_ratio, tx_ws_ratio, colors=tools_ws_ratio.get_colors())
set_ws_ratio_axis(ax)
set_capacity_ax(ax)
ax.legend()
rax.legend()
ax.set_ylabel("Capacity (GW)")

# %% PLOT BOTTOM LEFT

ax = ax_bottom_left
ax.clear()
ax.tick_params(top=False, bottom=True, right=False, left=True, which="both")

plot_storage(ax, storage_data_ws_ratio)
ax.set_ylabel("Storage Duration (h)")
ax.set_yticks(storage_ticks)
ax.yaxis.set_major_formatter(ScalarFormatter())
set_ws_ratio_axis(ax)
ax.text(baseline_ws_ratio - 0.03, 50, "Baseline Scenario", rotation=90, style="italic")

# %% PLOT TOP RIGHT
ax = ax_top_right
rax = rax_top_right
ax.clear()
rax.clear()
ax.tick_params(top=False, bottom=False, right=False, left=False, which="both")
rax.tick_params(top=False, bottom=False, right=False, left=False, which="both")

plot_cap_and_tx_change(ax, rax, cap_hydro, tx_hydro, colors=tools_hydro.get_colors())
set_capacity_ax(ax)
set_hydro_axis(ax)
ax.set_yticklabels([])
rax.set_yticklabels([])

# %% PLOT BOTTOM RIGHT
ax = ax_bottom_right
ax.clear()
ax.tick_params(top=False, bottom=True, right=False, left=False, which="both")
plot_storage(ax, storage_data_hydro)
ax.set_yticklabels([])
set_hydro_axis(ax)
ax.set_yticks(storage_ticks)
ax.legend()
# %% CALCULATIONS
df = cap_ws_ratio["Storage"].copy()
1- df.loc[0.5] / df.loc[baseline_ws_ratio]
#%%
df = storage_data_ws_ratio
df.loc[baseline_ws_ratio]
#%%
df.loc[0.5]
#%%
df.loc[0.833]