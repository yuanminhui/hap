from igraph import Graph


def gfa2dictlist(filepath: str) -> tuple[list[dict], list[dict]]:
    """Parse a GFA file into node and edge lists. Only basic properties of nodes are extracted (id and length)."""

    nodes = []
    edges = []
    with open(filepath) as f:
        for line in f:
            line = line.rstrip("\n")
            if line[0] == "S":
                line = line.split("\t")
                length = -1
                if line[2] != "*":
                    length = len(line[2])
                elif len(line) > 3:
                    for tag in line[3:]:
                        if "LN" in tag:
                            length = int(tag.split(":")[-1])
                            break
                if length < 0:
                    raise AttributeError("Invalid GFA file: Missing segment length")
                nodes.append({"name": line[1], "length": length})

            elif line[0] == "L":
                _, src, _, tar, _ = line.split("\t", 4)
                edges.append({"source": src, "target": tar})

            elif line[0] == "P":
                _, _, path, _ = line.split("\t", 3)
                path = path.split(",")
                start = path[0].rstrip("+-")
                end = path[-1].rstrip("+-")
                edges.extend(
                    [
                        {"source": "head", "target": start},
                        {"source": end, "target": "tail"},
                    ]
                )
        if len(nodes) == 0 or len(edges) == 0:
            raise AttributeError("Invalid GFA file: No graph elements found")
        else:
            nodes.extend([{"name": "head", "length": 0}, {"name": "tail", "length": 0}])
    return nodes, edges


def gfa2ig(filepath: str) -> Graph:
    """Convert a GFA file into a iGraph object."""

    nodes, edges = gfa2dictlist(filepath)
    if nodes and edges:
        g = Graph.DictList(nodes, edges, directed=True)
        empstart = g.vs.find("head").index
        for sv in g.vs(_indegree=0):
            # if sv.index != empstart:
            g.add_edge(empstart, sv.index)
        empend = g.vs.find("tail").index
        for ev in g.vs(_outdegree=0):
            # if ev.index != empend:
            g.add_edge(ev.index, empend)
        g = g.simplify()
        return g
    else:
        raise AttributeError("Invalid GFA file")
