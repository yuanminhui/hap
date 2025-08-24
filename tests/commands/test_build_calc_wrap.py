import importlib
import sys


def _rt_st_meta(pd_mod):
    rt = pd_mod.DataFrame([
        {"id": "r1", "type": "con", "level_range": [0, 0], "segments": ["s1", "s2"], "length": 0, "min_length": 0, "total_variants": 0, "parent_segment": None},
        {"id": "r2", "type": "con", "level_range": [1, 1], "segments": ["s3"], "length": 0, "min_length": 0, "total_variants": 0, "parent_segment": None},
    ])
    st = pd_mod.DataFrame([
        {"id": "s1", "level_range": [0, 0], "sub_regions": [], "length": 10, "total_variants": 0, "direct_variants": 0, "sources": [], "parent_segment": None},
        {"id": "s2", "level_range": [0, 0], "sub_regions": [], "length": 12, "total_variants": 0, "direct_variants": 0, "sources": [], "parent_segment": None},
        {"id": "s3", "level_range": [1, 1], "sub_regions": ["r1"], "length": 0, "total_variants": 0, "direct_variants": 0, "sources": [], "parent_segment": None},
    ])
    meta = {"sources": [], "name": "t"}
    return rt, st, meta


def test_calculate_and_wrap_properties(monkeypatch):
    # ensure sys.modules holds real pandas for subsequent imports
    sys.modules.pop("pandas", None)
    import pandas as pd  # real pandas
    import importlib as _il
    build = importlib.import_module("hap.commands.build")
    build = _il.reload(build)
    # ensure real pandas inside build
    monkeypatch.setattr(build, "pd", pd, raising=False)
    rt, st, meta = _rt_st_meta(pd)
    rt2, st2, meta2 = build.calculate_properties_l2r(rt.copy(), st.copy(), meta.copy())
    assert (rt2["length"] >= 0).all()
    rt3, st3, meta3 = build.wrap_rstree(rt2.copy(), st2.copy(), meta2.copy(), min_resolution=0.5)
    assert "max_level" in meta3 and meta3["max_level"] >= 0
    rt4, st4, meta4 = build.calculate_properties_r2l(rt3.copy(), st3.copy(), meta3.copy())
    assert isinstance(rt4, pd.DataFrame) and isinstance(st4, pd.DataFrame)