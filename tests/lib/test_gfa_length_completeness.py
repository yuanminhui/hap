import os


def test_ensure_length_completeness_gfa2_noop(tmp_path, monkeypatch):
    # Create a minimal GFA2-like file: start with 'E' to trigger version>=2 in our detection
    gfa_path = tmp_path / "t.gfa"
    gfa_path.write_text("E\tfoo\n")

    import importlib
    from hap.lib import gfa as gfa_mod

    # Force is_valid to True so __init__ passes
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)

    g = gfa_mod.GFA(str(gfa_path))
    # Monkeypatch version property to 2.0
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 2.0))
    # Should not raise
    g.ensure_length_completeness()


def test_ensure_length_completeness_gfa1_missing_ln(tmp_path, monkeypatch):
    # GFA1 with missing LN on S record
    gfa_path = tmp_path / "t.gfa"
    gfa_path.write_text("S\t1\t*\n")

    from hap.lib import gfa as gfa_mod

    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(gfa_path))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.0))

    from hap.lib.error import DataIncompleteError
    try:
        g.ensure_length_completeness()
        assert False, "Expected DataIncompleteError"
    except DataIncompleteError:
        pass


def test_ensure_length_completeness_gfa1_with_ln(tmp_path, monkeypatch):
    # GFA1 with LN present
    gfa_path = tmp_path / "t.gfa"
    gfa_path.write_text("S\t1\t*\tLN:i:10\n")

    from hap.lib import gfa as gfa_mod

    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(gfa_path))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.0))
    # Should not raise
    g.ensure_length_completeness()
