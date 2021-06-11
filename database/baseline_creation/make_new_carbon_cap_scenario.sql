-- Create a new carbon cap scenario 91 that updates the carbon cap for WECC and CA. The WECC cap is 80% of 1990 emissions by 2045 and subtracting out the cap for CA. The CA cap uses historical 2010 to 2018 actual emissions, and then reaches 0 by 2045 to meet SB100 goals
-- Text of the SB100 bill is here: https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=201720180SB100

-- testing:
-- make a new backup table to keep backup copy of carbon cap table
--CREATE TABLE switch.jsz_backup_carbon_cap (LIKE switch.carbon_cap INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup_carbon_cap SELECT * FROM switch.carbon_cap;

-- make a second backup table to test
--CREATE TABLE switch.jsz_backup2_carbon_cap (LIKE switch.carbon_cap INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup2_carbon_cap SELECT * FROM switch.carbon_cap;

--import csv into second backup table:
-- use PGAdmin import wizard, which runs this command:
-- "/Applications/pgAdmin 4.app/Contents/SharedSupport/psql" --command " "\\copy switch.jsz_backup2_carbon_cap (carbon_cap_scenario_id, carbon_cap_scenario_name, year, carbon_cap_tco2_per_yr, carbon_cost_dollar_per_tco2, carbon_cap_tco2_per_yr_ca) FROM '/Users/juliaszinai/Dropbox/Linux_work/switch/WECC/Data for SWITCH_WECC_baseline/carbon_cap_scenario_91.csv' DELIMITER ',' CSV HEADER QUOTE '\"' NULL 'NULL' ESCAPE '''';""
-- adding new data to real db table:

-- import csv into rps_target table:
-- use PGAdmin import wizard, which runs this command:
"/Applications/pgAdmin 4.app/Contents/SharedSupport/psql" --command " "\\copy switch.carbon_cap (carbon_cap_scenario_id, carbon_cap_scenario_name, year, carbon_cap_tco2_per_yr, carbon_cost_dollar_per_tco2, carbon_cap_tco2_per_yr_ca) FROM '/Users/juliaszinai/Dropbox/Linux_work/switch/WECC/Data for SWITCH_WECC_baseline/carbon_cap_scenario_91.csv' DELIMITER ',' CSV HEADER QUOTE '\"' NULL 'NULL' ESCAPE '''';""
