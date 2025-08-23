import importlib
from types import SimpleNamespace


def _mk_run(retcode, stdout=""):
    def _run(*a, **k):
        return SimpleNamespace(returncode=retcode, stdout=stdout)
    return _run


def test_contains_branches(monkeypatch, tmp_path):
    gfa_mod = importlib.import_module("hap.lib.gfa")
    # bypass validity
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    p = tmp_path / "a.gfa"
    p.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\nL\ts0\t+\ts0\t+\t0M\n")
    g = gfa_mod.GFA(str(p))

    # version header directly
    monkeypatch.setattr(gfa_mod.subprocess, "check_output", lambda *a, **k: "1.0")
    assert g.version == 1.0

    # contains_segment: run returns 0
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(0))
    assert g.contains_segment() is True
    # contains_edge: still 0
    assert g.contains_edge() is True
    # contains_path: emulate 1.0 branch; run returns 1 -> False
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(1))
    assert g.contains_path() is False

    # contains_sequence: emulate return 0 -> True
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(0))
    assert g.contains_sequence() is True

    # contains_length: emulate 1.0 branch run return 1 -> False
    monkeypatch.setattr(gfa_mod.subprocess, "run", _mk_run(1))
    assert g.contains_length() is False