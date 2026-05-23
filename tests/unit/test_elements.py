"""
Unit tests for hap.lib.elements — Segment and Region data models.
"""

import pytest
from hap.lib.elements import Segment, Region


# ============================================================
# Segment
# ============================================================

class TestSegment:
    def test_init_defaults(self):
        seg = Segment("s-1")
        assert seg.id == "s-1"
        assert seg.original_id is None   # original=False by default
        assert seg.semantic_id is None
        assert seg.level_range == [0, 0]
        assert seg.coordinate == [0, 0]
        assert seg.rank == 0
        assert seg.length == 0
        assert seg.frequency == 0
        assert seg.direct_variants == 0
        assert seg.total_variants == 0
        assert seg.is_wrapper is False
        assert seg.sub_regions == []
        assert seg.paths == []

    def test_init_original_true(self):
        seg = Segment("s-42", original=True)
        assert seg.id == "s-42"
        assert seg.original_id == "s-42"

    def test_to_dict_contains_expected_keys(self):
        seg = Segment("s-1", original=True)
        d = seg.to_dict()
        expected_keys = {
            "id", "original_id", "semantic_id",
            "level_range", "coordinate", "rank",
            "length", "frequency", "direct_variants",
            "total_variants", "is_wrapper", "sub_regions", "paths",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_to_dict_excludes_private(self):
        seg = Segment("s-1")
        seg._hidden = "should_not_appear"
        d = seg.to_dict()
        assert "_hidden" not in d

    def test_mutate_fields(self):
        seg = Segment("s-5", original=True)
        seg.length = 42
        seg.frequency = 0.75
        seg.rank = 3
        seg.level_range = [1, 3]
        seg.coordinate = [100, 200]
        d = seg.to_dict()
        assert d["length"] == 42
        assert d["frequency"] == 0.75
        assert d["rank"] == 3


# ============================================================
# Region
# ============================================================

class TestRegion:
    def test_init_con_type(self):
        r = Region("r-1", "con")
        assert r.id == "r-1"
        assert r.type == "con"
        assert r.is_variant is False
        assert r.segments == []
        assert r.paths == []

    def test_init_var_type(self):
        r = Region("r-2", "var")
        assert r.is_variant is True

    def test_init_unknown_type_is_variant(self):
        r = Region("r-3", "ale")
        assert r.is_variant is True  # anything != 'con' is variant

    def test_add_segment_basic(self):
        r = Region("r-1", "con")
        r.paths = ["smp1#0", "smp2#0"]
        r.level_range = [0, 2]
        seg = r.add_segment("s-10", original=True)

        assert seg.id == "s-10"
        assert "s-10" in r.segments
        assert seg.level_range == [0, 2]
        assert seg.paths == ["smp1#0", "smp2#0"]

    def test_add_multiple_segments(self):
        r = Region("r-1", "var")
        for i in range(3):
            r.add_segment(f"s-{i}")
        assert len(r.segments) == 3
        assert r.segments == ["s-0", "s-1", "s-2"]

    def test_to_dict(self):
        r = Region("r-10", "con")
        r.coordinate = [50, 150]
        d = r.to_dict()
        assert d["id"] == "r-10"
        assert d["type"] == "con"
        assert d["coordinate"] == [50, 150]

    def test_from_dict(self):
        r = Region("r-1", "con")
        r.from_dict({"coordinate": [5, 15], "total_variants": 3})
        assert r.coordinate == [5, 15]
        assert r.total_variants == 3

    def test_from_dict_ignores_unknown_keys(self):
        r = Region("r-1", "con")
        r.from_dict({"nonexistent_key": "value"})
        # Should not raise

    def test_from_dict_ignores_private_keys(self):
        r = Region("r-1", "con")
        r.from_dict({"_private": "value"})
        assert not hasattr(r, "_private") or r.__dict__.get("_private") is None
