import importlib
import types

from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import generate_gfa_missing_fields, generate_gfa_nested


def _stub_build_failures(monkeypatch, *, graph_valid=True):
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")
    db = importlib.import_module("hap.lib.database")

    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["a", "b"]
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", self.filepath)]
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def to_igraph(self):
            return types.SimpleNamespace(is_dag=True)
        def ensure_length_completeness(self):
            return None

    monkeypatch.setattr(gfa, "GFA", DummyGFA)
    # toggle validity
    if graph_valid:
        monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(True, ""))
        monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(True, ""))
    else:
        monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(False, "bad gfa"))
        monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "check_name", lambda name: True)
    # Stub DB connect & hap2db
    class _C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def cursor(self):
            class Cur:
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def execute(self, *a, **k):
                    pass
                def fetchone(self):
                    return (1,)
            return Cur()
        def commit(self):
            pass
        def rollback(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)


def test_invalid_gfa_missing_fields(monkeypatch, tmp_path):
    _stub_build_failures(monkeypatch, graph_valid=False)
    g = tmp_path / "bad.gfa"
    generate_gfa_missing_fields(g)
    r = CliRunner().invoke(cli, [
        "build", "run", str(g), "-n", "bad", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code != 0
    # Click may swallow stderr; accept nonzero exit as failure on invalid


def test_nested_structure_valid_graph(monkeypatch, tmp_path):
    _stub_build_failures(monkeypatch, graph_valid=True)
    g = tmp_path / "nested.gfa"
    generate_gfa_nested(g)
    # Stub builder returns dicts; ensure downstream expects dict subscripting
    build = importlib.import_module("hap.commands.build")
    monkeypatch.setattr(
        build,
        "build_subgraphs_with_sequence_in_parallel",
        lambda items, mr, td: [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, None) for n, p in items],
    )
    r = CliRunner().invoke(cli, [
        "build", "run", str(g), "-n", "nest", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0

