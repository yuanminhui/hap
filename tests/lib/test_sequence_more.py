import types
from pathlib import Path

import pytest

from hap.lib import sequence as seqmod


def test_read_sequences_empty_and_comments(monkeypatch, tmp_path):
    # Patch SeqIO.parse to return empty generator regardless of content
    monkeypatch.setattr(seqmod, "SeqIO", types.SimpleNamespace(parse=lambda h, fmt: iter([])))
    f = tmp_path / "empty.fa"
    f.write_text("#comment only\n;comment\n")
    assert list(seqmod.read_sequences_from_fasta(f)) == []


@pytest.mark.parametrize(
    "raw,label,expect_warn",
    [
        ("ACGN-", "ok", False),
        ("", "E1", True),
        ("AX*", "E2", True),
        ("   ", "E3", True),
    ],
)
def test_sanitize_variants(raw, label, expect_warn, capsys):
    out = seqmod.sanitize_sequence(raw, label)
    if expect_warn:
        err = capsys.readouterr().err
        assert "[WARN]" in err
        assert out is None
    else:
        assert out == raw.upper()


def test_write_functions_ignore_illegal(monkeypatch, tmp_path):
    def _fake_parse(handle, fmt):
        class R:
            def __init__(self, id, seq):
                self.id = id
                self.seq = seq
        yield R("s1", "ACGT")
        yield R("s2", "AX")
        yield R("gap", "A-CG")

    monkeypatch.setattr(seqmod, "SeqIO", types.SimpleNamespace(parse=_fake_parse))
    fa = tmp_path / "in.fa"
    fa.write_text("")
    tsv = tmp_path / "out.tsv"
    with tsv.open("w") as outfh:
        n = seqmod.write_fasta_or_fastq_to_tsv(fa, outfh)
    assert n == 2
    fa2 = tmp_path / "out.fa"
    with fa2.open("w") as outfa:
        m = seqmod.write_tsv_to_fasta(Path(tsv), outfa)
    assert m == 2

