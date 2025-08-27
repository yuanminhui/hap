import types


def test_prepare_and_build_preprocessed_subgraphs_in_parallel(monkeypatch, tmp_path):
    import importlib
    import subprocess
    import multiprocessing as mp
    from hap.lib import gfa as gfa_mod

    build = importlib.import_module("hap.commands.build")
    # Stub subprocess.run globally
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    # Stub GFA.ensure_length_completeness to no-op
    monkeypatch.setattr(gfa_mod, "GFA", type("_GFA", (), {"__init__": lambda self, p: None, "ensure_length_completeness": lambda self: None}))

    # Two tiny GFA inputs
    g1 = tmp_path / "g1.gfa"
    g2 = tmp_path / "g2.gfa"
    g1.write_text("S\tn1\t*\tLN:i:1\n")
    g2.write_text("S\tn2\t*\tLN:i:1\n")
    outdir = tmp_path / "w"
    outdir.mkdir()

    items = [("s1", str(g1)), ("s2", str(g2))]
    # Prepare stage
    pre = build.prepare_preprocessed_subgraphs_in_parallel(items, str(tmp_path / "seq.tsv"), str(outdir))
    assert len(pre) == 2

    # Build stage: stub build_from_gfa to return minimal frames and pass through
    import pandas as pd
    monkeypatch.setattr(build, "build_from_gfa", lambda name, gfa_path, sequence_file, min_resolution, temp_dir: (pd.DataFrame(), pd.DataFrame(), {"name": name}, sequence_file))
    # Monkeypatch Pool.starmap to synchronous execution to avoid pickling lambdas
    monkeypatch.setattr(mp.pool.Pool, "starmap", lambda self, func, iterable: [func(*it) for it in iterable])

    built = build.build_preprocessed_subgraphs_in_parallel(pre, 0.04)
    assert len(built) == 2 and built[0][2]["name"] in ("s1", "s2")


def test_hap2db_sequence_file_branch(monkeypatch, tmp_path):
    import importlib
    import pandas as pd
    build = importlib.import_module("hap.commands.build")

    # Minimal rt/st to trigger formatting and file dumps; include a sequence file path
    rt = pd.DataFrame([
        {"id": "r0", "semantic_id": "CON-1", "level_range": [0, 0], "coordinate": [0, 10], "is_default": True, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": pd.NA, "segments": ["s1"],
         "length": 10, "is_variant": False, "sources": ["h1"], "min_length": 10, "before": None, "after": None}
    ])
    st = pd.DataFrame([
        {"id": "s1", "semantic_id": "CON-1", "level_range": [0, 0], "coordinate": [0, 10], "rank": 0, "length": 10, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": [], "sources": ["h1"], "original_id": None}
    ])
    seq_file = tmp_path / "seq.tsv"
    seq_file.write_text("s1\tAC\n")

    # Deterministic IDs
    monkeypatch.setattr("hap.lib.database.get_next_id_from_table", lambda conn, table: 1)

    # Fake DB connection that accepts copy_from
    class _Cur:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, *a, **k):
            self._last = (a, k)
        def fetchone(self):
            # Return id for clade/pangenome/subgraph insert chains
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
    build.hap2db(hap_info, [(rt, st, {"name": "sub", "max_level": 1, "total_length": 10, "total_variants": 0, "sources": ["h1"]}, str(seq_file))], _Conn())
    assert isinstance(hap_info.get("source_ids"), list)

