import importlib


def test_connect_and_auto_connect(monkeypatch, tmp_path):
    db = importlib.import_module("hap.lib.database")
    import hap
    cfg = tmp_path / "hap.yaml"
    cfg.write_text("""db:\n  host: h\n  port: 5432\n  user: u\n  password: p\n  dbname: d\n""")
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg))
    # fake psycopg2.connect
    called = {"ok": 0}
    def _connect(**kwargs):
        called["ok"] += 1
        class Conn:
            def cursor(self):
                class C:
                    def execute(self, *a, **k):
                        pass
                return C()
        return Conn()
    import psycopg2
    monkeypatch.setattr(psycopg2, "connect", _connect)
    info = db.get_connection_info()
    c = db.connect(info)
    assert called["ok"] == 1
    c2 = db.auto_connect()
    assert called["ok"] == 2