-- These queries update the gen_tech labels in the generation plant table of the existing generators that were added from EIA data in 2020. This is designed to standardize the names of gen_tech bewteen the existing and candidate generation plants, and between EIA and AMPL data.

-- At the end a column is added to the generation_plant_technologies table that maps these AMPL gen_tech names to the gen_tech from EIA that is listed there

--'CC','Bio_Gas':'Bio_Gas','Bio_Gas',
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'CC'
AND gp.energy_source = 'Bio_Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Bio_Gas'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'GT','Bio_Gas':'Bio_Gas','Bio_Gas',
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'GT'
AND gp.energy_source = 'Bio_Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Bio_Gas'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'IC','Bio_Gas':'Bio_Gas_Internal_Combustion_Engine','Bio_Gas'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'IC'
AND gp.energy_source = 'Bio_Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Bio_Gas_Internal_Combustion_Engine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'ST','Bio_Gas':'Bio_Gas_Steam_Turbine','Bio_Gas'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'ST'
AND gp.energy_source = 'Bio_Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Bio_Gas_Steam_Turbine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'ST','Bio_Solid':'Bio_Solid_Steam_Turbine','Bio_Solid'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'ST'
AND gp.energy_source = 'Bio_Solid'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Bio_Solid_Steam_Turbine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'ST','Coal':'Coal_Steam_Turbine','Coal'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'ST'
AND gp.energy_source = 'Coal'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Coal_Steam_Turbine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'GT','DistillateFuelOil':'DistillateFuelOil_Combustion_Turbine','DistillateFuelOil'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'GT'
AND gp.energy_source = 'DistillateFuelOil'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'DistillateFuelOil_Combustion_Turbine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'IC','DistillateFuelOil':'DistillateFuelOil_Internal_Combustion_Engine','DistillateFuelOil'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'IC'
AND gp.energy_source = 'DistillateFuelOil'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'DistillateFuelOil_Internal_Combustion_Engine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'Battery_Storage','Electricity':'Battery_Storage','Electricity'
-- already matching, don't need to replace gen_tech

-- WITH t AS
-- (SELECT gp.generation_plant_id
-- FROM generation_plant gp
-- JOIN generation_plant_existing_and_planned gep
-- ON gp.generation_plant_id = gep.generation_plant_id
-- WHERE gp.gen_tech = 'Battery_Storage'
-- AND gp.energy_source = 'Electricity'
-- AND gep.generation_plant_existing_and_planned_scenario_id = 21)

-- UPDATE switch.generation_plant a
-- SET gen_tech = 'Battery_Storage'
-- FROM t
-- WHERE a.generation_plant_id = t.generation_plant_id

--'CC','Gas':'CCGT','Gas'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'CC'
AND gp.energy_source = 'Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'CCGT'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'GT','Gas':'Gas_Combustion_Turbine','Gas'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'GT'
AND gp.energy_source = 'Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Gas_Combustion_Turbine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'IC','Gas':'Gas_Internal_Combustion_Engine','Gas',
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'IC'
AND gp.energy_source = 'Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Gas_Internal_Combustion_Engine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'ST','Gas':'Gas_Steam_Turbine','Gas'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'ST'
AND gp.energy_source = 'Gas'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Gas_Steam_Turbine'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'BT','Geothermal':'Geothermal','Geothermal'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'BT'
AND gp.energy_source = 'Geothermal'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Geothermal'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'ST','Geothermal':'Geothermal','Geothermal'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'ST'
AND gp.energy_source = 'Geothermal'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Geothermal'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'CP','Solar':'CSP_Trough_No_Storage','Solar'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'CP'
AND gp.energy_source = 'Solar'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'CSP_Trough_No_Storage'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'PV','Solar':'Central_PV','Solar'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'PV'
AND gp.energy_source = 'Solar'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Central_PV'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'ST','Uranium':'Nuclear','Uranium'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'ST'
AND gp.energy_source = 'Uranium'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Nuclear'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'HY','Water':'Hydro_NonPumped','Water'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'HY'
AND gp.energy_source = 'Water'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Hydro_NonPumped'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'PS','Water':'Hydro_Pumped','Water'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'PS'
AND gp.energy_source = 'Water'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Hydro_Pumped'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

--'WT','Wind':'Wind','Wind'
WITH t AS
(SELECT gp.generation_plant_id
FROM generation_plant gp
JOIN generation_plant_existing_and_planned gep
ON gp.generation_plant_id = gep.generation_plant_id
WHERE gp.gen_tech = 'WT'
AND gp.energy_source = 'Wind'
AND gep.generation_plant_existing_and_planned_scenario_id = 21)

UPDATE switch.generation_plant a
SET gen_tech = 'Wind'
FROM t
WHERE a.generation_plant_id = t.generation_plant_id

-- Adding column into generation_plant_technologies table that documents the mapping
ALTER TABLE generation_plant_technologies
ADD COLUMN gen_tech_AMPL VARCHAR,
ADD COLUMN energy_source_AMPL VARCHAR;

-- Adding mapping for each gen_tech, energy_source pair from EIA to AMPL names
WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='CC' AND gp.energy_source = 'Bio_Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Bio_Gas', energy_source_AMPL = 'Bio_Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='GT' AND gp.energy_source = 'Bio_Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Bio_Gas', energy_source_AMPL = 'Bio_Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='IC' AND gp.energy_source = 'Bio_Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Bio_Gas_Internal_Combustion_Engine', energy_source_AMPL = 'Bio_Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='ST' AND gp.energy_source = 'Bio_Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Bio_Gas_Steam_Turbine', energy_source_AMPL = 'Bio_Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='ST' AND gp.energy_source = 'Bio_Solid') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Bio_Solid_Steam_Turbine', energy_source_AMPL = 'Bio_Solid' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='ST' AND gp.energy_source = 'Coal') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Coal_Steam_Turbine', energy_source_AMPL = 'Coal' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='GT' AND gp.energy_source = 'DistillateFuelOil') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'DistillateFuelOil_Combustion_Turbine', energy_source_AMPL = 'DistillateFuelOil' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='IC' AND gp.energy_source = 'DistillateFuelOil') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'DistillateFuelOil_Internal_Combustion_Engine', energy_source_AMPL = 'DistillateFuelOil' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='Battery_Storage' AND gp.energy_source = 'Electricity') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Battery_Storage', energy_source_AMPL = 'Electricity' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='CC' AND gp.energy_source = 'Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'CCGT', energy_source_AMPL = 'Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='GT' AND gp.energy_source = 'Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Gas_Combustion_Turbine', energy_source_AMPL = 'Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='IC' AND gp.energy_source = 'Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Gas_Internal_Combustion_Engine', energy_source_AMPL = 'Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='ST' AND gp.energy_source = 'Gas') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Gas_Steam_Turbine', energy_source_AMPL = 'Gas' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='BT' AND gp.energy_source = 'Geothermal') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Geothermal', energy_source_AMPL = 'Geothermal' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='ST' AND gp.energy_source = 'Geothermal') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Geothermal', energy_source_AMPL = 'Geothermal' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='CP' AND gp.energy_source = 'Solar') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'CSP_Trough_No_Storage', energy_source_AMPL = 'Solar' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='PV' AND gp.energy_source = 'Solar') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Central_PV', energy_source_AMPL = 'Solar' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='ST' AND gp.energy_source = 'Uranium') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Nuclear', energy_source_AMPL = 'Uranium' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='HY' AND gp.energy_source = 'Water') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Hydro_NonPumped', energy_source_AMPL = 'Water' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='PS' AND gp.energy_source = 'Water') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Hydro_Pumped', energy_source_AMPL = 'Water' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;

WITH t AS (SELECT gp.gen_tech, gp.energy_source FROM generation_plant_technologies gp WHERE gp.gen_tech ='WT' AND gp.energy_source = 'Wind') UPDATE switch.generation_plant_technologies a SET gen_tech_AMPL = 'Wind', energy_source_AMPL = 'Wind' FROM t WHERE a.gen_tech = t.gen_tech and a.energy_source = t.energy_source;
