"""
Unit tests for hap.lib.gfa — GFA file parsing class.
"""

import os
from pathlib import Path

import pytest

from hap.lib.gfa import GFA
from hap.lib.error import DataInvalidError


# ============================================================
# GFA instantiation
# ============================================================

class TestGFAInit:
    def test_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            GFA(str(tmp_path / "nonexistent.gfa"))

    def test_raises_for_invalid_file(self, tmp_path):
        p = tmp_path / "bad.gfa"
        p.write_text("this is not a gfa file at all\n")
        with pytest.raises(DataInvalidError):
            GFA(str(p))

    def test_valid_gfa10(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g is not None

    def test_valid_gfa11(self, gfa_11_path):
        g = GFA(str(gfa_11_path))
        assert g is not None

    def test_valid_mini_example(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        assert g is not None


# ============================================================
# Version detection
# ============================================================

class TestGFAVersion:
    def test_version_10_from_header(self, tmp_gfa):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\tATCG\tLN:i:4\n"
            "S\ts2\tGCTA\tLN:i:4\n"
            "L\ts1\t+\ts2\t+\t0M\n"
            "P\tchr1\ts1+,s2+\t0M\n"
        )
        g = GFA(str(p))
        assert g.version == 1.0

    def test_version_11_from_header(self, gfa_11_path):
        g = GFA(str(gfa_11_path))
        assert g.version == 1.1

    def test_mini_example_version(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        assert g.version == 1.1


# ============================================================
# contains_* predicates
# ============================================================

class TestGFAContains:
    def test_contains_segment_true(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.contains_segment() is True

    def test_contains_edge_gfa10(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.contains_edge() is True

    def test_contains_path_gfa10(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.contains_path() is True

    def test_contains_path_gfa11(self, gfa_11_path):
        g = GFA(str(gfa_11_path))
        assert g.contains_path() is True

    def test_contains_sequence_with_sequence(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.contains_sequence() is True

    def test_contains_sequence_without_sequence(self, tmp_gfa):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\t*\tLN:i:4\n"
            "S\ts2\t*\tLN:i:4\n"
            "L\ts1\t+\ts2\t+\t0M\n"
            "P\tchr1\ts1+,s2+\t0M\n"
        )
        g = GFA(str(p))
        assert g.contains_sequence() is False

    def test_contains_length_with_ln_tag(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.contains_length() is True

    def test_contains_length_without_ln_tag(self, tmp_gfa):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\tATCG\n"
            "S\ts2\tGCTA\n"
            "L\ts1\t+\ts2\t+\t0M\n"
            "P\tchr1\ts1+,s2+\t0M\n"
        )
        g = GFA(str(p))
        assert g.contains_length() is False


# ============================================================
# is_valid
# ============================================================

class TestGFAIsValid:
    def test_valid_gfa(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.is_valid() is True


# ============================================================
# can_extract_length
# ============================================================

class TestGFACanExtractLength:
    def test_can_extract_with_sequence(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        assert g.can_extract_length() is True

    def test_can_extract_with_ln_tag(self, gfa_11_path):
        g = GFA(str(gfa_11_path))
        assert g.can_extract_length() is True


# ============================================================
# ensure_length_completeness
# ============================================================

class TestEnsureLengthCompleteness:
    def test_ok_when_all_have_ln(self, gfa_11_path):
        g = GFA(str(gfa_11_path))
        g.ensure_length_completeness()  # should not raise

    def test_raises_when_missing_ln(self, tmp_gfa):
        from hap.lib.error import DataIncompleteError
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\tATCG\n"      # no LN tag
            "S\ts2\tGCTA\tLN:i:4\n"
            "L\ts1\t+\ts2\t+\t0M\n"
            "P\tchr1\ts1+,s2+\t0M\n"
        )
        g = GFA(str(p))
        with pytest.raises(DataIncompleteError):
            g.ensure_length_completeness()


# ============================================================
# get_genome_names
# ============================================================

class TestGetGenomeNames:
    def test_genome_names_mini_example(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        names = g.get_genome_names()
        assert isinstance(names, list)
        assert len(names) == 3
        assert "smp1#0" in names
        assert "smp2#0" in names
        assert "smp3#0" in names

    def test_genome_names_gfa10(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        names = g.get_genome_names()
        assert isinstance(names, list)


# ============================================================
# parse_paths
# ============================================================

class TestParsePaths:
    def test_parse_paths_mini_example(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        paths = g.parse_paths()
        assert len(paths) == 3
        for p in paths:
            assert "name" in p
            assert "walk" in p
            assert "sample" in p
            assert "haplotype_id" in p
            assert "genome_name" in p
            assert isinstance(p["walk"], list)
            assert len(p["walk"]) > 0

    def test_parse_paths_pansn_naming(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        paths = g.parse_paths()
        samples = {p["sample"] for p in paths}
        assert "smp1" in samples
        assert "smp2" in samples
        assert "smp3" in samples

    def test_parse_paths_no_path_raises(self, tmp_gfa):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\tATCG\tLN:i:4\n"
            "S\ts2\tGCTA\tLN:i:4\n"
            "L\ts1\t+\ts2\t+\t0M\n"
        )
        g = GFA(str(p))
        with pytest.raises(DataInvalidError):
            g.parse_paths()


# ============================================================
# validate_path_lines
# ============================================================

class TestValidatePathLines:
    def test_valid_gfa10_paths(self, simple_gfa_path):
        g = GFA(str(simple_gfa_path))
        ok, errors = g.validate_path_lines()
        assert ok is True
        assert errors == []

    def test_valid_gfa11_paths(self, gfa_11_path):
        g = GFA(str(gfa_11_path))
        ok, errors = g.validate_path_lines()
        assert ok is True
        assert errors == []

    def test_no_paths_returns_false(self, tmp_gfa):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\tATCG\tLN:i:4\n"
            "S\ts2\tGCTA\tLN:i:4\n"
            "L\ts1\t+\ts2\t+\t0M\n"
        )
        g = GFA(str(p))
        ok, errors = g.validate_path_lines()
        assert ok is False
        assert len(errors) > 0


# ============================================================
# extract_subgraph_names
# ============================================================

class TestExtractSubgraphNames:
    def test_mini_example_chr1(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        names = g.extract_subgraph_names(chr_only=False)
        assert isinstance(names, list)
        assert "chr1" in names

    def test_chr_only_filter(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        names = g.extract_subgraph_names(chr_only=True)
        assert all(n.lower().startswith("chr") for n in names)


# ============================================================
# separate_sequence
# ============================================================

class TestSeparateSequence:
    def test_separate_creates_seq_tsv(self, mini_gfa_path, tmp_path):
        g = GFA(mini_gfa_path)
        out_gfa, out_seq = g.separate_sequence(str(tmp_path), overwrite=True)
        assert out_gfa is not None
        assert Path(out_gfa).exists()
        if out_seq:
            assert Path(out_seq).exists()

    def test_no_sequence_copies_gfa(self, tmp_gfa, tmp_path):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "S\ts1\t*\tLN:i:4\n"
            "S\ts2\t*\tLN:i:4\n"
            "L\ts1\t+\ts2\t+\t0M\n"
            "P\tchr1\ts1+,s2+\t0M\n"
        )
        g = GFA(str(p))
        out_gfa, out_seq = g.separate_sequence(str(tmp_path), overwrite=True)
        assert Path(out_gfa).exists()
        assert out_seq is None


# ============================================================
# to_igraph
# ============================================================

class TestToIgraph:
    def test_mini_example_to_igraph(self, mini_gfa_path):
        g = GFA(mini_gfa_path)
        graph = g.to_igraph()
        import igraph as ig
        assert isinstance(graph, ig.Graph)
        assert graph.vcount() > 0
        assert graph.ecount() > 0
