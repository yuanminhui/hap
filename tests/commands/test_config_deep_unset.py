from pathlib import Path
from click.testing import CliRunner
import hap

from hap.__main__ import cli


def test_config_deep_nested_unset(tmp_path, monkeypatch):
    cfg = tmp_path / "hap.yaml"
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg))

    # Set deep nested keys
    r1 = CliRunner().invoke(cli, ["config", "set", "--key", "a.b.c", "--value", "v1"]) 
    assert r1.exit_code == 0
    r2 = CliRunner().invoke(cli, ["config", "get", "--key", "a.b.c"]) 
    assert r2.exit_code == 0 and r2.output.strip() == "v1"

    # Unset deep key
    r3 = CliRunner().invoke(cli, ["config", "unset", "--key", "a.b.c"]) 
    assert r3.exit_code == 0
    r4 = CliRunner().invoke(cli, ["config", "get", "--key", "a.b.c"]) 
    assert r4.exit_code == 0 and r4.output.strip() == ""