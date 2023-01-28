from papers.Martin_Staadecker_et_al_2022.util import get_scenario
from switch_model.tools.graph.main import GraphTools

tools = GraphTools(
    scenarios=[get_scenario("1342", "1342"), get_scenario("base", "base")]
)
tools.pre_graphing(multi_scenario=True)

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
    on=["GENERATION_PROJECT", "scenario_name", "scenario_index"],
)

projects = projects.merge(
    predetermined,
    on=["GENERATION_PROJECT", "build_year", "scenario_name", "scenario_index"],
    how="left",  # Makes a left join
)

prebuilt = projects[(projects.build_year != 2050) & (projects.scenario_name == "1342")]
print("prebuilt total :", len(prebuilt))
prebuilt = prebuilt[(prebuilt.build_year + prebuilt.gen_max_age) > 2051]
print("prebuilt alive :", len(prebuilt))

print("prebuild by tech")
prebuilt_by_tech = prebuilt.groupby(
    ["gen_energy_source", "gen_tech"]
).GENERATION_PROJECT.count()
print(prebuilt_by_tech)

prebuilt_by_tech = (
    prebuilt.groupby(["gen_energy_source", "gen_tech"]).gen_capacity_limit_mw.sum()
    / 1000
)
print("prebuilt by tech capacity")
print(prebuilt_by_tech.sort_values(ascending=False))
print(prebuilt_by_tech.sum())

candidate = projects[(projects.build_year == 2050) & (projects.scenario_name == "base")]
print(
    "candidate projects (50 extra than actual because storage gets overwritten): ",
    len(candidate),
)
candidate_by_tech = candidate.groupby(
    ["gen_energy_source", "gen_tech"]
).GENERATION_PROJECT.count()
print(candidate_by_tech)

candidate = projects[(projects.build_year == 2050) & (projects.scenario_name == "1342")]
print("candidate projects aggregated: ", len(candidate))
candidate_by_tech = (
    candidate.groupby(["gen_energy_source"]).gen_capacity_limit_mw.sum() / 1000
)
print(candidate_by_tech)

tools = GraphTools(scenarios=[get_scenario("WS043")])
tx = tools.get_dataframe("transmission.csv", convert_dot_to_na=True)
tx = tx[["BuildTx", "trans_length_km"]]
tx_new = (tx.BuildTx * tx.trans_length_km).sum() * 1e-6
print("Million MW-km tx deployed: ", tx_new)
