from pathlib import Path
import importlib
import types
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import generate_gfa_dag, generate_fasta, gzip_file


def test_build_with_external_gzip_fasta(monkeypatch, tmp_path):
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")
    db = importlib.import_module("hap.lib.database")

    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["x"]
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", self.filepath)]
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def to_igraph(self):
            return types.SimpleNamespace(is_dag=True)
        def ensure_length_completeness(self):
            return None

    monkeypatch.setattr(gfa, "GFA", DummyGFA)
    monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "check_name", lambda name: True)
    monkeypatch.setattr(
        build,
        "prepare_preprocessed_subgraphs_in_parallel",
        lambda items, tsv, td: [(n, p, tsv) for n, p in items],
    )
    monkeypatch.setattr(
        build,
        "build_preprocessed_subgraphs_in_parallel",
        lambda items, mr: [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, t) for n, p, t in items],
    )
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
        def rollback(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)

    g = tmp_path / "g.gfa"; generate_gfa_dag(g)
    nodes = tmp_path / "nodes.fa"; generate_fasta(nodes, [("s0", "A"), ("s1", "C")])
    nodes_gz = gzip_file(nodes)
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "gz", "-a", "c", "-c", "u", "-x", "", "--sequence-file", str(nodes_gz)])
    assert r.exit_code == 0

