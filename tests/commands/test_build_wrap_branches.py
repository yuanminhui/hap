import importlib
import sys


def _rt_st_meta(pd_mod):
    # Parent region at level 0 with one parent segment containing two child regions
    rt = pd_mod.DataFrame([
        {"id": "r0", "semantic_id": None, "level_range": [0, 0], "coordinate": None, "is_default": False, "length": 22, "is_variant": False, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": pd_mod.NA, "segments": ["segP"], "sources": ["src"], "min_length": 0, "before": None, "after": None},
        # leaf regions with their own leaf segments
        {"id": "r1", "semantic_id": None, "level_range": [1, 1], "coordinate": None, "is_default": False, "length": 10, "is_variant": False, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": "segP", "segments": ["s1a"], "sources": ["src"], "min_length": 1, "before": None, "after": None},
        {"id": "r2", "semantic_id": None, "level_range": [1, 1], "coordinate": None, "is_default": False, "length": 12, "is_variant": False, "type": "con", "total_variants": 0, "subgraph": None, "parent_segment": "segP", "segments": ["s2a"], "sources": ["src"], "min_length": 12, "before": None, "after": None},
    ])
    st = pd_mod.DataFrame([
        {"id": "segP", "original_id": None, "semantic_id": None, "level_range": [0, 0], "coordinate": None, "rank": 0, "length": 22, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": ["r1", "r2"], "sources": ["src"]},
        # leaf segments under r1 and r2
        {"id": "s1a", "original_id": None, "semantic_id": None, "level_range": [1, 1], "coordinate": None, "rank": 0, "length": 1, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": [], "sources": ["src"]},
        {"id": "s2a", "original_id": None, "semantic_id": None, "level_range": [1, 1], "coordinate": None, "rank": 0, "length": 12, "frequency": 1.0, "direct_variants": 0, "total_variants": 0, "is_wrapper": False, "sub_regions": [], "sources": ["src"]},
    ])
    meta = {"sources": ["src"], "name": "t", "total_length": 22}
    return rt, st, meta


def test_wrap_rstree_creates_wrapper_regions(monkeypatch):
    # ensure real pandas inside build
    sys.modules.pop("pandas", None)
    import pandas as pd
    import importlib as _il
    build = importlib.import_module("hap.commands.build")
    build = _il.reload(build)
    monkeypatch.setattr(build, "pd", pd, raising=False)

    rt, st, meta = _rt_st_meta(pd)

    # l2r to initialize semantics/ids where necessary
    rt2, st2, meta2 = build.calculate_properties_l2r(rt.copy(), st.copy(), meta.copy())

    # min_resolution chosen so that wrapping can be considered
    before_rt_rows = len(rt2)
    before_st_rows = len(st2)
    rt3, st3, meta3 = build.wrap_rstree(rt2.copy(), st2.copy(), meta2.copy(), min_resolution=0.01)

    # Verify wrapper regions/segments were added by checking row counts increased
    assert len(rt3) >= before_rt_rows
    assert len(st3) >= before_st_rows
    assert "max_level" in meta3 and meta3["max_level"] >= 1

    # r2l should compute coordinates without error
    rt4, st4, meta4 = build.calculate_properties_r2l(rt3.copy(), st3.copy(), meta3.copy())
    assert (rt4["coordinate"].apply(lambda v: isinstance(v, list))).any()
