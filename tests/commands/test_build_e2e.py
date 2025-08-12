import contextlib
import importlib
from pathlib import Path
import types
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from hap.lib.util_obj import ValidationResult


@pytest.fixture(scope="session")
def gfa_abs(prepare_mini_example_files) -> Path:
    return prepare_mini_example_files["mirror_gfa"]


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


@pytest.mark.parametrize(
    "with_nodes",
    [False, True],
)
def test_build_e2e_minimal(monkeypatch, gfa_abs: Path, with_nodes: bool, prepare_mini_example_files):
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
    monkeypatch.setattr(
        build,
        "build_subgraphs_with_sequence_in_parallel",
        lambda items, mr, td: [(types.SimpleNamespace(), types.SimpleNamespace(), {"sources": [], "name": n}, None) for n, p in items],
    )

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
        str(gfa_abs),
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
        nodes_fa = prepare_mini_example_files["mirror_nodes"]
        args.extend(["--sequence-file", str(nodes_fa)])

    r = CliRunner().invoke(cli, args)
    assert r.exit_code == 0
    assert captured["hap_info"]["name"] == "e2e"
    assert isinstance(captured["subgraphs"], list)