class Segment:
    def __init__(self, id):
        self.id = id
        self.name = None
        self.start = 0
        self.end = 0
        self.sub_regions = []
        self.level_range = [0, 0]
        self.length = 0
        self.is_default = False
        self.rank = 0
        self.sources = []
        self.dir_var = 0
        self.total_var = 0
        self.is_wrapper = False

    def to_dict(self):
        return self.__dict__


class Region:
    def __init__(self, id, type):
        self.id = id
        self.name = None
        self.start = 0
        self.end = 0
        self.parent_seg = None
        self.segments = []
        self.level_range = [0, 0]
        self.length = 0
        self.is_default = False
        self.is_var = True if type == "var" or type != "con" else False
        self.type = type
        self.total_var = 0
        # to be discarded after process
        self.min_length = 0
        self.before = None
        self.after = None

    def add_segment(self, id):
        """Create and add segment to current region, setting the same level.
        If region `type` is `con` and no segment exists, added segment is set
        to default."""

        segment = Segment(id)
        if self.type == "con" and len(self.segments) == 0:
            segment.is_default = True
        self.segments.append(segment.id)
        segment.level_range = self.level_range
        return segment

    def to_dict(self):
        return self.__dict__


ids = {
    "s": 0,
    "r": 0,
    "var": 0,
    "con": 0,
    "ale": 0,
    "ind": 0,
    "sv": 0,
    "snp": 0,
}


def get_id(type: str) -> str:
    ids[type] += 1
    prefix = type if type == "s" or type == "r" else type.upper()
    return "_".join([prefix, str(ids[type])])


import json
import os
import argparse
import collections
import subprocess
import tempfile
from igraph import Graph
import pandas as pd
import math
import copy
import multiprocessing as mp
import functools


def graph2rstree(graph: Graph) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build a region-segment tree for pangenome representation from a normalized sequence graph."""

    # Inits
    visited = set()
    pathstarts = collections.deque()
    paths = []
    sidmap = {}
    rt = pd.DataFrame(
        columns=[
            "id",
            "name",
            "start",
            "end",
            "parent_seg",
            "segments",
            "level_range",
            "length",
            "is_default",
            "is_var",
            "type",
            "total_var",
            "min_length",
            "before",
            "after",
        ]
    )
    st = pd.DataFrame(
        columns=[
            "id",
            "name",
            "start",
            "end",
            "sub_regions",
            "level_range",
            "length",
            "is_default",
            "rank",
            "sources",
            "dir_var",
            "total_var",
            "is_wrapper",
        ]
    )
    empstart = graph.vs.find("start").index
    pathstarts.append(empstart)

    # Traversing the graph
    while len(pathstarts) != 0:
        start = pathstarts.popleft()
        rt, st = process_path(start, graph, rt, st, visited, pathstarts, paths)

    # Postprocessing
    # Turn the nodes at segment end into each split region
    segends = graph.vs.select(parent_seg_ne=None)
    for se in segends:
        if se["name"] != "end" and se["name"] != "start":
            # get current level
            parseg_id = se["parent_seg"]
            pi = st[st["id"] == parseg_id].index[0]
            level = st.iat[pi, st.columns.get_loc("level_range")][0] + 1

            # build elements and fill properties
            region = Region(get_id("r"), "con")
            segment = region.add_segment(se["name"])
            segment.level_range = region.level_range = [level, level]
            segment.length = se["length"]
            region.parent_seg = parseg_id

            # write to dataframe
            subrg = st.iat[pi, st.columns.get_loc("sub_regions")]
            subrg.append(region.id)
            st.iat[pi, st.columns.get_loc("sub_regions")] = subrg
            st = pd.concat(
                [st, pd.DataFrame([segment.to_dict()])], ignore_index=True, copy=False
            )
            rt = pd.concat(
                [rt, pd.DataFrame([region.to_dict()])], ignore_index=True, copy=False
            )
        graph.vs[se.index]["parent_seg"] = None
    st = st.astype(
        {
            "id": "string",
            "name": "string",
            "start": "uint64",
            "end": "uint64",
            "length": "uint64",
            "is_default": "bool",
            "rank": "uint8",
            "dir_var": "uint8",
            "total_var": "uint64",
            "is_wrapper": "bool",
        },
        copy=False,
    )
    rt = rt.astype(
        {
            "id": "string",
            "name": "string",
            "start": "uint64",
            "end": "uint64",
            "parent_seg": "string",
            "length": "uint64",
            "is_default": "bool",
            "is_var": "bool",
            "type": "string",
            "total_var": "uint64",
            "min_length": "uint64",
            "before": "string",
            "after": "string",
        },
        copy=False,
    )

    # Fill other fields from leaves to root
    maxlevel = rt["level_range"].apply(lambda lr: lr[1]).max()
    for i in range(
        maxlevel, -1, -1
    ):  # process regions from maxlevel to 0, segments from (maxlevel - 1) to 0
        ris: list[int] = rt[
            rt["level_range"].apply(lambda lr: i >= lr[0] and i <= lr[1])
        ].index.tolist()  # regions at the same level
        for ri in ris:
            # fill region `length` from child segment's max length
            segments: list = rt.iat[ri, rt.columns.get_loc("segments")]
            sis = st[st["id"].isin(segments)].index.tolist()
            lensr = st.iloc[sis]["length"]
            maxlen = lensr.max()
            minlen = lensr.min()
            rt.iat[ri, rt.columns.get_loc("length")] = maxlen
            rt.iat[ri, rt.columns.get_loc("min_length")] = lensr[lensr > 0].min()

            # fill `total_var`
            rt.iat[ri, rt.columns.get_loc("total_var")] = st.iloc[sis][
                "total_var"
            ].sum()

            # fill region & segment's `name`
            if len(segments) > 1:  # variant exists
                d = maxlen - minlen
                std = lensr.std()
                mean = lensr.mean()

                # allele
                if std / mean < 0.1:
                    if (lensr == 1).all():
                        rt.iat[ri, rt.columns.get_loc("type")] = "snp"
                        rn = get_id("snp")
                    else:
                        rt.iat[ri, rt.columns.get_loc("type")] = "ale"
                        rn = get_id("ale")
                    rt.iat[ri, rt.columns.get_loc("name")] = rn
                    st.iloc[sis, st.columns.get_loc("name")] = [
                        rn + "_" + chr(j) for j in range(97, 97 + len(sis))
                    ]  # generate names like `ALE_{n}_a,b,c`

                # del exists
                elif minlen == 0 or (minlen < 10 and d / minlen > 5):
                    rt.iat[ri, rt.columns.get_loc("min_length")] = lensr[
                        lensr > minlen
                    ].min()
                    if d > 50:
                        rt.iat[ri, rt.columns.get_loc("type")] = "sv"
                        rn = get_id("sv")
                    else:
                        rt.iat[ri, rt.columns.get_loc("type")] = "ind"
                        rn = get_id("ind")
                    rt.iat[ri, rt.columns.get_loc("name")] = rn
                    mini = lensr.idxmin()
                    st.iat[mini, st.columns.get_loc("name")] = rn + "_d"
                    sis.remove(mini)
                    if len(sis) > 1:
                        st.iloc[sis, st.columns.get_loc("name")] = [
                            rn + "_i" + chr(j) for j in range(97, 97 + len(sis))
                        ]
                    else:
                        st.iloc[sis, st.columns.get_loc("name")] = rn + "_i"

                # not determined
                else:
                    rt.iat[ri, rt.columns.get_loc("type")] = "var"
                    rn = get_id("var")
                    rt.iat[ri, rt.columns.get_loc("name")] = rn
                    st.iloc[sis, st.columns.get_loc("name")] = [
                        rn + "_" + chr(j) for j in range(97, 97 + len(sis))
                    ]

            # consensus
            else:
                rn = get_id("con")
                rt.iat[ri, rt.columns.get_loc("name")] = rn
                st.iloc[sis, st.columns.get_loc("name")] = rn

        if i >= 1:
            sis = st[
                (st["level_range"].apply(lambda lr: i - 1 >= lr[0] and i - 1 <= lr[1]))
                & (st["sub_regions"].apply(len) > 0)
            ].index.tolist()  # (non-leaf) segments at the higher level
            for si in sis:
                segment = st.iloc[si].to_dict()
                # fill segment `length` by summating child region's length
                sub_regions = segment["sub_regions"]
                srdf = rt[rt["id"].isin(sub_regions)]
                totallen = srdf["length"].sum()
                segment["length"] = totallen

                # fill `dir_var` & `total_var`
                segment["dir_var"] = len(srdf[srdf["type"] != "con"])
                segment["total_var"] = srdf["total_var"].sum() + segment["dir_var"]

                st.iloc[si] = segment

    return rt, st


def unvisited_path(
    start: int, graph: Graph, visited: set, pathstarts: collections.deque
):
    """
    Returns a generator of an unvisited path the `start` node belongs to. Each
    node in the path is unvisited, and the path's predecessor & successor are
    both visited or empty.

    When encounter node with multiple successors, proceed with one of them and
    move the remainder to `pathstarts`.
    """

    next = start
    while next != None:
        yield next
        successors = graph.neighbors(next, mode="out")
        next = None
        if successors:
            for sr in successors:
                if sr not in visited:
                    if next != None:
                        pathstarts.append(sr)
                    else:
                        next = sr


def process_path(
    start: int,
    graph: Graph,
    rt: pd.DataFrame,
    st: pd.DataFrame,
    visited: set,
    pathstarts: collections.deque,
    paths: list[list[int]],
):
    """Traverse and process an independant path."""

    g = graph

    # Init the path based on traverse order
    # If is main path
    if g.vs[start]["name"] == "start":
        region = Region(get_id("r"), "con")
        segment = Segment(get_id("s"))

    # or side path
    else:
        before = g.neighbors(start, mode="in")[
            0
        ]  # PROBLEM: may have multiple "before" nodes
        # TODO: eliminate multiple attachment relations

        # Split into regions if hasn't been treated
        if rt[rt["before"] == g.vs[before]["name"]].empty:
            # Get parent segment's properties
            parseg_id = g.vs[before]["parent_seg"]
            pi = st[st["id"] == parseg_id].index[0]
            level = st.iat[pi, st.columns.get_loc("level_range")][0] + 1
            subrg = st.iat[pi, st.columns.get_loc("sub_regions")]

            # Build elements and fill properties
            if g.vs[before]["name"] != "start":
                pre_region = Region(get_id("r"), "con")
                pre_region.level_range = [level, level]
                pre_seg = pre_region.add_segment(g.vs[before]["name"])
                pre_seg.length = g.vs[before]["length"]
                pre_region.parent_seg = parseg_id
                # write to dataframe
                st = pd.concat(
                    [st, pd.DataFrame([pre_seg.to_dict()])],
                    ignore_index=True,
                    copy=False,
                )
                rt = pd.concat(
                    [rt, pd.DataFrame([pre_region.to_dict()])],
                    ignore_index=True,
                    copy=False,
                )
                subrg.append(pre_region.id)
            region = Region(get_id("r"), "var")
            segment = Segment(get_id("s"))
            segment.level_range = region.level_range = [level, level]
            segment.is_default = True  # set the first added segment to default
            g.vs[before]["parent_seg"] = None  # "before" can't be accessed anymore
            region.parent_seg = parseg_id
            region.before = g.vs[before]["name"]
            subrg.append(region.id)
            # suspend current region dumping (to df) for potential updates

        # or add segment to existing region
        else:
            region = rt[rt["before"] == g.vs[before]["name"]].iloc[0].to_dict()
            segment = Segment(get_id("s"))
            segment.level_range = region.level_range

    # Generate current path & process its nodes
    path = []
    for node in unvisited_path(start, g, visited, pathstarts):
        visited.add(node)
        path.append(node)
        # if run across del site
        if node in pathstarts:
            # find the farther predecessor
            # other = None
            for pr in g.neighbors(node, mode="in"):
                if pr in visited and pr != last:
                    s = pr
                    break
                    # if other == None:
                    #     other = pr
                    #     otherspaths = g.get_all_simple_paths(pr, node)
                    # else:
                    #     s = pr
                    #     for path in otherspaths:
                    #         if pr in path:
                    #             s = other
                    #             break
            if not s:
                raise SystemExit("Internal Error: unsolved graph structure.")

            d = g.add_vertex(get_id("s"), length=0).index
            g.add_edges([(s, d), (d, node)])
            g.delete_edges((s, node))
            ni = pathstarts.index(node)
            pathstarts.insert(ni, d)
            pathstarts.remove(node)
        g.vs[node]["parent_seg"] = segment.id
        g.vs[node]["path"] = len(paths)
        last = node

    # Rewrite properties if no `sub_regions` would be found
    if len(path) == 1:
        ni = path[0]
        segment.id = g.vs[ni]["name"]
        segment.length = g.vs[ni]["length"]
        g.vs[ni][
            "parent_seg"
        ] = None  # inseperable segment has no `parent_seg` record, a flag for leaves
        g.vs[ni]["path"] = None
    else:
        paths.append(path)
    region.segments.append(segment.id)
    st = pd.concat(
        [st, pd.DataFrame([segment.to_dict()])], ignore_index=True, copy=False
    )

    # Process allele region if have
    if g.vs[start]["name"] != "start":
        # Find allele path
        pi = g.vs[before]["path"]
        org_path = paths[pi]
        b = org_path.index(before)
        afters = g.neighbors(node, mode="out")
        for af in afters:
            if af in visited:
                region.after = g.vs[af][
                    "name"
                ]  # PROBLEM: may have multiple "after" nodes
                # TODO: eliminate multiple attachment relations
                break
        a = org_path.index(af)
        if b < a:
            org_ale_path = org_path[b + 1 : a]

        # Build allele segment
        if not org_ale_path:  # allele is del
            d = g.add_vertex(
                get_id("s"), length=0
            ).index  # NOTE: `d` node isn't added to origin path
            g.add_edges([(before, d), (d, af)])
            g.delete_edges((before, af))
            visited.add(d)
            org_ale_path = [d]
        if len(org_ale_path) == 1:
            org_ale_node = org_ale_path[0]
            ale_seg = Segment(g.vs[org_ale_node]["name"])
            ale_seg.length = g.vs[org_ale_node]["length"]
            g.vs[org_ale_node]["parent_seg"] = None
        else:
            ale_seg = Segment(get_id("s"))
            for v in org_ale_path:
                g.vs[v]["parent_seg"] = ale_seg.id  # Update parent for separable nodes
        ale_seg.level_range = [level, level]
        region.segments.append(ale_seg.id)
        st = pd.concat(
            [st, pd.DataFrame([ale_seg.to_dict()])], ignore_index=True, copy=False
        )

    rt = pd.concat(
        [rt, pd.DataFrame([region.to_dict()])], ignore_index=True, copy=False
    )
    return rt, st


def wrap_rstree(rt: pd.DataFrame, st: pd.DataFrame, minres=0.04):
    """Wrap small regions, deepen the region-segment tree and establish hierarchy."""

    if minres <= 0:
        raise ValueError("Min resolution must be greater than 0.")
    totallen = rt[rt["level_range"].apply(lambda lr: lr[0] == 0 and lr[1] == 0)][
        "length"
    ].iloc[0]
    maxlevel = math.ceil(
        math.log2(totallen / 1000 / minres)
    )  # new max level for hierarchical graph
    meta = {"max_level": maxlevel, "total_length": int(totallen)}
    minlenpx = 1 / minres
    # clear old level ranges
    mask = rt["level_range"].apply(lambda lr: lr[1] > 1)
    rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(lambda lr: [])
    mask = st["level_range"].apply(lambda lr: lr[1] > 1)
    st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(lambda lr: [])

    # Traverse the hierarchical graph from top to bottom
    for i in range(1, maxlevel):  # exclude top & bottom layer
        res = 2 ** (maxlevel - i) * minres
        rmdregions = set(
            rt[
                rt["level_range"].apply(
                    lambda lr: len(lr) > 0 and i >= lr[0] and i <= lr[1]
                )
            ]["id"].to_list()
        )
        parseg_df = st[
            st["level_range"].apply(
                lambda lr: len(lr) > 0 and i - 1 >= lr[0] and i - 1 <= lr[1]
            )
            & (st["sub_regions"].apply(len) > 0)
        ]

        # Treat regions in each parent segment seperately
        for rid_list in copy.deepcopy(parseg_df["sub_regions"].to_list()):
            rmdregions.difference_update(set(rid_list))
            ris = rt[rt["id"].isin(rid_list)].index.to_list()
            r2bw_iranges_dq = collections.deque()
            normal_regions = set(rid_list)
            for ri in ris:
                region = rt.iloc[ri].to_dict()
                # if region["id"] not in rid_list:
                #     continue

                # Add wrapper nodes if one of its segment's length is too small
                if region["min_length"] < res * minlenpx:
                    # Extend to find proper wrapping range
                    posi = rid_list.index(region["id"])
                    b = a = posi
                    totallen = 0
                    while totallen < res * minlenpx and not (
                        b < 0 and a > len(rid_list) - 1
                    ):  # continue extending if wrapped region still too small
                        if b >= 1:
                            lefti = b
                            b = -1
                            for j in range(lefti - 1, -1, -1):
                                if rt[rt["id"] == rid_list[j]]["type"].iloc[0] != "con":
                                    b = j
                                    break
                        else:
                            b = -1
                        if a <= len(rid_list) - 2:
                            righti = a
                            a = len(rid_list)
                            for j in range(righti + 1, len(rid_list)):
                                if rt[rt["id"] == rid_list[j]]["type"].iloc[0] != "con":
                                    a = j
                                    break
                        else:
                            a = len(rid_list)
                        r2bw_ids = rid_list[b + 1 : a]
                        r2bw_df = rt[rt["id"].isin(r2bw_ids)]
                        totallen = r2bw_df["length"].sum()

                    r2bw_iranges_dq.append([b + 1, a - 1])
                    # del rid_list[b + 1 : a]

            # union regions to be wrapped
            r2bw_iranges: list[list[int]] = []
            last = None
            while len(r2bw_iranges_dq) > 0:
                current = r2bw_iranges_dq.popleft()
                if last == None:
                    last = current
                else:
                    if last[1] >= current[0]:
                        last[1] = current[1]
                    else:
                        r2bw_iranges.append(last)
                        last = current
            r2bw_iranges.append(last)

            # move parent segment to current layer if all its child regions are wrapped into one
            if (
                len(r2bw_iranges) == 1
                and r2bw_iranges[0][0] == 0
                and r2bw_iranges[0][1] == len(rid_list) - 1
            ):
                si = st[st["id"] == region["parent_seg"]].index.to_list()[0]
                lvlrg = st.iat[si, st.columns.get_loc("level_range")]
                lvlrg[1] = i  # NOTE: update df cell in place
                mask = rt["id"].isin(rid_list)
                rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(
                    lambda lr: [i + 1, i + 1]
                )
                segments = rt.loc[mask, "segments"].sum()
                mask = st["id"].isin(segments)
                st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(
                    lambda lr: [i + 1, i + 1]
                )
                normal_regions = set()
                r2bw_iranges = []

            # Wrap regions
            for irange in r2bw_iranges:
                r2bw_ids = rid_list[irange[0] : irange[1] + 1]
                r2bw_df = rt[rt["id"].isin(r2bw_ids)]
                totallen = r2bw_df["length"].sum()
                normal_regions.difference_update(set(r2bw_ids))

                # build wrapper elements and fill properties
                # if len(rid_list) > 0:
                wrap_region = Region(get_id("r"), "con")
                wrap_region.level_range = [i, i]
                wrap_segment = wrap_region.add_segment(get_id("s"))
                wrap_region.length = (
                    wrap_region.min_length
                ) = wrap_segment.length = totallen
                wrap_segment.name = wrap_region.name = get_id("con")
                wrap_segment.dir_var = len(r2bw_df[r2bw_df["is_var"]])
                wrap_segment.total_var = (
                    r2bw_df["total_var"].sum() + wrap_segment.dir_var
                )
                wrap_region.total_var = wrap_segment.total_var
                wrap_region.parent_seg = region["parent_seg"]
                wrap_segment.sub_regions = r2bw_ids

                # write to dataframe
                wr_df = pd.DataFrame([wrap_region.to_dict()])
                wr_df = wr_df.astype(
                    {
                        "id": "string",
                        "name": "string",
                        "start": "uint64",
                        "end": "uint64",
                        "parent_seg": "string",
                        "length": "uint64",
                        "is_default": "bool",
                        "is_var": "bool",
                        "type": "string",
                        "total_var": "uint64",
                        "min_length": "uint64",
                        "before": "string",
                        "after": "string",
                    },
                    copy=False,
                )
                ws_df = pd.DataFrame([wrap_segment.to_dict()])
                ws_df = ws_df.astype(
                    {
                        "id": "string",
                        "name": "string",
                        "start": "uint64",
                        "end": "uint64",
                        "length": "uint64",
                        "is_default": "bool",
                        "rank": "uint8",
                        "dir_var": "uint8",
                        "total_var": "uint64",
                        "is_wrapper": "bool",
                    },
                    copy=False,
                )

                rt = pd.concat([rt, wr_df], ignore_index=True, copy=False)
                st = pd.concat([st, ws_df], ignore_index=True, copy=False)

                # iterate preparation for update of parent segment's `sub_regions` property
                rid_list[irange[0] : irange[1] + 1] = [""] * (irange[1] - irange[0] + 1)
                rid_list[irange[0]] = wrap_region.id

                # Move wrapped elements to next layer
                mask = rt["id"].isin(r2bw_ids)
                # if len(rid_list) > 0:
                rt.loc[mask, "parent_seg"] = wrap_segment.id
                rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(
                    lambda lr: [i + 1, i + 1]
                )
                segments = rt.loc[mask, "segments"].sum()
                mask = st["id"].isin(segments)
                st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(
                    lambda lr: [i + 1, i + 1]
                )

            if len(r2bw_iranges) > 0:
                rid_list = [rid for rid in rid_list if rid]
                si = st[st["id"] == wrap_region.parent_seg].index.to_list()[0]
                st.iat[si, st.columns.get_loc("sub_regions")] = rid_list

            for rid in normal_regions:
                region = rt[rt["id"] == rid].iloc[0].to_dict()
                sis = st[st["id"].isin(region["segments"])].index.to_list()
                # If no child segment exists, copy current region & segments to next layer
                if st.iloc[sis]["sub_regions"].apply(lambda rgs: rgs == []).all():
                    mask = rt["id"] == region["id"]
                    rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(
                        lambda lr: [i, i + 1]
                    )
                    st.loc[sis, "level_range"] = st.loc[sis, "level_range"].apply(
                        lambda lr: [i, i + 1]
                    )
                # Otherwise, replace current elements with child structure
                else:
                    sub_regions = st.iloc[sis]["sub_regions"].sum()
                    mask = rt["id"].isin(sub_regions)
                    rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(
                        lambda lr: [i + 1, i + 1]
                    )
                    subrg_segments = rt.loc[
                        rt["id"].isin(sub_regions), "segments"
                    ].sum()
                    mask = st["id"].isin(subrg_segments)
                    st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(
                        lambda lr: [i + 1, i + 1]
                    )

        # Copy inherited elements directly to next layer
        ris = rt[rt["id"].isin(rmdregions)].index.to_list()
        for ri in ris:
            segments = rt.iloc[ri]["segments"]
            sis = st[st["id"].isin(segments)].index.to_list()
            lvlrg = rt.iat[ri, rt.columns.get_loc("level_range")]
            lvlrg[1] = i + 1  # NOTE: update df cell in place
            # rt.iat[ri, rt.columns.get_loc("level_range")] = lr
            st.iloc[sis, st.columns.get_loc("level_range")] = st.iloc[
                sis, st.columns.get_loc("level_range")
            ].apply(lambda lr: lvlrg)

    # TODO: Find algorithm to unwrap all elements within max level limit
    if len(rt[rt["level_range"].apply(lambda lr: len(lr) == 0)]) > 0:
        raise Exception(
            "Warning: There are small regions remain wrapped, to unwrap all regions, flatten your input graph or decrease `minres`."
        )

    # TODO: (Postprocessing) rewrite `dir_var` and `total_var` from leave to root

    return rt, st, meta


def build_index(rt: pd.DataFrame, st: pd.DataFrame, meta: dict):
    """Build range index for elements in region-segment tree at various levels."""

    # TODO: add default tag

    # Fill range index from root to leave
    totallen = meta["total_length"]
    root_ri = rt[rt["parent_seg"].isna()].index.to_list()[0]
    rt.iloc[root_ri, rt.columns.get_indexer(["start", "end"])] = [0, totallen]
    root_sid = rt.iat[root_ri, rt.columns.get_loc("segments")][0]
    root_si = st[st["id"] == root_sid].index.to_list()[0]
    st.iloc[root_si, st.columns.get_indexer(["start", "end"])] = [0, totallen]
    seg_dq = collections.deque([root_sid])
    while len(seg_dq) > 0:
        segid = seg_dq.popleft()
        parseg: dict = st[st["id"] == segid].iloc[0].to_dict()
        parrange: list[int] = [parseg["start"], parseg["end"]]
        rids: list[str] = parseg["sub_regions"]
        totalsublen = rt[rt["id"].isin(rids)]["length"].sum()
        if totalsublen > parrange[1] - parrange[0]:
            raise Exception("Internal Error: element attribute calculation error")
        elif totalsublen == parrange[1] - parrange[0]:
            start = parrange[0]
        else:
            dlen = parrange[1] - parrange[0] - totalsublen
            start = parrange[0] + math.floor(dlen / 2)
        for rid in rids:
            ri = rt[rt["id"] == rid].index.to_list()[0]
            length = rt.iat[ri, rt.columns.get_loc("length")]
            rt.iloc[ri, rt.columns.get_indexer(["start", "end"])] = [
                start,
                start + length,
            ]
            sids = rt.iat[ri, rt.columns.get_loc("segments")]
            sis = st[st["id"].isin(sids)].index.to_list()
            st.iloc[sis, st.columns.get_indexer(["start", "end"])] = [
                start,
                start + length,
            ]
            seg_dq.extend(sids)
            start += length

    rt.drop(["min_length", "before", "after"], axis=1, inplace=True)
    return rt, st, meta


def calculate_properties(rt, st, meta):
    """Calculates the properties for elements in the region-segment tree."""

    for i in range(0, meta.maxlevel + 1):
        pass


def export(
    rt: pd.DataFrame,
    st: pd.DataFrame,
    meta: dict,
    outfp_base: str,
    format="hp",
):
    """Export region-segment tree to assigned format."""

    if format == "hp":
        with open(outfp_base + ".hp", "w") as file:
            file.write(json.dumps(meta)[1:-1] + "\n\n")
        rt.insert(0, "tag", "r")
        rt.to_csv(
            outfp_base + ".hp",
            sep="\t",
            na_rep="none",
            mode="a",
            header=False,
            index=False,
        )
        st.insert(0, "tag", "s")
        st.to_csv(
            outfp_base + ".hp",
            sep="\t",
            na_rep="none",
            mode="a",
            header=False,
            index=False,
        )
    elif format == "tsv":
        rt.to_csv(outfp_base + "_rt.tsv", sep="\t", na_rep="none", index=False)
        st.to_csv(outfp_base + "_st.tsv", sep="\t", na_rep="none", index=False)
    else:
        raise ValueError("Unsupported output format.")


def union_hps(
    indir: str,
    pgname: str,
    outdir: str,
    format: str = "hp",
):
    """Union a list of sub-Hierarchical-Pangenomes into a whole."""

    # TODO: Add `pgname` prefix to each element's name

    if format == "hp":
        subprocess.run(f"cat {indir}/*.hp > {outdir}/{pgname}.hp", shell=True)
    elif format == "tsv":
        cat = functools.partial(subprocess.run, shell=True)
        with mp.Pool() as pool:
            pool.map(
                cat,
                [
                    f"cat {indir}/*_rt.tsv > {outdir}/{pgname}_rt.tsv",
                    f"cat {indir}/*_st.tsv > {outdir}/{pgname}_st.tsv",
                ],
            )
    else:
        raise ValueError("Unsupported output format.")


def register_command(subparsers: argparse._SubParsersAction, module_help_map: dict):
    # Interface of hpbuilder
    psr_hpbuilder = subparsers.add_parser(
        "hpbuilder",
        prog="palchemy hpbuilder",
        description="Build a Hierarchical Pangenome as an input for Prowse, from a pangenome graph in GFA format.",
        help="build a Hierarchical Pangenome",
    )
    psr_hpbuilder.set_defaults(func=hpbuilder)
    module_help_map["hpbuilder"] = psr_hpbuilder.print_help

    psr_hpbuilder.add_argument("file", help="input graph file")
    psr_hpbuilder.add_argument("-n", "--name", help="name of the pangenome")
    # I/O options
    grp_io = psr_hpbuilder.add_argument_group("I/O options")
    grp_io.add_argument("-o", "--outdir", help="output directory")
    grp_io.add_argument(
        "-s",
        "--split",
        action="store_true",
        help="split output file into tables for dumping to database",
    )
    # Build parameters
    grp_build_params = psr_hpbuilder.add_argument_group("Build parameters")
    # grp_build_params.add_argument(
    #     "--no-wrap",
    #     action="store_true",
    #     help="Do not wrap elements to form into a Hierarchical Pangenome, return a intermediate Region-Segment Tree for further editing",
    # )
    # grp_build_params.add_argument(
    #     "-w",
    #     "--wrap",
    #     action="store_true",
    #     help="Wrap a Region-Segment Tree generated from hpbuilder into a Hierarchical Pangenome",
    # )
    grp_build_params.add_argument(
        "-r",
        "--min-res",
        type=float,
        default=0.04,
        dest="minres",
        help="minimum resolution of the Hierarchical Pangenome, in bp/px",
    )


def gzip_gfa(filepath: str):
    """Gzip a GFA file and return the compressed file path."""

    outfp = filepath + ".gz"
    with open(outfp, "w") as file:
        subprocess.run(["gzip", "-c", filepath], stdout=file)

    return outfp


def get_gfa_version(filepath: str) -> float:
    """Get the version of a (gzipped) GFA file. When no `VN` tag in `H` line is
    provided, an examination will run."""

    # a quick scan on version record
    cmd_rv = [
        "zcat",
        filepath,
        "|",
        "head",
        "-n",
        "1",
        "|",
        "awk",
        """'$1 == "H" {for (i = 2; i <= NF; ++i) if ($i ~ /^VN:/) {split($i, a, ":"); print a[3]}}'""",
    ]
    ver = subprocess.check_output(" ".join(cmd_rv), shell=True, text=True)
    try:
        ver = float(ver)
    except ValueError:
        # examine the essential charistics a version has
        cmd_ec = [
            "zcat",
            filepath,
            "|",
            "grep",
            "-m",
            "1",
            "-o",
            "-E",
            "^(E|J|W)",
        ]
        char = subprocess.check_output(" ".join(cmd_ec), shell=True, text=True)
        if char == "E":
            ver = 2.0
        elif char == "J":
            ver = 1.2
        elif char == "W":
            ver = 1.1
        else:
            ver = 1.0
    finally:
        return ver


def move_sequences(filepath: str, outdir: str, gfa_version: float):
    """Move the sequences in a (gzipped) GFA file to `sequence.txt.gz`, leaving
    a `*` as placeholder, add `LN` tag if not exist, and return the file path of
    the modified GFA file."""

    seqfp = outdir + "/sequence.txt.gz"
    outfp = filepath.replace(".gfa.gz", ".min.gfa.gz")
    if os.path.exists(seqfp):
        os.remove(seqfp)

    zcat = [
        "zcat",
        filepath,
    ]
    # `awk` -- move sequences and calculate segment length
    awk = ["|", "awk"]
    gzip = [
        "|",
        "gzip",
    ]
    if gfa_version < 2:
        awk.append(
            f"""'BEGIN {{OFS="\\t"}} /^S/ {{if ($3 != "*") {{cmd = "gzip >> {seqfp}"; print $2, $3 | cmd; close(cmd); len = length($3); $3 = "*"; if (!match($0, /LN:/)) $0 = $0 "\tLN:i:" len}}}} {{print}}'"""
        )
    else:  # GFA 2
        awk.append(
            f"""'BEGIN {{OFS="\\t"}} /^S/ {{if ($4 != "*") {{cmd = "gzip >> {seqfp}"; print $2, $4 | cmd; close(cmd); $4 = "*"}}}} {{print}}'"""
        )

    cmd = zcat + awk + gzip
    with open(outfp, "w") as file:
        subprocess.run(" ".join(cmd), shell=True, stdout=file)

    return outfp


def extract_subgraph_names(
    filepath: str, gfa_version: float, chr_only: bool = True
) -> list[str]:
    """Extract the names of subgraphs from a (gzipped) GFA file. Segment names
    in `W` lines are treated as subgraph names. When no `W` line exists, `PanSN`
    naming convention is required for extracting segment name from ids in `P` or
    `O|U` lines."""

    zcat = [
        "zcat",
        filepath,
    ]
    grep = ["|", "grep"]
    awk = [
        "|",
        "awk",
    ]
    # `grep1` -- get records containing subgraph names
    # `awk` -- extract subgraph names
    if gfa_version < 1.1:
        grep1 = grep + ["^P"]
        awk.append(
            r"""'{if (sep=="") {split(" 0,0\\.0;0:0/0\\|0#0_0\\-", seps, "0"); for (i in seps) {sep = seps[i]; c = gsub(sep,sep,$2); if (c==2) break} if (c!=2) exit} {split($2,a,sep); if (length(a)<3) next; else print a[3]}}'"""
        )
    elif gfa_version >= 2.0:
        grep1 = grep + ["-E", "^(O|U)"]
        awk.append(
            r"""'{if (sep=="") {split(" 0,0\\.0;0:0/0\\|0#0_0\\-", seps, "0"); for (i in seps) {sep = seps[i]; c = gsub(sep,sep,$2); if (c==2) break} if (c!=2) exit} {split($2,a,sep); if (length(a)<3) next; else print a[3]}}'"""
        )
    else:
        grep1 = grep + ["^W"]
        awk.append("'{print $4}'")
    sort = ["|", "sort", "-u"]

    cmd = zcat + grep1 + awk + sort
    # filter out non-chromosome level subgraphs
    if chr_only:
        grep2 = grep + ["-i", "^chr"]
        cmd += grep2

    return subprocess.check_output(" ".join(cmd), shell=True, text=True).splitlines()


def extract_subgraph(name: str, gfa_path: str, gfa_version: float, outdir: str):
    """Extract a subgraph by name from a (gzipped) GFA file, returning the sub-GFA's file path."""

    outfp = outdir + "/" + name + ".gfa.gz"

    zgrep = ["zgrep", "-E"]
    awk = ["|", "awk"]
    # `zgrep1` -- get records that contain set of nodes from the whole graph by subgraph name
    # `awk` -- extract node ids from set records
    if gfa_version < 2:
        if gfa_version == 1.0:
            zgrep1 = zgrep + [f"^P.*{name}"]
            awk.append(
                """'/^P/ {split($3,a,","); for (i in a) print substr(a[i], 1, length(a[i]) - 1)}'"""
            )
        elif gfa_version == 1.1:
            zgrep1 = zgrep + [f"^W.*{name}"]
            awk.append(
                """'/^W/ {split($7,a,"[<>]"); for (i=2;i in a;i++) print a[i]}'"""
            )
    else:  # GFA 2
        zgrep1 = zgrep + [f"^(O|U).*{name}"]
        awk.append(
            """'/^O/ {split($3,a," "); for (i in a) print a[i]} /^U/ {split($3,a," "); for (i in a) print substr(a[i], 1, length(a[i]) - 1)}'"""
        )
    zgrep1.append(gfa_path)
    # `tee` -- save set records to subgraph
    tee = ["|", "tee", f">(gzip > {outfp})"]
    # `sed` & `zgrep2` -- get related records from the whole graph by segment id
    sed = ["|", "sed", r"'s/^/\t/;s/$/[+-]?\t/'", "|"]
    zgrep2 = zgrep + ["-f", "-", gfa_path]
    gzip = ["|", "gzip", ">>", outfp]

    cmd = zgrep1 + tee + awk + sed + zgrep2 + gzip
    subprocess.run(" ".join(cmd), shell=True, executable="/bin/bash")

    return outfp


def subgraph_hpbuilder(
    filepath: str, outdir: str, gfa_version: float, args, subg_name: str = None
):
    """Build a hierarchical pangenome from a inseparable graph."""

    if not subg_name:
        subg_name = os.path.basename(filepath).replace(".gfa.gz", "")
    outfp_base = outdir + "/" + subg_name

    # create temp files
    fd, nodefp = tempfile.mkstemp()
    os.close(fd)
    fd, edgefp = tempfile.mkstemp()
    os.close(fd)
    fd, edgetmp = tempfile.mkstemp()
    os.close(fd)

    zcat = ["zcat", filepath]
    # `awk` -- convert the GFA format subgraph to CSV table of nodes and edges
    awk = ["|", "awk"]
    if gfa_version < 2:
        awk.append(
            f"""'BEGIN {{ OFS=","; print "start,0\\nend,0" > "{nodefp}"; print "source", "target" > "{edgefp}"}} /^S/ {{if (match($0, /LN:i:[0-9]+/)) {{s = substr($0, RSTART, RLENGTH); split(s, a, ":"); len = a[3]}} else len = -1; print $2, len >> "{nodefp}"}} /^L/ {{ print $2, $4 >> "{edgefp}" }} /^P/ {{split($3,a,","); nc = length(a); print "start", substr(a[1],1,length(a[1])-1) "\\n" substr(a[nc],1,length(a[nc]-1)), "end" >> "{edgefp}"}} /^W/ {{split($7,a,"[<>]"); nc = length(a); print "start", a[2] "\\n" a[nc], "end" >> "{edgefp}"}}'"""
        )  # in GFA 1 there is a situation that lacks segment length, -1 is set here and pass to subsequent processing
    else:  # GFA 2
        awk.append(
            f"""'BEGIN {{ OFS=","; print "start,0\\nend,0" > "{nodefp}"; print "source", "target" > "{edgefp}"}} /^S/ {{print $2, $3 >> "{nodefp}"}} /^E/ {{ print substr($3, 1, length($3) - 1), substr($4, 1, length($4) - 1) >> "{edgefp}" }} /^O/ {{split($3,a," "); nc = length(a); print "start", a[1] "\\n" a[nc], "end" >> "{edgefp}"}} /^U/ {{split($3,a," "); nc = length(a); print "start", substr(a[1],1,length(a[1])-1) "\\n" substr(a[nc],1,length(a[nc]-1)), "end" >> "{edgefp}"}}'"""
        )

    # `sort` & `join` -- remove edges with absent segment id
    sort = ["sort", "-t", ",", "-k"]
    sort_n = sort + ["1,1", "-o", nodefp, nodefp]
    sort_e1 = sort + ["1,1", "-o", edgetmp, edgefp]
    sort_e2 = ["|"] + sort + ["2,2", "|"]
    join = ["join", "-t", ","]
    join1 = join + ["-1", "1", "-2", "1", "-o", "2.1,2.2", nodefp, edgetmp]
    join2 = join + ["-1", "2", "-2", "1", "-o", "1.1,1.2", "-", nodefp, ">", edgefp]

    # `sed` -- add table headers
    sed = ["sed", "-i"]
    sed_n = sed + [r"1i\name,length", nodefp]
    sed_e = sed + [r"1i\source,target", edgefp]

    cmd1 = zcat + awk
    cmd2 = join1 + sort_e2 + join2
    subprocess.run(" ".join(cmd1), shell=True)
    subprocess.run(sort_n)
    subprocess.run(sort_e1)
    subprocess.run(" ".join(cmd2), shell=True)
    subprocess.run(sed_n)
    subprocess.run(sed_e)

    # convertions
    nodedf = pd.read_csv(f"{nodefp}", dtype={"name": "str", "length": "int32"})
    edgedf = pd.read_csv(f"{edgefp}", dtype={"source": "str", "target": "str"})
    g = Graph.DataFrame(edgedf, vertices=nodedf, use_vids=False)
    if not g.is_dag:
        raise ValueError("Cycle detected in graph, modify it into a DAG and re-run.")
    rt, st = graph2rstree(g)

    # if not args.no_wrap:
    rt, st, meta = wrap_rstree(rt, st, args.minres)
    rt, st, meta = build_index(rt, st, meta)
    if args.split:
        export(rt, st, meta, outfp_base, "tsv")
    else:
        export(rt, st, meta, outfp_base, "hp")

    # remove temp files
    os.remove(nodefp)
    os.remove(edgefp)
    os.remove(edgetmp)


def hpbuilder(args):
    """Build a Hierarchical Pangenome from a pangenome graph in GFA format."""

    # if args.wrap:
    #     # TODO: parse .hp file and run build_hierarchical_graph()
    #     pass

    # env var for performance
    os.environ["LC_ALL"] = "C"

    outdir = args.outdir if args.outdir else os.getcwd()
    gfagz = (
        args.file if ".gz" in args.file else gzip_gfa(args.file)
    )  # temp gzipped GFA for process performance
    pgname = args.name if args.name else os.path.basename(gfagz).replace(".gfa.gz", "")
    gfaver = get_gfa_version(gfagz)

    # preprocess
    gfamin = move_sequences(gfagz, outdir, gfaver)
    subgnames = extract_subgraph_names(gfamin, gfaver)

    # build Hierachical Pangenomes
    if len(subgnames) == 0:
        subgraph_hpbuilder(gfamin, outdir, gfaver, args, pgname)
    else:
        subgdir = outdir + "/subgraph"
        if os.path.exists(subgdir):
            ctn = input(
                "There is a directory 'subgraph' in the output directory, continuing the program will erase files in it. Continue? (y/n) "
            )
            invalid = True
            while invalid:
                if ctn.lower() == "y":
                    subprocess.run(["rm", "-rf", subgdir])
                    invalid = False
                elif ctn.lower() == "n":
                    raise SystemExit("Unable to write to directory.")
                else:
                    ctn = input("Please enter 'y' or 'n'. ")
        subprocess.run(["mkdir", subgdir])
        exsubg = functools.partial(
            extract_subgraph,
            gfa_path=gfamin,
            gfa_version=gfaver,
            outdir=subgdir,
        )
        with mp.Pool() as pool:
            subg_fps = pool.map(exsubg, subgnames)
        sg_hpbd = functools.partial(
            subgraph_hpbuilder,
            gfa_version=gfaver,
            outdir=subgdir,
            args=args,
        )
        with mp.Pool() as pool:
            pool.map(sg_hpbd, subg_fps)
        if args.split:
            union_hps(subgdir, pgname, outdir, "tsv")
        else:
            union_hps(subgdir, pgname, outdir, "hp")

    # remove temp files
    os.remove(gfamin)
    if not ".gz" in args.file:
        os.remove(gfagz)
