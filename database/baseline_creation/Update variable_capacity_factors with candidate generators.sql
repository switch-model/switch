-- These queries select the variable capacity factors from 2006 for the candidate generators in scenario 23 from the variable_capacity_factors_historical table, and adds them to the variable_capacity_factors table repeated for 2011 to 2050 (the time horizon for the existing generators capacity factors in the table)

-- make a copy of the variable_capacity_factors table
CREATE TABLE switch.variable_capacity_factors_exist_and_candidate_gen (LIKE switch.variable_capacity_factors INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.variable_capacity_factors_exist_and_candidate_gen SELECT * FROM switch.variable_capacity_factors;


-- run query to copy data from variable_capacity_factors_historical table for candidate generators into new table


INSERT INTO switch.variable_capacity_factors_exist_and_candidate_gen (generation_plant_id, raw_timepoint_id, timestamp_utc, capacity_factor, is_new_cap_factor)

SELECT gps.generation_plant_id, rt.raw_timepoint_id, rt.timestamp_utc, v.capacity_factor, 0 as is_new_cap_factor
FROM variable_capacity_factors_historical v
JOIN projection_to_future_timepoint as pt ON(v.raw_timepoint_id = pt.historical_timepoint_id)
JOIN raw_timepoint as rt ON(rt.raw_timepoint_id = pt.future_timepoint_id)
JOIN generation_plant_scenario_member as gps USING(generation_plant_id)
LEFT JOIN generation_plant_existing_and_planned gep
ON gps.generation_plant_id = gep.generation_plant_id
WHERE gep.generation_plant_id IS NULL
AND gps.generation_plant_scenario_id = 22;


