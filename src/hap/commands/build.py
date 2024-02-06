import os
import math
import collections
import pathlib
import shutil
import subprocess
import copy
import functools
import tempfile

import igraph as ig
import pandas as pd
import multiprocessing as mp
import click

import hap
from hap.lib import gfautil
from hap.lib import fileutil
from hap.lib import fileutil
from hap.commands.divide import main as divide

# TODO: rewrite some DataFrame operations in a more efficient & elegant way


class Segment:
    def __init__(self, id):
        self.id = id
        self.name = None
        self.range = [0, 0]
        self.sub_regions = []
        self.level_range = [0, 0]
        self.length = 0
        self.rank = 0
        self.frequency = 0
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
        self.range = [0, 0]
        self.parent_seg = None
        self.segments = []
        self.level_range = [0, 0]
        self.length = 0
        self.is_default = False
        self.sources = []
        self.is_var = True if type == "var" or type != "con" else False
        self.type = type
        self.total_var = 0
        # to be discarded after process
        self.min_length = 0
        self.before = None
        self.after = None

    def add_segment(self, id):
        """Create and add segment to current region, setting the same `level_range`,
        `sources`, and return the created segment.
        If region `type` is `con` and no segment exists, added segment is set
        to default."""

        segment = Segment(id)
        self.segments.append(segment.id)
        segment.level_range = self.level_range
        segment.sources = self.sources
        return segment

    def to_dict(self):
        return self.__dict__

    def from_dict(self, dict: dict):
        for k, v in dict.items():
            if hasattr(self, k):
                setattr(self, k, v)


_ids = {
    "s": 0,
    "r": 0,
    "var": 0,
    "con": 0,
    "ale": 0,
    "ind": 0,
    "sv": 0,
    "snp": 0,
}


def _get_id(type: str) -> str:
    _ids[type] += 1
    prefix = type if type == "s" or type == "r" else type.upper()
    return "-".join([prefix, str(_ids[type])])


def graph2rstree(graph: ig.Graph):
    """Build a region-segment tree for pangenome representation from a normalized sequence graph."""

    # Inits
    visited = set()
    pathstarts = collections.deque()
    paths = []
    meta = {"sources": graph["haplotypes"].split(",")}
    rt = pd.DataFrame(
        columns=[
            "id",
            "name",
            "range",
            "parent_seg",
            "segments",
            "level_range",
            "length",
            "is_default",
            "sources",
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
            "range",
            "sub_regions",
            "level_range",
            "length",
            "rank",
            "frequency",
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

    # Postprocess
    # Turn the nodes at segment end into each split region
    segends = graph.vs.select(parent_seg_ne=None)
    for se in segends:
        if se["name"] != "end" and se["name"] != "start":
            # get current level
            parseg_id = se["parent_seg"]
            pi = st[st["id"] == parseg_id].index[0]
            level = st.iat[pi, st.columns.get_loc("level_range")][0] + 1

            # build elements and fill properties
            region = Region(_get_id("r"), "con")
            region.level_range = [level, level]
            region.sources = copy.deepcopy(st.iat[pi, st.columns.get_loc("sources")])
            segment = region.add_segment(se["name"])
            segment.length = se["length"]
            segment.frequency = len(segment.sources) / len(meta["sources"])
            region.parent_seg = parseg_id

            # write to dataframe
            subrg = st.iat[pi, st.columns.get_loc("sub_regions")]
            subrg.append(region.id)
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
            "length": "uint64",
            "rank": "uint8",
            "frequency": "float16",
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

    # Fill dispensable properties for created elements

    def fill_sources(group):
        """Fill `frequency` & `sources` field for some created segments."""
        rows = group["sources"].apply(len) == 0
        if rows.any():
            i = group.index[rows][0]
            group.at[i, "sources"] = list(
                set(group["sources_r"].iloc[0])
                - set().union(*[x for x in group["sources"] if len(x) > 0])
            )
            group.at[i, "frequency"] = len(group.at[i, "sources"]) / len(
                meta["sources"]
            )
        return group

    exploded = st.merge(
        rt.loc[:, ["id", "segments", "sources"]].explode("segments"),
        left_on="id",
        right_on="segments",
        how="left",
        suffixes=("", "_r"),
    ).drop(
        "segments", axis=1
    )  # add region id for grouping
    exploded = exploded.groupby("id_r", group_keys=False).apply(
        fill_sources
    )  # fill the blanks

    exploded["rank"] = (
        exploded.groupby("id_r")["frequency"]
        .rank(
            method="first", ascending=False
        )  # TODO: adjust rank method to prefer insertion
        .astype(int)
        - 1
    )  # calculate rank by ordering
    st = exploded.drop(["id_r", "sources_r"], axis=1)

    return rt, st, meta


def calculate_properties_l2r(rt: pd.DataFrame, st: pd.DataFrame, meta: dict):
    """Calculate properties of regions and segments from leaves to root. Some properties are essential that this function be called before other procedures."""

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
                        rn = _get_id("snp")
                    else:
                        rt.iat[ri, rt.columns.get_loc("type")] = "ale"
                        rn = _get_id("ale")
                    rt.iat[ri, rt.columns.get_loc("name")] = rn
                    st.iloc[sis, st.columns.get_loc("name")] = [
                        rn + "-" + chr(j) for j in range(97, 97 + len(sis))
                    ]  # generate names like `ALE-{n}-a,b,c`

                # del exists
                elif minlen == 0 or (minlen < 10 and d / minlen > 5):
                    rt.iat[ri, rt.columns.get_loc("min_length")] = lensr[
                        lensr > minlen
                    ].min()
                    if d > 50:
                        rt.iat[ri, rt.columns.get_loc("type")] = "sv"
                        rn = _get_id("sv")
                    else:
                        rt.iat[ri, rt.columns.get_loc("type")] = "ind"
                        rn = _get_id("ind")
                    rt.iat[ri, rt.columns.get_loc("name")] = rn
                    mini = lensr.idxmin()
                    st.iat[mini, st.columns.get_loc("name")] = rn + "-d"
                    sis.remove(mini)
                    if len(sis) > 1:
                        st.iloc[sis, st.columns.get_loc("name")] = [
                            rn + "-i" + chr(j) for j in range(97, 97 + len(sis))
                        ]
                    else:
                        st.iloc[sis, st.columns.get_loc("name")] = rn + "-i"

                # not determined
                else:
                    rt.iat[ri, rt.columns.get_loc("type")] = "var"
                    rn = _get_id("var")
                    rt.iat[ri, rt.columns.get_loc("name")] = rn
                    st.iloc[sis, st.columns.get_loc("name")] = [
                        rn + "-" + chr(j) for j in range(97, 97 + len(sis))
                    ]

            # consensus
            else:
                rn = _get_id("con")
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

    return rt, st, meta


def unvisited_path(
    start: int, graph: ig.Graph, visited: set, pathstarts: collections.deque
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
    graph: ig.Graph,
    rt: pd.DataFrame,
    st: pd.DataFrame,
    visited: set,
    pathstarts: collections.deque,
    paths: list[list[int]],
):
    """Traverse and process an independant path."""

    g = graph
    haps = g["haplotypes"].split(",")

    # Init the path based on traverse order
    # If is main path
    if g.vs[start]["name"] == "start":
        region = Region(_get_id("r"), "con")
        region.sources = haps
        segment = Segment(_get_id("s"))
        segment.is_wrapper = True

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
            sources = copy.deepcopy(st.iat[pi, st.columns.get_loc("sources")])

            # Build elements and fill properties
            if g.vs[before]["name"] != "start":
                # TODO: change to support consensus bead that contain more than one node
                pre_region = Region(_get_id("r"), "con")
                pre_region.level_range = [level, level]
                pre_region.sources = sources
                pre_seg = pre_region.add_segment(g.vs[before]["name"])
                pre_seg.length = g.vs[before]["length"]
                pre_seg.frequency = len(pre_seg.sources) / len(haps)
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
            region = Region(_get_id("r"), "var")
            segment = Segment(_get_id("s"))
            segment.level_range = region.level_range = [level, level]
            g.vs[before]["parent_seg"] = None  # "before" can't be accessed anymore
            region.parent_seg = parseg_id
            region.sources = sources
            region.before = g.vs[before]["name"]
            subrg.append(region.id)
            # suspend current region dumping (to df) for potential updates

        # or add segment to existing region
        else:
            rg_dict = rt[rt["before"] == g.vs[before]["name"]].iloc[0].to_dict()
            segment = Segment(_get_id("s"))
            region = Region(rg_dict["id"], rg_dict["type"])
            region.from_dict(rg_dict)
            segment.level_range = region.level_range
            level = region.level_range[0]

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

            d = g.add_vertex(_get_id("s"), length=0).index
            g.vs[d]["sources"] = []
            g.vs[d]["frequency"] = 0
            g.add_edges([(s, d), (d, node)])
            g.delete_edges((s, node))
            ni = pathstarts.index(node)
            pathstarts.insert(ni, d)
            pathstarts.remove(node)
        g.vs[node]["parent_seg"] = segment.id
        g.vs[node]["path"] = len(paths)
        if g.vs[node]["name"] != "start" and g.vs[node]["name"] != "end":
            segment.sources = list(set().union(segment.sources, g.vs[node]["sources"]))
            segment.frequency = max(segment.frequency, g.vs[node]["frequency"])
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
        segment.is_wrapper = True
    region.segments.append(segment.id)
    segdf = pd.DataFrame([segment.to_dict()])
    if st.empty:
        st = segdf
    else:
        st = pd.concat([st, segdf], ignore_index=True, copy=False)

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
                _get_id("s"), length=0
            ).index  # NOTE: `d` node isn't added to origin path
            g.vs[d]["sources"] = []
            g.vs[d]["frequency"] = 0
            g.add_edges([(before, d), (d, af)])
            g.delete_edges((before, af))
            visited.add(d)
            org_ale_path = [d]
        if len(org_ale_path) == 1:
            org_ale_node = org_ale_path[0]
            ale_seg = Segment(g.vs[org_ale_node]["name"])
            ale_seg.length = g.vs[org_ale_node]["length"]
            ale_seg.frequency = g.vs[org_ale_node]["frequency"]
            ale_seg.sources = g.vs[org_ale_node]["sources"]
            g.vs[org_ale_node]["parent_seg"] = None
        else:
            ale_seg = Segment(_get_id("s"))
            ale_seg.is_wrapper = True
            for n in org_ale_path:
                g.vs[n]["parent_seg"] = ale_seg.id  # Update parent for separable nodes
                ale_seg.sources = list(set().union(ale_seg.sources, g.vs[n]["sources"]))
                ale_seg.frequency = max(ale_seg.frequency, g.vs[n]["frequency"])

        ale_seg.level_range = [level, level]
        region.segments.append(ale_seg.id)
        st = pd.concat(
            [st, pd.DataFrame([ale_seg.to_dict()])], ignore_index=True, copy=False
        )

    rt = pd.concat(
        [rt, pd.DataFrame([region.to_dict()])], ignore_index=True, copy=False
    )
    return rt, st


def wrap_rstree(rt: pd.DataFrame, st: pd.DataFrame, meta: dict, minres=0.04):
    """Wrap small regions, deepen the region-segment tree and establish hierarchy."""

    if minres <= 0:
        raise ValueError("Min resolution must be greater than 0.")
    totallen = rt[rt["level_range"].apply(lambda lr: lr[0] == 0 and lr[1] == 0)][
        "length"
    ].iloc[0]
    maxlevel = math.ceil(
        math.log2(totallen / 1000 / minres)
    )  # new max level for hierarchical graph
    meta["max_level"] = maxlevel
    meta["total_length"] = int(totallen)
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

            si = st[st["id"] == region["parent_seg"]].index.to_list()[0]

            # move parent segment to current layer if all its child regions are wrapped into one
            if (
                len(r2bw_iranges) == 1
                and r2bw_iranges[0][0] == 0
                and r2bw_iranges[0][1] == len(rid_list) - 1
            ):
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
                wrap_region = Region(_get_id("r"), "con")
                wrap_region.level_range = [i, i]
                wrap_region.sources = copy.deepcopy(
                    st.iat[si, st.columns.get_loc("sources")]
                )
                wrap_segment = wrap_region.add_segment(_get_id("s"))
                wrap_region.length = wrap_region.min_length = wrap_segment.length = (
                    totallen
                )
                wrap_segment.frequency = len(wrap_segment.sources) / len(
                    meta["sources"]
                )
                wrap_segment.is_wrapper = True
                wrap_segment.name = wrap_region.name = _get_id("con")
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
                        "length": "uint64",
                        "rank": "uint8",
                        "frequency": "float16",
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
            st.iloc[sis, st.columns.get_loc("level_range")] = st.iloc[
                sis, st.columns.get_loc("level_range")
            ].apply(lambda lr: lvlrg)

    # TODO: Find algorithm to unwrap all elements within max level limit
    if len(rt[rt["level_range"].apply(lambda lr: len(lr) == 0)]) > 0:
        raise Exception(
            "Warning: There are small regions remain wrapped, to unwrap all regions, flatten your input graph or decrease `minres`."
        )

    return rt, st, meta


def calculate_properties_r2l(rt: pd.DataFrame, st: pd.DataFrame, meta: dict):
    """Calculates the properties for elements from root to leaves in the region-segment tree."""

    # from root to leave
    root_ri = rt[rt["parent_seg"].isna()].index.to_list()[0]
    root_rid = rt.iat[root_ri, rt.columns.get_loc("id")]

    # bootstrap properties for root region & segment
    totallen = meta["total_length"]
    rt.iat[root_ri, rt.columns.get_loc("range")] = [0, totallen]  # range index
    rt.iat[root_ri, rt.columns.get_loc("is_default")] = True  # default on display
    reg_dq = collections.deque([root_rid])

    while len(reg_dq) > 0:
        regid = reg_dq.popleft()
        parreg: dict = rt[rt["id"] == regid].iloc[0].to_dict()
        sids: list[str] = parreg["segments"]

        for sid in sids:
            si = st[st["id"] == sid].index.to_list()[0]
            rids = st.iat[si, st.columns.get_loc("sub_regions")]

            # calculate range index for child segments
            length = int(st.iat[si, st.columns.get_loc("length")])
            if length > parreg["range"][1] - parreg["range"][0]:
                raise Exception("Internal Error: element attribute calculation error")
            elif length == parreg["range"][1] - parreg["range"][0]:
                start = parreg["range"][0]
            else:
                dlen = parreg["range"][1] - parreg["range"][0] - length
                start = parreg["range"][0] + math.floor(dlen / 2)
            st.iat[si, st.columns.get_loc("range")] = [
                start,
                start + length,
            ]

            # judge if is default
            segrank = st.iat[si, st.columns.get_loc("rank")]
            ris = rt[rt["id"].isin(rids)].index.to_list()
            rt.iloc[ris, rt.columns.get_loc("is_default")] = (
                parreg["is_default"] and segrank == 0
            )

            for rid in rids:
                ri = rt[rt["id"] == rid].index.to_list()[0]

                # calculate range index for child-child regions
                length = int(rt.iat[ri, rt.columns.get_loc("length")])
                rt.iat[ri, rt.columns.get_loc("range")] = [
                    start,
                    start + length,
                ]
                start += length

                reg_dq.append(rid)

    return rt, st, meta


def export(
    rt: pd.DataFrame,
    st: pd.DataFrame,
    meta: dict,
    basepath: str,
    format="st",
):
    """Export region-segment tree to assigned format."""

    rt.drop(
        [
            "name",
            "level_range",
            "length",
            "sources",
            "is_var",
            "total_var",
            "min_length",
            "before",
            "after",
        ],
        axis=1,
        inplace=True,
    )

    if format == "st":
        rt.rename(
            columns={
                "range": "region_range",
                "type": "region_type",
                "is_default": "region_is_default",
            },
            inplace=True,
        )
        st = st.merge(
            rt.loc[
                :,
                [
                    "segments",
                    "region_range",
                    "parent_seg",
                    "region_type",
                    "region_is_default",
                ],
            ].explode("segments"),
            left_on="id",
            right_on="segments",
            how="left",
            suffixes=("", "_r"),
        ).drop("segments", axis=1)
        st.to_csv(basepath + ".st.tsv", sep="\t", na_rep="*", index=False)

        meta["sources"] = ",".join(meta["sources"])
        metasr = pd.Series(meta)
        metasr.to_csv(basepath + ".meta.tsv", sep="\t", na_rep="*", header=False)

    elif format == "rst":
        rt.to_csv(basepath + ".rt.tsv", sep="\t", na_rep="*", index=False)
        st.to_csv(basepath + ".st.tsv", sep="\t", na_rep="*", index=False)
    else:
        raise ValueError("Unsupported output format.")


# def union(
#     indir: str,
#     pgname: str,
#     outdir: str,
#     format: str = "hp",
# ):
#     """Union a list of sub-Hierarchical-Pangenomes into a whole."""

#     # TODO: Add `pgname` prefix to each element's name

#     if format == "hp":
#         subprocess.run(f"cat {indir}/*.hp > {outdir}/{pgname}.hp", shell=True)
#     elif format == "tsv":
#         cat = functools.partial(subprocess.run, shell=True)
#         with mp.Pool() as pool:
#             pool.map(
#                 cat,
#                 [
#                     f"cat {indir}/*.rt.tsv > {outdir}/{pgname}.rt.tsv",
#                     f"cat {indir}/*.st.tsv > {outdir}/{pgname}.st.tsv",
#                 ],
#             )
#     else:
#         raise ValueError("Unsupported output format.")


def gfa2graph(filepath: str, gfa_version: float) -> ig.Graph:
    """Convert a GFA file to an igraph.Graph object."""

    # create temp files
    infofp, nodefp, edgefp, edgetmp = fileutil.create_tmp_files(4)

    # get awk scripts
    awkfp_pps = os.path.join(hap.pkgroot, "lib", "parse_pansn_str.awk")
    awkfp_g12c = os.path.join(hap.pkgroot, "lib", "gfa12csv.awk")
    awkfp_g22c = os.path.join(hap.pkgroot, "lib", "gfa22csv.awk")

    # `awk` -- convert the GFA format subgraph to CSV tables of nodes and edges, plus a info file
    awk = [
        "awk",
        "-v",
        f"infofp={infofp}",
        "-v",
        f"nodefp={nodefp}",
        "-v",
        f"edgefp={edgefp}",
        "-f",
        awkfp_pps,
        "-f",
    ]
    if gfa_version < 2:
        awk.append(awkfp_g12c)
    else:  # GFA 2
        awk.append(awkfp_g22c)
    awk.append(filepath)

    locale = ["LC_ALL=C"]

    # `sort` & `join` -- remove edges with absent segment id
    sort = ["sort", "-t", r"$'\t'", "-k"]
    sort_n = sort + ["1,1", "-o", nodefp, nodefp]
    sort_e1 = sort + ["1,1", "-o", edgetmp, edgefp]
    sort_e2 = ["|"] + sort + ["2,2", "|"]
    join = ["join", "-t", r"$'\t'"]
    join1 = join + ["-1", "1", "-2", "1", "-o", "2.1,2.2", nodefp, edgetmp]
    join2 = join + ["-1", "2", "-2", "1", "-o", "1.1,1.2", "-", nodefp, ">", edgefp]

    # `sed` -- add table headers
    sed = ["sed", "-i"]
    sed_n = sed + [r"1i\name\tlength\tfrequency\tsources", nodefp]
    sed_e = sed + [r"1i\source\ttarget", edgefp]

    cmd = locale + join1 + sort_e2 + join2
    try:
        subprocess.run(awk)
        subprocess.run(" ".join(locale + sort_n), shell=True, executable="/bin/bash")
        subprocess.run(" ".join(locale + sort_e1), shell=True, executable="/bin/bash")
        subprocess.run(" ".join(cmd), shell=True, executable="/bin/bash")
        subprocess.run(sed_n)
        subprocess.run(sed_e)

        # convertions
        nodedf = pd.read_csv(
            nodefp,
            sep="\t",
            dtype={"name": "str", "length": "int32", "frequency": "float32"},
            converters={"sources": lambda s: s.split(",")},
        )
        edgedf = pd.read_csv(edgefp, sep="\t", dtype={"source": "str", "target": "str"})

        g = ig.Graph.DataFrame(edgedf, vertices=nodedf, use_vids=False)
        if not g.is_dag:
            raise ValueError(
                "Cycle detected in graph, modify it into a DAG and re-run."
            )

        # store metadata in graph attributes
        infodf = pd.read_csv(infofp, sep="\t", header=None, names=["key", "value"])
        infodict = infodf.set_index("key")["value"].to_dict()
        for k, v in infodict.items():
            g[k] = v

    finally:
        # remove temp files
        fileutil.remove_files([infofp, nodefp, edgefp, edgetmp])

    return g


def build(filepath: str, gfa_version: float, outdir: str, min_resolution: float):
    """Build a Hierarchical Pangenome from a inseparable graph."""

    basename = fileutil.remove_suffix_containing(os.path.basename(filepath), ".gfa")
    basepath = os.path.join(outdir, basename)

    g = gfa2graph(filepath, gfa_version)
    rst = graph2rstree(g)
    rst = calculate_properties_l2r(*rst)

    # if not no_wrap:
    rst = wrap_rstree(*rst, min_resolution)
    rst = calculate_properties_r2l(*rst)

    export(*rst, basepath)


def build_in_parallel(filepath: list[str], outdir: str, min_resolution: float):
    """Build Hierarchical Pangenomes in parallel for a list of GFA files."""

    pp_gfa = functools.partial(
        gfautil.preprocess_gfa,
        outdir=outdir,
    )
    with mp.Pool() as pool:
        pp_res = pool.map(pp_gfa, filepath)

    gfamins, _ = zip(*pp_res)

    sg_hpbd = functools.partial(
        build,
        outdir=outdir,
        min_resolution=min_resolution,
    )
    with mp.Pool() as pool:
        try:
            pool.starmap(sg_hpbd, pp_res)
        finally:
            if click.confirm(
                f"Delete temporary files: {gfamins}?", default=True
            ):  # TODO: remove this after debugging
                pool.map_async(os.remove, gfamins)


def validate_arg_path(
    ctx: click.Context, param: click.Parameter, value: tuple[pathlib.Path]
):
    """Validate argument `path` of the `build` command."""

    if "subgraph" in ctx.params and ctx.params["subgraph"]:
        if len(value) == 1:
            if value[0].is_dir():
                return value
            else:
                raise click.BadParameter(
                    "More than one file, or a directory must be provided if specified with `-s/--subgraph`."
                )
        else:
            for v in value:
                if v.is_dir:
                    raise click.BadParameter(
                        "Multiple directories are not allowed, use one directory or a list of files instead."
                    )
            return value
    else:
        if len(value) > 1:
            raise click.BadParameter(
                "Building for more than one graph is not supported. use `-s/--subgraph` if building from a group of subgraphs."
            )
        return value


@click.command(
    "build",
    context_settings=hap.ctx_settings,
    short_help="Build a Hierarchical Pangenome",
)
@click.pass_context
@click.argument(
    "path",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    callback=validate_arg_path,
)
@click.option(
    "-s",
    "--subgraph",
    is_flag=True,
    default=False,
    help="Use a group of graphs as input",
)
@click.option(
    "-o",
    "--outdir",
    type=click.Path(file_okay=False, path_type=pathlib.Path),
    help="Output directory",
)
@click.option(
    "-r",
    "--min-res",
    type=float,
    default=0.04,
    help="Minimum resolution of the Hierarchical Pangenome, in bp/px",
)
def main(
    ctx: click.Context,
    path: tuple[pathlib.Path],
    subgraph: bool,
    outdir: pathlib.Path,
    min_res: float,
):
    """
    Build a Hierarchical Pangenome from a pangenome graph in GFA format.

    PATH: Path to the pangenome graph in GFA format. If `-s/--subgraph` is specified, PATH should be a list of subgraphs or a
    directory containing the subgraphs.
    """

    # if wrap:
    #     # TODO: parse .hp file and run build_hierarchical_graph()
    #     pass

    # get `basename` and `subg_fps`
    # subgraph as inputs
    if subgraph:
        if len(path) == 1:
            subg_fps = fileutil.get_files_from_dir(str(path[0]), "gfa")
        else:
            subg_fps = [str(fp) for fp in path]
            subg_fns = [str(fp.name) for fp in subg_fps]
        basename = os.path.commonprefix(subg_fns)
    else:
        gfafp = path[0]
        basename = fileutil.remove_suffix_containing(gfafp.name, ".gfa")
        # divide into subgraphs
        subgdir = tempfile.mkdtemp(prefix="hap.", suffix=".subgraph")
        ctx.invoke(divide, file=gfafp, outdir=pathlib.Path(subgdir))

        try:
            subg_fps = fileutil.get_files_from_dir(subgdir, "gfa")
        except FileNotFoundError:
            subg_fps = [str(gfafp)]

    if not outdir:
        outdir = pathlib.Path.cwd() / f"{basename}.hap"
    outdir = outdir.resolve()
    if outdir.exists() and not fileutil.is_dir_empty(str(outdir)):
        if click.confirm(
            f"Output directory {str(outdir)} is not empty, continuing the program will erase files in it. Continue?",
            abort=True,
        ):
            shutil.rmtree(str(outdir))
    outdir.mkdir(parents=True, exist_ok=True)

    # build Hierachical Pangenomes
    try:
        build_in_parallel(subg_fps, str(outdir), min_res)
    finally:
        if not subgraph:
            if click.confirm(
                f"Delete temporary subgraph directory: {subgdir}?",
                default=True,
            ):
                shutil.rmtree(subgdir)


if __name__ == "__main__":
    main()
