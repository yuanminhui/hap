import types


def test_build_subgraph_with_sequence_gzip(monkeypatch, tmp_path):
    import importlib
    import subprocess
    from hap.lib import fileutil as fileutil_mod

    build = importlib.import_module("hap.commands.build")

    # Create a gz path and stub ungzip to copy to a temp file
    gz = tmp_path / "x.gfa.gz"
    plain = tmp_path / "x.gfa"
    plain.write_text("S\tn1\t*\tLN:i:1\n")
    gz.write_text("GZ")
    monkeypatch.setattr(fileutil_mod, "ungzip_file", lambda p: str(plain))
    # Stub build_from_gfa to capture args and return minimal tuple
    import pandas as pd
    def _bfg(subgraph_name, gfa_path, sequence_file, min_resolution, temp_dir):
        return (pd.DataFrame(), pd.DataFrame(), {"name": subgraph_name, "max_level": 1, "total_length": 1, "total_variants": 0, "sources": []}, None)
    monkeypatch.setattr(build, "build_from_gfa", _bfg)

    res = build.build_subgraph_with_sequence("s", str(gz), 0.04, str(tmp_path))
    # Should return tuple with meta name preserved
    assert res[2]["name"] == "s"


def test_build_subgraphs_with_sequence_in_parallel(monkeypatch, tmp_path):
    import importlib
    import multiprocessing.pool as mp_pool
    build = importlib.import_module("hap.commands.build")

    # Prepare two fake items
    items = [("s1", str(tmp_path / "a.gfa")), ("s2", str(tmp_path / "b.gfa"))]
    # Stub sub function to simple passthrough; signature matches partial usage: (name, filepath, min_resolution=?, temp_dir=?)
    def _sub(name, filepath, min_resolution=None, temp_dir=None):
        return ([], [], {"name": name}, None)
    monkeypatch.setattr(build, "build_subgraph_with_sequence", _sub)
    # Synchronous starmap respecting partial args
    monkeypatch.setattr(mp_pool.Pool, "starmap", lambda self, func, it: [func(*args) for args in it])

    out = build.build_subgraphs_with_sequence_in_parallel(items, 0.05, str(tmp_path))
    assert len(out) == 2 and out[0][2]["name"] in ("s1", "s2")

