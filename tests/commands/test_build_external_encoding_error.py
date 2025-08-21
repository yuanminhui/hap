import importlib
from pathlib import Path
import types
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import generate_gfa_dag


def test_build_external_sequence_non_utf8(monkeypatch, tmp_path):
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")
    db = importlib.import_module("hap.lib.database")
    seqlib = importlib.import_module("hap.lib.sequence")

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
    # Non-UTF8 error when reading external sequences -> simulate by raising from converter
    def _to_tsv(path, outfh):
        raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid")
    monkeypatch.setattr(seqlib, "write_fasta_or_fastq_to_tsv", _to_tsv)
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

    g = tmp_path / "g.gfa"; generate_gfa_dag(g)
    nodes = tmp_path / "bad.fa"; nodes.write_bytes(b">a\n\x80\n")
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "x", "-a", "c", "-c", "u", "-x", "", "--sequence-file", str(nodes)])
    assert r.exit_code != 0

