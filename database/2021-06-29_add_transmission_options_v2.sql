/*
####################
Add transmission options

Date applied: 2021-06-29
Description:
Adds an extra scenario to the database for a 10x increase in transmission costs.
#################
*/

INSERT INTO switch.transmission_base_capital_cost (transmission_base_capital_cost_scenario_id,
                                                   trans_capital_cost_per_mw_km, description)
VALUES (5, 9600, '10x the costs of scenario #2. Approximates the no TX case.');
