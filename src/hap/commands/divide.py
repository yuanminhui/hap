import os
import functools
import multiprocessing as mp
import pathlib
import shutil

import click
import hap

from hap.lib import fileutil, gfautil, typeutil


@click.command(
    "divide",
    context_settings=hap.ctx_settings,
    short_help="Divide a graph into subgraphs",
)
@click.argument(
    "file",
    type=click.Path(exists=True, readable=True, dir_okay=False, path_type=pathlib.Path),
)
@click.option(
    "-o",
    "--outdir",
    type=click.Path(file_okay=False, path_type=pathlib.Path),
    help="Output directory",
)
@click.option(
    "-c",
    "--contig",
    is_flag=True,
    help="Extract subgraph at contig level (default chromosome)",
)
def main(file: pathlib.Path, outdir: pathlib.Path, contig: bool):
    """
    Divide a graph build from whole genome in GFA format into subgraphs by informative labels.

    FILE: GFA file path of the graph.
    """

    basename = typeutil.remove_suffix_containing(file.name, ".gfa")
    if not outdir:
        outdir = pathlib.Path.cwd() / f"{basename}.subgraphs"
    if outdir.exists() and not fileutil.is_dir_empty(str(outdir)):
        if click.confirm(
            f"Output directory {outdir} is not empty, continuing the program will erase files in it. Continue?",
            abort=True,
        ):
            shutil.rmtree(str(outdir))
    outdir.mkdir(parents=True, exist_ok=True)

    if file.suffix == ".gz":
        gfafp = fileutil.ungzip_file(str(file))  # temp ungzipped GFA
    gfaver = gfautil.get_gfa_version(gfafp)

    subgnames = gfautil.extract_subgraph_names(
        gfafp,
        gfaver,
        not contig,
    )

    exsubg = functools.partial(
        gfautil.extract_subgraph,
        gfa_path=gfafp,
        gfa_version=gfaver,
        outdir=outdir,
    )
    try:
        with mp.Pool() as pool:
            pool.map(exsubg, subgnames)
    finally:
        if file.suffix == ".gz":
            if click.confirm(
                f"Delete temporary ungzipped GFA file {gfafp}?", default=True
            ):  # TODO: remove this after debugging
                os.remove(gfafp)


if __name__ == "__main__":
    main()
