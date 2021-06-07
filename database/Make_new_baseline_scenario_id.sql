-- create new baseline scenario in the Scenario table, by copying a previous scenario and updating some of the scenario ids based on the new scenarios created for the 2020 baseline

insert into switch.scenario (scenario_id, name, description, study_timeframe_id, time_sample_id, demand_scenario_id, fuel_simple_price_scenario_id, generation_plant_scenario_id, generation_plant_cost_scenario_id, generation_plant_existing_and_planned_scenario_id, hydro_simple_scenario_id, carbon_cap_scenario_id, supply_curves_scenario_id, regional_fuel_market_scenario_id, zone_to_regional_fuel_market_scenario_id, rps_scenario_id, enable_dr, enable_ev)

select 171 as scenario_id, s.name, s.description, s.study_timeframe_id, s.time_sample_id, s.demand_scenario_id, s.fuel_simple_price_scenario_id, s.generation_plant_scenario_id, s.generation_plant_cost_scenario_id, s.generation_plant_existing_and_planned_scenario_id, s.hydro_simple_scenario_id, s.carbon_cap_scenario_id, s.supply_curves_scenario_id, s.regional_fuel_market_scenario_id, s.zone_to_regional_fuel_market_scenario_id, s.rps_scenario_id, s.enable_dr, s.enable_ev
from switch.scenario s where
scenario_id=147;

UPDATE switch.scenario SET
name = '[SWITCH_WEAP] Baseline_no_WEAP',
description = 'Baseline scenario with overnight costs from 2019 ATB in $2018, updated existing gen from EIA 2018 data, hydro 2002 - 2018 median year, candidate gen and load and carbon cap same as id 147, 60perc RPS by 2030 in CA, WECC 80perc reduced carbon cap',
fuel_simple_price_scenario_id = 4,
generation_plant_scenario_id = 22,
generation_plant_cost_scenario_id = 23,
generation_plant_existing_and_planned_scenario_id = 21,
hydro_simple_scenario_id = 22,
carbon_cap_scenario_id = 90,
supply_curves_scenario_id = 2,
rps_scenario_id = 6
WHERE scenario_id=171;


-- create new toy baseline scenario in the Scenario table, by copying the full baseline scenario and changing the time sampling scenario ids to a smaller time frame

insert into switch.scenario (scenario_id, name, description, study_timeframe_id, time_sample_id, demand_scenario_id, fuel_simple_price_scenario_id, generation_plant_scenario_id, generation_plant_cost_scenario_id, generation_plant_existing_and_planned_scenario_id, hydro_simple_scenario_id, carbon_cap_scenario_id, supply_curves_scenario_id, regional_fuel_market_scenario_id, zone_to_regional_fuel_market_scenario_id, rps_scenario_id, enable_dr, enable_ev)

select 172 as scenario_id, s.name, s.description, s.study_timeframe_id, s.time_sample_id, s.demand_scenario_id, s.fuel_simple_price_scenario_id, s.generation_plant_scenario_id, s.generation_plant_cost_scenario_id, s.generation_plant_existing_and_planned_scenario_id, s.hydro_simple_scenario_id, s.carbon_cap_scenario_id, s.supply_curves_scenario_id, s.regional_fuel_market_scenario_id, s.zone_to_regional_fuel_market_scenario_id, s.rps_scenario_id, s.enable_dr, s.enable_ev
from switch.scenario s where
scenario_id=171;

UPDATE switch.scenario SET
name = '[SWITCH_WEAP] Toy Baseline_no_WEAP',
description = 'Toy Baseline scenario same as 171 but with toy time sampling 2',
study_timeframe_id = 2,
time_sample_id = 2
WHERE scenario_id = 172;

-- create new baseline scenario in the Scenario table, by copying a previous scenario and updating some of the scenario ids based on the new scenarios created for the 2020 baseline

-- CHANGING THE HYDROPOWER SIMPLE SCENARIO ID TO USE THE AVERAGE GENERATION INSTEAD OF MEDIAN YEAR GENERATION

insert into switch.scenario (scenario_id, name, description, study_timeframe_id, time_sample_id, demand_scenario_id, fuel_simple_price_scenario_id, generation_plant_scenario_id, generation_plant_cost_scenario_id, generation_plant_existing_and_planned_scenario_id, hydro_simple_scenario_id, carbon_cap_scenario_id, supply_curves_scenario_id, regional_fuel_market_scenario_id, zone_to_regional_fuel_market_scenario_id, rps_scenario_id, enable_dr, enable_ev)

select 173 as scenario_id, s.name, s.description, s.study_timeframe_id, s.time_sample_id, s.demand_scenario_id, s.fuel_simple_price_scenario_id, s.generation_plant_scenario_id, s.generation_plant_cost_scenario_id, s.generation_plant_existing_and_planned_scenario_id, s.hydro_simple_scenario_id, s.carbon_cap_scenario_id, s.supply_curves_scenario_id, s.regional_fuel_market_scenario_id, s.zone_to_regional_fuel_market_scenario_id, s.rps_scenario_id, s.enable_dr, s.enable_ev
from switch.scenario s where
scenario_id=171;

UPDATE switch.scenario SET
name = '[SWITCH_WEAP] Baseline_no_WEAP_Hydro_Avg',
description = 'Baseline scenario with overnight costs from 2019 ATB in $2018, updated existing gen from EIA 2018 data, hydro monthly average of 2002 - 2018, candidate gen and load and carbon cap same as id 147, 60perc RPS by 2030 in CA, WECC 80perc reduced carbon cap',
hydro_simple_scenario_id = 23
WHERE scenario_id=173;


-- CREATING A NEW SCENARIO THAT REMOVES COMPRESSED AIR ENERGY STORAGE (CAES) FROM THE CANDIDATE GENERATOR LIST AND COSTS


insert into switch.scenario (scenario_id, name, description, study_timeframe_id, time_sample_id, demand_scenario_id, fuel_simple_price_scenario_id, generation_plant_scenario_id, generation_plant_cost_scenario_id, generation_plant_existing_and_planned_scenario_id, hydro_simple_scenario_id, carbon_cap_scenario_id, supply_curves_scenario_id, regional_fuel_market_scenario_id, zone_to_regional_fuel_market_scenario_id, rps_scenario_id, enable_dr, enable_ev)

select 174 as scenario_id, s.name, s.description, s.study_timeframe_id, s.time_sample_id, s.demand_scenario_id, s.fuel_simple_price_scenario_id, s.generation_plant_scenario_id, s.generation_plant_cost_scenario_id, s.generation_plant_existing_and_planned_scenario_id, s.hydro_simple_scenario_id, s.carbon_cap_scenario_id, s.supply_curves_scenario_id, s.regional_fuel_market_scenario_id, s.zone_to_regional_fuel_market_scenario_id, s.rps_scenario_id, s.enable_dr, s.enable_ev
from switch.scenario s where
scenario_id=173;

UPDATE switch.scenario SET
name = '[SWITCH_WEAP] Baseline_no_WEAP_Hydro_Avg_no_CAES',
description = 'Baseline scenario with overnight costs from 2019 ATB in $2018, updated gen from EIA 2018 data, hydro monthly average of 2002 - 2018, candidate gen and load and carbon cap same as id 173 but no CAES candiate gen',
generation_plant_cost_scenario_id = 24,
generation_plant_scenario_id = 23
WHERE scenario_id=174;