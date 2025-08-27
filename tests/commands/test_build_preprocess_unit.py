import types


def test_prepare_preprocessed_subgraph(monkeypatch, tmp_path):
    import importlib
    import subprocess
    from hap.lib import gfa as gfa_mod

    build = importlib.import_module("hap.commands.build")

    # Stub subprocess.run to no-op
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))

    # Stub GFA.ensure_length_completeness to no-op
    class _GFA:
        def __init__(self, path):
            self.filepath = path
        def ensure_length_completeness(self):
            return None

    monkeypatch.setattr(gfa_mod, "GFA", _GFA)

    # Build a tiny GFA and TSV
    gfa_in = tmp_path / "t.gfa"
    gfa_in.write_text("S\tn1\t*\tLN:i:1\n")
    tsv = tmp_path / "t.tsv"
    tsv.write_text("n1\tA\n")

    workdir = tmp_path / "work"
    workdir.mkdir()
    sub = build.prepare_preprocessed_subgraph("p0", str(gfa_in), str(tsv), str(workdir))
    # Returns (name, working_gfa, out_tsv)
    assert sub[0] == "p0" and sub[1].endswith("t.gfa") and sub[2].endswith(".seq.tsv")

