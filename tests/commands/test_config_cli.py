from click.testing import CliRunner
import importlib
import types

import hap
from hap.__main__ import cli


def test_config_set_get_unset_list(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.yaml"
    monkeypatch.setattr(hap, "CONFIG_PATH", str(cfg_file))

    r = CliRunner().invoke(cli, ["config", "set", "--key", "db.host", "--value", "localhost"])
    assert r.exit_code == 0

    r = CliRunner().invoke(cli, ["config", "get", "--key", "db.host"])
    assert r.exit_code == 0
    assert r.output.strip() == "localhost"

    r = CliRunner().invoke(cli, ["config", "list"])
    assert r.exit_code == 0
    assert "db.host" in r.output

    r = CliRunner().invoke(cli, ["config", "unset", "--key", "db.host"])
    assert r.exit_code == 0

    r = CliRunner().invoke(cli, ["config", "get", "--key", "db.host"])
    assert r.exit_code == 0
    assert r.output.strip() == ""


def test_wrap_rstree_smoke(monkeypatch, tmp_path):
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")

    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def ensure_length_completeness(self):
            return None
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", self.filepath)]
        def to_igraph(self):
            class G:
                is_dag = True
                def is_connected(self, mode="WEAK"):
                    return True
            return G()
    monkeypatch.setattr(gfa, "GFA", DummyGFA)

    seen = {"wrap": 0}
    monkeypatch.setattr(build, "validate_gfa", lambda gfa_obj: types.SimpleNamespace(valid=True, message=""))
    monkeypatch.setattr(build, "validate_graph", lambda graph: types.SimpleNamespace(valid=True, message=""))
    monkeypatch.setattr(build, "graph2rstree", lambda g: (__import__("pandas").DataFrame(), __import__("pandas").DataFrame(), {"sources": [], "name": "t"}))
    def _wrap(rt, st, meta, mr):
        seen["wrap"] += 1
        return rt, st, meta
    monkeypatch.setattr(build, "wrap_rstree", _wrap)
    monkeypatch.setattr(build, "calculate_properties_l2r", lambda rt, st, meta: (rt, st, meta))
    monkeypatch.setattr(build, "calculate_properties_r2l", lambda rt, st, meta: (rt, st, meta))
    def _builder(items, min_res, temp_dir):
        out = []
        for n, p in items:
            rt, st, meta = build.graph2rstree(None)
            rt, st, meta = build.calculate_properties_l2r(rt, st, meta)
            rt, st, meta = build.wrap_rstree(rt, st, meta, min_res)
            rt, st, meta = build.calculate_properties_r2l(rt, st, meta)
            out.append((rt, st, meta, None))
        return out
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", _builder)
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

    g = tmp_path / "w.gfa"; g.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\n")
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "w", "-a", "c", "-c", "u", "-x", "", "-r", "1.0"]) 
    assert r.exit_code == 0
    assert seen["wrap"] == 1