/*
####################
Add load zone: ALL

Date applied:
Description: This script adds a load_zone called ALL. The all load_zone can be used
to specify that a plant should belong to all load zones. get_inputs.py will handle copying the plant
to all the load zones.
#################
*/

INSERT INTO switch.load_zone (load_zone_id, name, description)
VALUES (
        51,
        '_ALL_ZONES',
        'This zone can only be used to specify that a generation plant should be copied to all the other zones.' ||
        'This zone will be filtered out during get_inputs and should never be read by SWITCH.'
        );