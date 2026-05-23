"""
Integration tests for the `hap build` CLI command.

These tests require a live PostgreSQL instance (started via infra/compose.test.yaml).
They are tagged with @pytest.mark.integration and skipped if DB is unavailable.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# Path to mini-example GFA (bundled with the repo)
REPO_ROOT = Path(__file__).parent.parent.parent
MINI_GFA = REPO_ROOT / "data" / "mini-example" / "mini-example.gfa"
TEST_ARTIFACTS = REPO_ROOT.parent / "test-artifacts"
BENCHMARK_FILE = TEST_ARTIFACTS / "summary" / "benchmark.json"


def _run_hap(args: list[str], env: dict, timeout: int = 120) -> subprocess.CompletedProcess:
    """Run `hap` CLI via subprocess."""
    cmd = [sys.executable, "-m", "hap"] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )


def _save_benchmark(key: str, elapsed_s: float):
    """Append a benchmark result to test-artifacts/summary/benchmark.json."""
    TEST_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (TEST_ARTIFACTS / "summary").mkdir(parents=True, exist_ok=True)

    benchmarks = {}
    if BENCHMARK_FILE.exists():
        try:
            benchmarks = json.loads(BENCHMARK_FILE.read_text())
        except Exception:
            benchmarks = {}
    benchmarks[key] = {"elapsed_s": round(elapsed_s, 3)}
    BENCHMARK_FILE.write_text(json.dumps(benchmarks, indent=2))


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def initialized_db(db_available, db_conn):
    """Ensure the HAP schema exists before running build tests."""
    import psycopg2
    from hap.lib.database import create_tables_if_not_exist
    create_tables_if_not_exist(db_conn)
    db_conn.commit()
    yield db_conn


# ---------------------------------------------------------------------------
# `hap build` CLI tests
# ---------------------------------------------------------------------------

class TestHapBuildCLI:
    """Test `hap build` end-to-end with mini-example."""

    @pytest.fixture(autouse=True)
    def _require_mini_gfa(self):
        if not MINI_GFA.exists():
            pytest.skip(f"mini-example GFA not found: {MINI_GFA}")

    def test_build_mini_example_exit_code(self, initialized_db, hap_env, tmp_path):
        """hap build should exit 0 on mini-example."""
        start = time.perf_counter()
        result = _run_hap(
            ["build", str(MINI_GFA), "--name", "test-mini-build"],
            hap_env,
        )
        elapsed = time.perf_counter() - start
        _save_benchmark("hap_build_mini_example", elapsed)

        # Print output for debugging if failed
        if result.returncode != 0:
            print("STDOUT:", result.stdout[-3000:])
            print("STDERR:", result.stderr[-3000:])

        assert result.returncode == 0, (
            f"hap build failed (rc={result.returncode}):\n"
            f"STDERR: {result.stderr[-2000:]}"
        )

    def test_build_creates_pangenome_record(self, initialized_db, hap_env):
        """After build, pangenome table should have a record."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pangenome WHERE name = 'test-mini-build'")
            count = cur.fetchone()[0]
        assert count >= 1, "No pangenome record created after build"

    def test_build_creates_subgraph_record(self, initialized_db, hap_env):
        """Build should create subgraph records (one per chromosome)."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM subgraph s
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
            """)
            count = cur.fetchone()[0]
        assert count >= 1, "No subgraph records created"

    def test_build_creates_region_records(self, initialized_db):
        """Build should create region records."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM region r
                JOIN subgraph s ON r.subgraph_id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
            """)
            count = cur.fetchone()[0]
        assert count > 0, "No region records created"

    def test_build_creates_segment_records(self, initialized_db):
        """Build should create segment records."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM segment seg
                JOIN region r ON seg.region_id = r.id
                JOIN subgraph s ON r.subgraph_id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
            """)
            count = cur.fetchone()[0]
        assert count > 0, "No segment records created"

    def test_build_creates_path_records(self, initialized_db):
        """Build should create path records (one per genome per subgraph)."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM path pt
                JOIN subgraph s ON pt.subgraph_id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
            """)
            count = cur.fetchone()[0]
        assert count >= 3, f"Expected at least 3 path records (one per sample), got {count}"

    def test_build_creates_path_segment_coordinates(self, initialized_db):
        """Build should create path-segment coordinate records."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM path_segment_coordinate psc
                JOIN path pt ON psc.path_id = pt.id
                JOIN subgraph s ON pt.subgraph_id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
            """)
            count = cur.fetchone()[0]
        assert count > 0, "No path_segment_coordinate records created"

    def test_build_coordinate_validity(self, initialized_db):
        """Segment coordinates should be valid non-negative ranges."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT seg.id, seg.coordinate
                FROM segment seg
                JOIN region r ON seg.region_id = r.id
                JOIN subgraph s ON r.subgraph_id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
                LIMIT 20
            """)
            rows = cur.fetchall()
        assert len(rows) > 0
        for row in rows:
            coord = row[1]
            # Coordinate is an INT8RANGE string like '[0,100)'
            assert coord is not None, f"Null coordinate for segment {row[0]}"

    def test_build_level_range_validity(self, initialized_db):
        """Region level_range should have valid non-negative bounds."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.id, r.level_range
                FROM region r
                JOIN subgraph s ON r.subgraph_id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
                LIMIT 20
            """)
            rows = cur.fetchall()
        assert len(rows) > 0
        for row in rows:
            assert row[1] is not None, f"Null level_range for region {row[0]}"

    def test_build_subgraph_statistics_exist(self, initialized_db):
        """Subgraph statistics should be populated after build."""
        conn = initialized_db
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ss.max_level, ss.total_length
                FROM subgraph_statistics ss
                JOIN subgraph s ON ss.id = s.id
                JOIN pangenome p ON s.pangenome_id = p.id
                WHERE p.name = 'test-mini-build'
            """)
            rows = cur.fetchall()
        assert len(rows) >= 1
        for row in rows:
            assert row[0] >= 0, "max_level should be >= 0"
            assert row[1] > 0, "total_length should be > 0"


# ---------------------------------------------------------------------------
# `hap build` help / smoke
# ---------------------------------------------------------------------------

class TestHapBuildSmoke:
    def test_help_exits_zero(self, hap_env):
        result = _run_hap(["build", "--help"], hap_env)
        assert result.returncode == 0
        assert "build" in result.stdout.lower()

    def test_missing_gfa_exits_nonzero(self, hap_env, tmp_path):
        result = _run_hap(
            ["build", "run", str(tmp_path / "nonexistent.gfa"), "--name", "fail"],
            hap_env,
        )
        assert result.returncode != 0
