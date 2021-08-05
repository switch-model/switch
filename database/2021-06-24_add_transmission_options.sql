/*
####################
Add transmission options

Date applied: 2021-06-23
Description:
Adds two rows to table transmission_base_capital_cost_scenario_id
1. A scenario where transmission costs are zero.
2. A scenario where transmission costs are infinity (building not allowed).
#################
*/

INSERT INTO switch.transmission_base_capital_cost (transmission_base_capital_cost_scenario_id,
                                                   trans_capital_cost_per_mw_km, description)
VALUES (3, 'Infinity', 'For scenarios where building transmission is forbidden.');

INSERT INTO switch.transmission_base_capital_cost (transmission_base_capital_cost_scenario_id,
                                                   trans_capital_cost_per_mw_km, description)
VALUES (4, 0, 'For scenarios where transmission is unlimited.');
