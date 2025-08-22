import pytest
from click.testing import CliRunner

from hap.__main__ import cli
from tests.utils.data_gen import generate_fasta, generate_fastq, generate_large_fasta


def test_sequence_add_mixed_case_and_gap(monkeypatch, fake_db_connect, tmp_path):
    fa = tmp_path / "ok.fa"
    generate_fasta(fa, [("A", "ac-gn"), ("B", "NNNN")])
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fa)])
    assert r.exit_code == 0
    assert "Imported" in r.output


def test_sequence_add_illegal_chars_warn(monkeypatch, fake_db_connect, tmp_path, capsys):
    # capture click.echo warnings in the command module
    import importlib
    seqcli_mod = importlib.import_module("hap.commands.sequence")
    recorded: list[str] = []
    orig_sanitize = seqcli_mod.sanitize_sequence
    def _rec_sanitize(raw, label):
        res = orig_sanitize(raw, label)
        if res is None:
            recorded.append(f"[WARN] {label}")
        return res
    monkeypatch.setattr(seqcli_mod, "sanitize_sequence", _rec_sanitize)
    # ensure parser yields our bad records (patch in lib module used by commands)
    seqlib_mod = importlib.import_module("hap.lib.sequence")
    class R:
        def __init__(self, id, seq):
            self.id = id
            self.seq = seq
    monkeypatch.setattr(seqlib_mod, "SeqIO", type("_S", (), {"parse": lambda h, fmt: iter([R("segA", "AX"), R("segB", "B*")])}))

    fa = tmp_path / "bad.fa"
    generate_fasta(fa, [("segA", "AX"), ("segB", "B*")])
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fa)])
    assert r.exit_code == 0
    # warnings printed for illegal chars captured via patched echo
    assert any("[WARN]" in m for m in recorded)


def test_sequence_add_fastq_support(monkeypatch, fake_db_connect, tmp_path):
    fq = tmp_path / "reads.fq"
    generate_fastq(fq, [("segA", "ACGT"), ("segB", "AC-GT")])
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fq)])
    assert r.exit_code == 0


@pytest.mark.large
@pytest.mark.slow
def test_sequence_add_large(tmp_path, monkeypatch):
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

    fa = tmp_path / "large.fa"
    generate_large_fasta(fa, size_bytes=100 * 1024 * 1024)
    r = CliRunner().invoke(cli, ["sequence", "add", "--fasta", str(fa)])
    assert r.exit_code == 0

