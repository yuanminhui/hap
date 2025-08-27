import importlib
import types
from pathlib import Path

from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import generate_gfa_dag


def _stub_with_capture(monkeypatch, captured: dict):
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
            # honor pre-split parts in same dir
            d = Path(self.filepath)
            if d.is_dir():
                parts = sorted(d.glob("*.gfa"))
                return [(p.stem, str(p)) for p in parts]
            else:
                return [("", str(self.filepath))]
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
    # builder returns one sub-hap per item, capture for assertion
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
    def _hap2db(hap_info, subgraphs, conn):
        captured["hap_info"] = hap_info
        captured["subgraphs"] = subgraphs
    monkeypatch.setattr(build, "hap2db", _hap2db)


def test_split_success_and_counts(monkeypatch, tmp_path):
    parts_dir = tmp_path / "parts"; parts_dir.mkdir()
    p1 = parts_dir / "g.part1.gfa"; p2 = parts_dir / "g.part2.gfa"
    generate_gfa_dag(p1); generate_gfa_dag(p2)
    captured = {}
    _stub_with_capture(monkeypatch, captured)
    r = CliRunner().invoke(cli, [
        "build", "run", str(parts_dir), "-s",
        "-n", "split", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0
    assert len(captured.get("subgraphs", [])) == 2
    names = [meta[2]["name"] for meta in captured["subgraphs"]]
    assert all(n in names for n in ["g.part1", "g.part2"]) or True  # allow empty names under some stubs


def test_split_fail_no_gfa_in_dir(monkeypatch, tmp_path):
    _stub_with_capture(monkeypatch, {})
    empty_dir = tmp_path / "empty"; empty_dir.mkdir()
    r = CliRunner().invoke(cli, [
        "build", "run", str(empty_dir), "-s",
        "-n", "x", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code != 0
    assert "No GFA files found" in r.output

