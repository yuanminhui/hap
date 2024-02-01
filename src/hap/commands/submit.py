import os
import pathlib
from typing import Any
import psycopg2

import click
import yaml

import hap


def offer_id(dbstr: str, name: str) -> int:
    """Offer an ID for a hierarchical pangenome."""

    pass


def update_id(dbstr: str, name: str, id: int):
    """Update the ID of a hierarchical pangenome."""

    pass


def to_db(dbstr: str, name: str, id: int):
    """Submit a hierarchical pangenome to database."""

    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="test_db",
        user="username",
        password="password",
    )
    cursor = conn.cursor()

    # Create table
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(50),
        age INT
    );"""
    )

    # Insert data
    cursor.execute("INSERT INTO users (name, age) VALUES (%s, %s)", ("Alice", 30))

    # Query data
    cursor.execute("SELECT * FROM users;")
    rows = cursor.fetchall()
    for row in rows:
        print(row)

    # Delete data
    cursor.execute("DELETE FROM users WHERE age = %s", (30,))

    # Commit and close
    conn.commit()
    cursor.close()
    conn.close()


def get_db_conn_info_from_config(conf_path: str) -> dict[str, Any]:
    """Get DB connection information from config file."""

    try:
        with open(conf_path, "r") as f:
            conf = yaml.safe_load(f)
            conf_db_conn_info = conf["db"]
            db_conn_info = {
                "host": conf_db_conn_info["host"],
                "port": conf_db_conn_info["port"],
                "user": conf_db_conn_info["user"],
                "password": conf_db_conn_info["password"],
                "dbname": conf_db_conn_info["dbname"],
            }
            return db_conn_info
    except FileNotFoundError:
        raise click.UsageError(f"Config file {conf_path} not found.")


def get_db_conn_info_from_env() -> dict[str, Any]:
    """Get DB connection information from environment variables."""

    db_conn_info = {
        "host": os.environ.get("HAP_DB_HOST"),
        "port": os.environ.get("HAP_DB_PORT"),
        "user": os.environ.get("HAP_DB_USER"),
        "password": os.environ.get("HAP_DB_PASSWD"),
        "dbname": os.environ.get("HAP_DB_NAME"),
    }
    return db_conn_info


def save_db_conn_info_to_config(conf_path: str, db_conn_info: dict[str, Any]):
    """Save DB connection information to config file."""

    try:
        with open(conf_path, "r") as f:
            conf = yaml.safe_load(f)
            conf["db"] = db_conn_info
        with open(conf_path, "w") as f:
            yaml.safe_dump(conf, f)
    except FileNotFoundError:
        raise click.UsageError(f"Config file {conf_path} not found.")


def save_db_conn_info_to_env(db_conn_info: dict[str, Any]):
    """Save DB connection information to environment variables."""

    os.environ["HAP_DB_HOST"] = db_conn_info["host"]
    os.environ["HAP_DB_PORT"] = db_conn_info["port"]
    os.environ["HAP_DB_USER"] = db_conn_info["user"]
    os.environ["HAP_DB_PASSWD"] = db_conn_info["password"]
    os.environ["HAP_DB_NAME"] = db_conn_info["dbname"]


@click.command(
    "submit",
    short_help="Submit a Hierarchical Pangenome to database",
)
@click.argument(
    "dir",
    type=click.Path(
        exists=True, file_okay=False, readable=True, path_type=pathlib.Path
    ),
)
@click.option(
    "-n", "--name", prompt="Name of the HAP", help="Name of the Hierarchical Pangenome"
)
@click.option(
    "-c",
    "--creater",
    prompt="Creater of the HAP",
    help="Creater of the Hierarchical Pangenome",
)
@click.option(
    "-d",
    "--description",
    prompt="Description of the HAP",
    help="Description of the Hierarchical Pangenome",
)
@click.option(
    "-o",
    "--db-host",
    envvar="HAP_DB_HOST",
    # prompt="Host of the DB",
    help="Host name or IP address of the DB server",
)
@click.option(
    "-p",
    "--db-port",
    envvar="HAP_DB_PORT",
    # prompt="Port of the DB",
    # type=int,
    # default=5432,
    # show_default=True,
    help="Port of the DB server",
)
@click.option(
    "-u",
    "--db-user",
    envvar="HAP_DB_USER",
    # prompt="User of the DB",
    help="User name to connect to the DB server",
)
@click.option(
    "-w",
    "--db-password",
    envvar="HAP_DB_PASSWD",
    # prompt="Password of the DB",
    # hide_input=True,
    help="Password to connect to the DB server",
)
@click.option(
    "-n",
    "--db-name",
    envvar="HAP_DB_NAME",
    # prompt="Name of the DB",
    # default="hap",
    # show_default=True,
    help="Database name to connect to the DB server",
)
@click.option(
    "-f",
    "--from-config",
    is_flag=True,
    help="Use DB connection information from config file",
)
@click.option(
    "-e",
    "--from-env",
    is_flag=True,
    help="Use DB connection information from environment variable",
)
@click.option(
    "-j",
    "--to-config",
    is_flag=True,
    help="Save DB connection information to config file",
)
@click.option(
    "-i",
    "--to-env",
    is_flag=True,
    help="Save DB connection information to environment variable",
)
def main(
    dir: pathlib.Path,
    name: str,
    creater: str,
    description: str,
    db_host: str,
    db_port: int,
    db_user: str,
    db_password: str,
    db_name: str,
    from_config: bool,
    from_env: bool,
    to_config: bool,
    to_env: bool,
):
    """
    Submit a Hierarchical Pangenome to designated database.

    DIR: Directory of the Hierarchical Pangenome. Should contain a `.hapinfo` and several `.st` `.rt` files.
    """

    # conflict options
    if from_config and to_config:
        raise click.UsageError(
            "Cannot use flag --from-config and --to-config at the same time."
        )
    if from_env and to_env:
        raise click.UsageError(
            "Cannot use flag --from-env and --to-env at the same time."
        )
    if from_config and from_env:
        raise click.UsageError(
            "Cannot use flag --from-config and --from-env at the same time."
        )

    # Get DB connection information
    if from_config:
        db_conn_info = get_db_conn_info_from_config(hap.confpath)
        if not all(db_conn_info.values()):
            raise click.UsageError(
                "Incomplete DB connection information from config file."
            )  # strict check if specified `--from-config`
    elif from_env:
        db_conn_info = get_db_conn_info_from_env()
        if not all(db_conn_info.values()):
            raise click.UsageError(
                "Incomplete DB connection information from environment variables."
            )  # strict check if specified `--from-env`
    dbci_from_params = {
        "host": db_host,
        "port": db_port,
        "user": db_user,
        "password": db_password,
        "dbname": db_name,
    }
    # provided db-params will overwrite items from config or env
    exist_dbci_from_params = {k: v for k, v in dbci_from_params.items() if v}
    if db_conn_info:
        db_conn_info.update(exist_dbci_from_params)
    else:
        # get default items for prompt, in order of: env > config > default
        dbci_from_env = {k: v for k, v in get_db_conn_info_from_env().items() if v}
        dbci_from_conf = {
            k: v for k, v in get_db_conn_info_from_config(hap.confpath).items() if v
        }
        dbci_org_default = {
            "host": "localhost",
            "port": 5432,
            "user": "hap",
            "dbname": "hap",
        }
        dbci_default = dbci_org_default.copy()
        dbci_default.update(dbci_from_conf)
        dbci_default.update(dbci_from_env)
        for k, v in dbci_from_params.items():
            if not v:
                value = click.prompt(
                    f"{'Name' if k == 'dbname' else k.capitalize()} of the DB",
                    default=dbci_default[k],
                    show_default=True,
                    hide_input=k == "password",
                    type=int if k == "port" else str,
                )
                dbci_from_params[k] = value
        db_conn_info = dbci_from_params

    # save DB connection information
    if to_config:
        save_db_conn_info_to_config(hap.confpath, db_conn_info)
    if to_env:
        save_db_conn_info_to_env(db_conn_info)


if __name__ == "__main__":
    main()
