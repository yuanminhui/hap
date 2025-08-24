import importlib
from pathlib import Path


def test_build_from_gfa_without_sequence_file(tmp_path, monkeypatch):
    build = importlib.import_module("hap.commands.build")
    gfa_mod = importlib.import_module("hap.lib.gfa")
    # Minimal GFA stub
    class DummyGFA:
        def __init__(self, fp):
            self.filepath = str(fp)
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["h1"]
        def ensure_length_completeness(self):
            return None
        def to_igraph(self):
            class G:
                is_dag = True
                def is_connected(self, mode="WEAK"):
                    return True
            return G()
    monkeypatch.setattr(gfa_mod, "GFA", DummyGFA)
    # record wrappers
    called = {"g2r": 0}
    monkeypatch.setattr(build, "validate_gfa", lambda gfa_obj: build.ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda g: build.ValidationResult(True, ""))
    monkeypatch.setattr(build, "graph2rstree", lambda g: (__import__("pandas").DataFrame(), __import__("pandas").DataFrame(), {"sources": [], "name": "t"}))
    monkeypatch.setattr(build, "calculate_properties_l2r", lambda rt, st, meta: (rt, st, meta))
    def _wrap(rt, st, meta, min_res):
        called["g2r"] += 1
        return rt, st, meta
    monkeypatch.setattr(build, "wrap_rstree", _wrap)
    monkeypatch.setattr(build, "calculate_properties_r2l", lambda rt, st, meta: (rt, st, meta))
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)
    monkeypatch.setattr(build, "check_name", lambda n: True)
    # DB stub
    db = importlib.import_module("hap.lib.database")
    class _C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def cursor(self):
            class C:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def execute(self, *a, **k):
                    pass
                def fetchone(self):
                    return (1,)
            return C()
        def commit(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())

    gfa_file = tmp_path / "g.gfa"; gfa_file.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\n")
    rt, st, meta, seq = build.build_from_gfa(subgraph_name="t", gfa_path=str(gfa_file), sequence_file=None, min_resolution=1.0, temp_dir=str(tmp_path))
    assert called["g2r"] == 1 and seq is None


def test_build_from_gfa_with_sequence_file(tmp_path, monkeypatch):
    build = importlib.import_module("hap.commands.build")
    gfa_mod = importlib.import_module("hap.lib.gfa")
    # same GFA stub
    class DummyGFA:
        def __init__(self, fp):
            self.filepath = str(fp)
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["h1"]
        def ensure_length_completeness(self):
            return None
        def to_igraph(self):
            class G:
                is_dag = True
                def is_connected(self, mode="WEAK"):
                    return True
            return G()
    monkeypatch.setattr(gfa_mod, "GFA", DummyGFA)
    monkeypatch.setattr(build, "validate_gfa", lambda gfa_obj: build.ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda g: build.ValidationResult(True, ""))
    monkeypatch.setattr(build, "graph2rstree", lambda g: (__import__("pandas").DataFrame(), __import__("pandas").DataFrame(), {"sources": [], "name": "t"}))
    monkeypatch.setattr(build, "calculate_properties_l2r", lambda rt, st, meta: (rt, st, meta))
    monkeypatch.setattr(build, "wrap_rstree", lambda rt, st, meta, mr: (rt, st, meta))
    monkeypatch.setattr(build, "calculate_properties_r2l", lambda rt, st, meta: (rt, st, meta))
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)
    monkeypatch.setattr(build, "check_name", lambda n: True)
    # DB stub
    db = importlib.import_module("hap.lib.database")
    class _C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def cursor(self):
            class C:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def execute(self, *a, **k):
                    pass
                def fetchone(self):
                    return (1,)
            return C()
        def commit(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())

    gfa_file = tmp_path / "g.gfa"; gfa_file.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\n")
    tsv = tmp_path / "nodes.tsv"; tsv.write_text("s0\tA\n")
    rt, st, meta, seq = build.build_from_gfa(subgraph_name="t", gfa_path=str(gfa_file), sequence_file=str(tsv), min_resolution=1.0, temp_dir=str(tmp_path))
    assert seq == str(tsv)