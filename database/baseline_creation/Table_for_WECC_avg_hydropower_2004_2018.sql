-- This query creates a table to document the year classification of total WECC hydropower annual generation

CREATE TABLE switch.hydro_avg_monthly_gen_2004_2018 (
generation_plant_id int,
month int,
hydro_min_flow_mw double precision,
hydro_avg_flow_mw double precision,
notes VARCHAR,
primary key (generation_plant_id, month)
);

-- This query sums all the hydropower generation across the WECC for each year of data in the baseline set of existing generators (scenario 21). Then it ranks the total WECC hydropower generation in descending order from highest year (1) to lowest year (15)

INSERT INTO switch.hydro_avg_monthly_gen_2004_2018
SELECT generation_plant_id, month, AVG(hydro_min_flow_mw) AS hydro_min_flow_mw, AVG(hydro_avg_flow_mw) AS hydro_avg_flow_mw
FROM hydro_historical_monthly_capacity_factors
WHERE hydro_simple_scenario_id = 21
GROUP BY generation_plant_id, month

UPDATE switch.hydro_avg_monthly_gen_2004_2018
SET notes = 'Monthly avg gen from EIA 2004 to 2018, for ids in hydro_simple_scenario 21'