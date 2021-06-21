-- Create a new RPS scenario 6 that updates the RPS requirements for the California load zones to be consistent with SB 100: 44% by 2024, 47% by 2025, 50% by 2026, 52% by 2027, 55% for 2028, 27% by 2029, 60% by 2030
-- Text of the SB100 bill is here: https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=201720180SB100

-- create a copy of scenario 1 as scenario 6
INSERT INTO switch.rps_target (rps_scenario_id, load_zone, year, rps_target)

SELECT 6 AS rps_scenario_id, load_zone, year, rps_target
FROM switch.rps_target
WHERE rps_scenario_id = 1;

-- update the percentages of RPS targets just for the CA load zones per the percentages consistent with SB 100: 44% by 2024, 47% by 2025, 50% by 2026, 52% by 2027, 55% for 2028, 27% by 2029, 60% by 2030

-- --testing on backup table first
-- DROP table switch.jsz_backup_rps_target; CREATE TABLE switch.jsz_backup_rps_target (LIKE switch.rps_target INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup_rps_target SELECT * FROM switch.rps_target;

-- -- 44% by 2024
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year = 2024)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.44
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id

-- -- 47% by 2025
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year = 2025)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.47
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id

-- -- 50% by 2026
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year = 2026)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.50
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id

-- -- 52% by 2027
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year = 2027)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.52
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id

-- -- 55% by 2028
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year = 2028)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.55
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id

-- -- 57% by 2029
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year = 2029)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.57
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id

-- -- 60% by 2030 and beyond
-- WITH t AS
-- (SELECT rps_scenario_id, load_zone, year, rps_target
-- FROM jsz_backup_rps_target
-- WHERE rps_scenario_id = 6
-- AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
-- AND year >= 2030)

-- UPDATE switch.jsz_backup_rps_target a
-- SET rps_target = 0.60
-- FROM t
-- WHERE a.year = t.year
-- AND a.load_zone = t.load_zone
-- AND a.rps_scenario_id = t.rps_scenario_id


-- Run queries on real rps_target table

-- 44% by 2024
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year = 2024)

UPDATE switch.rps_target a
SET rps_target = 0.44
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- 47% by 2025
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year = 2025)

UPDATE switch.rps_target a
SET rps_target = 0.47
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- 50% by 2026
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year = 2026)

UPDATE switch.rps_target a
SET rps_target = 0.50
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- 52% by 2027
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year = 2027)

UPDATE switch.rps_target a
SET rps_target = 0.52
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- 55% by 2028
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year = 2028)

UPDATE switch.rps_target a
SET rps_target = 0.55
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- 57% by 2029
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year = 2029)

UPDATE switch.rps_target a
SET rps_target = 0.57
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- 60% by 2030 and beyond
WITH t AS
(SELECT rps_scenario_id, load_zone, year, rps_target
FROM rps_target
WHERE rps_scenario_id = 6
AND load_zone IN ('CA_IID','CA_LADWP','CA_PGE_BAY','CA_PGE_CEN','CA_PGE_N','CA_PGE_S','CA_SCE_CEN','CA_SCE_S','CA_SCE_SE','CA_SCE_VLY','CA_SDGE','CA_SMUD')
AND year >= 2030)

UPDATE switch.rps_target a
SET rps_target = 0.60
FROM t
WHERE a.year = t.year
AND a.load_zone = t.load_zone
AND a.rps_scenario_id = t.rps_scenario_id

-- Make a new scenario 7 that updates all RPS in the SWITCH load zones (including outside of CA) and imports those values from a csv 'rps_scenario_id_7_new.csv'
-- documentation on the percentages for each load zone is here:
-- https://docs.google.com/document/d/1YZwKxv8_WFYBBP5WauEnpXcCGrrn31Jy-kdYEY1xo5o/edit

-- testing:
-- make a new backup table to keep backup copy of RPS target table
--CREATE TABLE switch.jsz_backup2_rps_target (LIKE switch.rps_target INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup2_rps_target SELECT * FROM switch.rps_target;

-- make a second backup table to test
-- CREATE TABLE switch.jsz_backup3_rps_target (LIKE switch.rps_target INCLUDING INDEXES INCLUDING DEFAULTS INCLUDING CONSTRAINTS); INSERT INTO switch.jsz_backup3_rps_target SELECT * FROM switch.rps_target;

--import csv into second backup table:
-- use PGAdmin import wizard, which runs this command:
-- "/Applications/pgAdmin 4.app/Contents/SharedSupport/psql" --command " "\\copy switch.jsz_backup3_rps_target (rps_scenario_id, load_zone, year, rps_target) FROM '/Users/juliaszinai/Dropbox/Linux_work/switch/WECC/Data for SWITCH_WECC_baseline/rps_scenario_id_7_new.csv' DELIMITER ',' CSV HEADER QUOTE '\"' ESCAPE '''';""

-- adding new data to real db table:

-- import csv into rps_target table:
-- use PGAdmin import wizard, which runs this command:
"/Applications/pgAdmin 4.app/Contents/SharedSupport/psql" --command " "\\copy switch.rps_target (rps_scenario_id, load_zone, year, rps_target) FROM '/Users/juliaszinai/Dropbox/Linux_work/switch/WECC/Data for SWITCH_WECC_baseline/rps_scenario_id_7_new.csv' DELIMITER ',' CSV HEADER QUOTE '\"' ESCAPE '''';""
