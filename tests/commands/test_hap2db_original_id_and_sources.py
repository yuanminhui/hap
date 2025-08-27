def test_hap2db_with_original_id_and_sources(monkeypatch, tmp_path):
    import importlib
    import pandas as pd

    build = importlib.import_module("hap.commands.build")

    # Regions and segments with original_id present and sources
    rt = pd.DataFrame([
        {"id": "r0", "semantic_id": "CON-1", "level_range": [0, 0], "coordinate": [0, 10], "is_default": True, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": pd.NA, "segments": ["s1"],
         "length": 10, "is_variant": False, "sources": ["h1", "h2"], "min_length": 10, "before": None, "after": None}
    ])
    st = pd.DataFrame([
        {"id": "s1", "original_id": "orig1", "semantic_id": "CON-1", "level_range": [0, 0], "coordinate": [0, 10], "rank": 0, "length": 10, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": [], "sources": ["h1"]}
    ])

    # DB id allocation
    def _next(conn, table):
        return {"region": 100, "segment": 200, "segment_source_coordinate": 300}.get(table, 1)
    monkeypatch.setattr("hap.lib.database.get_next_id_from_table", _next)

    # Fake DB connection/cursor
    class _Cur:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, *a, **k):
            self._last = (a, k)
        def fetchone(self):
            # Return ids for clade/pangenome/subgraph and inserts
            return (1,)
        def copy_from(self, f, *a, **k):
            _ = f.read()
        def executemany(self, *a, **k):
            pass
    class _Conn:
        autocommit = True
        def cursor(self):
            return _Cur()
        def commit(self):
            pass
        def rollback(self):
            pass

    # Ensure temp files created under tmp_path
    from hap.lib import fileutil
    def _create_tmp_files(n):
        files = []
        for i in range(n):
            p = tmp_path / f"t_{i}.tsv"
            p.write_text("")
            files.append(str(p))
        return tuple(files)
    monkeypatch.setattr(fileutil, "create_tmp_files", _create_tmp_files)

    hap_info = {"name": "n", "clade": "c", "description": "d", "creater": "u", "builder": ""}
    build.hap2db(hap_info, [(rt, st, {"name": "sub", "max_level": 1, "total_length": 10, "total_variants": 0, "sources": ["h1", "h2"]}, None)], _Conn())
    assert isinstance(hap_info.get("source_ids"), list) and len(hap_info["source_ids"]) >= 1

