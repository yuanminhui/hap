import importlib


def test_create_tables_if_not_exist(monkeypatch, tmp_path):
    db = importlib.import_module("hap.lib.database")
    # point SQL path to a temp file
    sql = tmp_path / "create.sql"
    sql.write_text("CREATE TABLE x (id int);")
    monkeypatch.setattr(db, "SCRIPT_PATH_CREATE_TABLES", str(sql), raising=False)

    executed = {"ran": False}
    class Cur:
        def execute(self, sql_text):
            executed["ran"] = True
    class Conn:
        def cursor(self):
            return Cur()
        def commit(self):
            pass
    db.create_tables_if_not_exist(Conn())
    assert executed["ran"] is True


def test_get_next_id_from_table():
    db = importlib.import_module("hap.lib.database")
    class C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, *a, **k):
            self._row = (3,)
        def fetchone(self):
            return self._row
    class Conn:
        def cursor(self):
            return C()
    nid = db.get_next_id_from_table(Conn(), "t")
    assert nid == 4