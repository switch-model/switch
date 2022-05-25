# %%
import matplotlib.pyplot as plt
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
ax = fig.gca()
# %% Get DATA
ax.clear()
duration = tools.get_dataframe("storage_capacity.csv")
duration = tools.transform.load_zone(duration)
duration = duration[duration.region == "CA"]
duration["duration"] = duration["duration"] = (
        duration["OnlineEnergyCapacityMWh"] / duration["OnlinePowerCapacityMW"]
)

duration = duration.sort_values("duration")
duration = duration[["duration", "OnlinePowerCapacityMW", "scenario_name"]]
duration.OnlinePowerCapacityMW /= 1e3  # Change to GW

for scenario_name in duration.scenario_name.unique():
    duration_scenario = duration[duration.scenario_name == scenario_name]
    duration_scenario["cuml_power"] = duration_scenario.OnlinePowerCapacityMW.cumsum()
    duration_scenario = duration_scenario.set_index("cuml_power")
    duration_scenario = duration_scenario["duration"]
    line = ax.plot(duration_scenario.index, duration_scenario, drawstyle="steps", label=scenario_name)
    if float(int(scenario_name)) == scenario_name:
        label = str(int(scenario_name))
    else:
        label = str(scenario_name)
    labellines.labelLine(line[0], duration_scenario.index.max(), outline_width=2, label=label + "$/KWh", align=False,
                         fontsize="small")

ax.set_yscale("log")
ax.set_xlabel("Storage Power Capacity (GW)")
ax.set_ylabel("Storage Duration (h)")
ax.set_yticks([10, 100, 1000])
ax.set_yticks([2, 3, 4, 5, 6, 7, 8, 9, 20, 30, 40, 50, 60, 70, 80, 90, 200, 300, 400, 500, 600, 700, 800, 900],
              minor=True)
ax.set_yticklabels(["10", "100", "1000"])
plt.tight_layout()

# %%
save_figure("figure-s6-duration-cdf-cost-scenarios-ca-only.png")