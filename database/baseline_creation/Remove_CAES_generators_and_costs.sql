--- This script makes a new scenario that does not include CAES (Compressed Air Energy Storage) as proposed generators

-- 1. Make new generation_plant scenario based on copy of scenario 22

INSERT INTO switch.generation_plant_scenario (generation_plant_scenario_id, name, description)

SELECT 23 AS generation_plant_scenario_id, 'EIA-WECC Existing and Proposed 2018, AMPL Basecase for Canada and Mex, AMPL proposed non-wind plants (only best of solar), Env Screen Wind Cat 3, No CAES' as name, 'same as id 22, but no Compressed Air Energy Storage gen_tech among candidate generators' as description
FROM switch.generation_plant_scenario
WHERE b.generation_plant_scenario_id = 22

-- 2. Make a copy of generation_plant_scenario 22 as scenario 23, without Compressed Air Energy Storage
INSERT INTO switch.generation_plant_scenario_member (generation_plant_scenario_id, generation_plant_id)

SELECT 23 as generation_plant_scenario_id, a.generation_plant_id
FROM generation_plant_scenario_member a
JOIN generation_plant b
ON a.generation_plant_id = b.generation_plant_id
WHERE a.generation_plant_scenario_id = 22
AND b.gen_tech != 'Compressed_Air_Energy_Storage'

-- 3. Make new generation_plant_cost_scenario based on copy of scenario 23
INSERT INTO switch.generation_plant_cost_scenario (generation_plant_cost_scenario_id, name, description)

SELECT 24 AS generation_plant_cost_scenario_id, 'SWITCH 2020 Baseline costs without CAES' as name, 'same costs as id 23 (updated costs for solar, wind, battery, geothermal, csp, ccgt, gt from NREL ATB 2019) but no Compressed Air Energy Storage' as description
FROM switch.generation_plant_cost_scenario
WHERE generation_plant_cost_scenario_id = 23

-- 4. Make a copy of generation_plant_scenario 22 as scenario 23, without Compressed Air Energy Storage
INSERT INTO switch.generation_plant_cost (generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)

SELECT 24 AS generation_plant_cost_scenario_id, a.generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh
FROM switch.generation_plant_cost a
JOIN switch.generation_plant b
ON a.generation_plant_id = b.generation_plant_id
WHERE a.generation_plant_cost_scenario_id = 23
AND b.gen_tech != 'Compressed_Air_Energy_Storage'

