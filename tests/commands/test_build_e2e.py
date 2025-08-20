import contextlib
import importlib
from pathlib import Path
import types
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult


@pytest.fixture(scope="session")
def gfa_rel() -> Path:
    return Path("data/mini-example/mini-example.gfa")


def _fake_conn_ctx():
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
                def executemany(self, *a, **k):
                    pass
                def copy_from(self, *a, **k):
                    pass
                def fetchone(self):
                    return None
                def fetchall(self):
                    return []
            return Cur()
        def commit(self):
            pass
        def rollback(self):
            pass
    return contextlib.nullcontext(_C())


@pytest.mark.parametrize("with_nodes", [False, True])
def test_build_e2e_minimal(monkeypatch, gfa_rel: Path, with_nodes: bool, existing_mini_example_files):
    # Import live modules
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")
    db = importlib.import_module("hap.lib.database")

    # Keep graph/prop phases, but set validations always pass
    monkeypatch.setattr(build, "validate_gfa", lambda *a, **k: ValidationResult(True, ""))
    monkeypatch.setattr(build, "validate_graph", lambda *a, **k: ValidationResult(True, ""))

    # Lightly override GFA class to avoid external tools but keep method signatures
    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def ensure_length_completeness(self):
            return None
        def get_haplotypes(self):
            return ["dummy"]
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", self.filepath)]
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def to_igraph(self):
            return types.SimpleNamespace()
    monkeypatch.setattr(gfa, "GFA", DummyGFA)

    # Avoid multiprocessing and file I/O heavy path; return minimal tuple shape
    def _fake_build(items, mr, td):
        sub_haps = []
        for n, p in items:
            rt = {"id": 1}
            st = {"id": 1}
            meta = {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}
            sub_haps.append((rt, st, meta, None))
        return sub_haps
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", _fake_build)
    monkeypatch.setattr(build, "check_name", lambda name: True)
    # When external sequence provided, avoid real preprocessing and parallel pool
    monkeypatch.setattr(
        build,
        "prepare_preprocessed_subgraphs_in_parallel",
        lambda items, sequence_file_tsv, temp_dir: [(n, p, str(Path(sequence_file_tsv))) for n, p in items],
    )
    monkeypatch.setattr(
        build,
        "build_preprocessed_subgraphs_in_parallel",
        lambda preprocessed, min_res: [({"id": 1}, {"id": 1}, {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}, tsv) for (n, p, tsv) in preprocessed],
    )
    # Avoid real DB in this e2e smoke
    monkeypatch.setattr(db, "auto_connect", _fake_conn_ctx)

    # DB connection becomes a no-op context
    monkeypatch.setattr(db, "auto_connect", _fake_conn_ctx)

    # Capture hap2db calls
    captured = {}
    monkeypatch.setattr(
        build,
        "hap2db",
        lambda hap_info, subgraphs, conn: captured.update(hap_info=hap_info, subgraphs=subgraphs),
    )

    # Assemble CLI args
    args = [
        "build",
        "run",
        str(gfa_rel),
        "-n",
        "e2e",
        "-a",
        "clade",
        "-c",
        "me",
        "-x",
        "desc",
    ]
    if with_nodes:
        nodes_fa = Path("data/mini-example/nodes.fa")
        args.extend(["--sequence-file", str(nodes_fa)])

    # Ensure absolute paths to avoid cwd issues in Click
    args[2] = str(Path(args[2]).resolve())
    if with_nodes:
        args[-1] = str(Path(args[-1]).resolve())
    r = CliRunner().invoke(cli, args)
    assert r.exit_code == 0
    assert captured["hap_info"]["name"] == "e2e"
    assert isinstance(captured["subgraphs"], list)