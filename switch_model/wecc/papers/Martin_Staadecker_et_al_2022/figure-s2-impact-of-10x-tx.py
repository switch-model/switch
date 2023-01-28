from matplotlib import pyplot as plt
from matplotlib.cm import get_cmap, ScalarMappable
from matplotlib.colors import (
    TwoSlopeNorm,
)
from matplotlib.ticker import PercentFormatter

from switch_model.tools.graph.main import GraphTools
from papers.Martin_Staadecker_et_al_2022.util import (
    get_scenario,
    set_style,
    save_figure,
)

scenarios_supplementary = [
    get_scenario("1342", "Baseline"),
    get_scenario("T5", "10x Tx Build Costs"),
]

tools_supplementary = GraphTools(scenarios=scenarios_supplementary, set_style=False)
tools_supplementary.pre_graphing(multi_scenario=True)

# Uncomment to make supplementary figure
tools = tools_supplementary
zones_to_highlight = None

n = len(scenarios_supplementary)


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

    duration = tools.get_dataframe("storage_capacity.csv").rename(
        {"load_zone": "gen_load_zone"}, axis=1
    )
    duration = duration[duration.scenario_index == scenario_index]
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
    duration["percent_power"] = (
        duration["OnlinePowerCapacityMW"] / duration["zone_demand_mw"] * 100
    )

    return df, duration


data = [get_data(i) for i in range(n)]

# %% DEFINE FIGURE AND PLOTTING FUNCTIONS
set_style()
plt.close()
fig = plt.figure()

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

    max_size = 400
    max = 50
    duration["size"] = duration["OnlinePowerCapacityMW"] / max * max_size
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
            bbox_to_anchor=(0.6, 0),
            loc="lower center",
            fontsize="small",
            title_fontsize="small",
            ncol=4,
        )
        # Add legend for power capacity
        sizes = [5, 10, 30]
        fig.legend(
            title="Storage Capacity (GW)",
            handles=[
                tools.plt.lines.Line2D(
                    [],
                    [],
                    color="dimgray",
                    marker=".",
                    markersize=l,
                    label=l,
                    linestyle="None",
                    markeredgewidth=1,
                    markeredgecolor="dimgray",
                )
                for l, s in zip(sizes, [x / max * max_size for x in sizes])
            ],
            bbox_to_anchor=(0.35, 0),
            loc="lower center",
            fontsize="small",
            title_fontsize="small",
            ncol=3,
            labelspacing=1.5,
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


def highlight_zones(zones, ax):
    if zones is None:
        return
    for _, lz in tools.maps._wecc_lz.iterrows():
        if lz.gen_load_zone in zones:
            # Add load zone borders
            ax.add_geometries(
                lz.geometry,
                crs=tools.maps.get_projection(),
                facecolor=(0, 0, 0, 0),  # Transparent
                edgecolor="tab:green",
                linewidth=1,
                # linestyle="--",
                # alpha=0,
            )


highlight_zones(zones_to_highlight, axes[0])

# %% SAVE FIGURE
save_figure("figure-s2-impact-of-10x-tx.png")

# %%
df = tools_supplementary.get_dataframe("storage_capacity.csv")
df = df.set_index("load_zone")
df_baseline = df[df.scenario_index == 0]
df_compare = df[df.scenario_index == 1]
df = df_baseline.join(df_compare, lsuffix="_base", rsuffix="_compare")
# df["change_in_cap"] = (
#     df["OnlineEnergyCapacityMWh_compare"] - df["OnlineEnergyCapacityMWh_base"]
# ) * 1e-3
df["change_in_cap"] = (
    df["OnlineEnergyCapacityMWh_compare"] / df["OnlineEnergyCapacityMWh_base"]
) * 100 - 100
df = df["change_in_cap"]
# df = df[df > 0]
# df.sum()
# df_compare["OnlineEnergyCapacityMWh"].sum() / df_baseline[
#     "OnlineEnergyCapacityMWh"
# ].sum() * 100 - 100
# df_compare["OnlineEnergyCapacityMWh"].sum() - df_baseline[
#     "OnlineEnergyCapacityMWh"
# ].sum()
df

# %% Num of load zones generating less than 25% of demand
scenario_index = 0
# scenario_index = 1 # For baseline
df = data[scenario_index][0].copy()
df = df[df < 50]
len(df)

# %% Contribution of zones to highlight

scenario_index = 0
# scenario_index = 1 # For baseline
dispatch = tools.get_dataframe("dispatch_zonal_annual_summary.csv")
dispatch = dispatch[dispatch.scenario_index == scenario_index]
dispatch = tools.transform.gen_type(dispatch)
dispatch = dispatch[dispatch.gen_type != "Storage"]
dispatch = dispatch.groupby("gen_load_zone")[["Energy_GWh_typical_yr"]].sum()
dispatch.columns = ["generation_gwh"]
dispatch = dispatch.reset_index()
dispatch.sort_values("generation_gwh")
total = dispatch.generation_gwh.sum()
total_for_zone = dispatch[
    dispatch.gen_load_zone.isin(zones_to_highlight)
].generation_gwh.sum()
total_for_zone / total

# %% Num zones to highlight
len(zones_to_highlight)

# %% Power contribution for load zones
df = tools.get_dataframe("storage_capacity.csv")
df = df.set_index("load_zone")
cities = ["CA_LADWP", "WA_SEATAC", "CA_PGE_BAY", "CA_SCE_S", "AZ_PHX"]
# df = df.loc[cities]
df["OnlineEnergyCapacityMWh"] *= 1e-3
df_compare = df[df.scenario_index == 0]
df_baseline = df[df.scenario_index == 1]
df = df_baseline.join(df_compare, lsuffix="_base", rsuffix="_compare")
df["change_in_cap"] = (
    df["OnlineEnergyCapacityMWh_compare"] - df["OnlineEnergyCapacityMWh_base"]
)
# df["change_in_cap"] = (df["OnlineEnergyCapacityMWh_compare"] / df["OnlineEnergyCapacityMWh_base"]) * 100
df = df["change_in_cap"]
df.sort_values()
# df.sum()
# df_compare["OnlineEnergyCapacityMWh"].sum() / df_baseline["OnlineEnergyCapacityMWh"].sum() * 100
