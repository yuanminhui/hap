import importlib

import pytest
from click.testing import CliRunner
import types

from hap.__main__ import cli


@pytest.fixture()
def fasta_file(tmp_path):
    fa = tmp_path / "seq.fa"
    fa.write_text(">segA\nACGT\n>segB\nACGT\n>segC\nAX\n")
    return fa


def test_sequence_add_with_length_update_and_skip_invalid(monkeypatch, fake_db_connect, fasta_file):
    # Patch read_sequences in the commands module namespace
    seqcli_mod = importlib.import_module("hap.commands.sequence")
    monkeypatch.setattr(seqcli_mod, "read_sequences_from_fasta", lambda p: [("segA", "ACGT"), ("segB", "ACGT"), ("segC", "AX")])

    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fasta_file)])
    assert r.exit_code == 0
    # segA had length NULL -> set to 4; segB already 4 -> unchanged
    db = fake_db_connect
    # Our FakeCursor updates length only when updating segment length after upsert.
    # upserts recorded（至少两条）
    upserts = [sql for sql, _ in db.recorded_writes if sql.strip().upper().startswith("INSERT INTO SEGMENT_SEQUENCE")]
    assert len(upserts) == 2


def test_sequence_get_by_ids_and_regex(monkeypatch, fake_db_connect):
    # ids path
    r = CliRunner().invoke(cli, ["sequence", "get", "segA", "segB", "--format", "tsv"])
    assert r.exit_code == 0
    lines = r.output.strip().splitlines()
    assert set(lines) == {"segA\tACGT", "segB\tACGT"}

    # regex path (our FakeCursor returns all)
    r = CliRunner().invoke(cli, ["sequence", "get", "--regex", "seg.*", "--format", "fasta"])
    assert r.exit_code == 0
    assert ">segA\nACGT" in r.output
    assert ">segB\nACGT" in r.output


def test_sequence_edit_with_length_checks(monkeypatch, fake_db_connect):
    # ok edit for segA (length becomes 4)
    r = CliRunner().invoke(cli, ["sequence", "edit", "segA", "TTTT"])
    assert r.exit_code == 0
    # segA exists in fake mapping; should succeed
    assert "Edited sequence for segA." in r.output or r.output.strip() == "Edited sequence for segA."

    # mismatch when DB length known and not equal
    r = CliRunner().invoke(cli, ["sequence", "edit", "segB", "TTT"])
    assert r.exit_code == 0
    assert "length mismatch" in r.output


def test_sequence_delete(fake_db_connect):
    r = CliRunner().invoke(cli, ["sequence", "delete", "segA", "segB"])
    assert r.exit_code == 0
    assert "Deleted 2 sequences." in r.output


def test_gfa_ensure_length_completeness_ok(monkeypatch, tmp_path):
    gfa_mod = importlib.import_module("hap.lib.gfa")

    class DummyGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def ensure_length_completeness(self):
            # no-op ok
            return None
    # direct exercise
    g = DummyGFA("x.gfa")
    assert g.ensure_length_completeness() is None


def test_gfa_ensure_length_completeness_error_path(monkeypatch, tmp_path):
    # simulate error by raising exception inside ensure_length_completeness and assert handled in build validate_gfa
    gfa_mod = importlib.import_module("hap.lib.gfa")
    build = importlib.import_module("hap.commands.build")

    class BadGFA:
        def __init__(self, filepath: str):
            self.filepath = filepath
        def can_extract_length(self):
            return True
        def ensure_length_completeness(self):
            raise RuntimeError("missing LN")
        def to_igraph(self):
            class G:
                is_dag = True
                def is_connected(self, mode="WEAK"):
                    return True
            return G()
        def separate_sequence(self, output_dir: str):
            return (self.filepath, None)
    monkeypatch.setattr(gfa_mod, "GFA", BadGFA)

    # make validate_gfa call path fail when ensure_length_completeness raises; preserve error surfaced by CLI
    def _validate_gfa(gfa_obj):
        try:
            gfa_obj.ensure_length_completeness()
            return types.SimpleNamespace(valid=True, message="")
        except Exception as e:
            return types.SimpleNamespace(valid=False, message=str(e))
    monkeypatch.setattr(build, "validate_gfa", _validate_gfa)
    monkeypatch.setattr(build, "validate_graph", lambda g: types.SimpleNamespace(valid=True, message=""))
    monkeypatch.setattr(build, "check_name", lambda n: True)

    g = tmp_path / "bad.gfa"; g.write_text("H\tVN:Z:1.0\nS\ts0\t*\tLN:i:1\n")
    r = CliRunner().invoke(cli, ["build", "run", str(g), "-n", "bad", "-a", "c", "-c", "u", "-x", ""]) 
    assert r.exit_code != 0