

-- Shiny + PHG, Nov 24th, 2021
-- New scenario that includes wave energy candidates (23 locations from 2017 data)


-- Ran:
-- insert into switch.generation_plant_cost_scenario
-- values(26,'SWITCH 2020 Baseline costs from id 25. DOE_wave', 
-- 			  'same costs as id 25, and added costs for wave candidates from 2017 data (Deborah S., Brian, PHG), 
-- 			  Shinys runs');

-- Ran:
-- select * from switch.generation_plant_cost_scenario;

-- Ran:
-- insert into switch.generation_plant_cost
-- select 26 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
-- storage_energy_capacity_cost_per_mwh
-- from switch.generation_plant_cost
-- where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
-- union
-- select 26 as generation_plant_cost_scenario_id, t."GENERATION_PROJECT" as generation_plant_id,
-- build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
-- NULL as storage_energy_capacity_cost_per_mwh
-- from public.gen_build_costs_wave as t;

-- reality check: -----------------------------------------------------------------------
-----------------------------------------------------------------------------------------
-- select *  from switch.generation_plant_cost
-- join switch.generation_plant using(generation_plant_id)
-- where generation_plant_cost_scenario_id=25;
-- and energy_source not in ('Wave');

-- select * 
-- from switch.generation_plant_cost
-- where generation_plant_cost_scenario_id = 26;


-- -- 303495 rows
-- select 26 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
-- storage_energy_capacity_cost_per_mwh
-- from switch.generation_plant_cost
-- where generation_plant_cost_scenario_id = 25;

-- -- 828 rows
-- select 26 as generation_plant_cost_scenario_id, t."GENERATION_PROJECT" as generation_plant_id,
-- build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
-- NULL as storage_energy_capacity_cost_per_mwh
-- from public.gen_build_costs_wave as t;


-- id 25: 303495 rows (2050-2010+1)

-- wave (gen_ids, year) should be 828 rows

-- id 26 should have 303495 + 828 = 304323

-- end of reality check -----------------------------------------------------------------------------
---------------------------------------------------------------------------------------------------

-- Summary: tables updated: generation_plant_cost_scenario, generation_plant_cost

-- delete from switch.generation_plant_scenario where generation_plant_scenario_id = 24;

-- Ran:
-- insert into switch.generation_plant_scenario
-- values(24,
-- 'EIA-WECC Existing and Proposed 2018 + wave, AMPL Basecase for Canada and Mex, AMPL proposed non-wind plants (only best of solar), Env Screen Wind Cat 3, No CAES',
-- 	'same as id 22 adding wave energy data from 2017 (Deborah, PHG, Brian), but no Compressed Air Energy Storage gen_tech among candidate generators'
-- );

select * from switch.generation_plant_scenario;


-- 10349 rows
-- insert into switch.generation_plant_scenario_member
-- select 24 as generation_plant_scenario_id, t1."GENERATION_PROJECT" as generation_plant_id
-- from public.generation_projects_info_wave as t1
-- union
-- select 24 as generation_plant_scenario_id, generation_plant_id
-- from switch.generation_plant_scenario_member
-- where generation_plant_scenario_id=23;


select * from switch.generation_plant_scenario_member where generation_plant_scenario_id = 24;








-- __________________________________________________________________________________________________
-- __________________________________________________________________________________________________

-- Ran: new table with wave capacity factors duplicated from 2006 for 2010-2060
-- drop table public.test_variable_capacity_factors_wave;
-- create table public.test_variable_capacity_factors_wave(
-- 	generation_plant_id double precision,
-- 	capacity_factor double precision,
-- 	time_stamp_utc text);


-- Ran:
-- do 
-- $$
-- begin
--    for year in 2010..2060 loop
-- 	raise notice 'year: %', year;
	
-- 	insert into public.test_variable_capacity_factors_wave
-- 	select t."GENERATION_PROJECT" as generation_plant_id, 
-- 	gen_max_capacity_factor as capacity_factor, 
-- 	CONCAT(year, TRIM(LEADING '2006' FROM timestamp)) as new_stamp
-- 	from public.variable_capacity_factors_wave as t;
--    end loop;
-- end; 
-- $$

-- 26280 rows (=(2012-2010+1)*8760)
-- 10275480 rows ( = (2060-2010+1) * 8760 * 23 )
-- select * from public.test_variable_capacity_factors_wave;




-- 359,400 (2011 - 2051)
-- select * from switch.variable_capacity_factors_exist_and_candidate_gen 
-- where generation_plant_id = 1191183122
-- order by timestamp_utc asc;

-- continue here:
-- 8260,680 (almost = (359,400) * 23 )
insert into switch.variable_capacity_factors_exist_and_candidate_gen
select t.generation_plant_id as generation_plant_id, raw_timepoint_id, t2.timestamp_utc,
t.capacity_factor as capacity_factor, 1 as is_new_cap_factor
from public.test_variable_capacity_factors_wave as t
join switch.variable_capacity_factors_exist_and_candidate_gen as t2 on (t.time_stamp_utc=to_char(t2.timestamp_utc, 'YYYY-MM-DD HH24:MI:SS'))
where t2.generation_plant_id=1191183122 -- random plant_id chosen to match raw_timepoint_id
order by 1,2 desc;