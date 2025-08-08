from pathlib import Path
from typing import Iterable, Tuple, TextIO

from Bio import SeqIO
import click

_ALLOWED = set("ATCGN-")  # dash is gap


def iter_fasta(path: Path) -> Iterable[Tuple[str, str]]:
    """
    Yield (header, sequence) from FASTA or FASTQ (.fa, .fasta, .fq, .fastq).
    `header` = record.id (1st whitespace-delimited token).
    """
    fmt = "fastq" if path.suffix.lower() in {".fastq", ".fq"} else "fasta"
    with path.open() as h:
        for rec in SeqIO.parse(h, fmt):
            yield rec.id, str(rec.seq)


def _clean(seq: str, name: str) -> str | None:
    """Upper-case & validate against _ALLOWED, warn+return None on failure."""
    up = seq.upper()
    bad = set(up) - _ALLOWED
    if bad or not up:
        click.echo(
            f"[WARN] {name}: illegal chars {''.join(sorted(bad))} – skipped",
            err=True,
        )
        return None
    return up


def fasta_to_tsv(fasta: Path, out_fh: TextIO) -> int:
    """
    Write `<header>\t<SEQ>` rows for every *valid* record, return count written.
    Used by the build command before any DB calls.
    """
    n = 0
    for hdr, raw in iter_fasta(fasta):
        if (seq := _clean(raw, hdr)):
            out_fh.write(f"{hdr}\t{seq}\n")
            n += 1
    return n