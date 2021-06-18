-- ####################
-- get_tables_and_row_count
--
-- Date created: 2021_06_11
-- Description: The script returns a csv with three columns: schema, table_name and row_count.
-- The csv contains one row for each table in the database.
-- #################

-- SQL Code goes here
COPY (
    SELECT nspname as schema, relname as table_name, reltuples as row_count
    FROM pg_class as pc
             INNER JOIN
         pg_namespace as pn ON (pn.oid = pc.relnamespace)
    WHERE pc.relkind = 'r'
    order by table_name
    ) TO '/tmp/db_tables.csv' (FORMAT CSV);
