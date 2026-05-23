"""
Unit tests for hap.lib.sequence — sequence parsing and sanitization.
"""

import io
from pathlib import Path

import pytest

from hap.lib.sequence import (
    sanitize_sequence,
    read_sequences_from_fasta,
    write_fasta_or_fastq_to_tsv,
    write_tsv_to_fasta,
)


FASTA_CONTENT = """\
>seg1
ATCGATCGAT
>seg2
GCTAGCTAGC
>seg3
NNNNATCG
"""

FASTQ_CONTENT = """\
@seg1
ATCGATCGAT
+
IIIIIIIIII
@seg2
GCTAGCTAGC
+
JJJJJJJJJJ
"""


class TestSanitizeSequence:
    def test_valid_uppercase(self):
        assert sanitize_sequence("ATCGN", "label") == "ATCGN"

    def test_lowercase_is_uppercased(self):
        assert sanitize_sequence("atcgn", "label") == "ATCGN"

    def test_dash_allowed(self):
        assert sanitize_sequence("ATC-GN", "label") == "ATC-GN"

    def test_invalid_chars_returns_none(self, capfd):
        result = sanitize_sequence("ATCGX", "seg1")
        assert result is None
        captured = capfd.readouterr()
        assert "seg1" in captured.err or "X" in captured.err

    def test_empty_string_returns_none(self, capfd):
        result = sanitize_sequence("", "label")
        assert result is None

    def test_mixed_valid_invalid(self, capfd):
        result = sanitize_sequence("ATCG12", "seg_bad")
        assert result is None

    def test_all_n(self):
        assert sanitize_sequence("NNNN", "n-seg") == "NNNN"


class TestReadSequencesFromFasta:
    def test_read_fasta(self, tmp_path):
        p = tmp_path / "test.fasta"
        p.write_text(FASTA_CONTENT)
        seqs = list(read_sequences_from_fasta(p))
        assert len(seqs) == 3
        ids = [s[0] for s in seqs]
        assert "seg1" in ids
        assert "seg2" in ids
        assert "seg3" in ids

    def test_read_fastq(self, tmp_path):
        p = tmp_path / "test.fastq"
        p.write_text(FASTQ_CONTENT)
        seqs = list(read_sequences_from_fasta(p))
        assert len(seqs) == 2
        assert seqs[0] == ("seg1", "ATCGATCGAT")

    def test_fasta_fa_extension(self, tmp_path):
        p = tmp_path / "test.fa"
        p.write_text(">s1\nATCG\n")
        seqs = list(read_sequences_from_fasta(p))
        assert seqs[0] == ("s1", "ATCG")


class TestWriteFastaToTsv:
    def test_basic_write(self, tmp_path):
        p = tmp_path / "in.fasta"
        p.write_text(FASTA_CONTENT)
        out = io.StringIO()
        n = write_fasta_or_fastq_to_tsv(p, out)
        assert n == 3
        out.seek(0)
        lines = out.read().strip().split("\n")
        assert len(lines) == 3
        # Each line should be tab-separated id\tSEQ
        for line in lines:
            parts = line.split("\t")
            assert len(parts) == 2
            assert len(parts[1]) > 0

    def test_invalid_sequences_skipped(self, tmp_path, capfd):
        p = tmp_path / "in.fasta"
        p.write_text(">bad\nATCGXXX\n>good\nATCGN\n")
        out = io.StringIO()
        n = write_fasta_or_fastq_to_tsv(p, out)
        assert n == 1  # only 'good' written
        captured = capfd.readouterr()
        assert "bad" in captured.err

    def test_returns_count(self, tmp_path):
        p = tmp_path / "in.fa"
        p.write_text(">a\nATCG\n>b\nGCTA\n>c\nNNNN\n")
        out = io.StringIO()
        n = write_fasta_or_fastq_to_tsv(p, out)
        assert n == 3


class TestWriteTsvToFasta:
    def test_basic_roundtrip(self, tmp_path):
        tsv = tmp_path / "seqs.tsv"
        tsv.write_text("seg1\tATCGATCGAT\nseg2\tGCTAGCTA\n")
        out = io.StringIO()
        n = write_tsv_to_fasta(tsv, out)
        assert n == 2
        out.seek(0)
        text = out.read()
        assert ">seg1\n" in text
        assert "ATCGATCGAT\n" in text
        assert ">seg2\n" in text

    def test_skips_malformed_lines(self, tmp_path):
        tsv = tmp_path / "bad.tsv"
        tsv.write_text("seg1\tATCG\nBAD_LINE_NO_TAB\nseg2\tGCTA\n")
        out = io.StringIO()
        n = write_tsv_to_fasta(tsv, out)
        assert n == 2
