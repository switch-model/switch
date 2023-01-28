# %% GET TOOLS

# Imports
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import gridspec
import labellines

from papers.Martin_Staadecker_et_al_2022.util import (
    set_style,
    get_set_e_scenarios,
    save_figure,
)
from switch_model.tools.graph.main import GraphTools

# Prepare graph tools
tools = GraphTools(scenarios=get_set_e_scenarios(), set_style=False)
tools.pre_graphing(multi_scenario=True)
raw_load_balance = tools.get_dataframe(
    "load_balance.csv",
    usecols=[
        "load_zone",
        "timestamp",
        "normalized_energy_balance_duals_dollar_per_mwh",
        "scenario_name",
    ],
).rename(columns={"normalized_energy_balance_duals_dollar_per_mwh": "value"})
# raw_load_balance.value *= 0.1  # Convert from $/MWh to c/kWh
raw_load_balance = tools.transform.load_zone(raw_load_balance)

# %% CREATE FIGURE
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(6.850394, 6.850394)
gs = gridspec.GridSpec(2, 2, figure=fig)
ax1 = fig.add_subplot(gs[0, 0])
ax2 = fig.add_subplot(gs[0, 1])
ax3 = fig.add_subplot(gs[1, 0])
ax4 = fig.add_subplot(gs[1, 1])

y_label = "Marginal Price of Electricity ($/MWh)"
x_label = "WECC-wide storage capacity (TWh)"

# %% Variability

ax = ax1
ax.clear()
duals = raw_load_balance.copy()
# duals = duals[duals.region == "WA"] # uncomment to filter by region
duals = duals.groupby("scenario_name").value
variability = pd.DataFrame()
quantiles = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
for quantile in quantiles:
    variability.loc[:, quantile] = duals.quantile(quantile)

cmap = plt.cm.get_cmap("viridis")

ax.fill_between(
    variability.index,
    variability[0.05],
    variability[0.95],
    alpha=0.3,
    color="dimgray",
    # marker=".",
    label="5th-95th quantile",
)
ax.fill_between(
    variability.index,
    variability[0.25],
    variability[0.75],
    alpha=1,
    color="dimgray",
    # marker=".",
    label="25th-75th quantile",
)
ax.plot(
    variability.index,
    variability[0.01],
    marker=".",
    color="dimgray",
    label="1st & 99th quantile",
)
ax.plot(variability.index, variability[0.99], marker=".", color="dimgray")
ax.plot(variability.index, variability[0.5], marker=".", color="red", label="Median")

ax.set_xlabel(x_label)

ax.set_ylabel(y_label)
ax.legend()
ax.set_title("A. Distribution of marginal prices")

# %% Daily LMP

ax = ax3
ax.clear()
time_mapping = {0: "Midnight", 4: "4am", 8: "8am", 12: "Noon", 16: "4pm", 20: "8pm"}
daily_lmp = raw_load_balance.copy()
daily_lmp = tools.transform.timestamp(daily_lmp)
daily_lmp = daily_lmp.groupby(["scenario_name", "hour"], as_index=False).value.mean()
daily_lmp = daily_lmp.pivot(index="scenario_name", columns="hour", values="value")
daily_lmp = daily_lmp.rename(time_mapping, axis=1).rename_axis(
    "Time of day (PST)", axis=1
)
daily_lmp = daily_lmp.sort_values(by=1.94, axis=1, ascending=False)
lines = []
for col in daily_lmp:
    line = ax.plot(daily_lmp[col], marker=".", label=col)
    if col in ("Noon", "4pm", "8am"):
        labellines.labelLine(
            line[0],
            10,
            label=col,
            outline_width=1,
            align=False,
            color="k",
            fontsize="small",
        )
    lines += line
ax.legend(lines, [l.get_label() for l in lines])
ax.set_xlabel(x_label)
ax.set_ylabel(y_label)

ax.set_title("C. Marginal price by time of day")
# %% YEARLY LMP
ax = ax4
ax.clear()
months_map = {
    1: "Jan",
    2: "Feb-May",
    3: "Feb-May",
    4: "Feb-May",
    5: "Feb-May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep-Oct",
    10: "Sep-Oct",
    11: "Nov",
    12: "Dec",
}

cap = raw_load_balance
cap = cap.groupby(["scenario_name", "timestamp"], as_index=False).value.mean()
cap = tools.transform.timestamp(cap)
cap = cap.set_index("datetime")
cap["month"] = cap.index.month
cap["month"] = cap.month.map(months_map)
cap = cap.groupby(["scenario_name", "month"]).value.mean()
cap = cap.unstack("month").rename_axis("Months", axis=1)
cap = cap.sort_values(by=1.94, ascending=False, axis=1)
# cap = cap[["Jan", "Feb-May", "Jun", "Jul", "Aug", "Sep-Oct", "Nov", "Dec"]]

lines = []

y_pos = {"Dec": 10, "Jul": 6, "Jan": 12, "Aug": 9, "Jun": 25}

for col in cap:
    line = ax.plot(cap[col], marker=".", label=col)
    if col in y_pos:
        labellines.labelLine(
            line[0],
            y_pos[col],
            label=col,
            outline_width=1,
            align=False,
            color="k",
            fontsize="small",
        )
    lines += line
ax.legend(lines, [l.get_label() for l in lines])
ax.set_xlabel(x_label)
ax.set_ylabel(y_label)


ax.set_title("D. Marginal price by time of year")
# %% GEOGRAPHICAL LMP
ax = ax2
ax.clear()

geo = raw_load_balance.copy()
region_map = {
    "CAN": "Canada",
    "WA": "OR, WA",
    "OR": "OR, WA",
    "ID": "Idaho",
    "MT": "Montana",
    "WY": "CO, UT, WY",
    "CO": "CO, UT, WY",
    "UT": "CO, UT, WY",
    "NV": "Nevada",
    "CA": "California",
    "AZ": "AZ, NM, MEX",
    "NM": "AZ, NM, MEX",
    "MEX": "AZ, NM, MEX",
}
geo.region = geo.region.map(region_map)
geo = geo.groupby(["scenario_name", "region"]).value.mean()
geo = geo.unstack("region")
geo = geo.sort_values(by=1.94, axis=1, ascending=False)
geo = geo.rename_axis("Regions", axis=1)
geo.plot(
    ax=ax,
    xlabel=x_label,
    marker=".",
    ylabel=y_label,
    # cmap="tab10"
)

lines = []

y_pos = {"California": 8, "Canada": 25}

for col in geo:
    line = ax.plot(geo[col], marker=".", label=col)
    if col in y_pos:
        labellines.labelLine(
            line[0],
            y_pos[col],
            label=col,
            outline_width=1,
            align=False,
            color="k",
            fontsize="small",
        )
    else:
        labellines.labelLine(
            line[0],
            48,
            label=col,
            outline_width=1,
            align=False,
            color="k",
            fontsize="small",
        )
    lines += line
ax.legend(lines, [l.get_label() for l in lines])
ax.set_xlabel(x_label)
ax.set_ylabel(y_label)

ax.set_title("B. Marginal price by region")
# %%
fig.tight_layout()
save_figure("figure-6-impact-of-LDES-on-COST.png")

# %% night time vs day time
df = daily_lmp.divide(daily_lmp["Noon"], axis=0) * 100 - 100
df.min()
df.max()
# %% average drop in daily duals
df = daily_lmp.mean(axis=1)
df / df.iloc[0] - 1
# daily_lmp / daily_lmp.iloc[0] - 1
# %% night time drop
df = daily_lmp[["Midnight", "8pm", "4am"]].mean(axis=1)
(1 - df.loc[3] / df.iloc[0]) * 100 / ((3 - 1.94) * 10)
# %% LMP stats
raw_load_balance.nunique()
raw_load_balance
# %% Variability baseline
baseline = raw_load_balance[raw_load_balance.scenario_name == 1.94]
len(baseline[baseline.value == 0]) / len(baseline) * 100  # Percent at 0 LMP
len(baseline[baseline.value > 40]) / len(baseline)
# %% Variability 20twh
df = raw_load_balance[raw_load_balance.scenario_name == 20]
df.value.quantile(0.99)
len(df[df.value == 0]) / len(df)
df.value.median()
# %% Regional NORTH
df = raw_load_balance[raw_load_balance.region.isin(["CAN", "OR", "WA"])]
df.groupby("scenario_name").value.mean()
# %% Regional CA
df = raw_load_balance[raw_load_balance.region == "CA"]
df = df.groupby("scenario_name").value.mean()
df
-(1 - df / df.iloc[0]) * 100
# %% Regional SOUTH
df = raw_load_balance[raw_load_balance.region.isin(["MEX", "AZ", "NV", "NM"])]
df = df.groupby("scenario_name").value.mean()
df
# %% MONTHLY
cap
cap.loc[20, :]
df = cap.loc[64, :].sort_values(ascending=False)
df
# %% CHANGE IN PRICE SURGE IN 99th percentile
1 - variability.loc[20, 0.99] / variability.loc[1.94, 0.99]
