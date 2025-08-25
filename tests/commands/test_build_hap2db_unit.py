import types


def _rt_st_meta(pd_mod):
    # Minimal tree: root region r0 with segment s1 and child region r1
    rt = pd_mod.DataFrame([
        {"id": "r0", "semantic_id": "CON-1", "level_range": [0, 0], "coordinate": [0, 10], "is_default": True, "length": 10, "is_variant": False, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": pd_mod.NA, "segments": ["s1"], "sources": ["h1"], "min_length": 10, "before": None, "after": None},
        {"id": "r1", "semantic_id": "CON-2", "level_range": [1, 1], "coordinate": [0, 10], "is_default": True, "length": 10, "is_variant": False, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": "s1", "segments": [], "sources": ["h1"], "min_length": 10, "before": None, "after": None},
    ])
    st = pd_mod.DataFrame([
        {"id": "s1", "original_id": None, "semantic_id": "CON-1", "level_range": [0, 0], "coordinate": [0, 10], "rank": 0, "length": 10, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": ["r1"], "sources": ["h1"]},
    ])
    meta = {"sources": ["h1"], "name": "sub", "max_level": 1, "total_length": 10, "total_variants": 0}
    return rt, st, meta


def test_hap2db_dump(monkeypatch, tmp_path):
    import importlib
    import pandas as pd

    build = importlib.import_module("hap.commands.build")

    # Make get_next_id_from_table deterministic
    monkeypatch.setattr("hap.lib.database.get_next_id_from_table", lambda conn, table: 100 if table == "region" else 200)

    # Fake connection and cursor with minimal behaviors
    class _Cur:
        def __init__(self):
            self._fetch = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            sql_up = sql.upper()
            # Return None for selects to trigger inserts
            if sql_up.startswith("SELECT ID FROM CLADE"):
                self._fetch = None
            elif sql_up.startswith("INSERT INTO CLADE"):
                self._fetch = (11,)
            elif sql_up.startswith("INSERT INTO PANGENOME"):
                self._fetch = (21,)
            elif sql_up.startswith("INSERT INTO SUBGRAPH ("):
                self._fetch = (31,)
            elif sql_up.startswith("SELECT ID FROM SOURCE"):
                self._fetch = None
            elif sql_up.startswith("INSERT INTO SOURCE"):
                self._fetch = (41,)
            else:
                self._fetch = None

        def fetchone(self):
            v = self._fetch
            self._fetch = None
            return v

        def fetchall(self):
            return []

        def copy_from(self, f, table, sep="\t", null="", columns=None):
            # Read all to ensure file exists
            _ = f.read()

        def executemany(self, *a, **k):
            return None

    class _Conn:
        def __init__(self):
            self.autocommit = True

        def cursor(self):
            return _Cur()

        def commit(self):
            pass

        def rollback(self):
            pass

    conn = _Conn()

    rt, st, meta = _rt_st_meta(pd)
    hap_info = {"name": "n", "clade": "c", "description": "d", "creater": "u", "builder": ""}

    # Ensure tmp file creation goes into tmp_path
    from hap.lib import fileutil
    def _create_tmp_files(n):
        files = []
        for i in range(n):
            p = tmp_path / f"t_{i}.tsv"
            p.write_text("")
            files.append(str(p))
        return tuple(files)
    monkeypatch.setattr(fileutil, "create_tmp_files", _create_tmp_files)

    build.hap2db(hap_info, [(rt, st, meta, None)], conn)

    # Source IDs populated
    assert isinstance(hap_info["source_ids"], list) and len(hap_info["source_ids"]) == 1

