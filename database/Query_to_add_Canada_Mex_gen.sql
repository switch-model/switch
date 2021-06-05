-- This script is the first of 2 sql scripts that create a new set of scenarios 21 which is a combination of the set of existing and planned generators from the EIA 2020 update (non-aggregated), scenario 19 and the existing generators from AMPL for Canada and Mexico

-- 5 tables to adjust with these new generation_plant_ids:
--generation_plant_cost
--generation_plant_scenario_member
--generation_plant_existing_and_planned
--hydro_historical_monthly_capacity_factors
--variable_capacity_factors

-- 1. Generation Plant table: make a copy of the original AMPL generators in Canada and Mexico, and make the connect_cost_mw 0

INSERT INTO switch.generation_plant (name, gen_tech, load_zone_id, connect_cost_per_mw, capacity_limit_mw, variable_o_m, forced_outage_rate,
scheduled_outage_rate, full_load_heat_rate, hydro_efficiency, max_age, min_build_capacity, is_variable, is_baseload, is_cogen, energy_source, unit_size,
storage_efficiency, store_to_release_ratio, min_load_fraction, startup_fuel, startup_om, ccs_capture_efficiency, ccs_energy_load, eia_plant_code,
latitude, longitude, county, state, geom, substation_connection_geom, geom_area)
(
SELECT name, gen_tech, load_zone_id, 0 AS connect_cost_per_mw, capacity_limit_mw, variable_o_m, forced_outage_rate,
scheduled_outage_rate, full_load_heat_rate, hydro_efficiency, max_age, min_build_capacity, is_variable, is_baseload, is_cogen, energy_source, unit_size,
storage_efficiency, store_to_release_ratio, min_load_fraction, startup_fuel, startup_om, ccs_capture_efficiency, ccs_energy_load, eia_plant_code,
latitude, longitude, county, state, geom, substation_connection_geom, geom_area
FROM generation_plant a
JOIN generation_plant_existing_and_planned b
ON a.generation_plant_id = b.generation_plant_id
WHERE generation_plant_existing_and_planned_scenario_id = 1
AND load_zone_id IN (8, 9, 28)
)

-- Generation plant cost scenario

-- Scenario mapping table (generation_plant_cost_scenario, generation_plant_cost_scenario_id)
-- 2. Add a new generation_plant_cost_scenario row and id into the generation_plant_cost_scenario table

INSERT INTO switch.generation_plant_cost_scenario (generation_plant_cost_scenario_id, name, description)
VALUES (21, 'EIA-WECC Existing and Proposed 2018, AMPL Basecase for Canada and Mexico', 'same as id 19, EIA 2018 data plus AMPL Basecase Canada and Mex existing gen')

-- Data table (generation_plant_cost, generation_plant_cost_scenario_id)
-- 2. Then copy the generation_plant_cost time series for scenario 19:

INSERT INTO switch.generation_plant_cost (generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)
SELECT 21 AS generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh
FROM switch.generation_plant_cost
WHERE generation_plant_cost_scenario_id = 19

-- 3. Add into new generation_plant_cost time series 21, the generation_plant_cost time series from scenario 1, for the AMPL existing generation plant ids for Canada and Mexico
-- The overnight costs are nonzero, unlike for the EIA data...

-- Generation plant scenario

-- Scenario mapping table (generation_plant_scenario_member, generation_plant_scenario_id)
-- 1. Add a new generation_plant_scenario and id into generation_plant_scenario_member scenario mapping table:

INSERT INTO switch.generation_plant_scenario (generation_plant_scenario_id, name, description)
VALUES (21, 'EIA-WECC Existing and Proposed 2018, AMPL Basecase for Canada and Mexico', 'same as id 19, EIA 2018 data plus AMPL Basecase Canada and Mex existing gen')

-- Data table (generation_plant_scenario, generation_plant_scenario_id)
-- 2. Then copy the generation_plant_scenario time series for scenario 19 into Data table:

INSERT INTO switch.generation_plant_scenario_member (generation_plant_scenario_id, generation_plant_id)
SELECT 21 as generation_plant_scenario_id, generation_plant_id
FROM switch.generation_plant_scenario_member
WHERE generation_plant_scenario_id = 19

-- 3. Add into new generation_plant_scenario time series 21, the generation_plant_scenario time series from scenario 1, for the AMPL existing generation plant ids for Canada and Mexico

-- Existing and planned generation plant scenario

-- Scenario mapping tables (generation_plant_existing_and_planned_scenario,generation_plant_existing_and_planned_scenario_id)
-- 1. Add a new generation_plant_existing_and_planned_scenario and id into generation_plant_existing_and_planned_scenario mapping table:
INSERT INTO switch.generation_plant_existing_and_planned_scenario (generation_plant_existing_and_planned_scenario_id, name, description)
VALUES (21, 'EIA-WECC Existing and Proposed 2018, AMPL Basecase for Canada and Mexico', 'same as id 19, EIA 2018 data plus AMPL Basecase Canada and Mex existing gen')


-- Data table (generation_plant_existing_and_planned, generation_plant_existing_and_planned_scenario_id)
-- 2. Then copy the generation_plant_existing_and_planned time series for scenario 19 into Data table:
INSERT INTO switch.generation_plant_existing_and_planned (generation_plant_existing_and_planned_scenario_id, generation_plant_id, build_year, capacity)
SELECT 21 as generation_plant_existing_and_planned_scenario_id, generation_plant_id, build_year, capacity
FROM switch.generation_plant_existing_and_planned
WHERE generation_plant_existing_and_planned_scenario_id = 19

-- 3. Add into new generation_plant_scenario time series 21, the generation_plant_scenario time series from scenario 1, for the AMPL existing generation plant ids for Canada and Mexico

-- Hydro capacity factors

-- Scenario mapping tables:
-- hydro_simple_scenario, hydro_simple_scenario_id
-- 1. create new hydro simple scenario id 21 in the hydro simple mapping table
INSERT INTO switch.hydro_simple_scenario (hydro_simple_scenario_id, name, description)
VALUES (21, 'EIA923 datasets 2004 until 2018, AMPL 2006 Basecase for Canada and Mexico repeated for 2004 to 2018', 'same as id 19, EIA 2004 to 2018 data plus AMPL 2006 Basecase Canada and Mex hydro cf repeated for 2004 to 2018')

-- data table:
-- hydro_historical_monthly_capacity_factors, hydro_simple_scenario_id
-- 2. Then copy the hydro capacity factors time series for scenario 19 into Data table
INSERT INTO switch.hydro_historical_monthly_capacity_factors (hydro_simple_scenario_id, generation_plant_id, year, month, hydro_min_flow_mw, hydro_avg_flow_mw)
SELECT 21 as hydro_simple_scenario_id, generation_plant_id, year, month, hydro_min_flow_mw, hydro_avg_flow_mw
FROM switch.hydro_historical_monthly_capacity_factors
WHERE hydro_simple_scenario_id = 19

-- 3. Add into new hydro simple scenario time series 21, the hydro capacity factors time series from scenario 1, for the AMPL existing generation plant ids for Canada and Mexico. Since the AMPL data is only available for 2006, the 2006 data is repeated for 2004 to 2018

CREATE TABLE switch.jsz_backup4_generation_plant (LIKE switch.generation_plant INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup4_generation_plant SELECT * FROM switch.generation_plant;

-- now run the 'Queries_to_copy_AMPL_Canada_Mex_attributes_to_new_gen_sql to copy the attributes of the original Canada and Mexico generation plants to the new ids for the same plant
