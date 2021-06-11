select generation_plant_id, t.raw_timepoint_id, capacity_factor
FROM variable_capacity_factors_exist_and_candidate_gen v
JOIN generation_plant_scenario_member USING(generation_plant_id)
JOIN sampled_timepoint as t ON(t.raw_timepoint_id = v.raw_timepoint_id)
WHERE generation_plant_scenario_id = 22
AND t.time_sample_id=3; 