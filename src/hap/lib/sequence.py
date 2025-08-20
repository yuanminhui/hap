from pathlib import Path
from typing import Iterable, Tuple, TextIO, Optional
from Bio import SeqIO
import click

_ALLOWED = set("ATCGN-")  # dash is gap


def read_sequences_from_fasta(path: Path) -> Iterable[Tuple[str, str]]:
    """Iterate over sequences in a FASTA/FASTQ file.

    Args:
        path (Path): Path to a .fa/.fasta/.fq/.fastq file.

    Yields:
        tuple[str, str]: `(header, sequence)` where header is the first
        whitespace-delimited token of the FASTA/FASTQ record id.
    """

    fmt = "fastq" if path.suffix.lower() in {".fastq", ".fq"} else "fasta"
    with path.open() as h:
        for rec in SeqIO.parse(h, fmt):
            yield rec.id, str(rec.seq)


def sanitize_sequence(raw_sequence: str, label: str) -> Optional[str]:
    """Normalize a raw sequence string and validate allowed characters.

    Upper-case the sequence and ensure it contains only characters in
    `_ALLOWED`. On invalid input, emit a warning and return None.

    Args:
        raw_sequence (str): Raw sequence string.
        label (str): Identifier used for warning messages.

    Returns:
        Optional[str]: Cleaned sequence or None when invalid.
    """

    up = raw_sequence.upper()
    bad = set(up) - _ALLOWED
    if bad or not up:
        click.echo(
            f"[WARN] {label}: illegal chars {''.join(sorted(bad))} – skipped",
            err=True,
        )
        return None
    return up


def write_fasta_or_fastq_to_tsv(fasta_path: Path, out_fh: TextIO) -> int:
    """Convert a FASTA/FASTQ file to a TSV with two columns: id and sequence.

    Only valid sequences are written. Returns the number of records written.
    """

    n = 0
    for hdr, raw in read_sequences_from_fasta(fasta_path):
        seq = sanitize_sequence(raw, hdr)
        if seq:
            out_fh.write(f"{hdr}\t{seq}\n")
            n += 1
    return n


def write_tsv_to_fasta(tsv_path: Path, out_fh: TextIO) -> int:
    """Convert a TSV `(id, sequence)` file to FASTA format.

    Returns the number of records written.
    """

    n = 0
    with tsv_path.open() as h:
        for line in h:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            out_fh.write(f">{parts[0]}\n{parts[1]}\n")
            n += 1
    return n