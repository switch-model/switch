-- Summer 2022, UC San Diego
--  New cost scenarios for DOE wave energy project
-- Natalia Gonzalez, Patricia Hidalgo-Gonzalez


-- second version, with more competitive costs for wave energy

-- drop table public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2;

create table public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2(
index bigint,
GENERATION_PROJECT double precision,
build_year double precision,
gen_fixed_om double precision,
gen_overnight_cost double precision,
scenario_id int,
primary key (scenario_id, GENERATION_PROJECT, build_year)
);




COPY public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2
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
values(39,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia), wave energy highest cost proj 2050, and offshore wind NREL ATB 2022 moderate (scenario_id = 1 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 39 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 39 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 1;


insert into switch.scenario
values (190, 
		'[DOE wave energy] scen1v2 wave offwind Ryansites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=1 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		39, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(40,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 2 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 40 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 40 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 2;


insert into switch.scenario
values (191, 
		'[DOE wave energy] scen2v2 wave offwind Ryansites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=2 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		40, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(41,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 3 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 41 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 41 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 3;


insert into switch.scenario
values (192, 
		'[DOE wave energy] scen3v2 wave offwind Ryansites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=3 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		41, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(42,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 4 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 42 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 42 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 4;


insert into switch.scenario
values (193, 
		'[DOE wave energy] scen4v2 wave offwind Ryansites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=4 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		42, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(43,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind NREL ATB 2022 moderate (scenario_id = 5 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 43 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 43 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 5;


insert into switch.scenario
values (194, 
		'[DOE wave energy] sce5v2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=5 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		43, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(44,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 6 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 44 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 44 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 6;


insert into switch.scenario
values (195, 
		'[DOE wave energy] sce6v2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=6 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		44, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(45,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 7 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 45 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 45 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 7;


insert into switch.scenario
values (196, 
		'[DOE wave energy] sce7v2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=7 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		45, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(46,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 8 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 46 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 46 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 8;


insert into switch.scenario
values (197, 
		'[DOE wave energy] sce8v2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=8 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		46, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(47,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 9 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 47 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 47 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 9;


insert into switch.scenario
values (198, 
		'[DOE wave energy] sce9v2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=9 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		47, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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
values(48,'2020 BAU from id 25. DOE_wave highwave ATB offwind',
 			  'same costs as id 25, wave energy 2020 (RM6, Sandia) then projected, and offshore wind from NREL ATB 2022 moderate to land based wind NREL ATB (scenario_id = 10 from csv), Natalia and Paul runs');



-- One query per scenario
insert into switch.generation_plant_cost
select 48 as generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost,
storage_energy_capacity_cost_per_mwh
from switch.generation_plant_cost
where generation_plant_cost_scenario_id = 25 -- 25 is the previous baseline scenario used for CEC LDES 2020-2022
union
select 48 as generation_plant_cost_scenario_id, t.generation_project as generation_plant_id,
build_year, gen_fixed_om as fixed_o_m, gen_overnight_cost as  overnight_cost,
NULL as storage_energy_capacity_cost_per_mwh
from public.gen_build_cost_scenarios_wave_offshore_wind_industry_sites_v2 as t
where t.scenario_id = 10;


insert into switch.scenario
values (199, 
		'[DOE wave energy] sce10v2 wave offwind Ryan sites', 
		'New: wave energy and offshore wind sites of industry Ryan, highwave ATB offwind scenario_id=10 from Natis csv. Same: WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		3, -- study_timeframe_id
		3, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		26, -- generation_plant_scenario_id
		48, -- generation_plant_cost_scenario_id HEREEEEEEEEEEEEEEEEE
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