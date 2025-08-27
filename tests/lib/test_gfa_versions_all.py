import importlib
from types import SimpleNamespace


def _mk_run(rc, out=""):
    return lambda *a, **k: SimpleNamespace(returncode=rc, stdout=out)


def test_gfa_version_symbols(tmp_path, monkeypatch):
    gfa_mod = importlib.import_module("hap.lib.gfa")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    p = tmp_path / "v.gfa"; p.write_text("S\ts0\t*\tLN:i:1\n")
    g = gfa_mod.GFA(str(p))
    # simulate grep finds 'E' -> v2.0
    monkeypatch.setattr(gfa_mod.subprocess, "check_output", lambda *a, **k: "bad")
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(0, "E\n"))
    assert g.version == 2.0
    # 'J' -> 1.2
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(0, "J\n"))
    assert g.version == 1.2
    # 'W' -> 1.1
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(0, "W\n"))
    assert g.version == 1.1


def test_contains_path_length_versions(tmp_path, monkeypatch):
    gfa_mod = importlib.import_module("hap.lib.gfa")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    p = tmp_path / "x.gfa"; p.write_text("S\ts0\t*\tLN:i:1\n")
    g = gfa_mod.GFA(str(p))
    # v1.0 path: contains_path uses '^P'
    monkeypatch.setattr(gfa_mod.subprocess, "check_output", lambda *a, **k: "1.0")
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(0))
    assert g.contains_path() is True
    # v2.0 path: version header 2.0; contains_length should be True fast-path
    monkeypatch.setattr(gfa_mod.subprocess, "check_output", lambda *a, **k: "2.0")
    assert g.contains_length() is True