import io
from pathlib import Path
import builtins
import types
import pytest
import sys

from hap.lib import sequence as seqmod


def _patch_bio_seqio_parse(monkeypatch, records):
    # records: list of (id, seq) tuples to yield
    Bio = types.ModuleType("Bio")
    SeqIO = types.ModuleType("Bio.SeqIO")

    def _parse(handle, fmt):
        class Rec:
            def __init__(self, id, seq):
                self.id = id
                self.seq = seq
        for rid, rseq in records:
            yield Rec(rid, rseq)

    SeqIO.parse = _parse
    Bio.SeqIO = SeqIO
    monkeypatch.setitem(builtins.__dict__, "Bio", Bio)
    monkeypatch.setitem(sys.modules, "Bio", Bio)
    monkeypatch.setitem(sys.modules, "Bio.SeqIO", SeqIO)


def test_read_sequences_from_fasta_fastq(monkeypatch, tmp_path):
    # simulate FASTA
    monkeypatch.setattr(seqmod, "SeqIO", types.SimpleNamespace(parse=lambda h, fmt: iter([types.SimpleNamespace(id="segA", seq="acgt")])))
    fa = tmp_path / "a.fa"
    fa.write_text(">segA\nacgt\n")
    out = list(seqmod.read_sequences_from_fasta(fa))
    assert out == [("segA", "acgt")]

    # simulate FASTQ
    monkeypatch.setattr(seqmod, "SeqIO", types.SimpleNamespace(parse=lambda h, fmt: iter([types.SimpleNamespace(id="segB", seq="AC-Gt")])))
    fq = tmp_path / "b.fq"
    fq.write_text("@segB\nAC-Gt\n+\n!!!!!\n")
    out = list(seqmod.read_sequences_from_fasta(fq))
    assert out == [("segB", "AC-Gt")]


def test_sanitize_sequence_cases_and_illegal_chars(monkeypatch, capsys):
    # valid with lowercase and gap
    assert seqmod.sanitize_sequence("ac-gn", "X") == "AC-GN"

    # empty
    seqmod.sanitize_sequence("", "E1")
    assert "[WARN] E1" in capsys.readouterr().err

    # illegal chars
    seqmod.sanitize_sequence("ABCX", "E2")
    err = capsys.readouterr().err
    assert "illegal chars" in err and "X" in err


def test_write_fasta_or_fastq_to_tsv_and_write_tsv_to_fasta(monkeypatch, tmp_path):
    # Patch reader to yield mixed valid/invalid
    def _fake_parse(handle, fmt):
        class R:
            def __init__(self, id, seq):
                self.id = id
                self.seq = seq
        yield R("s1", "acgt")
        yield R("s2", "NNNN")
        yield R("bad", "AX")  # invalid
        yield R("gap", "A-CG")

    monkeypatch.setattr(seqmod, "SeqIO", types.SimpleNamespace(parse=_fake_parse))

    fa = tmp_path / "in.fa"
    fa.write_text(">s1\nacgt\n>s2\nNNNN\n>bad\nAX\n>gap\nA-CG\n")

    tsv = tmp_path / "out.tsv"
    with tsv.open("w") as outfh:
        n = seqmod.write_fasta_or_fastq_to_tsv(fa, outfh)
    assert n == 3
    txt = tsv.read_text().strip().splitlines()
    assert txt[0] == "s1\tACGT"
    assert txt[1] == "s2\tNNNN"
    assert txt[2] == "gap\tA-CG"

    fa2 = tmp_path / "out.fa"
    with fa2.open("w") as outfa:
        m = seqmod.write_tsv_to_fasta(tsv, outfa)
    assert m == 3
    fa_lines = fa2.read_text().strip().splitlines()
    assert fa_lines == [">s1", "ACGT", ">s2", "NNNN", ">gap", "A-CG"]