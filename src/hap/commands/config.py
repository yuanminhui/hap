"""
This module contains the CLI command to get and set configurations of the program.

Examples:
    $ hap config get --key "key1.key2"
    $ hap config set --key "key1.key2" --value "value"
    $ hap config unset --key "key1.key2"
    $ hap config list
"""

from pathlib import Path

import click

import hap
from hap.lib.config import Config


@click.group(
    "config",
    context_settings=hap.CTX_SETTINGS,
    short_help="Get and set configurations",
)
def main():
    """Configuration management commands."""


def _ensure_config_file(cfg: Config) -> None:
    try:
        cfg.load_from_file(hap.CONFIG_PATH)
    except FileNotFoundError:
        cfg_path = Path(hap.CONFIG_PATH)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.touch()
        cfg.data = {}
        cfg.save_to_file(hap.CONFIG_PATH)


@main.command("get")
@click.option("--key", "key_to_get", required=True, help="Get a configuration value")
def get(key_to_get: str):
    cfg = Config()
    _ensure_config_file(cfg)
    value = cfg.get_nested_value(key_to_get)
    if value is not None:
        click.echo(value)


@main.command("set")
@click.option("--key", required=True, help="Configuration key to set")
@click.option("--value", required=True, help="Value to set")
def set(key: str, value: str):
    cfg = Config()
    _ensure_config_file(cfg)
    cfg.set_nested_value(key, value)
    cfg.save_to_file(hap.CONFIG_PATH)


@main.command("unset")
@click.option("--key", "key_to_unset", required=True, help="Configuration key to unset")
def unset(key_to_unset: str):
    cfg = Config()
    _ensure_config_file(cfg)
    cfg.unset_nested_value(key_to_unset)
    cfg.save_to_file(hap.CONFIG_PATH)


@main.command("list")
def list():
    cfg = Config()
    _ensure_config_file(cfg)
    cfg.print_items()


if __name__ == "__main__":
    main()
