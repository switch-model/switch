-- Ran:
insert into switch.generation_plant_cost_scenario
values(27,'SWITCH 2020 Baseline costs from id 25. DOE_wave',
 			  'same costs as id 25, and added costs for wave candidates from 2017 data (Deborah S., Brian, PHG), Shinys runs');

-- Ran:
create table public.shiny_v2_generation_project_info_wave_offshore_wind(
index bigint,
GENERATION_PROJECT double precision,
gen_capacity_limit_mw double precision,
gen_connect_cost_per_mw double precision,
gen_dbid double precision,
gen_energy_source text,
gen_forced_outage_rate double precision,
gen_full_load_heat_rate text,
gen_is_baseload boolean,
gen_is_cogen boolean,
gen_is_variable boolean,
gen_load_zone text,
gen_max_age double precision,
gen_min_build_capacity double precision,
gen_scheduled_outage_rate double precision,
gen_tech text,
gen_variable_om double precision,
lat double precision,
long double precision,
primary key (GENERATION_PROJECT, gen_tech)
);


select * from public.shiny_v2_generation_project_info_wave_offshore_wind;


--Ran:
create table public.shiny_v2_gen_build_cost_wave_offshore_wind(
index bigint,
GENERATION_PROJECT double precision,
build_year double precision,
gen_fixed_om double precision,
gen_overnight_cost double precision,
primary key (GENERATION_PROJECT, build_year)
);



COPY public.shiny_v2_generation_project_info_wave_offshore_wind
FROM '/home/schoudhury/REAM_lab/newData/newWaveOffshorePlants.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;


COPY public.shiny_v2_gen_build_cost_wave_offshore_wind
FROM '/home/schoudhury/REAM_lab/newData/newWaveOffshorePlants_cost.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;

-- QA/QC

select generation_project, count(*) 
from public.shiny_v2_gen_build_cost_wave_offshore_wind
group by generation_project
order by generation_project;




-- Wave at offshore wind sites
--SC: need to add capacity factor tables for both wave and offshore again in the exact format the wave table was from November implementation

-- Delete once v3 is done ------------------------------------------
create table public.wave_colocation_CF_v2(
GENERATION_PROJECT double precision,
gen_max_capacity_factor double precision,
site int,
timestamp text,
primary key (GENERATION_PROJECT, timestamp)
);

COPY public.wave_colocation_CF_v2
FROM '/home/schoudhury/REAM_lab/newData/switch_wave_CF.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;
-- End of Deleting block ------------------------------------------


-- QA/QC:
select * from public.wave_colocation_CF_v2;

select generation_project, count(*)
from wave_colocation_CF_v2
group by 1
order by 1;



-- version 3 and final:
drop table public.wave_colocation_CF_v3;

create table public.wave_colocation_CF_v3(
GENERATION_PROJECT double precision,
gen_max_capacity_factor double precision,
site int,
year text,
month text,
day text,
hour text,
primary key (GENERATION_PROJECT, year, month, day, hour)
);

COPY public.wave_colocation_CF_v3
FROM '/home/schoudhury/REAM_lab/newData/switch_wave_CF.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;

select * from public.wave_colocation_CF_v3;




-- Offshore wind
drop table public.offshore_colocation_CF_v3;

create table public.offshore_colocation_CF_v3(
GENERATION_PROJECT double precision,
gen_max_capacity_factor double precision,
site int,
year text,
month text,
day text,
hour text,
primary key (GENERATION_PROJECT, year, month, day, hour)
);

COPY public.offshore_colocation_CF_v3
FROM '/home/schoudhury/REAM_lab/newData/switch_offshore_CF_v3.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;


-- QA/QC:
select * from public.offshore_colocation_CF_v3;

select generation_project, count(*)
from offshore_colocation_CF_v3
group by 1
order by 1;


-- -----------------------------------------------------------------------

insert into switch.generation_plant_scenario
values(25,
'EIA-WECC Existing and Proposed 2018 + colocated offshore wind and wave, AMPL Basecase for Canada and Mex, AMPL proposed non-wind plants (only best of solar), Env Screen Wind Cat 3, No CAES',
'same as id 22 adding new sites for colocated wave and offshore wind from Levi s and NREL reports (Shiny,PHG), but no Compressed Air Energy Storage gen_tech among candidate generators. No wave sites from Bryan and Deborah.'
);


insert into switch.generation_plant (generation_plant_id, name, gen_tech, load_zone_id, connect_cost_per_mw, variable_o_m,
	forced_outage_rate, scheduled_outage_rate, max_age, min_build_capacity, is_variable, is_baseload,
	is_cogen, energy_source,  min_load_fraction, startup_fuel, startup_om)
select 
t1.generation_project as generation_plant_id, concat(t1.generation_project, '_Wave') as name, 
gen_tech, load_zone_id, gen_connect_cost_per_mw as connect_cost_per_mw,
gen_variable_om as variable_o_m, gen_forced_outage_rate as forced_outage_rate, gen_scheduled_outage_rate as scheduled_outage_rate, 
gen_max_age as max_age, gen_min_build_capacity as min_build_capacity, gen_is_variable as is_variable, gen_is_baseload as is_baseload, gen_is_cogen as is_cogen,
gen_energy_source as energy_source, 0 as min_load_fraction, 0 as startup_fuel, 0 as startup_om
from public.shiny_v2_generation_project_info_wave_offshore_wind as t1
join switch.load_zone as t2 on(t2.name=gen_load_zone);


insert into switch.generation_plant_scenario_member
select 25 as generation_plant_scenario_id, t1.generation_project as generation_plant_id
from public.shiny_v2_generation_project_info_wave_offshore_wind as t1
union
select 25 as generation_plant_scenario_id, generation_plant_id
from switch.generation_plant_scenario_member
where generation_plant_scenario_id=23;




insert into switch.generation_plant_cost
select 27 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 27 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.shiny_v2_gen_build_cost_wave_offshore_wind as t;



-- TO DO: QA/QC (as of april 25, 2022 it's still pending)
-- -- reality check: --------------NOT UPDATED---------------------------------------------------------
-- -----------------------------------------------------------------------------------------
-- 238800 rows retrieved
-- select *  from switch.generation_plant_cost
-- join switch.generation_plant using(generation_plant_id)
-- where generation_plant_cost_scenario_id=25
-- and energy_source not in ('Wave')
-- and energy_source not in ('Wind');

-- -- select *
-- -- from switch.generation_plant_cost
-- -- where generation_plant_cost_scenario_id = 27;


-- -- -- 303495 rows retrieved
-- select 27 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
-- storage_energy_capacity_cost_per_mwh
-- from switch.generation_plant_cost
-- where generation_plant_cost_scenario_id = 25;

-- 1078 rows retrieved = number of rows in Shiny's notebook (OK!)
-- select 27 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
-- build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
-- NULL as storage_energy_capacity_cost_per_mwh
-- from public.shiny_v2_gen_build_cost_wave_offshore_wind as t;


-- -- id 25: 303495 rows (2050-2010+1)


-- -- end of reality check -----------------------------------------------------------------------------
-- ---------------------------------------------------------------------------------------------------




-- Summary: tables updated: 
-- generation_plant_cost_scenario, 
-- generation_plant_scenario,
-- generation_plant,
-- generation_plant_scenario_member,
-- generation_plant_cost, 





----------------------checked---------------------------------------------------------------
-- -- 10354 (current scenario)
-- select * from switch.generation_plant_scenario_member where generation_plant_scenario_id = 25;

-- 10354 + 23 - 28 = 10349 (previous scenario with 23 old wave sites, 
-- minus 28 new sites from generation_plant_scenario_id = 25)
select * from switch.generation_plant_scenario_member 
where generation_plant_scenario_id = 24;
------------------------------------------------------------------------------------------


-- __________________________________________________________________________________________________
-- __________________________________________________________________________________________________

-- new table with WAVE capacity factors duplicated from 2010 for 2010-2060

-- to do:
DROP TABLE public.test_variable_capacity_factors_wave_shiny;

create table public.test_variable_capacity_factors_wave_shiny(
generation_plant_id double precision,
capacity_factor double precision,
time_stamp_utc text);

do
$$
begin
for year_index in 2010..2060 loop
raise notice 'year: %', year_index;
	
insert into public.test_variable_capacity_factors_wave_shiny
select t.generation_project as generation_plant_id,
gen_max_capacity_factor as capacity_factor, 
concat(year_index, '-', month, '-', day, ' ', hour, ':00:00') as new_stamp
from public.wave_colocation_CF_v3 t;
end loop;
end;
$$

-- QA/QC: 14 sites * 8760 hours * (2060 - 2010 + 1) = 6254640 rows retrieved. OK!
select * from public.test_variable_capacity_factors_wave_shiny;



select * from switch.variable_capacity_factors_exist_and_candidate_gen
where generation_plant_id = 1191183122
order by timestamp_utc asc;

-- Shiny: before inserting, make sure the number of rows adds to the number you expect for wave energy and offshore wind sites
-- The years with data should still be (2051-2011+1) because there is a join between the new tables you created and the SWITCH tables (which go from 2010 to 2051)
-- PHG checked: 5,028,240 rows = (2051-2011+1) * 8760 * 14
insert into switch.variable_capacity_factors_exist_and_candidate_gen
select t.generation_plant_id as generation_plant_id, raw_timepoint_id, t2.timestamp_utc,
t.capacity_factor as capacity_factor, 1 as is_new_cap_factor
from public.test_variable_capacity_factors_wave_shiny as t
join switch.variable_capacity_factors_exist_and_candidate_gen as t2 on (t.time_stamp_utc=to_char(t2.timestamp_utc, 'YYYY-MM-DD HH24:MI:SS'))
where t2.generation_plant_id=1191183122 -- random plant_id chosen to match raw_timepoint_id
order by 1,2 desc;




-- -- TODO: new table with OFFSHORE WIND capacity factors duplicated from 2010 for 2010-2060
create table public.test_variable_capacity_factors_offshore(
generation_plant_id double precision,
capacity_factor double precision,
time_stamp_utc text);


do
$$
begin
for year_index in 2010..2060 loop
raise notice 'year: %', year_index;
	
insert into public.test_variable_capacity_factors_offshore
select t.generation_project as generation_plant_id,
gen_max_capacity_factor as capacity_factor, 
concat(year_index, '-', month, '-', day, ' ', hour, ':00:00') as new_stamp
from public.offshore_colocation_CF_v3 t;
end loop;
end;
$$

-- QA/QC: 14 sites * 8760 hours * (2060 - 2010 + 1) = 6254640 rows retrieved. OK!
select * from public.test_variable_capacity_factors_offshore;


-- -- select * from switch.variable_capacity_factors_exist_and_candidate_gen
-- -- where generation_plant_id = 1191183122
-- -- order by timestamp_utc asc;

-- 5028240 rows retrieved = (2051 - 2011 + 1)*14*8760. OK!
insert into switch.variable_capacity_factors_exist_and_candidate_gen
select t.generation_plant_id as generation_plant_id, raw_timepoint_id, t2.timestamp_utc,
t.capacity_factor as capacity_factor, 1 as is_new_cap_factor
from public.test_variable_capacity_factors_offshore as t
join switch.variable_capacity_factors_exist_and_candidate_gen as t2 on (t.time_stamp_utc=to_char(t2.timestamp_utc, 'YYYY-MM-DD HH24:MI:SS'))
where t2.generation_plant_id=1191183122 -- random plant_id chosen to match raw_timepoint_id
order by 1,2 desc;