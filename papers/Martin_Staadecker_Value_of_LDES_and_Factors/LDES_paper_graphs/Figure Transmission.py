import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.cm import get_cmap, ScalarMappable
from matplotlib.colors import (
    TwoSlopeNorm,
)
from matplotlib.ticker import PercentFormatter

from switch_model.tools.graph.main import GraphTools
from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    get_scenario,
    set_style,
)

scenarios = [
    get_scenario("T4", "No Tx\nBuild Costs"),
    get_scenario("1342", "Baseline"),
    # get_scenario("T5", "10x Tx\nBuild Costs"),
]
tools = GraphTools(scenarios=scenarios)
tools.pre_graphing(multi_scenario=True)
n = len(scenarios)


# %%  GET DATA


def get_data(scenario_index):
    dispatch = tools.get_dataframe("dispatch_zonal_annual_summary.csv")
    dispatch = dispatch[dispatch.scenario_index == scenario_index]
    dispatch = tools.transform.gen_type(dispatch)
    dispatch = tools.transform.load_zone(dispatch, load_zone_col="gen_load_zone")
    dispatch = dispatch[dispatch.gen_type != "Storage"]
    dispatch = dispatch.groupby("gen_load_zone")[["Energy_GWh_typical_yr"]].sum()
    dispatch.columns = ["generation_gwh"]

    demand = tools.get_dataframe("load_balance_annual_zonal.csv")
    demand = demand[demand.scenario_index == scenario_index]
    demand = demand.set_index("load_zone")
    demand = demand["zone_demand_mw"]
    demand *= -1e-3
    demand = demand.rename("demand_gwh")

    df = dispatch.join(demand)
    df["percent_gen"] = df["generation_gwh"] / df["demand_gwh"] * 100
    df = df["percent_gen"]

    duration = tools.get_dataframe(
        "storage_capacity.csv",
        usecols=[
            "load_zone",
            "OnlineEnergyCapacityMWh",
            "OnlinePowerCapacityMW",
            "period",
        ],
    ).rename({"load_zone": "gen_load_zone"}, axis=1)
    duration = duration[duration["period"] == 2050].drop(columns="period")
    duration = duration.groupby("gen_load_zone", as_index=False).sum()
    duration["value"] = (
        duration["OnlineEnergyCapacityMWh"] / duration["OnlinePowerCapacityMW"]
    )
    duration = duration[["gen_load_zone", "value", "OnlinePowerCapacityMW"]]
    duration["OnlinePowerCapacityMW"] *= 1e-3

    demand = tools.get_dataframe("loads.csv", from_inputs=True)
    demand = demand[demand.scenario_index == scenario_index]
    demand = demand.groupby("LOAD_ZONE").zone_demand_mw.max()
    demand *= 1e-3
    duration = duration.set_index("gen_load_zone")
    duration = duration.join(demand)
    duration = duration.reset_index()
    duration["percent_power"] = duration["OnlinePowerCapacityMW"] / duration["zone_demand_mw"] * 100

    return df, duration


data = [get_data(i) for i in range(n)]

# %% DEFINE FIGURE AND PLOTTING FUNCTIONS
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(12, 6)

# Define axes
axes = []
for i in range(n):
    axes.append(fig.add_subplot(1, n, i + 1, projection=tools.maps.get_projection()))

plt.subplots_adjust(left=0.02, right=0.98, wspace=0.05)

Y_LIM = 11 * 100
cmap = get_cmap("bwr")

normalizer = TwoSlopeNorm(vmin=0, vcenter=100, vmax=Y_LIM)


def percent_to_color(percent):
    return cmap(normalizer(percent))


def plot(ax, data, legend):
    percent_gen, duration = data

    max_size = 1000
    max = 50
    duration["size"] = duration["OnlinePowerCapacityMW"] / max  * max_size
    tools.maps.draw_base_map(ax)
    percent_gen = percent_gen.apply(percent_to_color)
    tools.maps.graph_load_zone_colors(percent_gen, ax)
    legend_handles = tools.maps.graph_duration(
        duration, ax=ax, legend=False, bins=(0, 6, 10, 20, float("inf"))
    )

    if legend:
        fig.legend(
            title="Storage Duration (h)",
            handles=legend_handles,
            # bbox_to_anchor=(1, 1),
            loc="lower center",
            # framealpha=0,
            fontsize=8,
            title_fontsize=10,
            # labelspacing=1,
            ncol=4,
        )


for i, ax in enumerate(axes):
    plot(ax, data[i], legend=(i == n - 1))
    ax.set_title(tools.scenarios[i].name)

fig.colorbar(
    ScalarMappable(norm=normalizer, cmap=cmap),
    format=PercentFormatter(),
    ticks=[0, 20, 40, 60, 80, 100, 300, 500, 700, 900, 1100],
    extend="max",
    ax=axes,
    location="right",
    label="Yearly Generation / Yearly Demand",
)
