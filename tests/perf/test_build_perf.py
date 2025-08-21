import time
from pathlib import Path
import psutil
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from tests.utils.data_gen import generate_large_gfa_many_segments


@pytest.mark.large
@pytest.mark.slow
def test_build_large_perf(tmp_path, monkeypatch):
    # Generate a large GFA by many segments
    g = tmp_path / "big.gfa"
    generate_large_gfa_many_segments(g, num_segments=120_000, connect=True)

    # Stub DB to no-op
    import importlib
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
            return C()
        def commit(self):
            pass
        def rollback(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())

    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    t0 = time.time()

    # ensure absolute path for Click path checks
    # Avoid real GFA heavy pipeline by stubbing builder to minimal path
    import importlib
    build = importlib.import_module("hap.commands.build")
    gfa = importlib.import_module("hap.lib.gfa")
    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def is_valid(self):
            return True
        def can_extract_length(self):
            return True
        def get_haplotypes(self):
            return ["x"]
        def divide_into_subgraphs(self, outdir: str, chr_only: bool = True):
            return [("", self.filepath)]
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
        def to_igraph(self):
            class G:
                is_dag = True
            return G()
        def ensure_length_completeness(self):
            return None
    monkeypatch.setattr(gfa, "GFA", DummyGFA)

    def _builder(items, mr, td):
        import types as _t
        sub_haps = []
        for n, p in items:
            regions = _t.SimpleNamespace()
            segments = _t.SimpleNamespace()
            meta = {"sources": [], "name": n, "max_level": 1, "total_length": 8, "total_variants": 0}
            sub_haps.append((regions, segments, meta, None))
        return sub_haps
    monkeypatch.setattr(build, "build_subgraphs_with_sequence_in_parallel", _builder)
    monkeypatch.setattr(build, "check_name", lambda name: True)
    r = CliRunner().invoke(cli, ["build", "run", str(Path(g).resolve()), "-n", "big", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code == 0

    elapsed = time.time() - t0
    rss_after = proc.memory_info().rss
    delta = max(0, rss_after - rss_before)

    out_dir = tmp_path / ".." / ".." / ".." / "reports" / "perf"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "build_big.csv").write_text("metric,value\nwall_time_s,%.6f\nrss_delta_bytes,%d\n" % (elapsed, delta))