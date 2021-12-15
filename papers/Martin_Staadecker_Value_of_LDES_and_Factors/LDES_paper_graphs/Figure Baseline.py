# %%
from matplotlib import pyplot as plt
from matplotlib import dates as mdates

from switch_model.tools.graph.main import GraphTools

from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    set_style,
    get_scenario,
)

tools = GraphTools([get_scenario("1342")])
tools.pre_graphing(multi_scenario=False)

ROLLING_AVERAGE_DAYS = 14

# %%


dispatch = tools.get_dataframe(
    "dispatch.csv",
    usecols=[
        "timestamp",
        "gen_tech",
        "gen_energy_source",
        "DispatchGen_MW",
        "Curtailment_MW",
    ],
).rename({"DispatchGen_MW": "dispatch", "Curtailment_MW": "with_curtailment"}, axis=1)
dispatch = tools.transform.gen_type(dispatch)
dispatch["with_curtailment"] += dispatch["dispatch"]

# Sum dispatch across all the projects of the same type and timepoint
dispatch = dispatch[dispatch["gen_type"] != "Storage"]
dispatch = dispatch.groupby(["timestamp", "gen_type"], as_index=False).sum()

# Get load dataframe
load = tools.get_dataframe(
    "load_balance.csv",
    usecols=["timestamp", "zone_demand_mw"],
).rename({"zone_demand_mw": "value"}, axis=1)
# Sum load across all the load zones
load = load.groupby("timestamp", as_index=False).sum()
# Include Tx Losses in demand and flip sign
load["value"] *= -1


def process_time(df):
    # Add the datetime info like timestamps and PST time
    df = tools.transform.timestamp(df)
    # Filter range so we only get from Jan 2nd to Dec 31st
    df = df[(df["timestamp"] >= 2050010208) & (df["timestamp"] <= 2050123104)]
    # Keep only last period
    df = df.astype({"period": int})
    df = df[df["period"] == df["period"].max()].drop(columns="period")
    df = df.set_index("datetime")
    # Remove unneeded columns
    df = df.drop(
        columns=[
            "hour",
            "timestamp",
            "timepoint",
            "time_row",
            "time_column",
            "season",
            "timeseries",
        ]
    )
    return df


# Add the timestamp information and make period string to ensure it doesn't mess up the graphing
dispatch = process_time(dispatch)
load = process_time(load)

dispatch["dispatch"] *= dispatch["tp_duration"] / 1e6
dispatch["with_curtailment"] *= dispatch["tp_duration"] / 1e6
load["value"] *= load["tp_duration"] / 1e6
dispatch = dispatch.drop(columns="tp_duration")
load = load.drop(columns="tp_duration")

curtailment = (
    dispatch[["gen_type", "with_curtailment"]]
    .copy()
    .rename({"with_curtailment": "value"}, axis=1)
)
dispatch = dispatch[["gen_type", "dispatch"]].rename({"dispatch": "value"}, axis=1)


def rolling_avg(df):
    freq = str(ROLLING_AVERAGE_DAYS) + "D"
    df = df.rolling(freq, center=True).mean()
    return df


dispatch = (
    dispatch.groupby("gen_type").value.resample("D").sum().unstack(level=1).transpose()
)
dispatch = rolling_avg(dispatch)
curtailment = (
    curtailment.groupby("gen_type")
    .value.resample("D")
    .sum()
    .unstack(level=1)
    .transpose()
)
curtailment = rolling_avg(curtailment)
load = load[["value"]].resample("D").sum()
load = rolling_avg(load)
dispatch = dispatch[
    dispatch.columns[dispatch.max() > 1e-3]
]  # Remove techs that don't contribute more than 1GWh/day on any day
curtailment = curtailment[["Wind", "Solar"]]
dispatch = dispatch[dispatch.std().sort_values().index].rename_axis(
    "Technology", axis=1
)

duals = tools.get_dataframe(
    "load_balance.csv",
    usecols=["timestamp", "normalized_energy_balance_duals_dollar_per_mwh"],
).rename(columns={"normalized_energy_balance_duals_dollar_per_mwh": "value"})
duals = duals.groupby(["timestamp"], as_index=False).mean()
duals = process_time(duals).drop(columns=["tp_duration"])
duals = rolling_avg(duals)
# Convert from $/MWh to cents/kWh
duals *= 0.1

# %%
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(12, 6)
ax1 = fig.add_subplot(1, 2, 1)
ax2 = fig.add_subplot(1, 2, 2, projection=tools.maps.get_projection())
ax1_right = ax1.twinx()
# %%
ax = ax1
ax_right = ax1_right
# Plot
# Get the colors for the lines
# plot
colors = tools.get_colors()

lines = []
for (columnName, columnData) in dispatch.iteritems():
    lines += ax.plot(columnData, color=colors[columnName], label=columnName)
for (columnName, columnData) in curtailment.iteritems():
    lines += ax.plot(
        columnData,
        linestyle="dashed",
        color=colors[columnName],
        label=columnName + " (no curtail.)",
    )
ax_right.plot(duals, label="Dual Values", color="dimgray")
lines += ax.plot(load, color="red", label="Load")
ax.set_title("A. Seasonal Profiles in the Baseline")
ax.set_ylabel("Dispatch (TWh/day)")
ax_right.set_ylabel(u"Normalized Duals (\xa2/kWh)")
locator = mdates.MonthLocator()
ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
ax.set_ylim(-0.1, 4.7)
ax_right.set_ylim(-1, 47)
ax.legend(lines, [l.get_label() for l in lines], framealpha=0.5, loc="upper left")
ax_right.legend()

# %%
# Get data for mapping code
capacity = tools.get_dataframe("gen_cap.csv").rename({"GenCapacity": "value"}, axis=1)
capacity = tools.transform.gen_type(capacity)
capacity = capacity.groupby(["gen_type", "gen_load_zone"], as_index=False)["value"].sum()
capacity = capacity[capacity.value > 1e-3]  # Must have at least 1 kW of capacity
capacity.value *= 1e-3 # Convert to GW

transmission = tools.get_dataframe("transmission.csv", convert_dot_to_na=True).fillna(0)
transmission = transmission[transmission["PERIOD"] == 2050]
transmission = transmission.rename({"trans_lz1": "from", "trans_lz2": "to", "TxCapacityNameplate": "value"}, axis=1)
transmission = transmission[["from", "to", "value"]]
transmission = transmission[transmission.value != 0]
transmission.value *= 1e-3  # Convert to GW

duration = tools.get_dataframe("storage_capacity.csv", usecols=[
    "load_zone",
    "OnlineEnergyCapacityMWh",
    "OnlinePowerCapacityMW",
    "period"
]).rename({"load_zone": "gen_load_zone"}, axis=1)
duration = duration[duration["period"] == 2050].drop(columns="period")
duration = duration.groupby("gen_load_zone", as_index=False).sum()
duration["value"] = duration["OnlineEnergyCapacityMWh"] / duration["OnlinePowerCapacityMW"]
duration = duration[["gen_load_zone", "value"]]

#%%
ax = ax2
tools.maps.draw_base_map(ax)
tools.maps.graph_transmission(transmission, ax=ax, legend=False)
tools.maps.graph_pie_chart(capacity, ax=ax)
tools.maps.graph_duration(duration, ax=ax)
ax.set_title("B. Geographical Distributions in the Baseline")
plt.tight_layout()

