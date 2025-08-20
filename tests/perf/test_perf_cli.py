import os
import time
import psutil
import pytest
from click.testing import CliRunner

from hap.__main__ import cli


def _gen_large_fasta(path: str, size_bytes: int = 100 * 1024 * 1024) -> None:
    # Generate ~size_bytes FASTA by repeating a pattern; stream to avoid large memory
    with open(path, "w") as fh:
        fh.write(">seg0\n")
        chunk = ("ACGT" * 16384) + "\n"  # 65KB line roughly
        written = 0
        i = 0
        while written < size_bytes:
            fh.write(chunk)
            written += len(chunk)
            i += 1


@pytest.mark.large
@pytest.mark.slow
def test_sequence_add_large_file(tmp_path, monkeypatch):
    # Use a large FASTA and a dummy DB connection to avoid real DB I/O
    from hap.lib import database as dbmod

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
                    return (None,)
                def fetchall(self):
                    return []
            return Cur()
        def commit(self):
            pass

    monkeypatch.setattr(dbmod, "auto_connect", lambda: _C())

    large_fa = tmp_path / "large.fa"
    _gen_large_fasta(str(large_fa))

    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    t0 = time.time()

    # Run sequence add; we don't check DB effects, just completion and resource bounds
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(large_fa)])

    elapsed = time.time() - t0
    rss_after = proc.memory_info().rss
    peak_delta = max(0, rss_after - rss_before)

    # Basic assertions: should exit cleanly, time under a generous cap, memory delta below ~300MB
    assert r.exit_code == 0
    assert elapsed < 30
    assert peak_delta < 300 * 1024 * 1024

    # Emit simple CSV under reports/perf
    out_dir = tmp_path / ".." / ".." / ".." / "reports" / "perf"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sequence_add_large.csv").write_text(
        "metric,value\nwall_time_s,%.6f\nrss_delta_bytes,%d\n" % (elapsed, peak_delta)
    )

