import os

import psycopg2 as pg
import yaml


def load_config():
    """Read the config.yaml configuration file"""
    if not os.path.isfile("config.yaml"):
        raise Exception(
            "config.yaml does not exist. Try running 'switch new scenario' to auto-create it."
        )
    with open("config.yaml") as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def load_dotenv():
    try:
        # Try to load environment variables from .env file using dotenv package.
        # If package is not installed, nothing happens.
        from dotenv import load_dotenv

        load_dotenv()
    except ModuleNotFoundError:
        pass


def connect(schema="switch", connection_env_var="DB_URL"):
    """Connects to the Postgres DB

    This function uses the environment variables to get the URL to connect to the DB. Both
    password and user should be passed directly on the URL for safety purposes.

    Parameters
    ----------
    schema: str Schema of the DB to look for tables. Default is switch
    connection_env_var: The environment variable to use as the connection string

    Returns
    -------
    conn: Database connection object from psycopg2
    """
    load_dotenv()
    db_url = os.getenv(connection_env_var)
    if db_url is None:
        raise Exception(
            f"Please set the environment variable '{connection_env_var}' to the database URL."
            "The format is normally: postgresql://<user>:<password>@<host>:5432/<database>"
        )

    conn = pg.connect(
        db_url,
        options=f"-c search_path={schema}",
    )

    if conn is None:
        raise SystemExit(
            "Failed to connect to PostgreSQL database."
            "Ensure that the database url is correct, format should normally be:"
            "postgresql://<user>:<password>@<host>:5432/<database>"
        )

    # TODO: Send this to the logger
    print("Connection established to PostgreSQL database.")
    return conn
