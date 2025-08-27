import importlib


def _make_graph(deg_map, neighbors_map, vs_iter):
    class G:
        is_dag = True
        vs = vs_iter
        def is_connected(self, mode="WEAK"):
            return True
        def degree(self, node, mode="in"):
            key = (node, mode)
            return deg_map.get(key, 0)
        def neighbors(self, node, mode="in"):
            return neighbors_map.get((node, mode), [])
    return G()


def test_is_variation_node_true():
    build = importlib.import_module("hap.commands.build")
    deg = {(1, "in"): 1, (1, "out"): 1}
    g = _make_graph(deg, {}, vs_iter=[1])
    assert build.is_variation_node(1, g) is True


def test_is_variation_node_false():
    build = importlib.import_module("hap.commands.build")
    deg = {(1, "in"): 0, (1, "out"): 1}
    g = _make_graph(deg, {}, vs_iter=[1])
    assert build.is_variation_node(1, g) is False


def test_graph_has_successive_variation_node_true():
    build = importlib.import_module("hap.commands.build")
    # node 2 is variation; its in-neighbor 1 is also variation
    deg = {
        (1, "in"): 1, (1, "out"): 1,
        (2, "in"): 1, (2, "out"): 1,
    }
    neighbors = {
        (2, "in"): [1],
        (2, "out"): [3],
    }
    g = _make_graph(deg, neighbors, vs_iter=[2])
    assert build.graph_has_successive_variation_node(g) is True


def test_graph_has_successive_variation_node_false():
    build = importlib.import_module("hap.commands.build")
    deg = {
        (2, "in"): 2, (2, "out"): 1,  # not a variation node
    }
    neighbors = {}
    g = _make_graph(deg, neighbors, vs_iter=[2])
    assert build.graph_has_successive_variation_node(g) is False