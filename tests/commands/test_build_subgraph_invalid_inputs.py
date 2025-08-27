import importlib
import types

from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult


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
            # directory case handled by CLI helper; here just return as-is
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


def test_subgraphs_empty_file(monkeypatch, tmp_path):
    _stub(monkeypatch)
    f = tmp_path / "empty.gfa"
    f.write_text("")
    r = CliRunner().invoke(cli, ["build", "run", str(f), "-n", "x", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code != 0


def test_subgraphs_bad_format(monkeypatch, tmp_path):
    _stub(monkeypatch)
    f = tmp_path / "bad.txt"
    f.write_text("not gfa")
    # Click exists path type will pass; invalidity should cause fail during GFA init
    r = CliRunner().invoke(cli, ["build", "run", str(f), "-n", "x", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code != 0

