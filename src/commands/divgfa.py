import os
import argparse
import functools
import multiprocessing as mp

from lib import gfautil
import palchinfo


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

    # Parameters
    grp_params = psr_divgfa.add_argument_group("Parameters")
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

    gfagz = (
        gfafp if gfafp.endswith(".gz") else gfautil.gzip_gfa(gfafp)
    )  # temp gzipped GFA for process performance
    gfaver = gfautil.get_gfa_version(gfagz)

    subgnames = gfautil.extract_subgraph_names(
        gfagz,
        gfaver,
        not args.contig,
    )

    exsubg = functools.partial(
        gfautil.extract_subgraph,
        gfa_path=gfagz,
        gfa_version=gfaver,
        outdir=outdir,
    )
    with mp.Pool() as pool:
        pool.map(exsubg, subgnames)

    if not gfafp.endswith(".gz"):
        os.remove(gfagz)
