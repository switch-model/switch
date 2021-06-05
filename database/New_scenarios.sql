-- Updates for 100% RPS paper
-- Patricia Hidalgo-Gonzalez, Julia Szinai
-- May 2020



insert into scenario
values (163, 
		'[100% RPS paper] toy zero carbon2025byhand, ID147', 
		'WECC CA cap. Loads and hydro under CC (delta_MW divided by 3). Updated overnight_cost (E3 4% decr), updated gen listings (env cat 3), 2017 fuel costs from EIA, 2016 dollars, supply curve for Bio_Solid, current RPS and near zero carbon cap',
		2, -- study_timeframe_id
		2, -- time_sample_id
		115, -- demand_scenario_id
		3, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		14, -- generation_plant_scenario_id
		6, -- generation_plant_cost_scenario_id
		3, -- generation_plant_existing_and_planned_scenario_id
		11, -- hydro_simple_scenario_id
		88, -- carbon_cap_scenario_id
		1, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		1, -- zone_to_regional_fuel_market_scenario_id
		1 -- rps_scenario_id
		);
		

--delete from scenario where scenario_id=163;
		
/* 
insert into scenario
values (163, 
		'[100% RPS paper] toy as ID 147', 
		'New toy timepoints that include 2050, the rest copied from scenario 147.',
		6, -- study_timeframe_id
		6, -- time_sample_id
		115, -- demand_scenario_id
		3, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		14, -- generation_plant_scenario_id
		6, -- generation_plant_cost_scenario_id
		3, -- generation_plant_existing_and_planned_scenario_id
		11, -- hydro_simple_scenario_id
		90, -- carbon_cap_scenario_id
		1, -- supply_curve_scenario_id
		1, -- regional_fuel_market_scenario_id
		1, -- zone_to_regional_fuel_market_scenario_id
		1 -- rps_scenario_id
		);
 */