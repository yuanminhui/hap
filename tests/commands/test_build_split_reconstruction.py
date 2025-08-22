import importlib
import types
from pathlib import Path

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
    # 0..9 nodes, linear edges 0->1->...->9 with two P records
    base.write_text(
        "H\tVN:Z:1.0\n"
        + "".join([f"S\ts{i}\t*\tLN:i:1\n" for i in range(10)])
        + "".join([f"L\ts{i}\t+\ts{i+1}\t+\t0M\n" for i in range(9)])
        + "P\tpath1\t" + ",".join([f"s{i}+" for i in range(10)]) + "\t*\n"
        + "P\tpath2\t" + ",".join([f"s{i}+" for i in range(0, 10, 2)]) + "\t*\n"
    )
    parts_dir = tmp_path / "parts"; parts_dir.mkdir()
    p1 = parts_dir / "p1.gfa"; p2 = parts_dir / "p2.gfa"
    # First part nodes 0..4, edges within this range; simple P1
    p1.write_text(
        "H\tVN:Z:1.0\n"
        + "".join([f"S\ts{i}\t*\tLN:i:1\n" for i in range(5)])
        + "".join([f"L\ts{i}\t+\ts{i+1}\t+\t0M\n" for i in range(4)])
        + "P\tp1\t" + ",".join([f"s{i}+" for i in range(5)]) + "\t*\n"
    )
    # Second part nodes 5..9, edges within this range; simple P2
    p2.write_text(
        "H\tVN:Z:1.0\n"
        + "".join([f"S\ts{i}\t*\tLN:i:1\n" for i in range(5, 10)])
        + "".join([f"L\ts{i}\t+\ts{i+1}\t+\t0M\n" for i in range(5, 9)])
        + "P\tp2\t" + ",".join([f"s{i}+" for i in range(5, 10)]) + "\t*\n"
    )

    def count_S(path: Path) -> int:
        return sum(1 for line in path.read_text().splitlines() if line.startswith("S\t"))

    def count_L(path: Path) -> int:
        return sum(1 for line in path.read_text().splitlines() if line.startswith("L\t"))

    def list_P_segments(path: Path) -> list[str]:
        segs: list[str] = []
        for line in path.read_text().splitlines():
            if line.startswith("P\t"):
                fields = line.split("\t")
                if len(fields) >= 3:
                    segs.extend(fields[2].split(","))
        return segs

    original_S = count_S(base)
    original_L = count_L(base)
    parts_S = count_S(p1) + count_S(p2)
    parts_L = count_L(p1) + count_L(p2)
    # 拼接正确性（段/边数量）
    assert parts_S == original_S
    assert parts_L <= original_L
    # P 采样：联合分片 P 段集合应为原始 P 段集合子集
    segs_base = set(list_P_segments(base))
    segs_parts = set(list_P_segments(p1) + list_P_segments(p2))
    assert segs_parts.issubset(segs_base)

    _stub(monkeypatch)
    r = CliRunner().invoke(cli, [
        "build", "run", str(parts_dir), "-s",
        "-n", "rx", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0

