import types


def test_contains_functions_v1(tmp_path, monkeypatch):
    import subprocess
    from hap.lib import gfa as gfa_mod

    p = tmp_path / "t.gfa"
    p.write_text("H\tVN:Z:1.0\nS\t1\t*\tLN:i:1\nL\t1+\t1+\t0M\nP\tx\t1+\t*")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(p))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.0))
    # Stub subprocess to return code 0 for grep
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    assert g.contains_segment() is True
    assert g.contains_edge() is True
    assert g.contains_path() is True


def test_contains_functions_v2_negative(tmp_path, monkeypatch):
    import subprocess
    from hap.lib import gfa as gfa_mod

    p = tmp_path / "t2.gfa"
    p.write_text("H\tVN:Z:2.0\n")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(p))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 2.0))
    # Return code 1 (no matches)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=1))
    assert g.contains_edge() is False
    assert g.contains_path() is False
