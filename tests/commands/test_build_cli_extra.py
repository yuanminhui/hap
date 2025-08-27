import importlib
import types
from pathlib import Path

from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult


def _stub_graph_ok(monkeypatch):
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")
    db = importlib.import_module("hap.lib.database")

    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["dummy"]
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", self.filepath)]
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def to_igraph(self):
            return types.SimpleNamespace(is_dag=True)

    monkeypatch.setattr(gfa, "GFA", DummyGFA)
    monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "check_name", lambda name: True)
    monkeypatch.setattr(
        build,
        "build_subgraphs_with_sequence_in_parallel",
        lambda items, mr, td: [
            (
                types.SimpleNamespace(),
                types.SimpleNamespace(),
                {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0},
                None,
            )
            for n, p in items
        ],
    )
    # Avoid real DB/hap2db
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
                def fetchall(self):
                    return []
                def copy_from(self, *a, **k):
                    pass
            return Cur()
        def commit(self):
            pass
        def rollback(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)
    return build


def test_build_invalid_multi_without_s(monkeypatch, tmp_path):
    _stub_graph_ok(monkeypatch)
    g1 = Path("data/mini-example/mini-example.gfa").resolve()
    g2 = tmp_path / "b.gfa"
    g2.write_text(g1.read_text())
    r = CliRunner().invoke(
        cli,
        [
            "build",
            "run",
            str(g1),
            str(g2),
            "-n",
            "x",
            "-a",
            "c",
            "-c",
            "u",
        ],
    )
    assert r.exit_code != 0
    assert "more than one graph" in r.output.lower()


def test_build_sequence_file_dir_error(monkeypatch, tmp_path):
    _ = _stub_graph_ok(monkeypatch)
    gfa = Path("data/mini-example/mini-example.gfa").resolve()
    r = CliRunner().invoke(
        cli,
        [
            "build",
            "run",
            str(gfa),
            "-n",
            "x",
            "-a",
            "c",
            "-c",
            "u",
            "-x",
            "",
            "--sequence-file",
            str(tmp_path),
        ],
    )
    assert r.exit_code != 0
    assert "--sequence-file must be a single file" in r.output


def test_build_from_subgraphs_dir(monkeypatch, tmp_path):
    _ = _stub_graph_ok(monkeypatch)
    gfa = Path("data/mini-example/mini-example.gfa").resolve()
    d = tmp_path / "subs"
    d.mkdir()
    (d / "x.gfa").write_text(gfa.read_text())
    r = CliRunner().invoke(
        cli,
        [
            "build",
            "run",
            str(d),
            "-s",
            "-n",
            "x",
            "-a",
            "c",
            "-c",
            "u",
            "-x",
            "",
        ],
    )
    assert r.exit_code == 0

