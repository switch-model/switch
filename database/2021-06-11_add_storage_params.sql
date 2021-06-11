-- ####################
-- TITLE
-- Date:
-- Description:
-- ...
-- ...
-- ...
-- #################

-- SQL Code goes here
ALTER TABLE switch.generation_plant ADD COLUMN daily_self_discharge_rate real;
ALTER TABLE switch.generation_plant ADD COLUMN discharge_efficiency real;
ALTER TABLE switch.generation_plant ADD COLUMN land_use_rate real;