import os
import argparse
import functools
import multiprocessing as mp

from hap.lib import fileutil, gfautil
from hap import hapinfo


_PROG = "divide"


def register_command(subparsers: argparse._SubParsersAction, module_help_map: dict):
    psr_divide = subparsers.add_parser(
        _PROG,
        prog=f"{hapinfo.name} {_PROG}",
        description="Divide a graph build from whole genome in GFA format into subgraphs by informative labels.",
        help="divide a graph into subgraphs",
    )
    psr_divide.set_defaults(func=main)
    module_help_map[_PROG] = psr_divide.print_help

    psr_divide.add_argument("file", help="input graph file")

    # I/O options
    grp_io = psr_divide.add_argument_group("I/O options")
    grp_io.add_argument("-o", "--outdir", help="output directory")

    # Parameters
    grp_params = psr_divide.add_argument_group("Parameters")
    grp_params.add_argument(
        "-c",
        "--contig",
        action="store_true",
        help="extract subgraph at contig level (default chromosome)",
    )


def main(args: argparse.Namespace):
    outdir = args.outdir if args.outdir else os.getcwd()
    gfafp = os.path.normpath(args.file)
    if not os.path.exists(gfafp):
        raise FileNotFoundError(f"File {args.file} not found.")
    outdir = os.path.normpath(outdir)
    if not os.path.exists(outdir):
        os.mkdir(outdir)

    if args.file.endswith(".gz"):
        gfafp = fileutil.ungzip_file(gfafp)  # temp ungzipped GFA
    gfaver = gfautil.get_gfa_version(gfafp)

    subgnames = gfautil.extract_subgraph_names(
        gfafp,
        gfaver,
        not args.contig,
    )

    exsubg = functools.partial(
        gfautil.extract_subgraph,
        gfa_path=gfafp,
        gfa_version=gfaver,
        outdir=outdir,
    )
    with mp.Pool() as pool:
        pool.map(exsubg, subgnames)

    if args.file.endswith(".gz"):
        os.remove(gfafp)
