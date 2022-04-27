# %%
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
import labellines

from papers.Martin_Staadecker_et_al_2022.util import (
    set_style,
    get_scenario, save_figure
)
from switch_model.tools.graph.main import GraphTools

# Prepare graph tools
tools = GraphTools(scenarios=[
    get_scenario("C21", 0.5),
    get_scenario("C18", 1),
    get_scenario("C22", 2),
    get_scenario("C23", 5),
    get_scenario("C26", 7),
    get_scenario("C17", 10),
    get_scenario("C24", 15),
    get_scenario("1342", 22.43),
    get_scenario("C25", 40),
    get_scenario("C19", 70),
    get_scenario("C20", 102)
], set_style=False)
tools.pre_graphing(multi_scenario=True)

set_style()
plt.close()
fig = plt.figure()
# fig.set_size_inches(12, 6)
ax = fig.gca()

freq = "1D"

state_of_charge = tools.get_dataframe("StateOfCharge.csv")
state_of_charge = state_of_charge.rename(
    {"STORAGE_GEN_TPS_2": "timepoint", "StateOfCharge": "value"}, axis=1
)
state_of_charge = state_of_charge.groupby(
    ["scenario_name", "timepoint"], as_index=False
).value.sum()
state_of_charge.value *= 1e-6  # Convert from MWh to TWh
state_of_charge = tools.transform.timestamp(state_of_charge, use_timepoint=True)
state_of_charge = state_of_charge.set_index("datetime")
state_of_charge = state_of_charge.groupby("scenario_name").resample(freq).value.mean()
state_of_charge = state_of_charge.unstack("scenario_name").rename_axis(
    "Storage Capacity (TWh)", axis=1
)

demand = tools.get_dataframe("loads.csv", from_inputs=True).rename(
    {"TIMEPOINT": "timepoint", "zone_demand_mw": "value"}, axis=1
)
demand = demand[demand.scenario_name == 22.43]
demand = demand.groupby("timepoint", as_index=False).value.sum()
demand = tools.transform.timestamp(demand, use_timepoint=True)
demand = demand.set_index("datetime")["value"]
demand *= 4 * 1e-6  # Each timestep is 4 hours, converting to TWh
total_demand = demand.sum()
demand = demand.resample(freq).mean()
demand = demand * 35 / demand.max()

state_of_charge.plot(
    ax=ax,
    cmap="viridis",
    ylabel="WECC-wide stored energy (TWh, 24h mean)",
    xlabel="Time of year",
    legend=False,
)
plt.colorbar(
    cm.ScalarMappable(norm=Normalize(0.5, 102), cmap="viridis"),
    ax=ax,
    label="Energy Storage Capacity Costs ($/KWh)",
    fraction=0.1,
)

lines = ax.get_lines()
x_label = {
    5: 135,
    2: 160,
    1: 330,
    0.5: 230,
}
for line in lines:
    label = float(line.get_label())
    if label not in x_label.keys():
        continue
    labellines.labelLine(line, state_of_charge.index[x_label[label]], linespacing=1, outline_width=1, label=str(label)+"$/KWh", align=False, color='k', fontsize="small")

demand_lines = ax.plot(demand, c="dimgray", linestyle="--", alpha=0.5)
ax.legend(demand_lines, [f"Demand ({total_demand:.0f} TWh/year)"])

plt.tight_layout()
# %% SAVE FIGURE
save_figure("figure-s3-state-of-charge-under-different-costs.png")

