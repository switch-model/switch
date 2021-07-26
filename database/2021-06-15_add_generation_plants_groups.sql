/*
####################
Add generation plants groups

Date applied:
Description:
This script adds the option to specify generation plant groups.
The generation groups are specified in the table generation_plant_group.
Plants are assigned to a group by adding them to the many-to-many table generation_plant_group_member.
Groups are assigned to a generation_plant_scenario_id by specifying them in generation_plant_scenario_group_member
#################
*/

CREATE TABLE switch.generation_plant_group
(
    generation_plant_group_id serial                NOT NULL,
    description               text                  NOT NULL,
    name                      character varying(30) NOT NULL,
    PRIMARY KEY (generation_plant_group_id)
);

COMMENT ON TABLE switch.generation_plant_group
    IS 'This table specifies all the generation plant groups. Every group has a set of generation plants (see generation_plant_group_member). Groups can be assigned to a generation_plant_scenario (see generation_plant_scenario_group_member).';

CREATE TABLE switch.generation_plant_group_member
(
    generation_plant_group_id integer,
    generation_plant_id       integer,
    PRIMARY KEY (generation_plant_group_id, generation_plant_id)
);

ALTER TABLE switch.generation_plant_group_member
    ADD CONSTRAINT generation_plant_group_member_group_id_fkey
        FOREIGN KEY (generation_plant_group_id)
            REFERENCES switch.generation_plant_group (generation_plant_group_id);

ALTER TABLE switch.generation_plant_group_member
    ADD CONSTRAINT generation_plant_group_member_generation_plant_id_fkey
        FOREIGN KEY (generation_plant_id)
            REFERENCES switch.generation_plant (generation_plant_id);

COMMENT ON TABLE switch.generation_plant_group_member
    IS 'This table is a many-to-many table that specifies the generation plants that are associated with a generation group.';

CREATE TABLE switch.generation_plant_scenario_group_member
(
    generation_plant_scenario_id integer,
    generation_plant_group_id    integer,
    PRIMARY KEY (generation_plant_scenario_id, generation_plant_group_id)
);

ALTER TABLE switch.generation_plant_scenario_group_member
    ADD CONSTRAINT generation_plant_scenario_group_member_scenario_id_fkey
        FOREIGN KEY (generation_plant_scenario_id)
            REFERENCES switch.generation_plant_scenario (generation_plant_scenario_id);

ALTER TABLE switch.generation_plant_scenario_group_member
    ADD CONSTRAINT generation_plant_scenario_group_member_group_id_fkey
        FOREIGN KEY (generation_plant_group_id)
            REFERENCES switch.generation_plant_group (generation_plant_group_id);

COMMENT ON TABLE switch.generation_plant_scenario_group_member
    IS 'This table is a many-to-many table that specifies which generation plant groups belong to which generation plant scenarios';
