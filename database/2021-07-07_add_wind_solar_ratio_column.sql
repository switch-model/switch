/*
####################
Add wind_to_solar_ratio column

Date applied: 2021-07-07
Description:
Adds a column called wind_to_solar_ratio to the database which is used by
switch_model.policies.wind_to_solar_ratio
#################
*/

ALTER TABLE switch.scenario ADD COLUMN wind_to_solar_ratio real;