from papers.Martin_Staadecker_et_al_2022.util import get_scenario
from switch_model.tools.graph.main import GraphTools
import pandas as pd

tools = GraphTools(scenarios=[get_scenario("1342", "1342")])
tools.pre_graphing(multi_scenario=False)

projects = tools.get_dataframe(
    "generation_projects_info.csv", from_inputs=True, convert_dot_to_na=True
)
costs = tools.get_dataframe(
    "gen_build_costs.csv", from_inputs=True, convert_dot_to_na=True
)
predetermined = tools.get_dataframe(
    "gen_build_predetermined", from_inputs=True, convert_dot_to_na=True
)

projects = projects.merge(
    costs,
    on=["GENERATION_PROJECT"],
)

projects = projects.merge(
    predetermined,
    on=["GENERATION_PROJECT", "build_year"],
    how="left",  # Makes a left join
)

projects = projects[projects.build_year == 2050]
group = projects.groupby(["gen_energy_source", "gen_tech"])

overnight = group.gen_overnight_cost.mean()
fixed = group.gen_fixed_om.mean()
variable = group.gen_variable_om.mean()

all_data = pd.concat([overnight, fixed, variable], axis=1).round(0)
print(all_data)
