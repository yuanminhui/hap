import contextlib
import importlib
import types
from click.testing import CliRunner
from hap.__main__ import cli
from tests.data.small.mini_example import ensure_small_dataset
from hap.lib.util_obj import ValidationResult


def test_build_run_small_smoke(monkeypatch, tmp_path):
    ds = ensure_small_dataset(tmp_path / "mini")

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
            return types.SimpleNamespace()

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
                    # Simulate returning an id on INSERT ... RETURNING
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

    monkeypatch.setattr(db, "auto_connect", lambda: contextlib.nullcontext(_C()))
    # Avoid DataFrame-heavy hap2db; just capture input shape
    monkeypatch.setattr(
        build,
        "hap2db",
        lambda hap_info, subgraphs, conn: None,
    )

    r = CliRunner().invoke(
        cli,
        [
            "build",
            "run",
            str(ds["gfa"]),
            "-n",
            "smoke",
            "-a",
            "clade",
            "-c",
            "me",
            "-x",
            "desc",
        ],
    )
    assert r.exit_code == 0

