""" Create scenario inputs for SWITCH WECC

Copyright 2017 The Switch Authors. All rights reserved.
"""

# Standard packages
import os
import sys

# Thirdy-party packages
import pandas as pd
import psycopg2 as pg


def connect():
    # TODO: this should be an enviromental variable
    db_url = "postgresql://pesap@localhost:5432/wecc"
    conn = pg.connect(db_url)
    return conn


if __name__ == "__main__":
    conn = connect()
    # Main function that execute the query or insert based on the arguments passed
    with conn:
        with conn.cursor() as cur:
            query = "select * from switch.variable_capacity_factors limit 10;"
            cur.execute(query)
            dat = pd.read_sql_query(query, conn)
            breakpoint()
            print(cur.fetchall())

    conn.close()
    pass
    # args = parser.parse_args()
    # args.func(args)
