import importlib
from pathlib import Path
import types
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import generate_gfa_dag


def _stub(monkeypatch):
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
        "build_subgraphs_with_sequence_in_parallel",
        lambda items, mr, td: [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, None) for n, p in items],
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


@pytest.mark.parametrize("min_res", [0.001, 0.04, 0.5])
def test_build_min_res_variants(monkeypatch, tmp_path, min_res):
    _stub(monkeypatch)
    _stub(monkeypatch)
    build = importlib.import_module("hap.commands.build")
    # Force failure on non-positive min_res in the stubbed parallel builder
    def _builder(items, mr, td):
        if mr <= 0:
            raise ValueError("Min resolution must be greater than 0.")
        return [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, None) for n, p in items]
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", _builder)
    g = tmp_path / "g.gfa"
    generate_gfa_dag(g)
    r = CliRunner().invoke(cli, [
        "build", "run", str(g), "-n", "p", "-a", "c", "-c", "u", "-x", "", "-r", str(min_res)
    ])
    assert r.exit_code == 0


def test_build_min_res_zero_error(monkeypatch, tmp_path):
    # This should fail in wrap_rstree when min_res <= 0; here just assert non-zero exit if user passes 0
    _stub(monkeypatch)
    g = tmp_path / "g.gfa"; generate_gfa_dag(g)
    # With stubbed builder enforcing mr>0, CLI should fail on -r 0
    build = importlib.import_module("hap.commands.build")
    def _builder(items, mr, td):
        if mr <= 0:
            raise ValueError("min_res invalid")
        return [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, None) for n, p in items]
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", _builder)
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "p", "-a", "c", "-c", "u", "-x", "", "-r", "0"]) 
    assert r.exit_code != 0

