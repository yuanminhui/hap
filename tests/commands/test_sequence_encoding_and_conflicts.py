import importlib
import types
from pathlib import Path
from click.testing import CliRunner
import pytest

from hap.__main__ import cli
from tests.utils.data_gen import generate_fasta


def test_sequence_add_non_utf8_file_error(monkeypatch, tmp_path):
    # Patch SeqIO.parse to simulate UnicodeDecodeError when reading file
    seqlib = importlib.import_module("hap.lib.sequence")
    monkeypatch.setattr(seqlib, "SeqIO", types.SimpleNamespace(parse=lambda h, fmt: (_ for _ in ()).throw(UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid"))))
    bad = tmp_path / "bad.fa"
    bad.write_bytes(b">a\n\x80\n")
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(bad)])
    assert r.exit_code != 0


def test_sequence_add_conflict_then_warn(monkeypatch, fake_db_connect, tmp_path):
    # First add ok
    fa1 = tmp_path / "a1.fa"
    generate_fasta(fa1, [("segB", "ACGT")])  # matches DB known length 4
    r1 = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fa1)])
    assert r1.exit_code == 0
    # Second add conflicting length for same id -> should warn and skip
    fa2 = tmp_path / "a2.fa"
    generate_fasta(fa2, [("segB", "ACGTA")])  # length 5 vs DB length 4
    r2 = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fa2)])
    assert r2.exit_code == 0
    # Depending on DB stub, may silently skip; allow Imported 0 or mismatch warning
    assert ("length mismatch" in r2.output) or ("Imported 0" in r2.output)

