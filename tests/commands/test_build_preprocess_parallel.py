import importlib
import types


def test_prepare_preprocessed_subgraphs_in_parallel(tmp_path, monkeypatch):
    build = importlib.import_module("hap.commands.build")
    gfa_mod = importlib.import_module("hap.lib.gfa")
    # monkeypatch Pool.starmap to a local apply
    class DummyPool:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starmap(self, func, items):
            return [func(*args) for args in items]
    monkeypatch.setattr(build.mp, "Pool", lambda: DummyPool())
    # patch prepare_preprocessed_subgraph to a simple passthrough
    def _prep(name, src_gfa, sequence_file_tsv, temp_dir):
        return (name, src_gfa, sequence_file_tsv)
    monkeypatch.setattr(build, "prepare_preprocessed_subgraph", _prep)
    items = [("a", str(tmp_path/"a.gfa")), ("b", str(tmp_path/"b.gfa"))]
    out = build.prepare_preprocessed_subgraphs_in_parallel(items, sequence_file_tsv=str(tmp_path/"x.tsv"), temp_dir=str(tmp_path))
    assert out == [("a", str(tmp_path/"a.gfa"), str(tmp_path/"x.tsv")), ("b", str(tmp_path/"b.gfa"), str(tmp_path/"x.tsv"))]


def test_build_preprocessed_subgraphs_in_parallel(tmp_path, monkeypatch):
    build = importlib.import_module("hap.commands.build")
    # monkeypatch Pool.starmap to a local apply
    class DummyPool:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def starmap(self, func, items):
            return [func(*args) for args in items]
    monkeypatch.setattr(build.mp, "Pool", lambda: DummyPool())
    # stub build_from_gfa to return minimal tuple
    def _bf(name, gfa_path, sequence_file, min_resolution, temp_dir):
        import pandas as pd
        return pd.DataFrame(), pd.DataFrame(), {"sources": [], "name": name}, sequence_file
    monkeypatch.setattr(build, "build_from_gfa", _bf)
    items = [("a", str(tmp_path/"a.gfa"), str(tmp_path/"a.tsv"))]
    out = build.build_preprocessed_subgraphs_in_parallel(items, min_resolution=1.0)
    assert len(out) == 1 and out[0][2]["name"] == "a"