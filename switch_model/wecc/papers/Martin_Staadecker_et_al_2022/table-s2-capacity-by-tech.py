from papers.Martin_Staadecker_et_al_2022.util import get_scenario
from switch_model.tools.graph.main import GraphTools

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

prebuilt = projects[projects.build_year != 2050]
prebuilt_by_tech = (prebuilt.groupby(["gen_energy_source", "gen_tech"]).gen_capacity_limit_mw.sum() / 1000).round(1)
print("prebuilt by tech capacity")
print(prebuilt_by_tech)
print(prebuilt_by_tech.sum())


prebuilt = prebuilt[(prebuilt.build_year + prebuilt.gen_max_age) > 2051]
prebuilt_by_tech = (prebuilt.groupby(["gen_energy_source", "gen_tech"]).gen_capacity_limit_mw.sum() / 1000).round(1)
print("prebuilt by tech capacity still online")
print(prebuilt_by_tech)
print(prebuilt_by_tech.sum())

candidate = projects[projects.build_year == 2050]
candidate.gen_capacity_limit_mw = candidate.gen_capacity_limit_mw.fillna(-999999999)
print("candidate projects aggregated: ", len(candidate))
candidate_by_tech = (candidate.groupby(["gen_energy_source", "gen_tech"]).gen_capacity_limit_mw.sum() / 1000).round(1)
print(candidate_by_tech)
print(candidate_by_tech[candidate_by_tech > 0].sum())
