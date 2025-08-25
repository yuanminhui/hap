import types


def _small_rt_st(pd_mod):
    rt = pd_mod.DataFrame([
        {"id": "r1", "semantic_id": "R", "level_range": [0, 0], "coordinate": [0, 10], "is_default": True, "length": 10, "is_variant": False, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": pd_mod.NA, "segments": ["s1"], "sources": ["src"], "min_length": 10, "before": None, "after": None},
    ])
    st = pd_mod.DataFrame([
        {"id": "s1", "original_id": None, "semantic_id": "R", "level_range": [0, 0], "coordinate": [0, 10], "rank": 0, "length": 10, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": [], "sources": ["src"]},
    ])
    return rt, st


def test_update_ids_by_subgraph_basic(monkeypatch, tmp_path):
    import pandas as pd
    import importlib

    build = importlib.import_module("hap.commands.build")

    # Make get_next_id_from_table deterministic
    monkeypatch.setattr("hap.lib.database.get_next_id_from_table", lambda conn, table: 100 if table == "region" else 200)

    # Fake connection object (not used by get_next_id due to monkeypatch)
    class _Conn:
        def cursor(self):
            return types.SimpleNamespace(__enter__=lambda s: s, __exit__=lambda s, *a: False)

    conn = _Conn()
    rt, st = _small_rt_st(pd)

    # Also exercise sequence_file branch with a temp file, but subprocess does nothing
    seq_file = tmp_path / "seq.tsv"
    seq_file.write_text("s1\tACGT\n")

    # Neutralize subprocess.run side effects
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))

    build.update_ids_by_subgraph(rt, st, 1, conn, str(seq_file))

    # IDs should be remapped to integers starting at 100/200
    assert rt["id"].iloc[0] == 100
    assert st["id"].iloc[0] == 200
