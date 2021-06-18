/*
####################
Add Improved Storage Module columns

Date applied: 2021-06-11
Description: This script adds the columns daily_self_discharge_rate, discharge_efficiency and
land_use_rate to the generation_plant table. These columns were added as part of the
improvements to the storage module that Martin Staadecker completed when studying long-duration
energy storage. See REAM-lab pull request #42.
#################
*/

ALTER TABLE switch.generation_plant ADD COLUMN daily_self_discharge_rate real;
ALTER TABLE switch.generation_plant ADD COLUMN discharge_efficiency real;
ALTER TABLE switch.generation_plant ADD COLUMN land_use_rate real;