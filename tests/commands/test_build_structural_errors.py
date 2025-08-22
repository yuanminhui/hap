import importlib
import types

import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import (
    generate_gfa_dangling_edge,
    generate_gfa_invalid_path_record,
    generate_gfa_repeated_edge,
)


def _stub_fail(monkeypatch, message: str):
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
            # make graph invalid by validate_graph returning False
            return types.SimpleNamespace(is_dag=False)
        def ensure_length_completeness(self):
            return None

    monkeypatch.setattr(gfa, "GFA", DummyGFA)
    monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(False, message))
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


@pytest.mark.parametrize("maker,msg", [
    (generate_gfa_dangling_edge, "dangling"),
    (generate_gfa_repeated_edge, "repeated"),
    (generate_gfa_invalid_path_record, "invalid path"),
])
def test_build_structural_invalid(monkeypatch, tmp_path, maker, msg):
    _stub_fail(monkeypatch, message=msg)
    g = tmp_path / "bad.gfa"
    maker(g)
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "x", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code != 0
