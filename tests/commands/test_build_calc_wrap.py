import importlib
import pandas as pd


def _rt_st_meta():
    # Regions: two at level 0 with two segments (variant), and one consensus
    rt = pd.DataFrame([
        {"id": "r1", "type": "con", "level_range": [0, 0], "segments": ["s1", "s2"], "length": 0, "min_length": 0, "total_variants": 0},
        {"id": "r2", "type": "con", "level_range": [1, 1], "segments": ["s3"], "length": 0, "min_length": 0, "total_variants": 0},
    ])
    # Segments: s1 and s2 under r1; s3 as separate consensus
    st = pd.DataFrame([
        {"id": "s1", "level_range": [0, 0], "sub_regions": [], "length": 10, "total_variants": 0, "direct_variants": 0, "sources": []},
        {"id": "s2", "level_range": [0, 0], "sub_regions": [], "length": 12, "total_variants": 0, "direct_variants": 0, "sources": []},
        {"id": "s3", "level_range": [1, 1], "sub_regions": ["r1"], "length": 0, "total_variants": 0, "direct_variants": 0, "sources": []},
    ])
    meta = {"sources": [], "name": "t"}
    return rt, st, meta


def test_calculate_and_wrap_properties():
    build = importlib.import_module("hap.commands.build")
    rt, st, meta = _rt_st_meta()
    # l2r fills region types/semantic ids and segment stats
    rt2, st2, meta2 = build.calculate_properties_l2r(rt.copy(), st.copy(), meta.copy())
    assert (rt2["length"] >= 0).all()
    # wrap with min_resolution>0 should set meta fields and not crash
    rt3, st3, meta3 = build.wrap_rstree(rt2.copy(), st2.copy(), meta2.copy(), min_resolution=0.5)
    assert "max_level" in meta3 and meta3["max_level"] >= 0
    # r2l should accept the structure
    rt4, st4, meta4 = build.calculate_properties_r2l(rt3.copy(), st3.copy(), meta3.copy())
    assert isinstance(rt4, pd.DataFrame) and isinstance(st4, pd.DataFrame)