"""
A module for configuration object.

Classes:
    Config: A class to manipulate the configuration data object.
"""

from typing import Any
import yaml
import json

from hap.lib.error import UnsupportedError


class Config:
    """
    A class to manipulate the configuration data object.

    Attributes:
        data (Any): The configuration data.
    """

    def __init__(self, config: Any = None):
        self.data = config

    def load_from_file(self, filepath: str, format: str = "yaml") -> Any:
        """
        Load configurations from config file.

        Args:
            filepath (str): Path to the config file.
            format (str): Format of the config file, default is "yaml".

        Returns:
            Any: Configurations loaded from the file.

        Raises:
            FileNotFoundError: If the config file is not found.
        """
        try:
            with open(filepath, "r") as file:
                if format == "yaml":
                    config = yaml.safe_load(file)
                elif format == "json":
                    config = json.load(file)
                else:
                    raise UnsupportedError(f"Unsupported config file format: {format}")
                self.data = config
                return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file {filepath} not found.")

    def save_to_file(self, filepath: str, format: str = "yaml"):
        """
        Save configurations to config file.

        Args:
            filepath (str): Path to the config file.
            format (str): Format of the config file, default is "yaml".
        """
        with open(filepath, "w") as file:
            if format == "yaml":
                yaml.safe_dump(self.data, file, indent=4)
            elif format == "json":
                json.dump(self.data, file, indent=4)
            else:
                raise UnsupportedError(f"Unsupported config file format: {format}")

    def get_nested_value(self, key: str) -> Any:
        """
        Get a nested value from configuration.

        Args:
            key (str): Nested key string delimited by `.`.

        Returns:
            Any: The value of the nested key, or `None` if not found.
        """
        keys = key.split(".")
        nested_config = self.data
        for k in keys:
            if isinstance(nested_config, dict) and k in nested_config:
                nested_config = nested_config[k]
            else:
                return None
        return nested_config

    def set_nested_value(self, key: str, value: Any):
        """
        Set a nested value in configuration.

        Args:
            key (str): Nested key string delimited by `.`.
            value (Any): Value to set.
        """
        keys = key.split(".")
        nested_config = self.data
        for i, k in enumerate(keys):
            if not isinstance(nested_config, dict):
                raise TypeError(
                    f"Nested config {'.'.join(keys[:i])} is not a dictionary."
                )
            if i == len(keys) - 1:
                break
            if k not in nested_config:
                nested_config[k] = {}
            nested_config = nested_config[k]
        nested_config[keys[-1]] = value

    def unset_nested_value(self, key: str):
        """
        Unset a nested value in configuration.

        Args:
            key (str): Nested key string delimited by `.`.
        """
        keys = key.split(".")
        nested_config = self.data
        for k in keys[:-1]:
            if not isinstance(nested_config, dict) or k not in nested_config:
                return
            nested_config = nested_config[k]
        if isinstance(nested_config, dict) and keys[-1] in nested_config:
            del nested_config[keys[-1]]

    def print_items(self):
        """
        Print all items in the configuration.
        """

        def print_config_items(config, prefix=""):
            if isinstance(config, dict):
                for key, value in config.items():
                    current_key = f"{prefix}.{key}" if prefix else key
                    print_config_items(value, current_key)
            else:
                print(f"{prefix}: {config}" if prefix else config)

        print_config_items(self.data)
