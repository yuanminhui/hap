import importlib
from pathlib import Path
import types
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import generate_gfa_dag


def _base_stub(monkeypatch, valid_graph: bool):
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
            return types.SimpleNamespace(is_dag=valid_graph)
        def ensure_length_completeness(self):
            return None

    monkeypatch.setattr(gfa, "GFA", DummyGFA)
    # Align with CLI: validate_* are used; make invalid path propagate
    monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(valid_graph, "graph invalid" if not valid_graph else ""))
    monkeypatch.setattr(build, "check_name", lambda name: True)
    # Bypass heavy build by returning minimal tuple for valid path; fail early for invalid
    # Route through build_from_gfa to trigger validate_graph behavior
    monkeypatch.setattr(
        build,
        "build_subgraphs_with_sequence_in_parallel",
        lambda items, mr, td: [build.build_from_gfa(n, p, None, mr, td) for n, p in items],
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


@pytest.mark.parametrize("valid_graph", [False])
def test_build_invalid_graphs(monkeypatch, tmp_path, valid_graph):
    _base_stub(monkeypatch, valid_graph=valid_graph)
    g = tmp_path / "g.gfa"
    generate_gfa_dag(g)
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "ng", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code != 0

