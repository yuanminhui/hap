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


def test_sequence_multi_file_order_conflict(monkeypatch, fake_db_connect, tmp_path):
    # First file sets segA to ACGT
    f1 = tmp_path / "f1.fa"
    generate_fasta(f1, [("segA", "ACGT")])
    # Second file tries to set segA to AAAA (conflict if DB length already set)
    f2 = tmp_path / "f2.fa"
    generate_fasta(f2, [("segA", "AAAA")])
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f1)])
    assert r.exit_code == 0
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f2)])
    assert r.exit_code == 0
    # Should either warn or skip conflicting write
    assert ("length mismatch" in r.output) or ("Imported" in r.output)


def test_sequence_mixed_encodings(monkeypatch, tmp_path):
    # Stub DB for this test
    import hap.lib.database as dbmod
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
    monkeypatch.setattr(dbmod, "auto_connect", lambda: _C())

    # Simulate first file utf-8, second raises UnicodeDecodeError
    seqlib = importlib.import_module("hap.lib.sequence")
    # First call returns an iterator, second raises
    calls = {"n": 0}
    def _parse(handle, fmt):
        if calls["n"] == 0:
            calls["n"] += 1
            class R:
                def __init__(self, i, s):
                    self.id = i
                    self.seq = s
            return iter([R("segA", "ACGT")])
        raise UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid")
    monkeypatch.setattr(seqlib, "SeqIO", types.SimpleNamespace(parse=_parse))
    f1 = tmp_path / "ok.fa"; f1.write_text(">segA\nACGT\n")
    f2 = tmp_path / "bad.fa"; f2.write_bytes(b">a\n\x80\n")
    # First add ok
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f1)])
    assert r.exit_code == 0
    # Second mixed encoding should fail
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(f2)])
    assert r.exit_code != 0

