# Creating a test database.

This document describes how to create a test database to test changes before running
them on the `wecc` database. There are many ways to do this however we will be creating
a `wecc-test` database. If `wecc-test`
already exists, you may already have a database you can use to test. It may however
be out of sync with the `wecc` database.

We will be using [Liquibase](https://www.liquibase.org/) to make a copy of our database
schema. Liquibase is a tool to manage database version however here we're only using it
to copy over a database.

## Prequisites

1. Install [Liquibase](https://www.liquibase.org/download).

2. Ensure you can access the `wecc` database.

3. Download the [PostgreSQL JDBC driver](https://jdbc.postgresql.org/download.html).

## Creating the test database

1. Create a database called `wecc-test` (e.g. using PGAdmin).

2. Create a schema called `switch` in the `wecc-test` database.

3. On your computer where you've installed liquibase create a folder where you'll work out of.

4. Create a file called `liquibase.properties` with the following content.

```
changeLogFile:dbchangelog.sql
url:  jdbc:postgresql://localhost:5432/wecc
username:  postgres  
password:  password
classpath:  postgresql-42.2.21.jar
defaultSchemaName: switch
```

`classpath` should point to the driver you downloaded. Replace username and password
with your database username and password. Ensure that the database is running and
accessible at the provided `url`.

5. Run `liquibase generateChangeLog`. This will create `dbchangelog.sql` containing all
the SQL commands needed to recreate the database on `wecc-test`.
   
6. Modify `liquibase.properties` to point to the wecc-test database (change the url to `wecc-test`).

7. Run `liquibase update` to run the SQL changes on the `wecc-test` database. This might take a long time to run.

8. Delete the `liquibase.properties` file so that your password is no longer stored
in plain text.
   

Note: Liquibase will also create a `databasechangelog` and `databasechangeloglock` table which can be ignored.