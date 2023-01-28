-- Friday, Sept 23, 2020
-- PHG

-- First we create a draft table to receive the data from the csv:
-- Make sure to choose the next available demand_scenario_id for each scenario from evolved
-- The last scenario seems to be 152 (you can check by looking at switch.demand_scenario)
create table public.demands_from_evolved(
load_zone_id INT,
demand_scenario_id INT, -- change this for each scenario
raw_timepoint_id INT,
load_zone_name VARCHAR(30),
timestamp_utc timestamp without time zone,
demand_mw double precision,
primary key (load_zone_id, demand_scenario_id, raw_timepoint_id)
);

-- Then we copy the data in the csv file (it is expecting headers)
COPY public.demands_from_evolved
FROM 'path_in_the_servwer_to_file_ending_in.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;


-- Create new demand scenario in the appropriate table:
-- Change the name and description so it reflects the scenario
INSERT INTO switch.demand_scenario
VALUES(153, '[GridLab] Reference scen', 'Write a description here');

-- Now we can insert the data into the official SWITCH table
INSERT INTO switch.demand_timeseries
SELECT * FROM public.demands_from_evolved;
-- WHERE demand_scenario_id = 154; -- I added this comment because it will help when you upload more scenarios

-- Create new scenario to pull data using get_inputs:
-- edit ids to create the scenario of interest.
-- Edit the name and description text so you can recall the data it is pulling
-- (WECC emissions? zero or 80% reductions from 2005? RPS? etc)
INSERT INTO switch.scenario
VALUES (201, 
		'[GridLab] ...', 
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
		

		
-- Notes on what to change when you repeat this process for new scenarios:

-- When you repeat this process for the other two demand scenarios, you should not run the CREATE
-- statement from line 7, as the table will already exist.
-- You need to change the demand_scenario_id in line 26.
-- In lines 29-30, when you insert the data, now you should add a WHERE statement so it only adds 
-- the new rows you are copying  into the public.demands_from_evolved table.
-- In line 38 onwards you need to edit accordingly