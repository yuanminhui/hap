import os
import argparse
import functools
import multiprocessing as mp

from ..lib import gfautil
from ..lib import fileutil
from .. import palchinfo


_PROG = "divgfa"


def register_command(subparsers: argparse._SubParsersAction, module_help_map: dict):
    psr_divgfa = subparsers.add_parser(
        _PROG,
        prog=f"{palchinfo.name} {_PROG}",
        description="Divide a graph build from whole genome in GFA format into subgraphs by informative labels.",
        help="divide a graph into subgraphs",
    )
    psr_divgfa.set_defaults(func=main)
    module_help_map[_PROG] = psr_divgfa.print_help

    psr_divgfa.add_argument("file", help="input graph file")

    # I/O options
    grp_io = psr_divgfa.add_argument_group("I/O options")
    grp_io.add_argument("-o", "--outdir", help="output directory")


def main(args: argparse.Namespace):
    outdir = args.outdir if args.outdir else os.getcwd()
    gfaver, gfamin, seqfp = gfautil.preprocess_gfa(args.file, outdir)

    subgnames = gfautil.extract_subgraph_names(gfamin, gfaver)

    exsubg = functools.partial(
        gfautil.extract_subgraph,
        gfa_path=gfamin,
        gfa_version=gfaver,
        outdir=outdir,
    )
    with mp.Pool() as pool:
        pool.map(exsubg, subgnames)

    fileutil.remove_files([gfamin, seqfp])
