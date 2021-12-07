# %%
import pandas as pd

from switch_model.tools.graph.main import GraphTools

from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import (
    set_style,
    get_scenario,
)

set_style()

tools = GraphTools([get_scenario("1342")])
tools.pre_graphing(multi_scenario=False)

fig = tools.get_figure(size=(12, 12))
ax1 = fig.add_subplot(2, 2, 1)
ax2 = fig.add_subplot(2, 2, 2)
ax3 = fig.add_subplot(2, 2, 3)
ax4 = fig.add_subplot(2, 2, 4)

# %%
ax = ax1
ax.clear()
ax.tick_params(top=False, bottom=False, right=False, left=False, which="major")

dispatch = tools.get_dataframe(
    "dispatch.csv",
    usecols=["timestamp", "gen_tech", "gen_energy_source", "DispatchGen_MW"],
).rename({"DispatchGen_MW": "value"}, axis=1)
dispatch = tools.transform.gen_type(dispatch)

# Sum dispatch across all the projects of the same type and timepoint
dispatch = dispatch.groupby(["timestamp", "gen_type"], as_index=False).sum()
dispatch = dispatch[dispatch["gen_type"] != "Storage"]

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
    df["datetime"] = pd.to_datetime(df["timestamp"], format="%Y%m%d%H").dt.tz_localize("utc").dt.tz_convert("US/Pacific")
    df = df.astype({"period": int})
    df = df[df["period"] == df["period"].max()].drop(columns="period")
    df = df.set_index("datetime")
    df = df.shift(periods=1, freq="S")  # Shift by 1sec to ensure 00:00 gets counted on next day.
    return df


# Add the timestamp information and make period string to ensure it doesn't mess up the graphing
dispatch = process_time(dispatch)
load = process_time(load)

# Convert to TWh (incl. multiply by timepoint duration)
dispatch["value"] *= dispatch["tp_duration"] / 1e6
load["value"] *= load["tp_duration"] / 1e6

days = 14
freq = str(days) + "D"
offset = tools.pd.Timedelta(freq) / 2

def rolling_sum(df):
    df = df.rolling(freq, center=True).value.sum().reset_index()
    df["value"] /= days
    df = df[
        (df.datetime.min() + offset < df.datetime)
        & (df.datetime < df.datetime.max() - offset)
    ]
    return df

#%%
dispatch = dispatch.groupby("gen_type").value.resample("D").sum().unstack(1).transpose()
dispatch = rolling_sum(dispatch)
load = load.resample('D').sum()
load = load[["value"]]
load = rolling_sum(load).set_index("datetime")["value"]
#%%
# dispatch = dispatch.pivot(columns="gen_type", index="datetime", values="value")
dispatch = dispatch[
    dispatch.columns[dispatch.max() > 1e-6]
]  # Remove techs that don't contribute more than 1MWh/day on any day
dispatch = dispatch[dispatch.std().sort_values().index].rename_axis(
    "Technology", axis=1
)


# Plot
# Get the colors for the lines
# plot
dispatch.plot(ax=ax, color=tools.get_colors(), legend=True, xlabel="")
load.plot(ax=ax, color="red", linestyle="dashed", label="Total Demand", xlabel="")
ax.set_title("A. Seasonal storage breakdown")
ax.set_ylabel("Dispatch (TWh/day)")
