import collections
import functools
import math
import multiprocessing as mp
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Any, NamedTuple

import click
import igraph as ig
import pandas as pd
import psycopg2

import hap
from hap.lib import database as db
from hap.lib import fileutil
from hap.lib import gfa as gfa_mod
from hap.lib.elements import Region
from hap.lib.elements import Segment
from hap.lib.error import (
    DataInvalidError,
    DatabaseError,
    InternalError,
)
from hap.lib.util_obj import ValidationResult


# OPTIMIZE: Rewrite some DataFrame operations in a more efficient & elegant way
# TODO: Refactor this command into data validation, data processing, and data output parts
# TODO: Extract `main()` to a cli-lib-independent function which refered by `cli()`
# TODO: Refactor the class utils to composition or inheritance
# TODO: Change method for generating IDs to avoid conflicts
# TODO: Add params and funcs for distinct / optional parts of the input pangenome graph

# Incremental IDs for element names
identifiers = {
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
    """Get an incremental ID by type. Returns a string like `s-1`."""

    identifiers[type] += 1
    prefix = type if type == "s" or type == "r" else type.upper()
    return "-".join([prefix, str(identifiers[type])])


def validate_gfa(gfa_obj: gfa_mod.GFA) -> ValidationResult:
    """Validate a GFA file for building."""

    if not gfa_obj.can_extract_length():
        return ValidationResult(False, "The GFA file lacks length information.")
    if len(gfa_obj.get_haplotypes()) == 0:
        return ValidationResult(False, "The GFA file lacks haplotype information.")
    return ValidationResult(True, "")


def validate_graph(graph: ig.Graph) -> ValidationResult:
    """Validate a graph for building."""

    if not graph.is_dag:
        return ValidationResult(False, "The graph is not a DAG.")
    if not graph.is_connected(mode="WEAK"):
        return ValidationResult(False, "The graph is not connected.")
    if graph_has_successive_variation_node(graph):
        return ValidationResult(False, "The graph has successive variation nodes.")
    return ValidationResult(True, "")


def graph_has_successive_variation_node(graph: ig.Graph) -> bool:
    for node in graph.vs:
        if is_variation_node(node, graph):
            pr = graph.neighbors(node, mode="in")[0]
            sr = graph.neighbors(node, mode="out")[0]
            if is_variation_node(pr, graph) or is_variation_node(sr, graph):
                return True
    return False


def is_variation_node(node: ig.Vertex, graph: ig.Graph) -> bool:
    """Check if a node is a variation node."""

    if graph.degree(node, mode="in") == 1 and graph.degree(node, mode="out") == 1:
        return True
    return False


def unvisited_path(
    start_node: int, graph: ig.Graph, visited_nodes: set, path_starts: collections.deque
):
    """
    Returns a generator of an unvisited path the `start_node` belongs to. Each
    node in the path is unvisited, and the path's predecessor & successor are
    both visited or empty.

    When encounter node with multiple successors, proceed with one of them and
    move the remainder to `path_starts`.
    """

    next = start_node
    while next is not None:
        yield next
        successors = graph.neighbors(next, mode="out")
        next = None
        if successors:
            for sr in successors:
                if sr not in visited_nodes:
                    if next is not None:
                        path_starts.append(sr)
                    else:
                        next = sr


def process_path(
    start_node: int,
    graph: ig.Graph,
    regions: pd.DataFrame,
    segments: pd.DataFrame,
    visited_nodes: set,
    path_starts: collections.deque,
    paths: list[list[int]],
):
    """Traverse and process an independant path."""

    g = graph
    rt = regions
    st = segments
    start = start_node
    visited = visited_nodes
    haplotypes = g["haplotypes"].split(",")

    # Init the path based on traverse order
    # If is main path
    if g.vs[start]["name"] == "head":
        region = Region(get_id("r"), "con")
        region.sources = haplotypes
        segment = Segment(get_id("s"))
        segment.is_wrapper = True

    # or side path
    else:
        predecessors = g.neighbors(start, mode="in")
        befores = [p for p in predecessors if p in visited]
        if len(befores) > 1:
            raise DataInvalidError(
                "Unable to resolve complex graph structure. Flatten the graph and rerun."
            )
        else:
            before = befores[0]  # TODO: eliminate multiple attachment relations

        # Split into regions if hasn't been treated
        if rt[rt["before"] == g.vs[before]["name"]].empty:
            # Get parent segment's properties
            parseg_id = g.vs[before]["parent_segment"]
            pi = st[st["id"] == parseg_id].index[0]
            level = st.at[pi, "level_range"][0] + 1
            sub_regions = st.at[pi, "sub_regions"]
            sources = st.at[pi, "sources"].copy()

            # Build elements and fill properties
            if g.vs[before]["name"] != "head":
                # TODO: change to support consensus bead that contain more than one node
                previous_region = Region(get_id("r"), "con")
                previous_region.level_range = [level, level]
                previous_region.sources = sources
                previous_seg = (
                    previous_region.add_segment(g.vs[before]["name"], original=True)
                    if g.vs[before]["length"] > 0
                    else previous_region.add_segment(g.vs[before]["name"])
                )
                previous_seg.length = g.vs[before]["length"]
                previous_seg.frequency = len(previous_seg.sources) / len(haplotypes)
                previous_region.parent_segment = parseg_id
                # write to dataframe
                st = pd.concat(
                    [st, pd.DataFrame([previous_seg.to_dict()])],
                    ignore_index=True,
                    copy=False,
                )
                rt = pd.concat(
                    [rt, pd.DataFrame([previous_region.to_dict()])],
                    ignore_index=True,
                    copy=False,
                )
                sub_regions.append(previous_region.id)
            region = Region(get_id("r"), "var")
            segment = Segment(get_id("s"))
            segment.level_range = region.level_range = [level, level]
            g.vs[before]["parent_segment"] = None  # "before" can't be accessed anymore
            region.parent_segment = parseg_id
            region.sources = sources
            region.before = g.vs[before]["name"]
            sub_regions.append(region.id)
            # suspend current region dumping (to df) for potential updates

        # or add segment to existing region
        else:
            region_dict = rt[rt["before"] == g.vs[before]["name"]].iloc[0].to_dict()
            segment = Segment(get_id("s"))
            region = Region(region_dict["id"], region_dict["type"])
            region.from_dict(region_dict)
            segment.level_range = region.level_range
            level = region.level_range[0]

    # Generate current path & process its nodes
    path = []
    for node in unvisited_path(start, g, visited, path_starts):
        visited.add(node)
        path.append(node)
        # if run across del site
        while node in path_starts:
            # find the farther predecessor
            # other = None
            for predecessor in g.neighbors(node, mode="in"):
                if predecessor in visited and predecessor != last:
                    s = predecessor
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
                raise DataInvalidError(
                    "Unable to resolve complex graph structure. Flatten the graph and rerun."
                )

            del_node = g.add_vertex(get_id("s"), length=0).index
            g.vs[del_node]["sources"] = []
            g.vs[del_node]["frequency"] = 0
            g.add_edges([(s, del_node), (del_node, node)])
            g.delete_edges((s, node))
            ni = path_starts.index(node)
            path_starts.insert(ni, del_node)
            path_starts.remove(node)
        g.vs[node]["parent_segment"] = segment.id
        g.vs[node]["path"] = len(paths)
        if g.vs[node]["name"] != "head" and g.vs[node]["name"] != "tail":
            segment.sources = list(set().union(segment.sources, g.vs[node]["sources"]))
            segment.frequency = max(segment.frequency, g.vs[node]["frequency"])
        last = node

    # Rewrite properties if no `sub_regions` would be found
    if len(path) == 1:
        ni = path[0]
        segment.id = g.vs[ni]["name"]  # TODO: debug why `original_id` is wrongly added
        segment.length = g.vs[ni]["length"]
        if segment.length > 0:
            segment.original_id = segment.id
        g.vs[ni][
            "parent_segment"
        ] = None  # inseperable segment has no `parent_segment` record, a flag for leaves
        g.vs[ni]["path"] = None
    else:
        paths.append(path)
        segment.is_wrapper = True
    region.segments.append(
        segment.id
    )  # if region exists in the dataframe, it's `segments` will be updated
    segment_df = pd.DataFrame([segment.to_dict()])
    if st.empty:
        st = segment_df
    else:
        st = pd.concat([st, segment_df], ignore_index=True, copy=False)

    # Process allele region if have
    if g.vs[start]["name"] != "head":
        if not rt[rt["before"] == g.vs[before]["name"]].empty:
            return rt, st
        else:
            # Find allele path
            pi = g.vs[before]["path"]
            origin_path = paths[pi]
            b = origin_path.index(before)
            successors = g.neighbors(node, mode="out")
            afters = [s for s in successors if s in visited]
            if len(afters) > 1:
                raise DataInvalidError(
                    "Unable to resolve complex graph structure. Flatten the graph and rerun."
                )
            af = afters[0]
            region.after = g.vs[af][
                "name"
            ]  # TODO: eliminate multiple attachment relations
            a = origin_path.index(af)
            if b < a:
                origin_allele_path = origin_path[b + 1 : a]

            # Build allele segment
            if not origin_allele_path:  # allele is del
                del_node = g.add_vertex(
                    get_id("s"), length=0
                ).index  # NOTE: `d` node isn't added to origin path
                g.vs[del_node]["sources"] = []
                g.vs[del_node]["frequency"] = 0
                g.add_edges([(before, del_node), (del_node, af)])
                g.delete_edges((before, af))
                visited.add(del_node)
                origin_allele_path = [del_node]
            if len(origin_allele_path) == 1:
                origin_allele_node = origin_allele_path[0]
                allele_segment = (
                    Segment(g.vs[origin_allele_node]["name"], original=True)
                    if g.vs[origin_allele_node]["length"] > 0
                    else Segment(g.vs[origin_allele_node]["name"])
                )
                allele_segment.length = g.vs[origin_allele_node]["length"]
                allele_segment.frequency = g.vs[origin_allele_node]["frequency"]
                allele_segment.sources = g.vs[origin_allele_node]["sources"]
                g.vs[origin_allele_node]["parent_segment"] = None
            else:
                allele_segment = Segment(get_id("s"))
                allele_segment.is_wrapper = True
                for node in origin_allele_path:
                    g.vs[node][
                        "parent_segment"
                    ] = allele_segment.id  # Update parent for separable nodes
                    allele_segment.sources = list(
                        set().union(allele_segment.sources, g.vs[node]["sources"])
                    )
                    allele_segment.frequency = max(
                        allele_segment.frequency, g.vs[node]["frequency"]
                    )

            allele_segment.level_range = [level, level]
            region.segments.append(allele_segment.id)
            st = pd.concat(
                [st, pd.DataFrame([allele_segment.to_dict()])],
                ignore_index=True,
                copy=False,
            )

    rt = pd.concat(
        [rt, pd.DataFrame([region.to_dict()])], ignore_index=True, copy=False
    )
    return rt, st


def graph2rstree(graph: ig.Graph):
    """Build a region-segment tree for pangenome representation from a normalized sequence graph."""

    # Inits
    visited_nodes: set[int] = set()
    path_starts: collections.deque = collections.deque()
    paths: list[list] = []
    meta = {"sources": graph["haplotypes"].split(",")}
    rt = pd.DataFrame(
        columns=[
            "id",
            "semantic_id",
            "level_range",
            "coordinate",
            "is_default",
            "length",
            "is_variant",
            "type",
            "total_variants",
            "subgraph",
            "parent_segment",
            "segments",
            "sources",
            "min_length",
            "before",
            "after",
        ]
    )
    st = pd.DataFrame(
        columns=[
            "id",
            "original_id",
            "semantic_id",
            "level_range",
            "coordinate",
            "rank",
            "length",
            "frequency",
            "direct_variants",
            "total_variants",
            "is_wrapper",
            "sub_regions",
            "sources",
        ]
    )
    try:
        head = graph.vs.find("head").index
    except ValueError:
        head = graph.add_vertex("head", length=0).index
    for start in graph.vs.select(_indegree=0):
        if not graph.are_connected(head, start.index):
            graph.add_edges([(head, start.index)])
    try:
        tail = graph.vs.find("tail").index
    except ValueError:
        tail = graph.add_vertex("tail", length=0).index
    for end in graph.vs.select(_outdegree=0):
        if not graph.are_connected(end.index, tail):
            graph.add_edges([(end.index, tail)])
    path_starts.append(head)

    # Traversing the graph
    while len(path_starts) != 0:
        start = path_starts.popleft()
        rt, st = process_path(start, graph, rt, st, visited_nodes, path_starts, paths)

    # Postprocess
    # Turn the nodes at segment end into each split region
    segends = graph.vs.select(parent_segment_ne=None)
    for se in segends:
        if se["name"] != "tail" and se["name"] != "head":
            # get current level
            parseg_id = se["parent_segment"]
            pi = st[st["id"] == parseg_id].index[0]
            level = st.at[pi, "level_range"][0] + 1

            # build elements and fill properties
            region = Region(get_id("r"), "con")
            region.level_range = [level, level]
            region.sources = st.at[pi, "sources"].copy()
            segment = (
                region.add_segment(se["name"], original=True)
                if se["length"] > 0
                else region.add_segment(se["name"])
            )
            segment.length = se["length"]
            segment.frequency = len(segment.sources) / len(meta["sources"])
            region.parent_segment = parseg_id

            # write to dataframe
            subrg = st.at[pi, "sub_regions"]
            subrg.append(region.id)
            st = pd.concat(
                [st, pd.DataFrame([segment.to_dict()])], ignore_index=True, copy=False
            )
            rt = pd.concat(
                [rt, pd.DataFrame([region.to_dict()])], ignore_index=True, copy=False
            )
        graph.vs[se.index]["parent_segment"] = None
    st = st.astype(
        {
            "id": "string",
            "original_id": "string",
            "semantic_id": "string",
            "rank": "uint8",
            "length": "uint64",
            "frequency": "float16",
            "direct_variants": "uint8",
            "total_variants": "uint64",
            "is_wrapper": "bool",
        },
        copy=False,
    )
    rt = rt.astype(
        {
            "id": "string",
            "semantic_id": "string",
            "is_default": "bool",
            "length": "uint64",
            "is_variant": "bool",
            "type": "string",
            "total_variants": "uint64",
            "subgraph": "string",
            "parent_segment": "string",
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
            segments: list = rt.at[ri, "segments"]
            sis = st[st["id"].isin(segments)].index.tolist()
            lensr = st.iloc[sis]["length"]
            maxlen = lensr.max()
            minlen = lensr.min()
            rt.at[ri, "length"] = maxlen
            rt.at[ri, "min_length"] = lensr[lensr > 0].min()

            # fill `total_variants`
            rt.at[ri, "total_variants"] = st.iloc[sis]["total_variants"].sum()

            # fill region & segment's `semantic_id`
            if len(segments) > 1:  # variant exists
                d = maxlen - minlen
                std = lensr.std()
                mean = lensr.mean()

                # allele
                if std / mean < 0.1:
                    if (lensr == 1).all():
                        rt.at[ri, "type"] = "snp"
                        rn = get_id("snp")
                    else:
                        rt.at[ri, "type"] = "ale"
                        rn = get_id("ale")
                    rt.at[ri, "semantic_id"] = rn
                    st.loc[sis, "semantic_id"] = [
                        rn + "-" + chr(j) for j in range(97, 97 + len(sis))
                    ]  # generate names like `ALE-{n}-a,b,c`

                # del exists
                elif minlen == 0 or (minlen < 10 and d / minlen > 5):
                    rt.at[ri, "min_length"] = lensr[lensr > minlen].min()
                    if d > 50:
                        rt.at[ri, "type"] = "sv"
                        rn = get_id("sv")
                    else:
                        rt.at[ri, "type"] = "ind"
                        rn = get_id("ind")
                    rt.at[ri, "semantic_id"] = rn
                    mini = lensr.idxmin()
                    st.at[mini, "semantic_id"] = rn + "-d"
                    sis.remove(mini)
                    if len(sis) > 1:
                        st.loc[sis, "semantic_id"] = [
                            rn + "-i" + chr(j) for j in range(97, 97 + len(sis))
                        ]
                    else:
                        st.loc[sis, "semantic_id"] = rn + "-i"

                # not determined
                else:
                    rt.at[ri, "type"] = "var"
                    rn = get_id("var")
                    rt.at[ri, "semantic_id"] = rn
                    st.loc[sis, "semantic_id"] = [
                        rn + "-" + chr(j) for j in range(97, 97 + len(sis))
                    ]

            # consensus
            else:
                rn = get_id("con")
                rt.at[ri, "semantic_id"] = rn
                st.loc[sis, "semantic_id"] = rn

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

                # fill `direct_variants` & `total_variants`
                segment["direct_variants"] = len(srdf[srdf["type"] != "con"])
                segment["total_variants"] = (
                    srdf["total_variants"].sum() + segment["direct_variants"]
                )

                st.iloc[si] = segment

    return rt, st, meta


def wrap_rstree(
    regions: pd.DataFrame,
    segments: pd.DataFrame,
    meta: dict,
    min_resolution=0.04,
):
    """Wrap small regions, deepen the region-segment tree and establish hierarchy."""

    rt = regions
    st = segments

    if min_resolution <= 0:
        raise ValueError("Min resolution must be greater than 0.")
    total_length = rt[rt["level_range"].apply(lambda lr: lr[0] == 0 and lr[1] == 0)][
        "length"
    ].iloc[0]
    max_level = math.ceil(
        math.log2(total_length / 1000 / min_resolution)
    )  # new max level for hierarchical graph
    meta["max_level"] = max_level
    meta["total_length"] = int(total_length)
    min_length_px = 1 / min_resolution
    # clear old level ranges
    mask = rt["level_range"].apply(lambda lr: lr[1] > 1)
    rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(lambda lr: [])
    mask = st["level_range"].apply(lambda lr: lr[1] > 1)
    st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(lambda lr: [])

    def calc_wrapping_within_segment(segment: NamedTuple, group_has_default: bool):
        """
        Calculate changes of properties after wrapping regions within
        a segment.

        Args:
            segment (NamedTuple): Parent segment containing regions to be
            processed.
            group_has_default (bool): Whether the group within parent region
            has defined default regions.

        Returns (in a dict):
            wrapper_regions (DataFrame): Wrapper regions to be added.
            wrapper_segments (DataFrame): Wrapper segments to be added.
            normal_regions (set): Regions that don't need to be wrapped.
            new_sub_regions (list): Updated sub regions for the parent segment.
            is_default (bool): Whether regions in the segment are default on
            display.

        Relies on the following variables:
            rt: DataFrame
            st: DataFrame
            meta: dict
            resolution: float
            min_length_px: float
        """

        region_ids = segment.sub_regions.copy()
        r2bw_iranges_dq: collections.deque = (
            collections.deque()
        )  # "r2bw" = "regions to be wrapped"
        wrapper_regions = pd.DataFrame(columns=rt.columns)
        wrapper_segments = pd.DataFrame(columns=st.columns)
        normal_regions = set(region_ids)
        # Judge if regions need to be wrapped
        for region in rt[rt["id"].isin(region_ids)].itertuples():

            # Add wrapper nodes if one of its segment's length is too small
            if region.min_length < resolution * min_length_px:
                # Extend to find proper wrapping range
                posi = region_ids.index(region.id)
                b = a = posi
                total_length = 0
                while total_length < resolution * min_length_px and not (
                    b < 0 and a > len(region_ids) - 1
                ):  # continue extending if wrapped region still too small
                    if b >= 1:
                        lefti = b
                        b = -1
                        for j in range(lefti - 1, -1, -1):
                            if rt[rt["id"] == region_ids[j]]["type"].iloc[0] != "con":
                                b = j
                                break
                    else:
                        b = -1
                    if a <= len(region_ids) - 2:
                        righti = a
                        a = len(region_ids)
                        for j in range(righti + 1, len(region_ids)):
                            if rt[rt["id"] == region_ids[j]]["type"].iloc[0] != "con":
                                a = j
                                break
                    else:
                        a = len(region_ids)
                    r2bw_ids = region_ids[b + 1 : a]
                    r2bw_df = rt[rt["id"].isin(r2bw_ids)]
                    total_length = r2bw_df["length"].sum()

                r2bw_iranges_dq.append([b + 1, a - 1])

        # Union regions to be wrapped
        r2bw_iranges: list[list[int]] = []
        last = None
        while len(r2bw_iranges_dq) > 0:
            current = r2bw_iranges_dq.popleft()
            if last is None:
                last = current
            else:
                if last[1] >= current[0]:
                    last[1] = current[1]  # merge last and current range if overlapped
                else:
                    r2bw_iranges.append(last)
                    last = current
        if last is not None:
            r2bw_iranges.append(last)

        # Wrap regions
        for irange in r2bw_iranges:
            r2bw_ids = region_ids[irange[0] : irange[1] + 1]
            r2bw_df = rt[rt["id"].isin(r2bw_ids)]
            total_length = r2bw_df["length"].sum()
            normal_regions.difference_update(set(r2bw_ids))

            # build wrapper elements and fill properties
            wrapper_region = Region(get_id("r"), "con")
            wrapper_region.level_range = [i, i]
            wrapper_region.sources = segment.sources.copy()
            wrapper_segment = wrapper_region.add_segment(get_id("s"))
            wrapper_region.length = wrapper_region.min_length = (
                wrapper_segment.length
            ) = total_length
            wrapper_segment.frequency = len(wrapper_segment.sources) / len(
                meta["sources"]
            )
            wrapper_segment.is_wrapper = True
            wrapper_segment.semantic_id = wrapper_region.semantic_id = get_id("con")
            wrapper_segment.direct_variants = len(r2bw_df[r2bw_df["is_variant"]])
            wrapper_segment.total_variants = (
                r2bw_df["total_variants"].sum() + wrapper_segment.direct_variants
            )
            wrapper_region.total_variants = wrapper_segment.total_variants
            wrapper_region.parent_segment = segment.id
            wrapper_segment.sub_regions = r2bw_ids.copy()

            # write to dataframe
            wrapper_region_df = pd.DataFrame([wrapper_region.to_dict()])
            wrapper_region_df = wrapper_region_df.astype(
                {
                    "id": "string",
                    "semantic_id": "string",
                    "is_default": "bool",
                    "length": "uint64",
                    "is_variant": "bool",
                    "type": "string",
                    "total_variants": "uint64",
                    "subgraph": "string",
                    "parent_segment": "string",
                    "min_length": "uint64",
                    "before": "string",
                    "after": "string",
                },
                copy=False,
            )
            wrapper_segment_df = pd.DataFrame([wrapper_segment.to_dict()])
            wrapper_segment_df = wrapper_segment_df.astype(
                {
                    "id": "string",
                    "original_id": "string",
                    "semantic_id": "string",
                    "rank": "uint8",
                    "length": "uint64",
                    "frequency": "float16",
                    "direct_variants": "uint8",
                    "total_variants": "uint64",
                    "is_wrapper": "bool",
                },
                copy=False,
            )

            wrapper_regions = pd.concat(
                [wrapper_regions, wrapper_region_df],
                ignore_index=True,
                copy=False,
            )
            wrapper_segments = pd.concat(
                [wrapper_segments, wrapper_segment_df],
                ignore_index=True,
                copy=False,
            )

            # iterate preparation for update of parent segment's `sub_regions` property
            region_ids[irange[0] : irange[1] + 1] = [""] * (irange[1] - irange[0] + 1)
            region_ids[irange[0]] = wrapper_region.id

        # New `sub_regions` property for parent segment
        new_sub_regions = [rid for rid in region_ids if rid != ""]

        is_default = (
            True if not group_has_default and len(normal_regions) > 0 else False
        )

        return {
            "wrapper_regions": wrapper_regions,
            "wrapper_segments": wrapper_segments,
            "normal_regions": normal_regions,
            "new_sub_regions": new_sub_regions,
            "is_default": is_default,
        }

    # Traverse the hierarchical graph from top to bottom
    for i in range(1, max_level):  # exclude top & bottom layer
        # In each iteration, the script does the following:
        # 1. Find regions at current level
        # 2. Judge if these regions are proper to be at this level (need to be wrapped or not)
        # 3. Fill next level with regions (from former level, unwrapped regions, or wrapped regions)
        resolution = 2 ** (max_level - i) * min_resolution
        remaining_regions = set(
            rt[
                rt["level_range"].apply(
                    lambda lr: len(lr) > 0 and i >= lr[0] and i <= lr[1]
                )
            ]["id"].to_list()
        )
        parent_segment_series = st[
            st["level_range"].apply(
                lambda lr: len(lr) > 0 and i - 1 >= lr[0] and i - 1 <= lr[1]
            )
            & (st["sub_regions"].apply(len) > 0)
        ]["id"]
        regions_with_child = rt[
            rt["level_range"].apply(
                lambda lr: len(lr) > 0 and i - 1 >= lr[0] and i - 1 <= lr[1]
            )
            & rt["segments"].apply(
                lambda segs: not set(segs).isdisjoint(set(parent_segment_series))
            )
        ]

        # Process a group of sub-regions in parent region's segments
        for parent_region in regions_with_child.itertuples():
            group_has_default = False
            calc_after_wrapping: list[dict[str, Any]] = []

            # Treat regions in each parent segment seperately
            for segment in (
                st[st["id"].isin(parent_region.segments)]
                .sort_values("rank")
                .itertuples()
            ):
                if len(segment.sub_regions) == 0:
                    continue
                remaining_regions.difference_update(set(segment.sub_regions))
                result = calc_wrapping_within_segment(segment, group_has_default)
                if result["is_default"]:
                    group_has_default = True
                result.update({"parent_segment_index": segment.Index})
                calc_after_wrapping.append(result)

            # Move parent region and segments to current layer if all its child regions are wrapped into one
            if all([len(res["normal_regions"]) == 0 for res in calc_after_wrapping]):
                level_range = rt.at[parent_region.Index, "level_range"]
                level_range[1] = i  # update parent region's `level_range` in place
                mask = st["id"].isin(parent_region.segments)
                st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(
                    lambda lr: [lr[0], i]
                )
                # Move elements to next layer
                regions = st.loc[mask, "sub_regions"].sum()
                mask = rt["id"].isin(regions)
                rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(
                    lambda lr: [i + 1, i + 1]
                )
                segments = rt.loc[mask, "segments"].sum()
                mask = st["id"].isin(segments)
                st.loc[mask, "level_range"] = st.loc[mask, "level_range"].apply(
                    lambda lr: [i + 1, i + 1]
                )
                continue

            if not group_has_default:
                raise InternalError("Calculation error during wrapping regions.")

            # Process by each segment with sub-regions
            for res in calc_after_wrapping:

                # Add wrapper regions and segments to dataframes
                rt = pd.concat(
                    [rt, res["wrapper_regions"]], ignore_index=True, copy=False
                )
                st = pd.concat(
                    [st, res["wrapper_segments"]], ignore_index=True, copy=False
                )

                # Update parent segment's `sub_regions` property
                st.at[res["parent_segment_index"], "sub_regions"] = res[
                    "new_sub_regions"
                ]

                # Update `parent_segment` property for wrapped regions
                for wrapper_segment in res["wrapper_segments"].itertuples():
                    mask = rt["id"].isin(wrapper_segment.sub_regions)
                    rt.loc[mask, "parent_segment"] = wrapper_segment.id

                # Fill next layer
                for rid in res["new_sub_regions"]:
                    region = rt[rt["id"] == rid].iloc[0].to_dict()
                    sis = st[st["id"].isin(region["segments"])].index.to_list()
                    # If no sub-region exists, copy current region & segments to next layer
                    if st.iloc[sis]["sub_regions"].apply(lambda rgs: rgs == []).all():
                        mask = rt["id"] == region["id"]
                        rt.loc[mask, "level_range"] = rt.loc[mask, "level_range"].apply(
                            lambda lr: [i, i + 1]
                        )
                        st.loc[sis, "level_range"] = st.loc[sis, "level_range"].apply(
                            lambda lr: [i, i + 1]
                        )
                    # Otherwise, fill next layer with child structure
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

                # Mark default regions
                if res["is_default"]:
                    mask = rt["id"].isin(res["new_sub_regions"])
                    rt.loc[mask, "is_default"] = True

        # Copy inherited elements directly to next layer
        ris = rt[rt["id"].isin(remaining_regions)].index.to_list()
        for ri in ris:
            segments = rt.iloc[ri]["segments"]
            sis = st[st["id"].isin(segments)].index.to_list()
            level_range = rt.at[ri, "level_range"]
            level_range[1] = i + 1  # update region's `level_range` in place
            st.loc[sis, "level_range"] = st.loc[sis, "level_range"].apply(
                lambda lr: level_range
            )

    # Add `is_default` property for regions in the bottom layer
    parent_segment_series = st[
        st["level_range"].apply(
            lambda lr: len(lr) > 0 and max_level - 1 >= lr[0] and max_level - 1 <= lr[1]
        )
        & (st["sub_regions"].apply(len) > 0)
    ]["id"]
    regions_with_child = rt[
        rt["level_range"].apply(
            lambda lr: len(lr) > 0 and max_level - 1 >= lr[0] and max_level - 1 <= lr[1]
        )
        & rt["segments"].apply(
            lambda segs: not set(segs).isdisjoint(set(parent_segment_series))
        )
    ]
    for parent_region in regions_with_child.itertuples():
        first_segment_with_sub_regions = (
            st[
                (st["id"].isin(parent_region.segments))
                & (st["sub_regions"].apply(len) > 0)
            ]
            .sort_values("rank")
            .iloc[0]
        )
        mask = rt["id"].isin(first_segment_with_sub_regions["sub_regions"])
        rt.loc[mask, "is_default"] = True

    # TODO: Find algorithm to unwrap all elements within max level limit
    if len(rt[rt["level_range"].apply(lambda lr: len(lr) == 0)]) > 0:
        raise InternalError(
            "Warning: There are small regions remain wrapped, to unwrap all regions, flatten your input graph or decrease `minres`."
        )

    root_region = rt[rt["parent_segment"].isna()].iloc[0].to_dict()
    meta["total_variants"] = root_region["total_variants"]

    return rt, st, meta


def calculate_properties_r2l(regions: pd.DataFrame, segments: pd.DataFrame, meta: dict):
    """Calculates the properties for elements from root to leaves in the region-segment tree."""

    rt = regions
    st = segments

    # from root to leave
    root_ri = rt[rt["parent_segment"].isna()].index.to_list()[0]
    root_rid = rt.at[root_ri, "id"]

    # bootstrap properties for root region & segment
    totallen = meta["total_length"]
    rt.at[root_ri, "coordinate"] = [
        0,
        totallen,
    ]  # coordinate index
    rt.at[root_ri, "is_default"] = True  # default on display
    region_deque = collections.deque([root_rid])

    while len(region_deque) > 0:
        regid = region_deque.popleft()
        parent_region: dict = rt[rt["id"] == regid].iloc[0].to_dict()
        sids: list[str] = parent_region["segments"]

        for sid in sids:
            si = st[st["id"] == sid].index.to_list()[0]
            rids = st.at[si, "sub_regions"]

            # calculate coordinate index for child segments
            length = int(st.at[si, "length"])
            if length > parent_region["coordinate"][1] - parent_region["coordinate"][0]:
                raise InternalError("Element attribute calculation error occured.")
            elif (
                length
                == parent_region["coordinate"][1] - parent_region["coordinate"][0]
            ):
                start = parent_region["coordinate"][0]
            else:
                dlen = (
                    parent_region["coordinate"][1]
                    - parent_region["coordinate"][0]
                    - length
                )
                start = parent_region["coordinate"][0] + math.floor(dlen / 2)
            st.at[si, "coordinate"] = [
                start,
                start + length,
            ]

            for rid in rids:
                ri = rt[rt["id"] == rid].index.to_list()[0]

                # calculate coordinate index for child-child regions
                length = int(rt.at[ri, "length"])
                rt.at[ri, "coordinate"] = [
                    start,
                    start + length,
                ]
                start += length

                region_deque.append(rid)

    return rt, st, meta


def build_subgraph(
    subgraph_name: str,
    filepath: str,
    min_resolution: float,
    temp_dir: str,
):
    """Build a subgraph from a validated GFA file (can be gzipped) for a Hierarchical Pangenome."""

    gfa_file = fileutil.ungzip_file(filepath) if filepath.endswith(".gz") else filepath

    try:
        gfa_obj = gfa_mod.GFA(gfa_file)
        result = validate_gfa(gfa_obj)
        if not result.valid:
            raise DataInvalidError(result.message)
        gfa_no_sequence, sequence_file = gfa_obj.separate_sequence(temp_dir)
    finally:
        if filepath.endswith(".gz"):
            os.remove(gfa_file)

    # TODO: Add function to merge successive variation / consensus nodes
    gfa_obj = gfa_mod.GFA(gfa_no_sequence)
    g = gfa_obj.to_igraph()
    result = validate_graph(g)
    if not result.valid:
        raise DataInvalidError(result.message)
    rst = graph2rstree(g)
    rst = calculate_properties_l2r(*rst)
    rst = wrap_rstree(*rst, min_resolution)
    rst = calculate_properties_r2l(*rst)
    rst[2]["name"] = subgraph_name

    return *rst, sequence_file


def build_subgraphs_in_parallel(
    subgraph_items: list[tuple[str, str]],
    min_resolution: float,
    temp_dir: str,
):
    """Build Hierarchical Pangenome subgraphs in parallel for a list of GFA subgraphs."""

    partial_build_subgraph = functools.partial(
        build_subgraph,
        min_resolution=min_resolution,
        temp_dir=temp_dir,
    )

    with mp.Pool() as pool:
        sub_haps = pool.starmap(
            partial_build_subgraph,
            subgraph_items,
        )

    return sub_haps


def update_ids_by_subgraph(
    regions: pd.DataFrame,
    segments: pd.DataFrame,
    subgraph_id: int,
    db_connection: psycopg2.extensions.connection,
    sequence_file: str = None,
):
    """Update IDs for regions and segments, and sequence file (if have) with
    subgraph ID."""

    rt = regions
    st = segments
    conn = db_connection

    # Update subgraph ID in regions
    rt["subgraph"] = subgraph_id
    rt["subgraph"] = rt["subgraph"].astype("uint16")

    # Update region & segment IDs
    id_start_region = db.get_next_id_from_table(conn, "region")
    id_start_segment = db.get_next_id_from_table(conn, "segment")
    id_map_region = {
        old_id: new_id
        for old_id, new_id in zip(
            rt["id"], range(id_start_region, id_start_region + len(rt))
        )
    }
    id_map_segment = {
        old_id: new_id
        for old_id, new_id in zip(
            st["id"], range(id_start_segment, id_start_segment + len(st))
        )
    }
    rt["id"] = rt["id"].map(id_map_region)
    st["id"] = st["id"].map(id_map_segment)
    rt["parent_segment"] = rt["parent_segment"].map(id_map_segment)
    rt["segments"] = rt["segments"].apply(
        lambda segments: [id_map_segment[old_id] for old_id in segments]
    )
    st["sub_regions"] = st["sub_regions"].apply(
        lambda regions: [id_map_region[old_id] for old_id in regions]
    )

    # Update segment IDs in sequence file
    if sequence_file:
        id_map_segment_file, tmp_sequence_file = fileutil.create_tmp_files(2)
        try:
            id_map_segment_df = pd.DataFrame(
                list(id_map_segment.items()), columns=["old", "new"]
            )
            id_map_segment_df.to_csv(
                id_map_segment_file, sep="\t", index=False, header=False
            )
            cmd = [
                "awk",
                r"""'BEGIN {FS = OFS = "\t"} NR==FNR {a[$1] = $2; next} {$1 = a[$1]; print}'""",
                id_map_segment_file,
                sequence_file,
                ">",
                tmp_sequence_file,
                "&&",
                "mv",
                tmp_sequence_file,
                sequence_file,
            ]
            subprocess.run(" ".join(cmd), shell=True, executable="/bin/bash")

        finally:
            os.remove(id_map_segment_file)


def hap2db(
    hap_info: dict,
    subgraphs: list[tuple[pd.DataFrame, pd.DataFrame, dict, str | None]],
    db_connection: psycopg2.extensions.connection,
):
    """Dump a hierarchical pangenome to database."""

    conn = db_connection

    with conn.cursor() as cursor:
        try:
            conn.autocommit = False
            # Get clade ID
            cursor.execute("SELECT id FROM clade WHERE name = %s", (hap_info["clade"],))
            result = cursor.fetchone()
            if result is not None:
                clade_id = result[0]
            else:  # Add `clade` record if not exists
                cursor.execute(
                    "INSERT INTO clade (name) VALUES (%s) RETURNING id",
                    (hap_info["clade"],),
                )
                result = cursor.fetchone()
                if result is None:
                    raise DatabaseError("Failed to insert clade record.")
                clade_id = result[0]

            # Add `pangenome` record
            hap_info["builder"] = f"hap v{hap.VERSION}"
            hap_info["source_ids"] = []
            cursor.execute(
                "INSERT INTO pangenome (name, clade_id, description,creater, builder) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    hap_info["name"],
                    clade_id,
                    hap_info["description"],
                    hap_info["creater"],
                    hap_info["builder"],
                ),
            )
            result = cursor.fetchone()
            if result is None:
                raise DatabaseError("Failed to insert pangenome record.")
            hap_id = result[0]

            for regions, segments, meta, sequence_file in subgraphs:
                rt = regions
                st = segments
                cursor.execute(
                    "INSERT INTO subgraph (name, pangenome_id) VALUES (%s, %s) RETURNING id",
                    (meta["name"], hap_id),
                )  # Add `subgraph` record
                result = cursor.fetchone()
                if result is None:
                    raise DatabaseError("Failed to insert subgraph record.")
                subgraph_id = result[0]
                cursor.execute(
                    "INSERT INTO subgraph_statistics (id, max_level, total_length, total_variants) VALUES (%s, %s, %s, %s)",
                    (
                        subgraph_id,
                        meta["max_level"],
                        meta["total_length"],
                        meta["total_variants"],
                    ),
                )  # Add subgraph statistics record

                update_ids_by_subgraph(rt, st, subgraph_id, conn, sequence_file)

                # Add source IDs to hap_info
                id_map_source: dict[str, int] = {}
                for source_name in meta["sources"]:
                    cursor.execute(
                        "SELECT id FROM source WHERE name = %s", (source_name,)
                    )
                    result = cursor.fetchone()
                    if result is not None:
                        source_id = result[0]
                    else:
                        cursor.execute(
                            "INSERT INTO source (name, clade_id) VALUES (%s, %s) RETURNING id",
                            (source_name, clade_id),
                        )  # Add `source` record
                        result = cursor.fetchone()
                        if result is None:
                            raise DatabaseError("Failed to insert source record.")
                        else:
                            source_id = result[0]
                    id_map_source[source_name] = source_id
                hap_info["source_ids"] = list(
                    set().union(hap_info["source_ids"], id_map_source.values())
                )

                # Generate `segment_source_coordinate` table
                segment_sources = st[["id", "sources"]].explode("sources")
                segment_sources["sources"] = segment_sources["sources"].map(
                    id_map_source
                )
                segment_sources.rename(
                    columns={"id": "segment_id", "sources": "source_id"}, inplace=True
                )
                segment_sources.dropna(inplace=True)
                id_start_segment_sources = db.get_next_id_from_table(
                    conn, "segment_source_coordinate"
                )
                segment_sources.insert(
                    0,
                    "id",
                    range(
                        id_start_segment_sources,
                        id_start_segment_sources + len(segment_sources),
                    ),
                )
                segment_sources = segment_sources.astype(
                    {"id": "uint64", "segment_id": "uint64", "source_id": "uint32"},
                    copy=False,
                )

                # Generate `segment_original_id` table
                segment_original_id = st[["id", "original_id"]].dropna()
                segment_original_id = segment_original_id.astype(
                    {"id": "uint64", "original_id": "string"}, copy=False
                )

                # Format `segment` table
                st = st.merge(
                    rt[["id", "segments"]].explode("segments"),
                    left_on="id",
                    right_on="segments",
                    how="left",
                    suffixes=("", "_r"),
                    copy=False,
                ).drop(["segments", "original_id", "sub_regions", "sources"], axis=1)
                st.rename(columns={"id_r": "region_id"}, inplace=True)
                st = st[
                    [
                        "id",
                        "semantic_id",
                        "level_range",
                        "coordinate",
                        "rank",
                        "length",
                        "frequency",
                        "direct_variants",
                        "total_variants",
                        "is_wrapper",
                        "region_id",
                    ]
                ]
                st["coordinate"] = st["coordinate"].apply(
                    lambda range: f"[{range[0]},{range[1]})"
                )
                st = st.astype(
                    {
                        "id": "uint64",
                        "semantic_id": "string",
                        "coordinate": "string",
                        "rank": "uint8",
                        "length": "uint64",
                        "frequency": "float16",
                        "direct_variants": "uint8",
                        "total_variants": "uint64",
                        "is_wrapper": "bool",
                        "region_id": "uint64",
                    },
                    copy=False,
                )

                # Format `region` table
                rt.drop(
                    [
                        "length",
                        "is_variant",
                        "segments",
                        "sources",
                        "min_length",
                        "before",
                        "after",
                    ],
                    axis=1,
                    inplace=True,
                )
                rt.rename(
                    columns={
                        "subgraph": "subgraph_id",
                        "parent_segment": "parent_segment_id",
                    },
                    inplace=True,
                )
                rt = rt[
                    [
                        "id",
                        "semantic_id",
                        "level_range",
                        "coordinate",
                        "is_default",
                        "type",
                        "total_variants",
                        "subgraph_id",
                        "parent_segment_id",
                    ]
                ]
                rt["coordinate"] = rt["coordinate"].apply(
                    lambda range: f"[{range[0]},{range[1]})"
                )
                rt = rt.astype(
                    {
                        "id": "uint64",
                        "semantic_id": "string",
                        "coordinate": "string",
                        "is_default": "bool",
                        "type": "string",
                        "total_variants": "uint64",
                        "subgraph_id": "uint32",
                        "parent_segment_id": "Int64",  # nullable
                    },
                    copy=False,
                )

                # Copy from temporary files to database
                (
                    tmp_segment,
                    tmp_region,
                    tmp_segment_org_id,
                    tmp_segment_src,
                ) = fileutil.create_tmp_files(4)
                try:
                    st.to_csv(tmp_segment, sep="\t", index=False, header=False)
                    rt.to_csv(tmp_region, sep="\t", index=False, header=False)
                    segment_original_id.to_csv(
                        tmp_segment_org_id, sep="\t", index=False, header=False
                    )
                    segment_sources.to_csv(
                        tmp_segment_src, sep="\t", index=False, header=False
                    )
                    with open(tmp_segment) as f:
                        cursor.copy_from(
                            f, "segment", sep="\t", null=""
                        )  # Dump `segment` records
                    with open(tmp_region) as f:
                        cursor.copy_from(
                            f, "region", sep="\t", null=""
                        )  # Dump `region` records
                    with open(tmp_segment_org_id) as f:
                        cursor.copy_from(
                            f, "segment_original_id", sep="\t", null=""
                        )  # Dump `segment_original_id` records
                    with open(tmp_segment_src) as f:
                        cursor.copy_from(
                            f,
                            "segment_source_coordinate",
                            sep="\t",
                            null="",
                            columns=("id", "segment_id", "source_id"),
                        )  # Dump `segment_source_coordinate` records
                    if sequence_file:
                        with open(sequence_file) as f:
                            cursor.copy_from(
                                f, "segment_sequence", sep="\t", null=""
                            )  # Dump `segment_sequence` records
                finally:
                    fileutil.remove_files(
                        [tmp_segment, tmp_region, tmp_segment_org_id, tmp_segment_src]
                    )
            # Dump `pangenome_source` records
            pangenome_source = [
                (hap_id, source_id) for source_id in hap_info["source_ids"]
            ]
            cursor.executemany(
                "INSERT INTO pangenome_source (pangenome_id, source_id) VALUES (%s, %s)",
                pangenome_source,
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.autocommit = True


# def export(
#     rt: pd.DataFrame,
#     st: pd.DataFrame,
#     meta: dict,
#     basepath: str,
#     format="st",
# ):
#     """Export region-segment tree to assigned format."""

#     rt.drop(
#         [
#             "semantic_id",
#             "level_range",
#             "length",
#             "sources",
#             "is_variant",
#             "total_variants",
#             "min_length",
#             "before",
#             "after",
#         ],
#         axis=1,
#         inplace=True,
#     )

#     if format == "st":
#         rt.rename(
#             columns={
#                 "coordinate": "region_coordinate",
#                 "type": "region_type",
#                 "is_default": "region_is_default",
#             },
#             inplace=True,
#         )
#         st = st.merge(
#             rt.loc[
#                 :,
#                 [
#                     "segments",
#                     "region_coordinate",
#                     "parent_segment",
#                     "region_type",
#                     "region_is_default",
#                 ],
#             ].explode("segments"),
#             left_on="id",
#             right_on="segments",
#             how="left",
#             suffixes=("", "_r"),
#         ).drop("segments", axis=1)
#         st.to_csv(basepath + ".st.tsv", sep="\t", na_rep="*", index=False)

#         meta["sources"] = ",".join(meta["sources"])
#         metasr = pd.Series(meta)
#         metasr.to_csv(basepath + ".meta.tsv", sep="\t", na_rep="*", header=False)

#     elif format == "rst":
#         rt.to_csv(basepath + ".rt.tsv", sep="\t", na_rep="*", index=False)
#         st.to_csv(basepath + ".st.tsv", sep="\t", na_rep="*", index=False)
#     else:
#         raise UnsupportedError("Unsupported output format.")


def validate_arg_path(
    context: click.Context, param: click.Parameter, value: tuple[pathlib.Path]
):
    """Validate argument `path` of the `build` command."""

    if "from_subgraphs" in context.params and context.params["from_subgraphs"]:
        if len(value) == 1:
            if value[0].is_dir():
                return value
            else:
                raise click.BadParameter(
                    "More than one file, or a directory must be provided if specified with `-s/--from-subgraphs`."
                )
        else:
            for v in value:
                if v.is_dir():
                    raise click.BadParameter(
                        "Multiple directories are not allowed, use one directory or a list of files instead."
                    )
            return value
    else:
        if len(value) > 1:
            raise click.BadParameter(
                "Building for more than one graph is not supported. use `-s/--from-subgraphs` if building from a group of subgraphs."
            )
        return value


def get_name_from_context(context: click.Context) -> str:
    """Get the inferred name from the context."""

    if "from_subgraphs" in context.params and context.params["from_subgraphs"]:
        if len(context.params["path"]) == 1:
            subgraph_files = fileutil.get_files_from_dir(
                str(context.params["path"][0]), "gfa"
            )
        else:
            subgraph_files = [str(fp) for fp in context.params["path"]]
        subgraph_filenames = [os.path.basename(fp) for fp in subgraph_files]
        name = os.path.commonprefix(subgraph_filenames).split(".")[0]
    else:
        gfa_file = context.params["path"][0]
        name = fileutil.remove_suffix_containing(gfa_file.name, ".gfa")
    return name


def check_name(name: str) -> bool:
    """Check if the name is able to insert into the database."""

    # Check if the name is valid
    if (not name) or (len(name) > 20) or (not re.match(r"^[a-zA-Z0-9_-]+$", name)):
        return False

    # Check if the name exists in the database
    try:
        with db.auto_connect() as conn:
            db.create_tables_if_not_exist(conn)
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pangenome WHERE name = %s", (name,))
                return not cursor.fetchone()
    except psycopg2.Error as e:
        raise DatabaseError(f"Failed to check the name in the database: {e}")


def get_username() -> str:
    """Get the username of the current user."""

    return db.get_connection_info().get("user", "")


@click.command(
    "build",
    context_settings=hap.CTX_SETTINGS,
    short_help="Build a Hierarchical Pangenome",
)
@click.pass_context
@click.option(
    "--gfa",
    type=click.Path(exists=True, path_type=pathlib.Path),
)
@click.option(
    "--seqfile",
    type=click.Path(exists=True, path_type=pathlib.Path),
    help="External node-sequence FASTA/FASTQ.",
)
@click.option(
    "-n",
    "--name",
    prompt="Name of the HAP",
    # default=get_name_from_context(ctx),  # FIXME: Add dynamic default value
    help="Name of the Hierarchical Pangenome",
)
@click.option(
    "-a",
    "--clade",
    prompt="Clade of the HAP",
    help="Clade of the Hierarchical Pangenome",
)
@click.option(
    "-c",
    "--creater",
    prompt="Creater of the HAP",
    default=get_username,
    help="Creater of the Hierarchical Pangenome",
)
@click.option(
    "-x",
    "--description",
    prompt="Description of the HAP",
    default="",
    help="Description of the Hierarchical Pangenome",
)
@click.option(
    "-s",
    "--from-subgraphs",
    is_flag=True,
    help="Use a group of graphs as input",
)
@click.option("--contig", is_flag=True, help="Save contig level subgraphs")
@click.option(
    "-r",
    "--min-res",
    type=float,
    default=0.04,
    help="Minimum resolution of the Hierarchical Pangenome, in bp/px",
)
def main(
    ctx: click.Context,
    gfa: pathlib.Path | None,
    seqfile: pathlib.Path | None,
    name: str,
    clade: str,
    creater: str,
    description: str,
    from_subgraphs: bool,
    contig: bool,
    min_res: float,
):
    """
    Build a Hierarchical Pangenome from a pangenome graph in GFA format, and
    save to database.

    PATH: Path to the pangenome graph in GFA format. If `-s/--from-subgraphs`
    is specified, PATH should be a list of subgraphs or a directory containing
    the subgraphs.
    """

    # Get `name`
    while not check_name(name):
        click.echo(
            "The name is invalid or already exists in the database, please try another one."
        )
        name = click.prompt("Name of the HAP")

    # Subgraph as inputs
    if from_subgraphs:
        raise click.ClickException("--from-subgraphs mode currently requires positional PATH; not supported with --gfa.")
    else:
        if not gfa:
            raise click.ClickException("--gfa is required when not using --from-subgraphs.")
        gfa_file = gfa
        gfa_obj = gfa_mod.GFA(str(gfa_file))
        # Divide into subgraphs
        subgraph_dir = tempfile.mkdtemp(prefix="hap.", suffix=".subgraph")
        subgraph_items = gfa_obj.divide_into_subgraphs(subgraph_dir, not contig)
        if len(subgraph_items) == 0:
            subgraph_items = [("", str(gfa_file))]
        subgraph_files = [fp for _, fp in subgraph_items]

    temp_dir = tempfile.mkdtemp(prefix="hap.", suffix=".out")

    # Build Hierachical Pangenomes
    try:
        sub_haps = build_subgraphs_in_parallel(subgraph_items, min_res, temp_dir)

        # If external sequence file provided, parse once and prepare per-subgraph TSVs
        external_seq_map = None
        if seqfile:
            try:
                from hap.lib.io import iter_fasta as _iter_fa, _clean as _clean_seq
                seq_pairs = list(_iter_fa(seqfile))
                external_seq_map = {
                    hdr: s for hdr, raw in seq_pairs if (s := _clean_seq(raw, hdr))
                }
            except Exception as e:
                raise click.ClickException(f"Failed to read --seqfile: {e}")

        # If provided, override/attach per-subgraph sequence files using external mapping
        if external_seq_map is not None:
            from hap.lib import fileutil as _fu
            sub_haps2 = []
            for (regions, segments, meta, _seq_file) in sub_haps:
                st = segments
                # Compose per-subgraph TSV with only ids present in this subgraph
                (tmp_tsv,) = _fu.create_tmp_files(1)
                with open(tmp_tsv, "w") as out:
                    # st['id'] are original segment ids for true nodes
                    ids_in_sub = set(map(str, st["id"].tolist()))
                    for sid in ids_in_sub:
                        seq = external_seq_map.get(sid)
                        if seq:
                            out.write(f"{sid}\t{seq}\n")
                sub_haps2.append((regions, segments, meta, tmp_tsv))
            sub_haps = sub_haps2

        # Save to database
        hap_info = {
            "name": name,
            "clade": clade,
            "creater": creater,
            "description": description,
        }
        with db.auto_connect() as conn:
            hap2db(hap_info, sub_haps, conn)
    finally:
        if not from_subgraphs:
            shutil.rmtree(subgraph_dir)
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()
