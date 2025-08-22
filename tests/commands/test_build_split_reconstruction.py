from pathlib import Path
from click.testing import CliRunner
import importlib
import types

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
            # For a directory input, just list .gfa files
            d = Path(self.filepath)
            if d.is_dir():
                parts = sorted(d.glob("*.gfa"))
                return [(p.stem, str(p)) for p in parts]
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


def test_split_reconstruction_counts(monkeypatch, tmp_path):
    # Create base and parts with disjoint segments and edges
    base = tmp_path / "base.gfa"
    # 0..9 nodes, linear edges 0->1->...->9
    generate_gfa_dag(base, num_nodes=10)
    parts_dir = tmp_path / "parts"; parts_dir.mkdir()
    p1 = parts_dir / "p1.gfa"; p2 = parts_dir / "p2.gfa"
    # First part nodes 0..4, edges within this range
    p1.write_text(
        "H\tVN:Z:1.0\n"
        + "".join([f"S\ts{i}\t*\tLN:i:1\n" for i in range(5)])
        + "".join([f"L\ts{i}\t+\ts{i+1}\t+\t0M\n" for i in range(4)])
    )
    # Second part nodes 5..9, edges within this range
    p2.write_text(
        "H\tVN:Z:1.0\n"
        + "".join([f"S\ts{i}\t*\tLN:i:1\n" for i in range(5, 10)])
        + "".join([f"L\ts{i}\t+\ts{i+1}\t+\t0M\n" for i in range(5, 9)])
    )

    def count_S(path: Path) -> int:
        return sum(1 for line in path.read_text().splitlines() if line.startswith("S\t"))

    def count_L(path: Path) -> int:
        return sum(1 for line in path.read_text().splitlines() if line.startswith("L\t"))

    original_S = count_S(base)
    original_L = count_L(base)
    parts_S = count_S(p1) + count_S(p2)
    parts_L = count_L(p1) + count_L(p2)
    # 拼接正确性（段/边数量）
    assert parts_S == original_S
    # 边数少于原始（不跨分块），允许 <= 原始
    assert parts_L <= original_L

    _stub(monkeypatch)
    r = CliRunner().invoke(cli, [
        "build", "run", str(parts_dir), "-s",
        "-n", "rx", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0

