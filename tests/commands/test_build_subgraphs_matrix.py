import importlib
import types
from pathlib import Path

import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult
from tests.utils.data_gen import (
    generate_gfa_dag,
    generate_large_fasta_many_records,
    generate_large_gfa_many_segments,
    gzip_file,
)


def _stub_build(monkeypatch):
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
            # split by simple rule: files that exist with suffix .part*.gfa under same dir
            d = Path(self.filepath).parent
            parts = sorted(d.glob("*.part*.gfa"))
            if parts:
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
    # Stub parallel builders to avoid multiprocessing and heavy I/O
    monkeypatch.setattr(
        build,
        "build_subgraphs_with_sequence_in_parallel",
        lambda items, mr, td: [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, None) for n, p in items],
    )
    monkeypatch.setattr(
        build,
        "prepare_preprocessed_subgraphs_in_parallel",
        lambda items, tsv, td: [(n, p, tsv) for n, p in items],
    )
    monkeypatch.setattr(
        build,
        "build_preprocessed_subgraphs_in_parallel",
        lambda items, mr: [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, t) for n, p, t in items],
    )
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
                def fetchall(self):
                    return []
            return Cur()
        def commit(self):
            pass
        def rollback(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)


def test_subgraphs_multi_files(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    g1 = tmp_path / "g1.part1.gfa"
    g2 = tmp_path / "g1.part2.gfa"
    generate_gfa_dag(g1)
    generate_gfa_dag(g2)
    r = CliRunner().invoke(cli, [
        "build", "run", str(g1), str(g2), "-s",
        "-n", "submulti", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0


def test_subgraphs_single_directory(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    d = tmp_path / "subs"
    d.mkdir()
    p1 = d / "g.part1.gfa"
    p2 = d / "g.part2.gfa"
    generate_gfa_dag(p1)
    generate_gfa_dag(p2)
    r = CliRunner().invoke(cli, [
        "build", "run", str(d), "-s",
        "-n", "subdir", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0


def test_subgraphs_multiple_directories(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    d1 = tmp_path / "d1"; d1.mkdir()
    d2 = tmp_path / "d2"; d2.mkdir()
    generate_gfa_dag(d1 / "a.part1.gfa"); generate_gfa_dag(d1 / "a.part2.gfa")
    generate_gfa_dag(d2 / "b.part1.gfa"); generate_gfa_dag(d2 / "b.part2.gfa")
    r = CliRunner().invoke(cli, [
        "build", "run", str(d1), "-s",
        "-n", "subdirs", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0


def test_subgraph_single_file(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    g = tmp_path / "one.gfa"
    generate_gfa_dag(g)
    r = CliRunner().invoke(cli, [
        "build", "run", str(g), "-n", "one", "-a", "c", "-c", "u", "-x", "",
    ])
    assert r.exit_code == 0


def test_subgraphs_overlap_and_mismatch_graphs(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    # overlap within same prefix parts
    d = tmp_path / "o"; d.mkdir()
    generate_gfa_dag(d / "o.part1.gfa"); generate_gfa_dag(d / "o.part2.gfa")
    # mismatch: file from another graph name
    m = tmp_path / "mismatch.part1.gfa"
    generate_gfa_dag(m)
    r = CliRunner().invoke(cli, [
        "build", "run", str(d), "-s",
        "-n", "ovmm", "-a", "c", "-c", "u", "-x", "",
    ])
    # still should not crash under stub; real impl may reject
    assert r.exit_code == 0


def test_inputs_gzip_and_plain(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    g = tmp_path / "plain.gfa"; generate_gfa_dag(g)
    gz = gzip_file(g)
    nodes = tmp_path / "nodes.fa"; generate_large_fasta_many_records(nodes, num_records=1000, seq_len=30)
    nodes_gz = gzip_file(nodes)
    # plain gfa + gz fasta/fastq (tsv预处理路径会触发)
    r1 = CliRunner().invoke(cli, [
        "build", "run", str(g), "-n", "gz1", "-a", "c", "-c", "u", "-x", "", "--sequence-file", str(nodes_gz),
    ])
    assert r1.exit_code == 0
    # gz gfa + plain sequences
    r2 = CliRunner().invoke(cli, [
        "build", "run", str(gz), "-n", "gz2", "-a", "c", "-c", "u", "-x", "", "--sequence-file", str(nodes),
    ])
    assert r2.exit_code == 0


@pytest.mark.large
@pytest.mark.slow
def test_large_inputs_many_entries(monkeypatch, tmp_path):
    _stub_build(monkeypatch)
    # Generate many segments to reach large file by entries count
    big_gfa = tmp_path / "big.gfa"
    generate_large_gfa_many_segments(big_gfa, num_segments=150_000, connect=True)
    many_nodes = tmp_path / "nodes.fa"
    generate_large_fasta_many_records(many_nodes, num_records=150_000, seq_len=30)
    r = CliRunner().invoke(cli, [
        "build", "run", str(big_gfa), "-n", "big", "-a", "c", "-c", "u", "-x", "", "--sequence-file", str(many_nodes)
    ])
    assert r.exit_code == 0

