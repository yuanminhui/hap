import os
import argparse
import functools
import multiprocessing as mp
import psycopg2

from hap.lib import fileutil, gfautil
from hap import hapinfo


_PROG = "submit"


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


def register_command(subparsers: argparse._SubParsersAction, module_help_map: dict):
    psr_submit = subparsers.add_parser(
        _PROG,
        prog=f"{hapinfo.name} {_PROG}",
        description="Submit Hierarchical Pangenomes to designated database.",
        help="submit hierarchical pangenomes to database",
    )
    psr_submit.set_defaults(func=main)
    module_help_map[_PROG] = psr_submit.print_help

    psr_submit.add_argument("db", help="database connection string")

    # I/O options
    grp_io = psr_submit.add_argument_group("I/O options")
    grp_input = grp_io.add_mutually_exclusive_group(required=True)
    grp_input.add_argument("name", nargs="+", help="hierarchical pangenome name")
    grp_input.add_argument(
        "-d",
        "--dir",
        nargs="+",
        help="use directorys as input",
    )

    # # Parameters
    # grp_params = psr_submit.add_argument_group("Parameters")
    # grp_params.add_argument(
    #     "-c",
    #     "--contig",
    #     action="store_true",
    #     help="extract subgraph at contig level (default chromosome)",
    # )


def main(args: argparse.Namespace):
    dbstr = args.db if args.db else os.environ["HAP_DB"]
    # dbstr = os.path.normpath(dbstr)
    # if not os.path.exists(dbstr):
    #     os.mkdir(dbstr)

    # glob files in dirs
    if args.dir:
        pass
    # search recursively in cwd for name-related files
    else:
        pass
