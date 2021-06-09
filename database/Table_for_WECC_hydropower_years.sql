-- This query creates a table to document the year classification of total WECC hydropower annual generation

CREATE TABLE switch.hydro_year_classification (
hydro_simple_scenario_id int,
year int,
total_WECC_hydro_gen_GWh double precision,
year_rank int,
primary key (hydro_simple_scenario_id, year)
);

-- This query sums all the hydropower generation across the WECC for each year of data in the baseline set of existing generators (scenario 21). Then it ranks the total WECC hydropower generation in descending order from highest year (1) to lowest year (15)

INSERT INTO switch.hydro_year_classification
SELECT 21 AS hydro_simple_scenario_id, year, SUM(hydro_avg_flow_mw * 24 * 30 )/1000 AS total_WECC_hydro_gen_GWh,
	RANK ()
		OVER (
		ORDER BY SUM(hydro_avg_flow_mw * 24 * 30 )/1000 DESC
	) year_rank
FROM hydro_historical_monthly_capacity_factors
WHERE hydro_simple_scenario_id = 21
GROUP BY year

