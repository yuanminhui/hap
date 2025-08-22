"""
A module for database.

Classes:
    DatabaseConnectionInfo: A class to hold the database connection information.
"""

import os

import psycopg2

import hap
from hap.lib.config import Config

SCRIPT_NAME_CREATE_TABLES = "create_tables.sql"
SCRIPT_PATH_CREATE_TABLES = os.path.join(
    hap.SOURCE_ROOT, "sql", SCRIPT_NAME_CREATE_TABLES
)


class DatabaseConnectionInfo:
    """
    A class to hold the database connection information.

    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        dbname: str = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.dbname = dbname

    def __str__(self):
        return f"host={self.host} port={self.port} user={self.user} password={self.password} dbname={self.dbname}"

    def __repr__(self):
        return f"DatabaseConnectionInfo(host={self.host}, port={self.port}, user={self.user}, password={self.password}, dbname={self.dbname})"

    def is_complete(self) -> bool:
        return all([self.host, self.port, self.user, self.password, self.dbname])

    def from_env(self):
        self.host = os.environ.get("HAP_DB_HOST")
        self.port = (
            int(os.environ.get("HAP_DB_PORT"))
            if os.environ.get("HAP_DB_PORT")
            else None
        )
        self.user = os.environ.get("HAP_DB_USER")
        self.password = os.environ.get("HAP_DB_PASSWORD")
        self.dbname = os.environ.get("HAP_DB_DBNAME")

    def to_env(self):
        os.environ["HAP_DB_HOST"] = self.host
        os.environ["HAP_DB_PORT"] = self.port
        os.environ["HAP_DB_USER"] = self.user
        os.environ["HAP_DB_PASSWORD"] = self.password
        os.environ["HAP_DB_DBNAME"] = self.dbname

    def from_config(self, config_file: str):
        cfg = Config()
        cfg.load_from_file(config_file)
        self.host = cfg.get_nested_value("db.host")
        self.port = (
            int(cfg.get_nested_value("db.port"))
            if cfg.get_nested_value("db.port")
            else None
        )
        self.user = cfg.get_nested_value("db.user")
        self.password = cfg.get_nested_value("db.password")
        self.dbname = cfg.get_nested_value("db.dbname")

    def to_config(self, config_file: str):
        cfg = Config()
        cfg.load_from_file(config_file)
        cfg.set_nested_value("db.host", self.host)
        cfg.set_nested_value("db.port", self.port)
        cfg.set_nested_value("db.user", self.user)
        cfg.set_nested_value("db.password", self.password)
        cfg.set_nested_value("db.dbname", self.dbname)
        cfg.save_to_file(config_file)

    def from_dict(self, data: dict):
        self.host = data.get("host")
        self.port = int(data.get("port")) if data.get("port") else None
        self.user = data.get("user")
        self.password = data.get("password")
        self.dbname = data.get("dbname")

    def to_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dbname": self.dbname,
        }


def get_connection_info() -> dict:
    """
    Get the database connection information from environment variables
    and configuration file. Environment variables override config values.

    Returns:
        A dictionary with the database connection information.

    Raises:
        FileNotFoundError: If the configuration file is not found.
    """

    # Read from config file first
    cfg = Config()
    try:
        cfg.load_from_file(hap.CONFIG_PATH)
    except FileNotFoundError:
        # Mirror previous behavior: propagate FileNotFoundError to caller
        raise

    conn_info_from_config = {
        "host": cfg.get_nested_value("db.host"),
        "port": int(cfg.get_nested_value("db.port")) if cfg.get_nested_value("db.port") else None,
        "user": cfg.get_nested_value("db.user"),
        "password": cfg.get_nested_value("db.password"),
        "dbname": cfg.get_nested_value("db.dbname"),
    }

    # Overlay with environment variables (use os.getenv to avoid os.environ monkeypatch issues)
    conn_info_from_env = {
        "host": os.getenv("HAP_DB_HOST") or None,
        "port": int(os.getenv("HAP_DB_PORT")) if os.getenv("HAP_DB_PORT") else None,
        "user": os.getenv("HAP_DB_USER") or None,
        "password": os.getenv("HAP_DB_PASSWORD") or None,
        "dbname": os.getenv("HAP_DB_DBNAME") or None,
    }

    result = conn_info_from_config
    for k, v in conn_info_from_env.items():
        if v is not None:
            result[k] = v
    return result


# def test_connection(connection_info: dict) -> dict:
#     """
#     Test the connection to PostgreSQL by psycopg2.

#     Args:
#         connection_info: A dictionary with the database connection information.

#     Returns:
#         dict: A dictionary with the database connection information.

#     Raises:
#         DataIncompleteError: If the database connection information is incomplete.
#         psycopg2.OperationalError: If the connection to the database fails.
#     """

#     db_conn_info = DatabaseConnectionInfo()
#     db_conn_info.from_dict(connection_info)
#     if not db_conn_info.is_complete():
#         raise DataIncompleteError("Database connection information is incomplete.")
#     connection_info = db_conn_info.to_dict()
#     with psycopg2.connect(**connection_info):
#         pass
#     return connection_info


def connect(connection_info: dict) -> psycopg2.extensions.connection:
    """
    Connect to the database.

    Args:
        connection_info: A dictionary with the database connection information.

    Returns:
        psycopg2.extensions.connection: A psycopg2 connection object.

    Raises:
        psycopg2.OperationalError: If the connection to the database fails.
    """

    return psycopg2.connect(**connection_info)


def auto_connect() -> psycopg2.extensions.connection:
    """
    Connect to the database using the connection information from the environment
    variables and configuration file.

    Returns:
        psycopg2.extensions.connection: A psycopg2 connection object.

    Raises:
        psycopg2.OperationalError: If the connection to the database fails.
    """

    connection_info = get_connection_info()
    return connect(connection_info)


def create_tables_if_not_exist(connection: psycopg2.extensions.connection):
    """
    Create the tables for HAP into the database if they do not exist.

    Args:
        connection: A psycopg2 connection object.

    Raises:
        psycopg2.Error: If an error occurs when executing the SQL statements.
        OSError: If the SQL file with the table creation statements is not found.
    """

    cursor = connection.cursor()
    try:
        with open(SCRIPT_PATH_CREATE_TABLES, "r") as file:
            sql_text = file.read()
        cursor.execute(sql_text)
        connection.commit()
    except psycopg2.Error:
        connection.rollback()
        raise


def get_next_id_from_table(
    connection: psycopg2.extensions.connection, table_name: str
) -> int:
    """
    Get the next ID from a table.

    Args:
        connection: A psycopg2 connection object.
        table_name: The name of the table.

    Returns:
        int: The next ID from the table.

    Raises:
        psycopg2.Error: If an error occurs when executing the SQL statements.
    """

    with connection.cursor() as cursor:
        cursor.execute(f"SELECT MAX(id) FROM {table_name}")
        row = cursor.fetchone()
        max_id = row[0] if row else None
        return (max_id + 1) if max_id else 1


# # DEBUG
# if __name__ == "__main__":
#     os.environ["HAP_DB_HOST"] = "env_host"
#     os.environ["HAP_DB_PORT"] = "1234"
#     cfg = Config({})
#     cfg.set_nested_value("db.host", "cfg_host")
#     cfg.set_nested_value("db.port", "4321")
#     cfg.set_nested_value("db.user", "cfg_user")
#     cfg.set_nested_value("db.password", "cfg_password")
#     cfg.set_nested_value("db.dbname", "cfg_dbname")
#     cfg.save_to_file(hap.CONFIG_PATH)
#     get_connection_info()
#     os.environ.pop("HAP_DB_HOST")
#     os.environ.pop("HAP_DB_PORT")
#     cfg = Config(
#         {
#             "db": {
#                 "host": "localhost",
#                 "port": "5432",
#                 "user": "hap",
#                 "password": "hap",
#                 "dbname": "hap",
#             }
#         }
#     )
#     cfg.save_to_file(hap.CONFIG_PATH)
