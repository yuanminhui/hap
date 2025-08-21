from click.testing import CliRunner
import importlib
import types
import pytest

from hap.__main__ import cli


def test_sequence_get_by_regex(fake_db_connect):
    r = CliRunner().invoke(cli, ["sequence", "get", "--regex", "seg.*", "--format", "tsv"]) 
    assert r.exit_code == 0
    out = r.output.strip().splitlines()
    # Our fake DB contains segA/segB with ACGT
    assert any(line.startswith("segA\t") for line in out)


def test_sequence_edit_and_delete(fake_db_connect):
    # edit segA to TTTT
    r1 = CliRunner().invoke(cli, ["sequence", "edit", "segA", "TTTT"]) 
    assert r1.exit_code == 0
    # delete segA and segB
    r2 = CliRunner().invoke(cli, ["sequence", "delete", "segA", "segB"]) 
    assert r2.exit_code == 0
    assert "Deleted 2 sequences" in r2.output or "Deleted 2" in r2.output

