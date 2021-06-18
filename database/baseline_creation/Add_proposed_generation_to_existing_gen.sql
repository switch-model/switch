-- Copy scenario 21 and make scenario 22. This scenario is the existing and planned EIA and AMPL (Canada and Mexico)
-- data for exisiting generators + the proposed generators from generation_plant scenario 14

-- Generation plant scenario

-- Scenario mapping table (generation_plant_scenario_member, generation_plant_scenario_id)
-- 1. Add a new generation_plant_scenario and id into generation_plant_scenario_member scenario mapping table:

INSERT INTO switch.generation_plant_scenario (generation_plant_scenario_id, name, description)
VALUES (22, 'EIA-WECC Existing and Proposed 2018, AMPL Basecase for Canada and Mex, AMPL proposed non-wind plants (only best of solar), Env Screen Wind Cat 3', 'existing gen same as id 21, but adding proposed from scenario 14')

-- Data table (generation_plant_scenario, generation_plant_scenario_id)
-- 2. Then copy the generation_plant_scenario time series for scenario 19 into Data table:

INSERT INTO switch.generation_plant_scenario_member (generation_plant_scenario_id, generation_plant_id)
SELECT 22 as generation_plant_scenario_id, generation_plant_id
FROM switch.generation_plant_scenario_member
WHERE generation_plant_scenario_id = 21

-- 3. Add into new generation_plant_scenario time series 21, the generation_plant_scenario time series from scenario 1, for the AMPL existing generation plant ids for Canada and Mexico

-- proposed wind plants that are named
INSERT INTO switch.generation_plant_scenario_member (generation_plant_scenario_id, generation_plant_id)

SELECT 22 as generation_plant_scenario_id, b.generation_plant_id
FROM switch.generation_plant_scenario_member a
JOIN generation_plant b
ON a.generation_plant_id = b.generation_plant_id
where a.generation_plant_scenario_id = 14
and b.name != 'Proposed'
and b.gen_tech = 'Wind'

-- proposed non-wind plants that are not named
INSERT INTO switch.generation_plant_scenario_member (generation_plant_scenario_id, generation_plant_id)

SELECT 22 as generation_plant_scenario_id, a.generation_plant_id
FROM switch.generation_plant_scenario_member a
JOIN generation_plant b
ON a.generation_plant_id = b.generation_plant_id
WHERE a.generation_plant_scenario_id = 14
and b.name = 'Proposed'

-- Plant cost

-- Generation plant cost scenario

-- Scenario mapping table (generation_plant_cost_scenario, generation_plant_cost_scenario_id)
-- 1. Add a new generation_plant_cost_scenario row and id into the generation_plant_cost_scenario table

INSERT INTO switch.generation_plant_cost_scenario (generation_plant_cost_scenario_id, name, description)
VALUES (22, 'EIA-WECC Existing and Proposed 2018, AMPL Basecase for Canada and Mex, AMPL candidate non-wind plants (only best of solar), Env Screen Wind Cat 3', 'existing gen same as id 21, but adding proposed from scenario 14')

-- Data table (generation_plant_cost, generation_plant_cost_scenario_id)
-- 2. Then copy the generation_plant_cost time series for scenario 21:
INSERT INTO switch.generation_plant_cost (generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)

SELECT 22 AS generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh
FROM switch.generation_plant_cost
WHERE generation_plant_cost_scenario_id = 21

-- 3. Add into new generation_plant_cost time series 22, the proposed generation_plant_cost time series from scenario 14
-- The overnight costs are nonzero, unlike for the EIA data...

-- First insert the 'Wind' generators

INSERT INTO switch.generation_plant_cost (generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)

SELECT 22 as generation_plant_cost_scenario_id, a.generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh
FROM switch.generation_plant_cost a
JOIN generation_plant b
ON a.generation_plant_id = b.generation_plant_id
JOIN generation_plant_scenario_member c
ON a.generation_plant_id = c.generation_plant_id
WHERE c.generation_plant_scenario_id = 14
AND a.generation_plant_cost_scenario_id = 6
AND b.name != 'Proposed'
AND b.gen_tech = 'Wind'

-- Then insert the 'Proposed' aggregated generators by load zone

INSERT INTO switch.generation_plant_cost (generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)

SELECT 22 as generation_plant_cost_scenario_id, a.generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh
FROM switch.generation_plant_cost a
JOIN generation_plant b
ON a.generation_plant_id = b.generation_plant_id
JOIN generation_plant_scenario_member c
ON a.generation_plant_id = c.generation_plant_id
WHERE c.generation_plant_scenario_id = 14
AND b.name = 'Proposed'
AND a.generation_plant_cost_scenario_id = 6


