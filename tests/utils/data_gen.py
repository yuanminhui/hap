from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Iterable, Tuple
import gzip


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


def generate_large_fasta_many_records(path: Path, num_records: int, seq_len: int = 50) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for i in range(num_records):
            fh.write(f">r{i}\n{random_seq(seq_len)}\n")


def generate_large_gfa_many_segments(path: Path, num_segments: int, connect: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        for i in range(num_segments):
            fh.write(f"S\ts{i}\t*\tLN:i:1\n")
        if connect:
            for i in range(num_segments - 1):
                fh.write(f"L\ts{i}\t+\ts{i+1}\t+\t0M\n")


def generate_gfa_nested(path: Path) -> None:
    """Generate a DAG with nested branching (no cycles):
    s0 -> s1 -> s2
             \\-> s3 -> s4
      s0 -> s5 -> s6
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        for i in range(7):
            fh.write(f"S\ts{i}\t*\tLN:i:1\n")
        # nested branches
        fh.write("L\ts0\t+\ts1\t+\t0M\n")
        fh.write("L\ts1\t+\ts2\t+\t0M\n")
        fh.write("L\ts1\t+\ts3\t+\t0M\n")
        fh.write("L\ts3\t+\ts4\t+\t0M\n")
        fh.write("L\ts0\t+\ts5\t+\t0M\n")
        fh.write("L\ts5\t+\ts6\t+\t0M\n")
        fh.write("P\tpath1\ts0+,s1+,s2+\t*\n")
        fh.write("P\tpath2\ts0+,s1+,s3+,s4+\t*\n")
        fh.write("P\tpath3\ts0+,s5+,s6+\t*\n")


def gzip_file(src: Path, dst: Path | None = None) -> Path:
    dst = dst or src.with_suffix(src.suffix + ".gz")
    with src.open("rb") as f_in, gzip.open(dst, "wb") as f_out:
        while True:
            chunk = f_in.read(1024 * 1024)
            if not chunk:
                break
            f_out.write(chunk)
    return dst


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


def generate_gfa_dangling_edge(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        fh.write("S\ts0\t*\tLN:i:1\n")
        # edge to non-existing node s99
        fh.write("L\ts0\t+\ts99\t+\t0M\n")


def generate_gfa_repeated_edge(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        fh.write("S\ts0\t*\tLN:i:1\n")
        fh.write("S\ts1\t*\tLN:i:1\n")
        fh.write("L\ts0\t+\ts1\t+\t0M\n")
        fh.write("L\ts0\t+\ts1\t+\t0M\n")  # repeated


def generate_gfa_invalid_path_record(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        fh.write("H\tVN:Z:1.0\n")
        fh.write("S\ts0\t*\tLN:i:1\n")
        # Invalid P record (wrong columns)
        fh.write("P\tpath\t*\n")


def random_seq(length: int, alphabet: str = ALLOWED) -> str:
    return "".join(random.choice(alphabet) for _ in range(length))

