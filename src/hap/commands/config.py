"""
This module contains the CLI command to get and set configurations of the program.

Example:
    $ hap config --get "key1.key2"
    $ hap config --set "key1.key2" "value"
    $ hap config --unset "key1.key2"
    $ hap config --list
"""

from pathlib import Path

import click

import hap
from hap.lib.config import Config


@click.command(
    "config",
    context_settings=hap.CTX_SETTINGS,
    short_help="Get and set configurations",
)
@click.option("--get", "key_to_get", help="Get a configuration value")
@click.option("--set", "key_value", nargs=2, help="Set a configuration value")
@click.option("--unset", "key_to_unset", help="Unset a configuration value")
@click.option("--list", "list_all", is_flag=True, help="List all configuration values")
def main(key_to_get: str, key_value: list[str], key_to_unset: str, list_all: bool):
    """
    Get and set configurations of the program.
    """

    actions_specified_count = sum(
        map(bool, [key_to_get, key_value, key_to_unset, list_all])
    )
    if actions_specified_count != 1:
        raise click.UsageError(
            "Exactly one action should be specified, use `-h` or `--help` to see available options."
        )

    cfg = Config()
    try:
        cfg.load_from_file(hap.CONFIG_PATH)
    except FileNotFoundError:
        cfg_path = Path(hap.CONFIG_PATH)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.touch()
        cfg.data = {}
        cfg.save_to_file(hap.CONFIG_PATH)

    if key_to_get:
        value = cfg.get_nested_value(key_to_get)
        if value is not None:
            click.echo(value)
    elif key_value:
        key_to_set, value_to_set = key_value
        cfg.set_nested_value(key_to_set, value_to_set)
        cfg.save_to_file(hap.CONFIG_PATH)
    elif key_to_unset:
        cfg.unset_nested_value(key_to_unset)
        cfg.save_to_file(hap.CONFIG_PATH)
    elif list_all:
        cfg.print_items()


if __name__ == "__main__":
    main()
