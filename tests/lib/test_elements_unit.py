from hap.lib.elements import Region, Segment


def test_region_segment_roundtrip():
    r = Region("rX", "con")
    r.level_range = [0, 0]
    r.sources = ["A", "B"]
    s = r.add_segment("sX")
    s.length = 5
    s.frequency = 1.0
    s.sources = ["A"]
    d = r.to_dict()
    rr = Region(d["id"], d["type"])
    rr.from_dict(d)
    assert rr.id == "rX"
    assert rr.segments == ["sX"]
    sd = s.to_dict()
    # Basic dict contains keys and expected values
    assert sd["id"] == "sX"
    assert sd["length"] == 5
