"""
Unit tests for hap.lib.config — Config class.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from hap.lib.config import Config
from hap.lib.error import UnsupportedError


class TestConfigInit:
    def test_default_data_is_none(self):
        cfg = Config()
        assert cfg.data is None

    def test_init_with_dict(self):
        cfg = Config({"key": "value"})
        assert cfg.data == {"key": "value"}


class TestConfigLoadSave:
    def test_load_yaml(self, tmp_path):
        p = tmp_path / "cfg.yaml"
        p.write_text("db:\n  host: localhost\n  port: 5432\n")
        cfg = Config()
        cfg.load_from_file(str(p))
        assert cfg.data["db"]["host"] == "localhost"

    def test_load_json(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"db": {"host": "jsonhost"}}))
        cfg = Config()
        cfg.load_from_file(str(p), format="json")
        assert cfg.data["db"]["host"] == "jsonhost"

    def test_load_unsupported_format(self, tmp_path):
        p = tmp_path / "cfg.toml"
        p.write_text("[db]\nhost = 'x'\n")
        cfg = Config()
        with pytest.raises(UnsupportedError):
            cfg.load_from_file(str(p), format="toml")

    def test_load_missing_file(self):
        cfg = Config()
        with pytest.raises(FileNotFoundError):
            cfg.load_from_file("/nonexistent/path/config.yaml")

    def test_save_yaml(self, tmp_path):
        p = tmp_path / "out.yaml"
        cfg = Config({"db": {"host": "saved"}})
        cfg.save_to_file(str(p))
        loaded = yaml.safe_load(p.read_text())
        assert loaded["db"]["host"] == "saved"

    def test_save_json(self, tmp_path):
        p = tmp_path / "out.json"
        cfg = Config({"key": 42})
        cfg.save_to_file(str(p), format="json")
        loaded = json.loads(p.read_text())
        assert loaded["key"] == 42

    def test_save_unsupported_format(self, tmp_path):
        p = tmp_path / "out.toml"
        cfg = Config({})
        with pytest.raises(UnsupportedError):
            cfg.save_to_file(str(p), format="toml")

    def test_roundtrip_yaml(self, tmp_path):
        p = tmp_path / "rtrip.yaml"
        data = {"a": {"b": {"c": 99}}, "x": [1, 2, 3]}
        cfg = Config(data)
        cfg.save_to_file(str(p))
        cfg2 = Config()
        cfg2.load_from_file(str(p))
        assert cfg2.data == data


class TestConfigGetSet:
    def setup_method(self):
        self.cfg = Config({
            "db": {
                "host": "localhost",
                "port": 5432,
                "nested": {"deep": "value"},
            },
            "top_key": "top_value",
        })

    def test_get_top_level(self):
        assert self.cfg.get_nested_value("top_key") == "top_value"

    def test_get_nested(self):
        assert self.cfg.get_nested_value("db.host") == "localhost"

    def test_get_deeply_nested(self):
        assert self.cfg.get_nested_value("db.nested.deep") == "value"

    def test_get_missing_key(self):
        assert self.cfg.get_nested_value("db.missing") is None

    def test_get_missing_top(self):
        assert self.cfg.get_nested_value("nonexistent") is None

    def test_set_existing_key(self):
        self.cfg.set_nested_value("db.host", "newhost")
        assert self.cfg.get_nested_value("db.host") == "newhost"

    def test_set_new_nested_key(self):
        self.cfg.set_nested_value("db.username", "admin")
        assert self.cfg.get_nested_value("db.username") == "admin"

    def test_set_creates_intermediate_dicts(self):
        self.cfg.set_nested_value("new.a.b.c", 42)
        assert self.cfg.get_nested_value("new.a.b.c") == 42

    def test_unset_existing_key(self):
        self.cfg.unset_nested_value("db.host")
        assert self.cfg.get_nested_value("db.host") is None

    def test_unset_nonexistent_key_does_not_raise(self):
        self.cfg.unset_nested_value("db.nonexistent")  # should not raise

    def test_unset_missing_parent(self):
        self.cfg.unset_nested_value("totally.missing.key")  # should not raise

    def test_set_raises_on_non_dict_path(self):
        self.cfg.set_nested_value("top_key", "scalar")
        with pytest.raises(TypeError):
            self.cfg.set_nested_value("top_key.subkey", "value")


class TestConfigPrintItems:
    def test_print_items_does_not_raise(self, capsys):
        cfg = Config({"a": 1, "b": {"c": 2}})
        cfg.print_items()
        captured = capsys.readouterr()
        assert "a" in captured.out or "1" in captured.out
