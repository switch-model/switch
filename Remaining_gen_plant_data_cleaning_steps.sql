-- This script has a few final data cleaning queries to make sure the input data is in the format SWITCH wants and that the input data is properly loaded


-- change the full load heat rate to NULL for all Solar, Geothermal, and waste_heat, even if they have a ST as their gen_tech (59 rows should be updated)
with t as(select a.generation_plant_id, gen_tech, energy_source, full_load_heat_rate
from generation_plant as a
join generation_plant_scenario_member as b
on a.generation_plant_id = b.generation_plant_id
where generation_plant_scenario_id = 22
and energy_source IN ('Solar','Geothermal', 'Waste_Heat')
and a.full_load_heat_rate IS NOT NULL
)

update generation_plant c
set full_load_heat_rate = NULL
from t
where c.generation_plant_id = t.generation_plant_id


-- set all hydropower (water energy source) to be FALSE for the 'is variable' column (should be 590 rows)
with t as(
select a.generation_plant_id, gen_tech, energy_source, is_variable, name
from generation_plant as a
join generation_plant_scenario_member as b
on a.generation_plant_id = b.generation_plant_id
where generation_plant_scenario_id = 22
and energy_source IN ('Water')
and is_variable = TRUE
)

update generation_plant c
set is_variable = FALSE
from t
where c.generation_plant_id = t.generation_plant_id

-- the heat rate for a plant in CA_SCE_S to 10.8325567423 where the gen_tech is 'OT' and energy source is 'Gas', because that is the heat rate calculated for the same plant in the prior input data

with t as(
select a.generation_plant_id, load_zone_id, gen_tech, energy_source, full_load_heat_rate
from generation_plant as a
join generation_plant_scenario_member as b
on a.generation_plant_id = b.generation_plant_id
where generation_plant_scenario_id = 22
and energy_source IN ('Gas')
and gen_tech = 'OT'
and load_zone_id = 17
)

update generation_plant c
set full_load_heat_rate = 10.8325567423
from t
where c.generation_plant_id = t.generation_plant_id


-- for the existing battery storage, make sure the storage_energy_cost is 0 (already ran this)

WITH t AS
(SELECT gp.generation_plant_id, gp.gen_tech, gp.energy_source, gc.storage_energy_capacity_cost_per_mwh
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
JOIN generation_plant_cost gc
on gc.generation_plant_id = gp.generation_plant_id
WHERE gp.gen_tech = 'Battery_Storage'
AND gp.energy_source = 'Electricity'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant_cost a
SET storage_energy_capacity_cost_per_mwh = 0
FROM t
WHERE a.generation_plant_id = t.generation_plant_id


---testing var cap factors:

-- select * from
-- variable_capacity_factors_exist_and_candidate_gen
-- where generation_plant_id = 1100568
-- and raw_timepoint_id IN (354917, 354038)

-- select * from
-- variable_capacity_factors_historical
-- where generation_plant_id = 1100568
-- and capacity_factor < 0


-- select distinct(a.generation_plant_id), b.gen_tech, b.energy_source, b.name, c.generation_plant_scenario_id
-- from variable_capacity_factors_historical a
-- join generation_plan b
-- on a.generation_plant_id = b.generation_plant_id
-- join generation_plant_scenario_member
-- on a.generation_plant_id = c.generation_plant_id
-- where capacity_factor < 0

-- checking if cap factors are extending beyond generator retirement or max age
SELECT a.generation_plant_id, t.raw_timepoint_id, v.timestamp_utc, v.capacity_factor, max(c.build_year) AS max_build_year, a.max_age, sum(max_build_year, a.max_age) AS retire_year
FROM generation_plant AS a
JOIN variable_capacity_factors AS v ON (a.generation_plant_id = v.generation_plant_id)
JOIN generation_plant_existing_and_planned AS c ON (c.generation_plant_id = a.generation_plant_id)
JOIN generation_plant_scenario_member as gpsm ON (gpsm.generation_plant_id = a.generatin_plant_id)
JOIN sampled_timepoint AS t ON(t.raw_timepoint_id = v.raw_timepoint_id)
WHERE extract(YEAR FROM b.timestamp_utc) > retire_year
AND generation_plant_existing_and_planned_scenario_id = 21
AND generation_plant_scenario_id = 22
GROUP BY generation_plant_id

-- adjusting hydro time series query
select generation_plant_id, 
from hydro_historical_monthly_capacity_factors
join sampled_timeseries on(month = date_part('month', first_timepoint_utc) and year = date_part('year', first_timepoint_utc))
join generation_plant using (generation_plant_id)
join generation_plant_scenario_member using(generation_plant_id)
where generation_plant_scenario_id = 22
and hydro_simple_scenario_id=22
and time_sample_id = 2;
