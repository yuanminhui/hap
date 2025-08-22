from click.testing import CliRunner

import hap
from hap.__main__ import cli


def test_config_set_get_unset(tmp_path, monkeypatch):
    cfg = tmp_path / "hap.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg))

    # set
    r1 = CliRunner().invoke(cli, ["config", "set", "--key", "db.host", "--value", "localhost"])
    assert r1.exit_code == 0
    # get
    r2 = CliRunner().invoke(cli, ["config", "get", "--key", "db.host"])
    assert r2.exit_code == 0 and "localhost" in r2.output
    # unset
    r3 = CliRunner().invoke(cli, ["config", "unset", "--key", "db.host"])
    assert r3.exit_code == 0
    r4 = CliRunner().invoke(cli, ["config", "get", "--key", "db.host"])
    assert r4.exit_code == 0 and r4.output.strip() == ""


def test_config_list(tmp_path, monkeypatch):
    cfg = tmp_path / "hap.yaml"
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg))
    r = CliRunner().invoke(cli, ["config", "list"])  # empty -> no crash
    assert r.exit_code == 0

