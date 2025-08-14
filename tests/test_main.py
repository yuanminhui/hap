"""Test cases for the __main__ module."""

import pytest
from click.testing import CliRunner

from hap import __main__


@pytest.fixture
def runner() -> CliRunner:
    """Fixture for invoking command-line interfaces."""
    return CliRunner()


def test_main_help_succeeds(runner: CliRunner) -> None:
    """It exits with a status code of zero when showing help."""
    result = runner.invoke(__main__.cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.output or "hap" in result.output
