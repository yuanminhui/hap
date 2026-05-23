"""
Unit tests for build.py helper functions (no DB required).
"""

import pytest

# We import specific functions from commands.build to test them in isolation.
# Note: identifiers is module-level state — we reset it between tests.
import importlib
build_mod = importlib.import_module("hap.commands.build")


@pytest.fixture(autouse=True)
def reset_identifiers():
    """Reset global identifier counters before each test."""
    for k in build_mod.identifiers:
        build_mod.identifiers[k] = 0
    yield
    for k in build_mod.identifiers:
        build_mod.identifiers[k] = 0


class TestGetId:
    def test_segment_id_format(self):
        id1 = build_mod.get_id("s")
        assert id1 == "s-1"

    def test_region_id_format(self):
        id1 = build_mod.get_id("r")
        assert id1 == "r-1"

    def test_variant_type_prefix_uppercase(self):
        id1 = build_mod.get_id("var")
        assert id1 == "VAR-1"

    def test_con_prefix_uppercase(self):
        id1 = build_mod.get_id("con")
        assert id1 == "CON-1"

    def test_increments(self):
        ids = [build_mod.get_id("s") for _ in range(5)]
        assert ids == ["s-1", "s-2", "s-3", "s-4", "s-5"]

    def test_separate_counters_per_type(self):
        build_mod.get_id("s")
        build_mod.get_id("s")
        build_mod.get_id("r")
        assert build_mod.get_id("s") == "s-3"
        assert build_mod.get_id("r") == "r-2"


class TestCollectSegmentIdsFromGFA:
    def test_collects_all_segment_ids(self, mini_gfa_path):
        ids = build_mod.collect_segment_ids_from_gfa(mini_gfa_path)
        assert isinstance(ids, set)
        assert "s1" in ids
        assert "s23" in ids
        assert len(ids) == 23  # mini-example has 23 segments

    def test_ignores_non_s_lines(self, mini_gfa_path):
        ids = build_mod.collect_segment_ids_from_gfa(mini_gfa_path)
        # Verify no path/link names leaked in
        assert "chr1" not in ids

    def test_empty_gfa(self, tmp_gfa):
        p = tmp_gfa(
            "H\tVN:Z:1.0\n"
            "L\ts1\t+\ts2\t+\t0M\n"
        )
        ids = build_mod.collect_segment_ids_from_gfa(str(p))
        assert ids == set()


class TestFilterSequenceTsvByIds:
    def test_filters_correctly(self, tmp_path):
        tsv = tmp_path / "seqs.tsv"
        tsv.write_text("s1\tATCG\ns2\tGCTA\ns3\tNNNN\n")
        out = tmp_path / "filtered.tsv"
        id_to_len = build_mod.filter_sequence_tsv_by_ids(
            str(tsv), {"s1", "s3"}, str(out)
        )
        assert "s1" in id_to_len
        assert id_to_len["s1"] == 4
        assert "s3" in id_to_len
        assert "s2" not in id_to_len

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_empty_ids(self, tmp_path):
        tsv = tmp_path / "seqs.tsv"
        tsv.write_text("s1\tATCG\n")
        out = tmp_path / "filtered.tsv"
        id_to_len = build_mod.filter_sequence_tsv_by_ids(str(tsv), set(), str(out))
        assert id_to_len == {}

    def test_skips_malformed_lines(self, tmp_path):
        tsv = tmp_path / "seqs.tsv"
        tsv.write_text("s1\tATCG\nBAD_LINE\ns2\tGCTA\n")
        out = tmp_path / "filtered.tsv"
        id_to_len = build_mod.filter_sequence_tsv_by_ids(
            str(tsv), {"s1", "s2"}, str(out)
        )
        assert len(id_to_len) == 2
