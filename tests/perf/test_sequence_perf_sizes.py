import time
from pathlib import Path
import psutil
import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from tests.utils.data_gen import generate_large_fasta_many_records


def _measure(cmd):
    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    t0 = time.time()
    r = cmd()
    elapsed = time.time() - t0
    delta = max(0, proc.memory_info().rss - rss_before)
    return r, elapsed, delta


def _write_csv(out: Path, elapsed: float, delta: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("metric,value\nwall_time_s,%.6f\nrss_delta_bytes,%d\n" % (elapsed, delta))


@pytest.mark.slow
@pytest.mark.parametrize("label,num_records", [("small", 1000), ("medium", 20000)])
def test_sequence_perf_sizes(tmp_path, monkeypatch, label: str, num_records: int):
    # Stub DB for perf test
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
                    return (None,)
                def fetchall(self):
                    return []
            return C()
        def commit(self):
            pass
    monkeypatch.setattr(db, "auto_connect", lambda: _C())

    fa = tmp_path / f"{label}.fa"
    generate_large_fasta_many_records(fa, num_records=num_records, seq_len=50)
    def _run():
        return CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fa)])
    r, elapsed, delta = _measure(_run)
    assert r.exit_code == 0
    out = tmp_path / ".." / ".." / ".." / "reports" / "perf" / f"sequence_add_{label}.csv"
    _write_csv(out, elapsed, delta)