

-- GridLab, 2022
-- Paul ST and Patricia HG
-- Sept 9, 2022

insert into switch.scenario
values (200, 
		'[GridLab] scen 178, 2035, CO2 sce 9', 
		'2035 (2033 - 2037), year_round, WECC zero emissions, no RPS, NREL ATB 2020, updated gen listings (env cat 3), 2017 fuel costs from EIA, 2018 dollars, supply curve for Bio_Solid',
		30, -- study_timeframe_id
		30, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		23, -- generation_plant_scenario_id
		25, -- generation_plant_cost_scenario_id 
		21, -- generation_plant_existing_and_planned_scenario_id
		23, -- hydro_simple_scenario_id
		9, -- carbon_cap_scenario_id
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
		
		
select * from switch.scenario;


-- select * from switch.carbon_cap_scenarios;

-- insert into switch.carbon_cap_scenarios
-- values (93, '[GridLab] Zero emissions for all years');

select * from switch.carbon_cap_scenarios;


-- insert into switch.carbon_cap
-- values(93, 2020, 0);

insert into switch.carbon_cap
values(93, 2021, 0);
insert into switch.carbon_cap
values(93, 2022, 0);
insert into switch.carbon_cap
values(93, 2023, 0);
insert into switch.carbon_cap
values(93, 2024, 0);
insert into switch.carbon_cap
values(93, 2025, 0);
insert into switch.carbon_cap
values(93, 2026, 0);
insert into switch.carbon_cap
values(93, 2027, 0);
insert into switch.carbon_cap
values(93, 2028, 0);
insert into switch.carbon_cap
values(93, 2029, 0);
insert into switch.carbon_cap
values(93, 2030, 0);
insert into switch.carbon_cap
values(93, 2031, 0);
insert into switch.carbon_cap
values(93, 2032, 0);
insert into switch.carbon_cap
values(93, 2033, 0);
insert into switch.carbon_cap
values(93, 2034, 0);
insert into switch.carbon_cap
values(93, 2035, 0);
insert into switch.carbon_cap
values(93, 2036, 0);
insert into switch.carbon_cap
values(93, 2037, 0);
insert into switch.carbon_cap
values(93, 2038, 0);
insert into switch.carbon_cap
values(93, 2039, 0);
insert into switch.carbon_cap
values(93, 2040, 0);
insert into switch.carbon_cap
values(93, 2041, 0);
insert into switch.carbon_cap
values(93, 2042, 0);
insert into switch.carbon_cap
values(93, 2043, 0);
insert into switch.carbon_cap
values(93, 2044, 0);
insert into switch.carbon_cap
values(93, 2045, 0);
insert into switch.carbon_cap
values(93, 2046, 0);
insert into switch.carbon_cap
values(93, 2047, 0);
insert into switch.carbon_cap
values(93, 2048, 0);
insert into switch.carbon_cap
values(93, 2049, 0);
insert into switch.carbon_cap
values(93, 2050, 0);
insert into switch.carbon_cap
values(93, 2051, 0);
insert into switch.carbon_cap
values(93, 2052, 0);
insert into switch.carbon_cap
values(93, 2053, 0);
insert into switch.carbon_cap
values(93, 2054, 0);
insert into switch.carbon_cap
values(93, 2055, 0);
insert into switch.carbon_cap
values(93, 2056, 0);
insert into switch.carbon_cap
values(93, 2057, 0);
insert into switch.carbon_cap
values(93, 2058, 0);
insert into switch.carbon_cap
values(93, 2059, 0);
insert into switch.carbon_cap
values(93, 2060, 0);
insert into switch.carbon_cap
values(93, 2061, 0);
