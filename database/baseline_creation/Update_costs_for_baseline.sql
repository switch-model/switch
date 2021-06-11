--- This script imports new cost data for overnight, fixed O&M, variable O&M and adds them to the appropriate existing and proposed generators in the new baseline with EIA 2018 vintage existing generators, AMPL Canada and Mex existing generators, and AMPL candidate generators.

-- For some established technologies, overnight costs are not updated. Prior data is copied and adjusted from $2016 to $2018 based on the CPI inflation multiplier (1.05)

--- For fuel costs (supply curves and simple fuel prices) prior data is copied and adjusted from $2016 to $2018 based on the CPI inflation multiplier (1.05)

-- 1. Updating fuel costs, starting with the supply curve data for Bio_Gas and Bio_Solid
-- $2016 to $2018 based on the CPI inflation multiplier
INSERT INTO switch.fuel_supply_curves (supply_curves_scenario_id, regional_fuel_market, fuel, year, tier, unit_cost, max_avail_at_cost, notes)

SELECT 2 AS supply_curves_scenario_id, regional_fuel_market, fuel, year, tier, 1.05 * unit_cost as unit_cost, max_avail_at_cost, 'same as id 1, updated $2018 from $2016 with 1.05 CPI' as notes
FROM switch.fuel_supply_curves
WHERE supply_curves_scenario_id = 1

-- 2. Updating fuel costs, for the fuels using fuel_simple_scenario_id (all fuels other than Bio_Gas and Bio_Solid)
-- $2016 to $2018 based on the CPI inflation multiplier
INSERT INTO switch.fuel_simple_price_scenario (fuel_simple_price_scenario_id, name, description)

SELECT 4 AS fuel_simple_price_scenario_id, 'SWITCH 2020 Basecase' as name, 'same as id 3 but updated to $2018 from $2016' as description
FROM switch.fuel_simple_price_scenario
WHERE fuel_simple_price_scenario_id = 3

INSERT INTO switch.fuel_simple_price_yearly (fuel_simple_scenario_id, load_zone_id, load_zone_name, fuel, projection_Year, fuel_price, notes, eai_region)

SELECT 4 AS fuel_simple_scenario_id, load_zone_id, load_zone_name, fuel, projection_Year, 1.05 * fuel_price as fuel_price, 'same as id 3 but updated to 2018 $/MMBtu from $2016 with 1.05 CPI' as notes, eai_region
FROM switch.fuel_simple_price_yearly
WHERE fuel_simple_scenario_id = 3

--3. Update all connection_cost_per_mw, and variable_o_m in gen_plant table based on CPI inflation multiplier
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_scenario_member gps
ON gp.generation_plant_id = gps.generation_plant_id
WHERE gps.generation_plant_scenario_id = 22)

UPDATE switch.generation_plant a
SET variable_o_m = a.variable_o_m * 1.05,
connect_cost_per_mw = a.connect_cost_per_mw * 1.05
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--4. Create a new generation_plant_cost scenario 23 (copying 22) but updating all overnight cost, and fixed o_m based on CPI inflation multiplier
INSERT INTO switch.generation_plant_cost_scenario (generation_plant_cost_scenario_id, name, description)

SELECT 23 AS generation_plant_cost_scenario_id, 'SWITCH 2020 Basecase costs' as name, 'updated costs for solar, wind, battery, geothermal, csp, ccgt, gt from NREL ATB 2019, otherwise for all other tech same costs as id 6 for all generators in id 22 but updated to $2018 from $2016' as description
FROM switch.generation_plant_cost_scenario
WHERE generation_plant_cost_scenario_id = 22

INSERT INTO switch.generation_plant_cost (generation_plant_cost_scenario_id, generation_plant_id, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)

SELECT 23 AS generation_plant_cost_scenario_id, generation_plant_id, build_year, 1.05 * fixed_o_m as fixed_o_m, 1.05 * overnight_cost as overnight_cost, 1.05 * storage_energy_capacity_cost_per_mwh as storage_energy_capacity_cost_per_mwh
FROM switch.generation_plant_cost
WHERE generation_plant_cost_scenario_id = 22

--5. Replace the overnight, fixed_o_m and variable_o_m costs for certain technologies

-- add fixed o m and storage cost columns to the overnight cost update table
CREATE TABLE baseline_2020_generation_plant_cost_update (
  generation_plant_cost_scenario_id smallint,
  gen_tech character VARYING(60),
  build_year	integer,
  fixed_o_m	double precision,
  overnight_cost	double precision,
  storage_energy_capacity_cost_per_mwh double precision
)

-- upload the new overnight, fixed_o_m and storage costs for certain technologies

COPY baseline_2020_generation_plant_cost_update (generation_plant_cost_scenario_id, gen_tech, build_year, fixed_o_m, overnight_cost, storage_energy_capacity_cost_per_mwh)
FROM '/Users/juliaszinai/Dropbox/Linux_work/switch/WECC/Data for SWITCH_WECC_baseline/switch_costs_1_ptcitx_2.csv'
DELIMITER ','
CSV HEADER;

-- -- create backup table for testing
-- DROP TABLE switch.jsz_backup2_generation_plant_cost; CREATE TABLE switch.jsz_backup2_generation_plant_cost (LIKE switch.generation_plant_cost INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup2_generation_plant_cost SELECT * FROM switch.generation_plant_cost;

-- update the overnight and fixed o_m costs for all the technologies and years that are in the overnight cost update table, for generation_plant cost scenario 23, candidate generators (named 'proposed')
WITH t AS
(SELECT gps.generation_plant_cost_scenario_id, gps.generation_plant_id, gp.name, gp.gen_tech, gps.build_year, oc.fixed_o_m, oc.overnight_cost,  oc.storage_energy_capacity_cost_per_mwh
FROM generation_plant gp
JOIN generation_plant_cost gps
ON gp.generation_plant_id = gps.generation_plant_id
JOIN baseline_2020_generation_plant_cost_update oc
ON oc.gen_tech = gp.gen_tech
AND gps.build_year = oc.build_year
WHERE gps.generation_plant_cost_scenario_id = 23
and gp.name = 'Proposed')

UPDATE switch.generation_plant_cost a
SET overnight_cost = t.overnight_cost,
fixed_o_m = t.fixed_o_m,
storage_energy_capacity_cost_per_mwh = t.storage_energy_capacity_cost_per_mwh
FROM t
WHERE a.generation_plant_id = t.generation_plant_id
and a.build_year = t.build_year
and a.generation_plant_cost_scenario_id = t.generation_plant_cost_scenario_id

-- update the overnight and fixed o_m costs for all the technologies and years that are in the overnight cost update table, for generation_plant cost scenario 23, candidate wind generators (that are named and not called 'proposed')
WITH t AS
(SELECT gps.generation_plant_cost_scenario_id, gps.generation_plant_id, gp.name, gp.gen_tech, gps.build_year, oc.fixed_o_m, oc.overnight_cost,  oc.storage_energy_capacity_cost_per_mwh
FROM generation_plant gp
JOIN generation_plant_cost gps
ON gp.generation_plant_id = gps.generation_plant_id
JOIN baseline_2020_generation_plant_cost_update oc
ON oc.gen_tech = gp.gen_tech
AND gps.build_year = oc.build_year
LEFT JOIN generation_plant_existing_and_planned gep
ON gps.generation_plant_id = gep.generation_plant_id
WHERE gep.generation_plant_id IS NULL
AND gps.generation_plant_cost_scenario_id = 23
AND gp.name != 'Proposed'
AND gp.gen_tech = 'Wind')

UPDATE switch.generation_plant_cost a
SET overnight_cost = t.overnight_cost,
fixed_o_m = t.fixed_o_m,
storage_energy_capacity_cost_per_mwh = t.storage_energy_capacity_cost_per_mwh
FROM t
WHERE a.generation_plant_id = t.generation_plant_id
and a.build_year = t.build_year
and a.generation_plant_cost_scenario_id = t.generation_plant_cost_scenario_id

--6. Update the variable_o_m costs for certain technologies

-- Create a new table of the average variable_o_m costs that exist in the db in $2016, from the previous CEC runs (generation plant id = 14)
create table switch.variable_o_m_costs as
select 1 as variable_o_m_cost_scenario_id, gen_tech, energy_source, avg(variable_o_m)/1.05 as variable_o_m, 'gen_plant_cost_scenario_14 variable_o_m costs in $2016 dollars' as notes
from generation_plant a
join generation_plant_scenario_member b
on a.generation_plant_id = b.generation_plant_id
where generation_plant_scenario_id = 14
group by gen_tech, energy_source
order by energy_source, gen_tech

-- Create a scenario of the same average variable_o_m costs from the previous CEC runs genration_plant id 14, but in $2018 dollars
insert into switch.variable_o_m_costs (variable_o_m_cost_scenario_id, gen_tech, energy_source, variable_o_m, notes)

select 2 as variable_o_m_cost_scenario_id, gen_tech, energy_source, variable_o_m * 1.05 as variable_o_m, 'gen_plant_cost_scenario_14 variable_o_m costs in $2018 dollars' as notes
from switch.variable_o_m_costs
where variable_o_m_cost_scenario_id = 1


-- Copy the variable o_m costs from $2018 dollars and update the variable o and m costs for certain technologies based on the NREL ATB
insert into switch.variable_o_m_costs (variable_o_m_cost_scenario_id, gen_tech, energy_source, variable_o_m, notes)

select 3 as variable_o_m_cost_scenario_id, gen_tech, energy_source, variable_o_m, 'CSP, CCGT, Gas CT, Geothermal, Battery, Wind, Solar costs updated from 2020 NREL ATB in $2018, otherwise gen_plant_cost_scenario_14 costs in $2018 dollars, ' as notes
from switch.variable_o_m_costs
where variable_o_m_cost_scenario_id = 2

-- rename the gen_tech to the updated gen_tech names in scenario 3

-- testing on backup table
---CREATE TABLE switch.jsz_backup_variable_o_m_costs (LIKE switch.variable_o_m_costs INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup_variable_o_m_costs SELECT * FROM switch.variable_o_m_costs;

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Bio_Gas'
-- WHERE a.gen_tech = 'GT'
-- AND a.energy_source = 'Bio_Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Bio_Gas_Internal_Combustion_Engine'
-- WHERE a.gen_tech = 'IC'
-- AND a.energy_source = 'Bio_Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Bio_Gas_Steam_Turbine'
-- WHERE a.gen_tech = 'ST'
-- AND a.energy_source = 'Bio_Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Bio_Solid_Steam_Turbine'
-- WHERE a.gen_tech = 'ST'
-- AND a.energy_source = 'Bio_Solid'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Coal_Steam_Turbine'
-- WHERE a.gen_tech = 'ST'
-- AND a.energy_source = 'Coal'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'DistillateFuelOil_Combustion_Turbine'
-- WHERE a.gen_tech = 'GT'
-- AND a.energy_source = 'DistillateFuelOil'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'DistillateFuelOil_Internal_Combustion_Engine'
-- WHERE a.gen_tech = 'IC'
-- AND a.energy_source = 'DistillateFuelOil'
-- AND a.variable_o_m_cost_scenario_id = 3

-- --updating cost as well as gen_tech name
-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Gas_Combustion_Turbine'
-- WHERE a.gen_tech = 'GT'
-- AND a.energy_source = 'Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET variable_o_m = 2.161100196
-- WHERE a.gen_tech = 'Gas_Combustion_Turbine'
-- AND a.energy_source = 'Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'CCGT'
-- WHERE a.gen_tech = 'CC'
-- AND a.energy_source = 'Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET variable_o_m = 4.499017682
-- WHERE a.gen_tech = 'CCGT'
-- AND a.energy_source = 'Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Gas_Internal_Combustion_Engine'
-- WHERE a.gen_tech = 'IC'
-- AND a.energy_source = 'Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Gas_Steam_Turbine'
-- WHERE a.gen_tech = 'ST'
-- AND a.energy_source = 'Gas'
-- AND a.variable_o_m_cost_scenario_id = 3

-- --updating cost as well as gen_tech name
-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Geothermal'
-- WHERE a.gen_tech = 'BT'
-- AND a.energy_source = 'Geothermal'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Geothermal'
-- WHERE a.gen_tech = 'ST'
-- AND a.energy_source = 'Geothermal'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET variable_o_m = 0
-- WHERE a.gen_tech = 'Geothermal'
-- AND a.energy_source = 'Geothermal'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'CSP_Trough_No_Storage'
-- WHERE a.gen_tech = 'CP'
-- AND a.energy_source = 'Solar'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Central_PV'
-- WHERE a.gen_tech = 'PV'
-- AND a.energy_source = 'Solar'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Nuclear'
-- WHERE a.gen_tech = 'ST'
-- AND a.energy_source = 'Uranium'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Hydro_NonPumped'
-- WHERE a.gen_tech = 'HY'
-- AND a.energy_source = 'Water'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Hydro_Pumped'
-- WHERE a.gen_tech = 'PS'
-- AND a.energy_source = 'Water'
-- AND a.variable_o_m_cost_scenario_id = 3

-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET gen_tech = 'Wind'
-- WHERE a.gen_tech = 'WT'
-- AND a.energy_source = 'Wind'
-- AND a.variable_o_m_cost_scenario_id = 3

-- -- updated just CSP variable om
-- UPDATE switch.jsz_backup_variable_o_m_costs a
-- SET variable_o_m = 3.5854875
-- WHERE a.gen_tech = 'CSP_Trough_6h_Storage'
-- AND a.energy_source = 'Solar'
-- AND a.variable_o_m_cost_scenario_id = 3

-- Run queries to update variable o_m costs now on the real table for scenario 3

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Bio_Gas'
WHERE a.gen_tech = 'CC'
AND a.energy_source = 'Bio_Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Bio_Gas'
WHERE a.gen_tech = 'GT'
AND a.energy_source = 'Bio_Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Bio_Gas_Internal_Combustion_Engine'
WHERE a.gen_tech = 'IC'
AND a.energy_source = 'Bio_Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Bio_Gas_Steam_Turbine'
WHERE a.gen_tech = 'ST'
AND a.energy_source = 'Bio_Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Bio_Solid_Steam_Turbine'
WHERE a.gen_tech = 'ST'
AND a.energy_source = 'Bio_Solid'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Coal_Steam_Turbine'
WHERE a.gen_tech = 'ST'
AND a.energy_source = 'Coal'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'DistillateFuelOil_Combustion_Turbine'
WHERE a.gen_tech = 'GT'
AND a.energy_source = 'DistillateFuelOil'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'DistillateFuelOil_Internal_Combustion_Engine'
WHERE a.gen_tech = 'IC'
AND a.energy_source = 'DistillateFuelOil'
AND a.variable_o_m_cost_scenario_id = 3;

--updating cost as well as gen_tech name
UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Gas_Combustion_Turbine'
WHERE a.gen_tech = 'GT'
AND a.energy_source = 'Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET variable_o_m = 2.161100196
WHERE a.gen_tech = 'Gas_Combustion_Turbine'
AND a.energy_source = 'Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'CCGT'
WHERE a.gen_tech = 'CC'
AND a.energy_source = 'Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET variable_o_m = 4.499017682
WHERE a.gen_tech = 'CCGT'
AND a.energy_source = 'Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Gas_Internal_Combustion_Engine'
WHERE a.gen_tech = 'IC'
AND a.energy_source = 'Gas'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Gas_Steam_Turbine'
WHERE a.gen_tech = 'ST'
AND a.energy_source = 'Gas'
AND a.variable_o_m_cost_scenario_id = 3;

--updating cost as well as gen_tech name
UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Geothermal'
WHERE a.gen_tech = 'BT'
AND a.energy_source = 'Geothermal'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Geothermal'
WHERE a.gen_tech = 'ST'
AND a.energy_source = 'Geothermal'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET variable_o_m = 0
WHERE a.gen_tech = 'Geothermal'
AND a.energy_source = 'Geothermal'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'CSP_Trough_No_Storage'
WHERE a.gen_tech = 'CP'
AND a.energy_source = 'Solar'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Central_PV'
WHERE a.gen_tech = 'PV'
AND a.energy_source = 'Solar'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Nuclear'
WHERE a.gen_tech = 'ST'
AND a.energy_source = 'Uranium'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Hydro_NonPumped'
WHERE a.gen_tech = 'HY'
AND a.energy_source = 'Water'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Hydro_Pumped'
WHERE a.gen_tech = 'PS'
AND a.energy_source = 'Water'
AND a.variable_o_m_cost_scenario_id = 3;

UPDATE switch.variable_o_m_costs a
SET gen_tech = 'Wind'
WHERE a.gen_tech = 'WT'
AND a.energy_source = 'Wind'
AND a.variable_o_m_cost_scenario_id = 3;

-- updated just CSP variable om
UPDATE switch.variable_o_m_costs a
SET variable_o_m = 3.5854875
WHERE a.gen_tech = 'CSP_Trough_6h_Storage'
AND a.energy_source = 'Solar'
AND a.variable_o_m_cost_scenario_id = 3;

-- re-averaging because some of the gen_tech rows are now repeated
WITH t AS
(SELECT gen_tech, energy_source, avg(variable_o_m) as variable_o_m, variable_o_m_cost_scenario_id
FROM variable_o_m_costs
WHERE variable_o_m_cost_scenario_id = 3
group by variable_o_m_cost_scenario_id, gen_tech, energy_source)

UPDATE switch.variable_o_m_costs a
SET variable_o_m = t.variable_o_m
FROM t
WHERE a.gen_tech = t.gen_tech
and a.energy_source = t.energy_source
and a.variable_o_m_cost_scenario_id = 3

-- removing duplicates in scenario 3

-- create a copy of the table with no duplicates
CREATE TABLE switch.variable_o_m_costs_new (LIKE switch.variable_o_m_costs INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

INSERT INTO switch.variable_o_m_costs_new

select distinct on (variable_o_m_cost_scenario_id, gen_tech, energy_source, variable_o_m) *
from switch.variable_o_m_costs;

-- rename old table
ALTER TABLE variable_o_m_costs
RENAME TO variable_o_m_costs_backup;

-- rename new table as original name
ALTER TABLE variable_o_m_costs_new
RENAME TO variable_o_m_costs;



--6. Add fixed_o_m costs to existing generators that don't have them (but are supposed to have them)

--- Skipping this for now....



