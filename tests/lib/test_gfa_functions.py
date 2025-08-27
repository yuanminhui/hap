from pathlib import Path
import importlib


def test_gfa_version_parsing(tmp_path, monkeypatch):
    gfa_mod = importlib.import_module("hap.lib.gfa")
    # bypass heavy validity checks for constructor
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    p = tmp_path / "v1.gfa"
    p.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\nL\ts0\t+\ts0\t+\t0M\n")
    g = gfa_mod.GFA(str(p))
    assert g.version >= 1.0


def test_extract_subgraph_names_simple(tmp_path, monkeypatch):
    gfa_mod = importlib.import_module("hap.lib.gfa")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    # Minimal GFA content
    p = tmp_path / "s.gfa"
    p.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\nP\tchr1\ts0+\t*\n")
    g = gfa_mod.GFA(str(p))
    names = g.extract_subgraph_names(chr_only=True)
    assert isinstance(names, list)