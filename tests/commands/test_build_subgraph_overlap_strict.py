import importlib
import types

from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult


def test_subgraph_overlap_across_graphs_fails(monkeypatch, tmp_path):
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
    # Make validate_gfa fail on mismatched sources
    monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(False, "subgraphs not from same graph"))
    monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "check_name", lambda name: True)
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

    # mix files from different virtual graphs -> force failure
    d1 = tmp_path / "g1"; d1.mkdir(); p1 = d1 / "g1.part1.gfa"; p1.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\n")
    p2 = tmp_path / "g2.part1.gfa"; p2.write_text("H\tVN:Z:1.0\nS\tsX\t*\tLN:i:1\n")
    r = CliRunner().invoke(cli, ["build", "run", str(d1), str(p2), "-s", "-n", "x", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code != 0

