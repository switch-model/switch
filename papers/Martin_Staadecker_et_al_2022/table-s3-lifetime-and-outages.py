from papers.Martin_Staadecker_et_al_2022.util import get_scenario
from switch_model.tools.graph.main import GraphTools
import pandas as pd

tools = GraphTools(scenarios=[
    get_scenario("1342", "1342")
])
tools.pre_graphing(multi_scenario=False)

projects = tools.get_dataframe("generation_projects_info.csv", from_inputs=True, convert_dot_to_na=True)
costs = tools.get_dataframe("gen_build_costs.csv", from_inputs=True, convert_dot_to_na=True)
predetermined = tools.get_dataframe("gen_build_predetermined", from_inputs=True, convert_dot_to_na=True)

projects = projects.merge(
    costs,
    on=["GENERATION_PROJECT"],
)

projects = projects.merge(
    predetermined,
    on=["GENERATION_PROJECT", "build_year"],
    how="left"  # Makes a left join
)

# prebuilt = projects[projects.build_year != 2050]
age = (projects.groupby(["gen_energy_source", "gen_tech"]).gen_max_age.unique())

forced_outage_rate = (projects.groupby(["gen_energy_source", "gen_tech"]).gen_forced_outage_rate.unique())

scheduled_outage_rate = (projects.groupby(["gen_energy_source", "gen_tech"]).gen_scheduled_outage_rate.unique())

all_data = pd.concat([age, forced_outage_rate, scheduled_outage_rate], axis=1)
print(all_data)
