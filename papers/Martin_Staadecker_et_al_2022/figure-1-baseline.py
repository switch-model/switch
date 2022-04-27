# %% IMPORT + CREATE tools
from matplotlib import pyplot as plt
from matplotlib import dates as mdates

from switch_model.tools.graph.main import GraphTools

from papers.Martin_Staadecker_et_al_2022.util import (
    set_style,
    get_scenario, save_figure,
)

tools = GraphTools([get_scenario("1342")], set_style=False)
tools.pre_graphing(multi_scenario=False)

ROLLING_AVERAGE_DAYS = 7

# %% CALC TOP PANEL DATA


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
# Flip sign
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

# %% CREATE PLOT FRAME
set_style()
plt.close()
fig = plt.figure()
ax1 = fig.add_subplot(1, 2, 1)
ax2 = fig.add_subplot(1, 2, 2, projection=tools.maps.get_projection())
# %% PLOT TOP PANEL
ax = ax1
ax_right = ax1.twinx()
ax_right.grid(False)
# Plot
# Get the colors for the lines
# plot
colors = tools.get_colors()

lines = []
for (columnName, columnData) in dispatch.items():
    lines += ax.plot(columnData, color=colors[columnName], label=columnName)
for (columnName, columnData) in curtailment.items():
    lines += ax.plot(
        columnData,
        linestyle="dashed",
        color=colors[columnName],
        label=columnName + " (no curtail.)",
    )
ax_right.plot(duals, label="Estimated LMP", color="red")
lines += ax.plot(load, color="orange", label="Demand")
ax.set_title("A. Seasonal Profiles in the Baseline")
ax.set_ylabel("Dispatch (TWh/day)")
ax_right.set_ylabel(u"Estimated Locational Marginal Price ($/MWh)")
locator = mdates.MonthLocator()
ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
ax.set_ylim(-0.1, 4.7)
ax_right.set_ylim(-10, 470)
ax.legend(lines, [l.get_label() for l in lines], framealpha=0.5, loc="upper left")
ax_right.legend()

# %% CALC BOTTOM PANEL DATA
# Get data for mapping code
capacity = tools.get_dataframe("gen_cap.csv").rename({"GenCapacity": "value"}, axis=1)
capacity = tools.transform.gen_type(capacity)
capacity = capacity.groupby(["gen_type", "gen_load_zone"], as_index=False)["value"].sum()
# capacity = capacity[capacity.value > 1e-3]  # Must have at least 1 kW of capacity
capacity.value *= 1e-3  # Convert to GW

transmission = tools.get_dataframe("transmission.csv", convert_dot_to_na=True).fillna(0)
transmission = transmission[transmission["PERIOD"] == 2050]
newtx = transmission.copy()
transmission = transmission.rename({"trans_lz1": "from", "trans_lz2": "to", "TxCapacityNameplate": "value"}, axis=1)
transmission = transmission[["from", "to", "value"]]
transmission = transmission[transmission.value != 0]
transmission.value *= 1e-3  # Convert to GW

newtx = newtx.rename({"trans_lz1": "from", "trans_lz2": "to", "BuildTx": "value"}, axis=1)
newtx = newtx[["from", "to", "value"]]
newtx = newtx[newtx.value != 0]
newtx.value *= 1e-3  # Convert to GW

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

# %% PLOT BOTTOM PANEL
ax = ax2
tools.maps.draw_base_map(ax)
tools.maps.graph_transmission_capacity(transmission, ax=ax, legend=True, color="green", bbox_to_anchor=(1, 0.61),
                                       title="Total Tx Capacity (GW)")
tools.maps.graph_transmission_capacity(newtx, ax=ax, legend=True, color="red", bbox_to_anchor=(1, 0.4),
                                       title="New Tx Capacity (GW)")
tools.maps.graph_pie_chart(capacity, ax=ax)
tools.maps.graph_duration(duration, ax=ax)
ax.set_title("B. Geographical Distributions in the Baseline")
plt.tight_layout()
plt.tight_layout()  # Twice to ensure it works properly, it's a bit weird at times

# %%
save_figure("figure-1-baseline.png")
# %% CALCULATIONS

# Panel A analysis
df = curtailment.copy()
df = df[["Solar"]]
df.columns = ["Curtailed"]

df2 = dispatch.copy()
df2 = df2[["Solar"]]
df2.columns = ["Total"]

df = df.join(df2)

df["Percent"] = (df.Curtailed - df.Total) / df.Total * 100
# ax1.plot(df["Percent"])
print("Max percent curtailed (%)", df.Percent.max())

# %%

df = duals
df = df.sort_values("value")
df = df[df.index.month != 12]  # Toggle to get value for mid year
# Inspect df to find maximum in each zone

# %%

df = dispatch.copy()
df["Nuclear"].unique() * 7

# %%

df = dispatch.copy()
df = df["Hydro"] * 7
print(df.min())
print(df.max())

# %%

df = curtailment.copy()
df_winter = df[(df.index.month <= 3) | (df.index.month >= 11)]
df_summer = df[~df.index.isin(df_winter.index)]
df_winter = df_winter.mean()
df_summer = df_summer.mean()
((df_winter / df_summer) - 1) * 100

# %%

# Get California stats
df = tools.get_dataframe("dispatch.csv")
df = tools.transform.gen_type(df)
df = df.groupby(["gen_load_zone", "gen_type"], as_index=False).sum()
df2 = df
# %%
# Get solar percent in generation
df = df2.copy()
df = tools.transform.load_zone(df, load_zone_col="gen_load_zone")
df_ca = df[df.region == "CA"]
df_ca = df_ca.groupby("gen_type")["DispatchGen_MW"].sum()
df_ca = df_ca[df_ca.index != "Storage"]

df_ca = df_ca / df_ca.sum()
df_ca

# %%
df = capacity.copy()
df = tools.transform.load_zone(df, load_zone_col="gen_load_zone")
df = df[df.region == "CA"]
df = df.groupby("gen_type").sum()
# df = (df / df.sum())
df
df = df[~df.index.isin(["Storage", "Solar"])]
df.sum()

# %%
df = capacity.copy()
southern_regions = ("CA", "NV", "UT", "CO", "AZ", "NM", "MEX")
df = tools.transform.load_zone(df, load_zone_col="gen_load_zone")
df = df.groupby(["region", "gen_type"], as_index=False).sum()
df_north = df[~df["region"].isin(southern_regions)]
df_north = df_north.groupby("gen_type").sum()
df = df.groupby("gen_type").sum()
df_north / df * 100

# %%
# Get load dataframe
df = tools.get_dataframe("load_balance.csv").rename({"zone_demand_mw": "value"}, axis=1)
df = tools.transform.load_zone(df)
df = df.groupby("region").value.sum() * -1
df_north = df[~df.index.isin(southern_regions)]
df_north.sum() / df.sum() * 100

# %%
df = tools.get_dataframe("transmission.csv", convert_dot_to_na=True).fillna(0)
df = df[df["PERIOD"] == 2050]
df = tools.transform.load_zone(df, load_zone_col="trans_lz1").rename({"region": "region_1"}, axis=1)
df = tools.transform.load_zone(df, load_zone_col="trans_lz2").rename({"region": "region_2"}, axis=1)
df.BuildTx *= df.trans_length_km
df.TxCapacityNameplate *= df.trans_length_km
df = df[["region_1", "region_2", "BuildTx", "TxCapacityNameplate"]]
df_north = df[(~df.region_1.isin(southern_regions)) & (~df.region_2.isin(southern_regions))]
df = df[df.region_1.isin(southern_regions) == df.region_2.isin(southern_regions)]
df = df[["BuildTx", "TxCapacityNameplate"]]
df_north = df_north[["BuildTx", "TxCapacityNameplate"]]
df_north = df_north.sum()
df = df.sum()
df_north / df

# %%
df = duration
df = df.sort_values(by="value")
df

# %%
df = tools.get_dataframe("storage_capacity.csv")
df = df[df["period"] == 2050].drop(columns="period")
# df = df[df["load_zone"] != "CAN_ALB"]
# df = df.groupby("gen_load_zone", as_index=False).sum()
df["duration"] = df["OnlineEnergyCapacityMWh"] / df["OnlinePowerCapacityMW"]
df_long = df[df.duration > 10]
1 - df_long.OnlineEnergyCapacityMWh.sum() / df.OnlineEnergyCapacityMWh.sum()

# %% BIOMASS PERCENT MAX USAGE
df = dispatch
df = df.join(load)
df["biomass_contr"] = df["Biomass"] / df["value"]
df = df["biomass_contr"]
df = df.sort_values(ascending=False)
df * 100

# %% CALI DEMAND PEAK AND MEDIAN
# Get load dataframe
df = tools.get_dataframe(
    "load_balance.csv",
    usecols=["timestamp", "load_zone", "zone_demand_mw"],
).rename({"zone_demand_mw": "value"}, axis=1)
df = tools.transform.load_zone(df, load_zone_col="load_zone")
df = df[df.region == "CA"]
df = tools.transform.timestamp(df)
df = df.groupby("datetime").value.sum()
df *= -1e-3
df = df.sort_values()
df.mean()
# df
