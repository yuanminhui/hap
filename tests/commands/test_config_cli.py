from click.testing import CliRunner

import hap
from hap.__main__ import cli


def test_config_set_get_unset_list(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.yaml"
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg_file))

    r = CliRunner().invoke(cli, ["config", "set", "--key", "db.host", "--value", "localhost"])
    assert r.exit_code == 0

    r = CliRunner().invoke(cli, ["config", "get", "--key", "db.host"])
    assert r.exit_code == 0
    assert r.output.strip() == "localhost"

    r = CliRunner().invoke(cli, ["config", "list"])
    assert r.exit_code == 0
    assert "db.host" in r.output

    r = CliRunner().invoke(cli, ["config", "unset", "--key", "db.host"])
    assert r.exit_code == 0

    r = CliRunner().invoke(cli, ["config", "get", "--key", "db.host"])
    assert r.exit_code == 0
    assert r.output.strip() == ""