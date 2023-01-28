# %% IMPORT + CREATE tools
from matplotlib import pyplot as plt

from papers.Martin_Staadecker_et_al_2022.util import (
    set_style,
    get_scenario,
    save_figure,
)
from switch_model.tools.graph.main import GraphTools

tools_baseline = GraphTools(
    [get_scenario("1342", "Baseline Scenario")], set_style=False
)
tools_baseline.pre_graphing(multi_scenario=False)

tools_hydro = GraphTools(
    [get_scenario("H050", "50% Hydro Scenario (from Set B)")], set_style=False
)
tools_hydro.pre_graphing(multi_scenario=False)

ROLLING_AVERAGE_DAYS = 7

# %% CREATE PLOT FRAME
set_style()
plt.close()
fig = plt.figure()
ax1 = fig.add_subplot(1, 2, 1, projection=tools_baseline.maps.get_projection())
ax2 = fig.add_subplot(1, 2, 2, projection=tools_hydro.maps.get_projection())


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
plot(tools_hydro, ax2, get_data(tools_hydro))

# %% PLOT LEFT PANEL
plot(tools_baseline, ax1, get_data(tools_baseline), legend=False)
plt.tight_layout()
plt.tight_layout()  # Twice to ensure it works properly, it's a bit weird at times'
# %% SAVE FIGURE
save_figure("figure-s1-impact-of-half-hydro.png")
