# %% IMPORT + CREATE tools
from matplotlib import pyplot as plt

from switch_model.tools.graph.main import GraphTools

from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    set_style,
    get_scenario, save_figure,
)

tools_solar = GraphTools([get_scenario("WS10", "91% Solar to 9% Wind")], set_style=False)
tools_solar.pre_graphing(multi_scenario=False)

tools_wind = GraphTools([get_scenario("WS066", "40% Solar to 60% Wind")], set_style=False)
tools_wind.pre_graphing(multi_scenario=False)

ROLLING_AVERAGE_DAYS = 7

# %% CREATE PLOT FRAME
set_style()
plt.close()
fig = plt.figure()
ax1 = fig.add_subplot(1, 2, 1, projection=tools_solar.maps.get_projection())
ax2 = fig.add_subplot(1, 2, 2, projection=tools_wind.maps.get_projection())


# %% CALC BOTTOM PANEL DATA
def get_data(tools):
    # Get data for mapping code
    capacity = tools.get_dataframe("gen_cap.csv").rename(
        {"GenCapacity": "value"}, axis=1
    )
    capacity = tools.transform.gen_type(capacity)
    capacity = capacity.groupby(["gen_type", "gen_load_zone"], as_index=False)[
        "value"
    ].sum()
    # capacity = capacity[capacity.value > 1e-3]  # Must have at least 1 kW of capacity
    capacity.value *= 1e-3  # Convert to GW

    transmission = tools.get_dataframe(
        "transmission.csv", convert_dot_to_na=True
    ).fillna(0)
    transmission = transmission[transmission["PERIOD"] == 2050]
    newtx = transmission.copy()
    transmission = transmission.rename(
        {"trans_lz1": "from", "trans_lz2": "to", "TxCapacityNameplate": "value"}, axis=1
    )
    transmission = transmission[["from", "to", "value"]]
    transmission = transmission[transmission.value != 0]
    transmission.value *= 1e-3  # Convert to GW

    newtx = newtx.rename(
        {"trans_lz1": "from", "trans_lz2": "to", "BuildTx": "value"}, axis=1
    )
    newtx = newtx[["from", "to", "value"]]
    newtx = newtx[newtx.value != 0]
    newtx.value *= 1e-3  # Convert to GW

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
    duration = duration[["gen_load_zone", "value"]]
    return transmission, newtx, capacity, duration


def plot(tools, ax, data, legend=True):
    transmission, newtx, capacity, duration = data
    tools.maps.draw_base_map(ax)
    tools.maps.graph_transmission_capacity(
        transmission,
        ax=ax,
        legend=legend,
        color="green",
        bbox_to_anchor=(1, 0.65),
        title="Total Tx Capacity (GW)",
    )
    tools.maps.graph_transmission_capacity(
        newtx,
        ax=ax,
        legend=legend,
        color="red",
        bbox_to_anchor=(1, 0.44),
        title="New Tx Capacity (GW)",
    )
    tools.maps.graph_pie_chart(capacity, ax=ax, legend=legend)
    tools.maps.graph_duration(
        duration, ax=ax, legend=legend, bins=(0, 6, 10, 20, float("inf"))
    )
    ax.set_title(tools.scenarios[0].name)


# %% PLOT BOTTOM PANEL
plot(tools_wind, ax2, get_data(tools_wind))

# %% PLOT LEFT PANEL
plot(tools_solar, ax1, get_data(tools_solar), legend=False)
plt.tight_layout()
plt.tight_layout()  # Twice to ensure it works properly, it's a bit weird at times'

# %%
save_figure("figure-3-wind-vs-solar.png")
