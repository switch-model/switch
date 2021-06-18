# The REAM database

This document gives details about the REAM database. It covers: 

- An overview
  
- How to connect

- The process to make changes

## Overview

As described in [`docs/Overview.md`](/docs/Overiew.md), the database is where
all our data is stored. When we wish to run a scenario in Switch, we run `switch get_inputs`
to retrieve the necessary data from the database.

There are a few useful tools and techniques to understand what each table in the databse does.
First, [PGAdmin](https://www.pgadmin.org/) and [DBVisualizer](https://www.dbvis.com/) are two great
tools that allow viewing a database. I recommending installing both as they each have
their strong points. DBVisualizer can also create a graph of all the relationships between
tables.

Further, it is often useful to read the comments on tables (PGAdmin: right-click table -> Properties)
as they sometimes give details on the tables role. Finally, if the table is used in [`get_inputs.py`](/switch_model/wecc/get_inputs.py)
one can discover what it does by looking at how get_inputs.py uses the table to generate the SWITCH inputs.

## Connecting to the database

First you'll need access to the REAM server. Then you'll need an account in the database.
For both of these, ask Paty for access. Once you have access you can connect by creating
an SSH tunnel. An SSH tunnel binds the database port to your computer port. The following
command creates an SSH tunnel to your 5432 port.

`ssh -L 5432:localhost:5432 -N -f <user>@<server_url>`

After running this command, tools like PGAdmin and DBVisualizer can access the database
at `localhost` port 5432.

Of course, you can always ssh directly into the server and access the database from the SSH terminal.
The command to enter PostgreSQL while SSH'd into the server is `psql wecc`.

## Making changes to the database

Whether it's adding data to the database or changing its schema, it's important
to proceed carefully when making changes to the database. Always make sure to
**test and keep track of your changes**.

Here are the steps to make a change.

1. In the `\database` folder, make a copy of `TEMPLATE.sql` and name it according
to the convention `YYYY-MM-DD_<script_name>`.
   
2. Fill out the title, date and description fields in the `.sql` file and then add your SQL commands.

3. Run your script on the `wecc-test` database to make sure it works properly. If the
`wecc-test` database doesn't exist or is out of sync you might need to create it 
   (see [`Create a Test Database.md`](/database/utils/Create%20a%20Test%20Database.md)).
   
4. Once you are sure your changes work as expected run them on the `wecc` database.

5. Open a pull request to add your script to the repository (see [`docs/Contribute.md`](Contribute.md))
so we can keep track of the changes that have been made.

### Bigger changes

Sometimes, it isn't feasible to have your entire change as a single SQL script.
One way to make bigger changes is to use a Python script. Use the same process
as for the SQL scripts. That is save your Python scripts in the `/database` folder.

When adding large datasets to the database, you won't be able to store
the initial data with your script in this Git repo. Do however indicate
where that initial data can be found.

