from pathlib import Path
import importlib


def test_db_conn_info_str_repr():
    db = importlib.import_module("hap.lib.database")
    info = db.DatabaseConnectionInfo(host="h", port=1, user="u", password="p", dbname="d")
    s = str(info)
    r = repr(info)
    assert "host=h" in s
    assert "DatabaseConnectionInfo(" in r


def test_get_connection_info_from_config(tmp_path, monkeypatch):
    db = importlib.import_module("hap.lib.database")
    # point CONFIG_PATH to a temp file with minimal YAML
    import hap
    cfg = tmp_path / "hap.yaml"
    cfg.write_text("""db:\n  host: h\n  port: 5432\n  user: u\n  password: p\n  dbname: d\n""")
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg))
    info = db.get_connection_info()
    assert info["host"] == "h" and info["port"] == 5432 and info["user"] == "u" and info["dbname"] == "d"