from pathlib import Path
from typing import Dict, List, Optional

import click

import hap
from hap.lib import database as db
from hap.lib.sequence import (
    read_sequences_from_fasta,
    sanitize_sequence,
)


@click.group(
    "sequence",
    context_settings=hap.CTX_SETTINGS,
    short_help="Sequence management commands",
)
def main():
    """Manage segment sequences in the database."""


def resolve_segment_id(conn, external_id: str) -> Optional[int]:
    """Resolve a semantic or original segment identifier to internal numeric id."""

    with conn.cursor() as cur:
        cur.execute("SELECT id FROM segment WHERE semantic_id = %s", (external_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "SELECT id FROM segment_original_id WHERE original_id = %s",
            (external_id,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    return None


def resolve_segment_ids(conn, external_ids: List[str]) -> Dict[str, int]:
    """Resolve many semantic/original ids to internal segment ids."""

    result: Dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT semantic_id, id FROM segment WHERE semantic_id = ANY(%s)",
            (external_ids,),
        )
        for sid, id_ in cur.fetchall():
            result[sid] = id_
        unresolved = [x for x in external_ids if x not in result]
        if unresolved:
            cur.execute(
                "SELECT original_id, id FROM segment_original_id WHERE original_id = ANY(%s)",
                (unresolved,),
            )
            for oid, id_ in cur.fetchall():
                result[oid] = id_
    return result


@main.command()
@click.option(
    "--fasta",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="FASTA/FASTQ file to import.",
)
def add(fasta: Path):
    """Bulk import sequences from FASTA/FASTQ into the database."""

    conn = db.auto_connect()
    seqs = list(read_sequences_from_fasta(fasta))
    ext_ids = [hdr for hdr, _ in seqs]
    id_map = resolve_segment_ids(conn, ext_ids)

    imported_count = 0
    with conn.cursor() as cur:
        # Fetch existing lengths
        cur.execute(
            "SELECT id, length FROM segment WHERE id = ANY(%s)",
            (list(id_map.values()),),
        )
        lengths = dict(cur.fetchall())

        for hdr, raw in seqs:
            seg_id = id_map.get(hdr)
            if not seg_id:
                click.echo(f"[WARN] {hdr}: not found in DB – skipped", err=True)
                continue
            seq = sanitize_sequence(raw, hdr)
            if not seq:
                continue
            known_length = lengths.get(seg_id)
            if known_length is not None and known_length != len(seq):
                msg = (
                    f"[WARN] length mismatch for {seg_id}: existing length {known_length}, "
                    f"new length {len(seq)}; skipping."
                )
                click.echo(msg, err=True)
                continue
            # upsert
            cur.execute(
                "INSERT INTO segment_sequence (id, segment_sequence) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET segment_sequence = EXCLUDED.segment_sequence",
                (seg_id, seq),
            )
            # If length is NULL, update it
            cur.execute(
                "UPDATE segment SET length = %s WHERE id = %s AND length IS NULL",
                (len(seq), seg_id),
            )
            imported_count += 1

    conn.commit()
    click.echo(f"Imported {imported_count} sequences.")


@main.command()
@click.argument("ids", nargs=-1)
@click.option("--regex", type=str, help="Regex for semantic_id or original_id.")
@click.option("--format", "fmt", type=click.Choice(["tsv", "fasta"]), default="tsv")
def get(ids: tuple[str, ...], regex: str, fmt: str):
    """Get sequences by ID(s) or regex."""

    conn = db.auto_connect()
    out = []
    with conn.cursor() as cur:
        if regex:
            cur.execute(
                """
                SELECT s.semantic_id, sq.segment_sequence
                FROM segment s
                JOIN segment_sequence sq ON s.id = sq.id
                LEFT JOIN segment_original_id so ON s.id = so.id
                WHERE s.semantic_id ~ %s OR so.original_id ~ %s
                """,
                (regex, regex),
            )
            out = cur.fetchall()
        elif ids:
            id_map = resolve_segment_ids(conn, list(ids))
            if not id_map:
                click.echo("No valid IDs found.", err=True)
                return
            cur.execute(
                (
                    "SELECT semantic_id, segment_sequence FROM segment JOIN segment_sequence "
                    "USING (id) WHERE id = ANY(%s)"
                ),
                (list(id_map.values()),),
            )
            out = cur.fetchall()
        else:
            click.echo("No IDs or regex provided.", err=True)
            return
    if fmt == "tsv":
        for sid, seq in out:
            click.echo(f"{sid}\t{seq}")
    else:
        for sid, seq in out:
            click.echo(f">{sid}\n{seq}")


@main.command()
@click.argument("id")
@click.argument("newseq")
def edit(id: str, newseq: str):
    """Edit a sequence for a given segment ID."""

    conn = db.auto_connect()
    seg_id = resolve_segment_id(conn, id)
    if not seg_id:
        click.echo(f"[ERROR] {id}: not found in DB", err=True)
        return
    seq = sanitize_sequence(newseq, id)
    if not seq:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT length FROM segment WHERE id = %s", (seg_id,))
        row = cur.fetchone()
        known_length = row[0] if row else None
        if known_length is not None and known_length != len(seq):
            msg = (
                f"[WARN] length mismatch for {seg_id}: existing length {known_length}, "
                f"new length {len(seq)}; skipping."
            )
            click.echo(msg, err=True)
            return
        cur.execute(
            (
                "INSERT INTO segment_sequence (id, segment_sequence) VALUES (%s, %s) "
                "ON CONFLICT (id) DO UPDATE SET segment_sequence = EXCLUDED.segment_sequence"
            ),
            (seg_id, seq),
        )
        cur.execute(
            "UPDATE segment SET length = %s WHERE id = %s AND length IS NULL",
            (len(seq), seg_id),
        )
    conn.commit()
    click.echo(f"Edited sequence for {id}.")


@main.command()
@click.argument("ids", nargs=-1)
def delete(ids: tuple[str, ...]):
    """Delete sequences by ID(s)."""

    conn = db.auto_connect()
    id_map = resolve_segment_ids(conn, list(ids))
    if not id_map:
        click.echo("No valid IDs found.", err=True)
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM segment_sequence WHERE id = ANY(%s)",
            (list(id_map.values()),),
        )
    conn.commit()
    click.echo(f"Deleted {len(id_map)} sequences.")