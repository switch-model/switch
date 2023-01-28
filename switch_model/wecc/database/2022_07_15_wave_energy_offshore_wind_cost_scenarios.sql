-- Summer 2022, UC San Diego
--  New cost scenarios for DOE wave energy project
-- Natalia Gonzalez, Patricia Hidalgo-Gonzalez



drop table public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites;

create table public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites(
index bigint,
GENERATION_PROJECT double precision,
build_year double precision,
gen_fixed_om double precision,
gen_overnight_cost double precision,
scenario_id int,
primary key (scenario_id, GENERATION_PROJECT, build_year)
);




COPY public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites
FROM '/home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;


-- previous scenario:
-- insert into switch.generation_plant_cost_scenario
-- values(28,'SWITCH 2020 Baseline costs from id 25. DOE_wave',
-- 			  'same costs as id 25, and added costs for wave energy and offshore wind candidates from 2017 data (Deborah S., Brian, PHG), Natalia and Paul runs');

-- --------------------------------------------------------------------------------
-- scenario 1 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(29,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia), wave energy highest cost proj 2050, and offshore wind NREL ATB 2022 moderate (scenario_id = 1 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 29 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 29 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 1;


insert into switch.scenario
values (180, 
		'[DOE wave energy] scen 1 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=1 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		29, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);

-- --------------------------------------------------------------------------------

-- scenario 2 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(30,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 2 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 30 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 30 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 2;


insert into switch.scenario
values (181, 
		'[DOE wave energy] scen 2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=2 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		30, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);


-- --------------------------------------------------------------------------------

-- scenario 3 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(31,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 3 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 31 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 31 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 3;


insert into switch.scenario
values (182, 
		'[DOE wave energy] scen 3 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=3 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		31, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);



-- --------------------------------------------------------------------------------

-- scenario 4 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(32,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 4 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 32 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 32 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 4;


insert into switch.scenario
values (183, 
		'[DOE wave energy] scen 4 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=4 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		32, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);


-- --------------------------------------------------------------------------------

-- scenario 5 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(33,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 5 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 33 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 33 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 5;


insert into switch.scenario
values (184, 
		'[DOE wave energy] scen 5 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=5 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		33, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);
		

-- --------------------------------------------------------------------------------

-- scenario 6 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(34,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 6 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 34 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 34 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 6;


insert into switch.scenario
values (185, 
		'[DOE wave energy] scen 6 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=6 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		34, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);
		



-- --------------------------------------------------------------------------------

-- scenario 7 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(35,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 7 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 35 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 35 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 7;


insert into switch.scenario
values (186, 
		'[DOE wave energy] scen 7 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=7 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		35, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);
		


-- --------------------------------------------------------------------------------

-- scenario 8 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(36,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 8 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 36 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 36 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 8;


insert into switch.scenario
values (187, 
		'[DOE wave energy] scen 8 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=8 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		36, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);
		
		
-- --------------------------------------------------------------------------------

-- scenario 9 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(37,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 9 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 37 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 37 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 9;


insert into switch.scenario
values (188, 
		'[DOE wave energy] scen 9 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=9 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		37, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);
		
		
		
-- --------------------------------------------------------------------------------

-- scenario 10 from csv
-- /home/n7gonzalez/switch/wave_energy/all_scenarios_gen_build_cost_wave_offshore_wind.csv

insert into switch.generation_plant_cost_scenario
values(38,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 10 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 38 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 38 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites as t
where t.scenario_id = 10;


insert into switch.scenario
values (189, 
		'[DOE wave energy] scen 10 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=10 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		25, -- study_timeframe_id
		25, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		38, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		92, -- carbon_cap_scenario_id
		2, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		NULL, -- rps_scenario_id
		NULL, --enable_dr
		NULL, --enable_ev
		2, --transmission_base_capital_cost_scenario_id
		NULL, --ca_policies_scenario_id
		0, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL --wind_to_solar_ratio
		);