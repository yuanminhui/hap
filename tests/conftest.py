"""
Root conftest.py for hap tests.
Provides shared fixtures across all test modules.
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(__file__).parent / "fixtures"
MINI_EXAMPLE_DIR = FIXTURES_DIR / "mini-example"
MEDIUM_EXAMPLE_DIR = FIXTURES_DIR / "medium-example"
HAP_DATA_DIR = REPO_ROOT / "data"
MINI_GFA = HAP_DATA_DIR / "mini-example" / "mini-example.gfa"

# ---------------------------------------------------------------------------
# Test environment markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no external deps)")
    config.addinivalue_line("markers", "integration: Requires PostgreSQL")
    config.addinivalue_line("markers", "smoke: Smoke test")
    config.addinivalue_line("markers", "perf: Performance benchmark")


# ---------------------------------------------------------------------------
# DB connection helpers
# ---------------------------------------------------------------------------

TEST_DB_ENV = {
    "HAP_DB_HOST": os.environ.get("HAP_DB_HOST", "localhost"),
    "HAP_DB_PORT": os.environ.get("HAP_DB_PORT", "15432"),
    "HAP_DB_USER": os.environ.get("HAP_DB_USER", "haptest"),
    "HAP_DB_PASSWORD": os.environ.get("HAP_DB_PASSWORD", "haptest"),
    "HAP_DB_DBNAME": os.environ.get("HAP_DB_DBNAME", "haptest"),
}


@pytest.fixture(scope="session")
def db_env():
    """Return test database environment variables."""
    return TEST_DB_ENV.copy()


@pytest.fixture(scope="session")
def db_connection_info():
    """Return psycopg2-compatible connection dict."""
    return {
        "host": TEST_DB_ENV["HAP_DB_HOST"],
        "port": int(TEST_DB_ENV["HAP_DB_PORT"]),
        "user": TEST_DB_ENV["HAP_DB_USER"],
        "password": TEST_DB_ENV["HAP_DB_PASSWORD"],
        "dbname": TEST_DB_ENV["HAP_DB_DBNAME"],
    }


@pytest.fixture(scope="session")
def db_available(db_connection_info):
    """Check if test DB is available; skip if not."""
    try:
        import psycopg2
        conn = psycopg2.connect(**db_connection_info, connect_timeout=3)
        conn.close()
        return True
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")


@pytest.fixture
def db_conn(db_available, db_connection_info):
    """Return an open, auto-rolling-back psycopg2 connection."""
    import psycopg2
    conn = psycopg2.connect(**db_connection_info)
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


# ---------------------------------------------------------------------------
# GFA fixture helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mini_gfa_path():
    """Path to the mini-example GFA file."""
    assert MINI_GFA.exists(), f"mini-example GFA not found: {MINI_GFA}"
    return str(MINI_GFA)


@pytest.fixture(scope="session")
def mini_example_dir():
    return MINI_EXAMPLE_DIR


@pytest.fixture(scope="session")
def medium_example_dir():
    return MEDIUM_EXAMPLE_DIR


@pytest.fixture
def tmp_gfa(tmp_path):
    """
    Factory fixture: call tmp_gfa(content) to get a Path to a temp GFA file.
    """
    def _make(content: str, filename: str = "test.gfa") -> Path:
        p = tmp_path / filename
        p.write_text(content)
        return p

    return _make


@pytest.fixture
def simple_gfa_path(tmp_gfa):
    """A minimal valid GFA 1.0 file for fast unit tests."""
    content = (
        "H\tVN:Z:1.0\n"
        "S\ts1\tATCG\tLN:i:4\n"
        "S\ts2\tGCTA\tLN:i:4\n"
        "L\ts1\t+\ts2\t+\t0M\n"
        "P\tsmp1#0#chr1\ts1+,s2+\t0M\n"
    )
    return tmp_gfa(content, "simple.gfa")


@pytest.fixture
def gfa_11_path(tmp_gfa):
    """A minimal valid GFA 1.1 file (W-lines)."""
    content = (
        "H\tVN:Z:1.1\n"
        "S\ts1\tATCGATCGAT\tLN:i:10\n"
        "S\ts2\tGCTA\tLN:i:4\n"
        "L\ts1\t+\ts2\t+\t0M\n"
        "W\tsmp1\t0\tchr1\t*\t*\t>s1>s2\n"
    )
    return tmp_gfa(content, "gfa11.gfa")


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def hap_env(db_env):
    """Env dict suitable for subprocess calls to `hap`."""
    env = os.environ.copy()
    env.update(db_env)
    return env


@pytest.fixture
def mock_connection_info():
    """Used in legacy database tests."""
    return {
        "host": "localhost",
        "port": 5432,
        "user": "test_user",
        "password": "test_password",
        "dbname": "test_db",
    }
