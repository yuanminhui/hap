from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Iterable, Tuple


ALLOWED = "ATCGN-"


def generate_fasta(
    path: Path,
    records: Iterable[Tuple[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for rid, seq in records:
            fh.write(f">{rid}\n{seq}\n")


def generate_fastq(
    path: Path,
    records: Iterable[Tuple[str, str]],
    quality_char: str = "!",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for rid, seq in records:
            fh.write(f"@{rid}\n{seq}\n+\n{quality_char * max(1, len(seq))}\n")


def generate_large_fasta(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write(">seg0\n")
        chunk = ("ACGT" * 16384) + "\n"
        written = 0
        while written < size_bytes:
            fh.write(chunk)
            written += len(chunk)


def generate_tsv(path: Path, rows: Iterable[Tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for k, v in rows:
            fh.write(f"{k}\t{v}\n")


def generate_gfa_dag(path: Path, num_nodes: int = 5, include_path: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        for i in range(num_nodes):
            fh.write(f"S\ts{i}\t*\tLN:i:{i+1}\n")
        for i in range(num_nodes - 1):
            fh.write(f"L\ts{i}\t+\ts{i+1}\t+\t0M\n")
        if include_path:
            ids = ",".join([f"s{i}+" for i in range(num_nodes)])
            fh.write(f"P\tpath1\t{ids}\t*\n")


def generate_gfa_cycle(path: Path, num_nodes: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        for i in range(num_nodes):
            fh.write(f"S\tc{i}\t*\tLN:i:{i+1}\n")
        for i in range(num_nodes):
            j = (i + 1) % num_nodes
            fh.write(f"L\tc{i}\t+\tc{j}\t+\t0M\n")


def generate_gfa_missing_fields(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        fh.write("S\tsegA\n")  # missing length/sequence fields


def random_seq(length: int, alphabet: str = ALLOWED) -> str:
    return "".join(random.choice(alphabet) for _ in range(length))

