class _Vertex:
    def __init__(self, index):
        self.index = index
        self._attrs = {}

    def __getitem__(self, key):
        return self._attrs.get(key)

    def __setitem__(self, key, value):
        self._attrs[key] = value


class _VS:
    def __init__(self, graph):
        self.g = graph

    def __iter__(self):
        return iter(self.g.vertices)

    def __getitem__(self, idx):
        return self.g.vertices[idx]

    def find(self, name):
        for v in self.g.vertices:
            if v["name"] == name:
                return v
        raise ValueError("not found")

    def select(self, _indegree=None, _outdegree=None, parent_segment_ne=None):
        res = []
        for v in self.g.vertices:
            if _indegree is not None:
                if self.g.degree(v, mode="in") == _indegree:
                    res.append(v)
            elif _outdegree is not None:
                if self.g.degree(v, mode="out") == _outdegree:
                    res.append(v)
            elif parent_segment_ne is None:
                # select vertices whose parent_segment is not None
                if v["parent_segment"] is not None:
                    res.append(v)
        return res


class StubGraph:
    def __init__(self):
        self.vertices = []
        self._edges_out = {}
        self._edges_in = {}
        self._attrs = {}
        self.vs = _VS(self)
        # Build head -> n1 -> tail
        h = self.add_vertex("head", length=0)
        m = self.add_vertex("n1", length=10)
        t = self.add_vertex("tail", length=0)
        self.add_edges([(h.index, m.index), (m.index, t.index)])
        self["haplotypes"] = "h1"
        # sources/freq
        h["sources"], h["frequency"] = [], 0.0
        m["sources"], m["frequency"] = ["h1"], 1.0
        t["sources"], t["frequency"] = [], 0.0

    def __getitem__(self, key):
        return self._attrs.get(key)

    def __setitem__(self, key, value):
        self._attrs[key] = value

    @property
    def is_dag(self):
        return True

    def is_connected(self, mode="WEAK"):
        return True

    def add_vertex(self, name, length=0):
        v = _Vertex(len(self.vertices))
        v["name"] = name
        v["length"] = length
        v["sources"] = []
        v["frequency"] = 0.0
        v["parent_segment"] = None
        v["path"] = None
        self.vertices.append(v)
        self._edges_out[v.index] = set()
        self._edges_in[v.index] = set()
        return v

    def add_edges(self, pairs):
        for u, v in pairs:
            self._edges_out[u].add(v)
            self._edges_in[v].add(u)

    def delete_edges(self, pair):
        u, v = pair
        self._edges_out[u].discard(v)
        self._edges_in[v].discard(u)

    def are_connected(self, u, v):
        return v in self._edges_out.get(u, set())

    def neighbors(self, node, mode="out"):
        idx = node if isinstance(node, int) else node.index
        if mode == "out":
            return list(self._edges_out.get(idx, set()))
        else:
            return list(self._edges_in.get(idx, set()))

    def degree(self, node, mode="in"):
        idx = node if isinstance(node, int) else node.index
        if mode == "in":
            return len(self._edges_in.get(idx, set()))
        elif mode == "out":
            return len(self._edges_out.get(idx, set()))
        else:
            return len(self._edges_in.get(idx, set())) + len(self._edges_out.get(idx, set()))


def test_graph2rstree_with_stub_graph():
    import importlib
    build = importlib.import_module("hap.commands.build")
    g = StubGraph()
    rt, st, meta = build.graph2rstree(g)
    # Should produce at least one region and one segment
    assert len(rt) > 0 and len(st) > 0
    rt2, st2, meta2 = build.calculate_properties_l2r(rt.copy(), st.copy(), meta.copy())
    rt3, st3, meta3 = build.wrap_rstree(rt2.copy(), st2.copy(), meta2.copy(), min_resolution=0.04)
    rt4, st4, meta4 = build.calculate_properties_r2l(rt3.copy(), st3.copy(), meta3.copy())
    assert "total_length" in meta4

