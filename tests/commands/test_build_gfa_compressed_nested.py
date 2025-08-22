import gzip
from pathlib import Path
from click.testing import CliRunner
import importlib
import types

import pytest

from hap.__main__ import cli
from tests.utils.data_gen import generate_gfa_nested, gzip_file


@pytest.mark.parametrize("use_gzip", [False, True])
def test_build_nested_gfa_compressed(monkeypatch, tmp_path, use_gzip: bool):
    # Prepare nested GFA and optional gzip
    gfa = tmp_path / "nested.gfa"
    generate_gfa_nested(gfa)
    if use_gzip:
        gfa = gzip_file(gfa)

    # Stub GFA class to accept gzip path and route to our file
    gfa_mod = importlib.import_module("hap.lib.gfa")
    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def is_valid(self):
            return True
        def can_extract_length(self):
            return True
        def ensure_length_completeness(self):
            return None
        def separate_sequence(self, output_dir: str):
            return (str(Path(self.filepath)), None)
        def to_igraph(self):
            class G:
                is_dag = True
                def is_connected(self, mode="WEAK"):
                    return True
            return G()
        def get_haplotypes(self):
            return ["h1"]
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            # One chunk containing the original file
            return [("part0", str(Path(self.filepath)))]
    monkeypatch.setattr(gfa_mod, "GFA", DummyGFA)

    # Stub DB
    db = importlib.import_module("hap.lib.database")
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
                def fetchall(self):
                    return []
            return C()
        def commit(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())

    # Avoid heavy downstream by stubbing validation and rstree pipeline
    import pandas as pd
    build = importlib.import_module("hap.commands.build")
    monkeypatch.setattr(build, "validate_gfa", lambda gfa_obj: types.SimpleNamespace(valid=True, message=""))
    monkeypatch.setattr(build, "validate_graph", lambda graph: types.SimpleNamespace(valid=True, message=""))
    monkeypatch.setattr(build, "graph2rstree", lambda g: (pd.DataFrame(), pd.DataFrame(), {"sources": [], "name": ""}))
    monkeypatch.setattr(build, "calculate_properties_l2r", lambda rt, st, meta: (rt, st, meta))
    def _wrap(rt, st, meta, min_res):
        return rt, st, meta
    monkeypatch.setattr(build, "wrap_rstree", _wrap)
    monkeypatch.setattr(build, "calculate_properties_r2l", lambda rt, st, meta: (rt, st, meta))

    # Avoid heavy hap2db
    monkeypatch.setattr(build, "hap2db", lambda hap_info, subgraphs, conn: None)
    monkeypatch.setattr(build, "check_name", lambda n: True)

    args = ["build", "run", str(Path(gfa).resolve()), "-n", "nested", "-a", "c", "-c", "u", "-x", ""]
    r = CliRunner().invoke(cli, args)
    assert r.exit_code == 0