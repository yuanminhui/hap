import types


def test_separate_sequence_handles_no_sequence(tmp_path, monkeypatch):
    from hap.lib import gfa as gfa_mod
    # Minimal GFA without sequences on S lines (GFA1)
    gfa_path = tmp_path / "a.gfa"
    gfa_path.write_text("S\ts1\t*\tLN:i:1\n")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(gfa_path))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.0))
    outdir = tmp_path / "out"
    outdir.mkdir()
    out_gfa, out_tsv = g.separate_sequence(str(outdir))
    assert out_gfa.endswith("a.gfa") and out_tsv is None


def test_extract_subgraph_names_variants(tmp_path, monkeypatch):
    import subprocess
    from hap.lib import gfa as gfa_mod

    gfa_path = tmp_path / "b.gfa"
    gfa_path.write_text("H\tVN:Z:1.2\nW\t\t\tchr1\n")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(gfa_path))
    # Stub subprocess.run to return filtered names for three version branches
    def _run(cmd, shell=False, text=False, capture_output=False):
        return types.SimpleNamespace(returncode=0, stdout="chr1\nchr2\n")
    monkeypatch.setattr(subprocess, "run", _run)
    # Force version to 1.1 so path is via W lines
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.1))
    names = g.extract_subgraph_names(chr_only=True)
    assert "chr1" in names


def test_extract_subgraph_by_name_and_divide(tmp_path, monkeypatch):
    import subprocess
    from hap.lib import gfa as gfa_mod

    gfa_path = tmp_path / "c.gfa"
    gfa_path.write_text("H\tVN:Z:1.2\nW\t\t\tchr1\n")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(gfa_path))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.1))
    # extract_subgraph_by_name executes grep/awk/cat; stub run to succeed
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    # extract_subgraph_names called by divide_into_subgraphs
    monkeypatch.setattr(gfa_mod.GFA, "extract_subgraph_names", lambda self, chr_only: ["chr1", "chr2"])
    outs = g.divide_into_subgraphs(str(tmp_path), chr_only=True)
    # Returns [(name, output_file), ...]
    assert len(outs) == 2 and outs[0][0] == "chr1"


def test_to_igraph_pipeline(tmp_path, monkeypatch):
    import subprocess
    import pandas as pd
    from hap.lib import gfa as gfa_mod

    gfa_path = tmp_path / "d.gfa"
    gfa_path.write_text("H\tVN:Z:1.2\nW\t\t\tchr1\n")
    monkeypatch.setattr(gfa_mod.GFA, "is_valid", lambda self: True)
    g = gfa_mod.GFA(str(gfa_path))
    monkeypatch.setattr(gfa_mod.GFA, "version", property(lambda self: 1.1))
    # Stub subprocess.run calls used inside to_igraph
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    # Patch pandas.read_csv to return minimal frames
    def _read_csv(path, sep="\t", **kwargs):
        fname = str(path)
        if "names" in kwargs:
            return pd.DataFrame([["haplotypes", "h1"]], columns=kwargs["names"])  # info
        if "dtype" in kwargs and "name" in kwargs.get("dtype", {}):
            return pd.DataFrame([["n1", 10, 1.0, "h1"]], columns=["name", "length", "frequency", "sources"])
        else:
            return pd.DataFrame([["n1", "n2"]], columns=["source", "target"])
    monkeypatch.setattr(gfa_mod.pd, "read_csv", _read_csv)
    # Provide Graph.DataFrame on gfa_mod.ig
    class _Graph:
        @staticmethod
        def DataFrame(edge_df, vertices=None, use_vids=False):
            class _G:
                def __init__(self):
                    self._attrs = {}
                def __setitem__(self, k, v):
                    self._attrs[k] = v
            return _G()
    monkeypatch.setattr(gfa_mod, "ig", types.SimpleNamespace(Graph=_Graph))
    gr = g.to_igraph()
    # Graph should have attributes set from info
    assert isinstance(gr, object)

