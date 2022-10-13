-- October 12, 2022
-- Author: pesap

-- Reason: We detected a type in the transmission derating factor for all the transmission
-- lines for the WECC model. This is the description in the switch module of what the
-- transmission derate factor does: trans_derating_factor[tx in TRANSMISSION_LINES] is an
-- overall derating factor for each transmission line that can reflect forced outage
-- rates, stability or contingency limitations. This parameter is optional and defaults to
-- 1. This parameter should be in the range of 0 to 1, being 0 a value that disables the
-- line completely.
-- In our scenarios we have been using 0.59 for no apparent reason and this limited the
-- amount of electricity that flow throught the transmission line. The new value that we
-- will use for the scenarios is 0.95 or a 5% derate.

alter table 
  switch.transmission_lines 
add 
  column transmission_scenario_id int;

alter table 
  switch.scenario 
add 
  column transmission_scenario_id int;

UPDATE switch.transmission_lines SET transmission_scenario_id = 1;
UPDATE switch.scenario SET transmission_scenario_id = 1;

alter table switch.transmission_lines drop constraint transmission_lines_pkey;

insert into switch.transmission_lines(
  transmission_line_id, start_load_zone_id,
  end_load_zone_id, trans_length_km,
  trans_efficiency, existing_trans_cap_mw,
  new_build_allowed, derating_factor,
  terrain_multiplier, transmission_cost_econ_multiplier,
  transmission_scenario_id
)
select
  transmission_line_id,
  start_load_zone_id,
  end_load_zone_id,
  trans_length_km,
  trans_efficiency,
  existing_trans_cap_mw,
  new_build_allowed,
  0.95 as derating_factor,
  terrain_multiplier,
  transmission_cost_econ_multiplier,
  2 as transmission_scenario_id
from
  switch.transmission_lines;

insert into switch.scenario
values (179,
		'[LDES and SWITCH_WEAP]',
		'Baseline scenario with 0 carbon cap for WECC and CA by 2045, 15% PRM, updated 2 days per month sampling and tranmission_line scenario',
		17, -- study_timeframe_id
		16, -- time_sample_id
		115, -- demand_scenario_id
		4, -- fuel_simple_price_scenario, without Bio_Solid costs, because they are provided by supply curve
		23, -- generation_plant_scenario_id
		25, -- generation_plant_cost_scenario_id
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
		1, --enable_planning_reserves
		2, --generation_plant_technologies_scenario_id
		3, --variable_o_m_cost_scenario_id
		NULL,--wind_to_solar_ratio
    2 --tranmission_scenario_id
		);
