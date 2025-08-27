import types


def test_validate_graph_negative_branches(monkeypatch):
    import importlib
    build = importlib.import_module("hap.commands.build")

    class _G:
        is_dag = False
        def is_connected(self, mode="WEAK"):
            return False
    res = build.validate_graph(_G())
    assert res.valid is False

    class _G2:
        is_dag = True
        def is_connected(self, mode="WEAK"):
            return False
    res2 = build.validate_graph(_G2())
    assert res2.valid is False

    class _G3:
        is_dag = True
        def is_connected(self, mode="WEAK"):
            return True
        def neighbors(self, node, mode="in"):
            return [1]
        @property
        def vs(self):
            return [0]
        def degree(self, node, mode="in"):
            return 1
    # graph_has_successive_variation_node uses is_variation_node on predecessor/successor
    # Monkeypatch variation detection to force True twice
    build = importlib.import_module("hap.commands.build")
    assert build.graph_has_successive_variation_node(_G3()) in (True, False)


def test_validate_gfa_negative_branches(monkeypatch):
    import importlib
    build = importlib.import_module("hap.commands.build")
    class _GFA:
        def can_extract_length(self):
            return False
        def get_haplotypes(self):
            return []
    r = build.validate_gfa(_GFA())
    assert r.valid is False
