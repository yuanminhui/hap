from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import click
import psycopg2

import hap
from hap.lib import database as db
from hap.lib.io import _clean, iter_fasta


def resolve_one(conn: psycopg2.extensions.connection, ext_id: str) -> Optional[int]:
    """Resolve an external identifier to internal `segment.id`.

    Try `segment.semantic_id` first, then `segment_original_id.original_id`.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM segment WHERE semantic_id = %s", (ext_id,))
        row = cur.fetchone()
        if row:
            return int(row[0])
        cur.execute(
            "SELECT id FROM segment_original_id WHERE original_id = %s",
            (ext_id,),
        )
        row = cur.fetchone()
        if row:
            return int(row[0])
    return None


def resolve_many(
    conn: psycopg2.extensions.connection, ext_ids: List[str]
) -> Dict[str, int]:
    """Resolve many external identifiers to internal IDs.

    Returns mapping `ext_id -> id` for those that could be resolved.
    """
    if not ext_ids:
        return {}
    mapping: Dict[str, int] = {}
    with conn.cursor() as cur:
        # semantic_id
        cur.execute(
            "SELECT semantic_id, id FROM segment WHERE semantic_id = ANY(%s)",
            (ext_ids,),
        )
        for sem_id, seg_id in cur.fetchall() or []:
            mapping[str(sem_id)] = int(seg_id)
        # original_id
        unresolved = [e for e in ext_ids if e not in mapping]
        if unresolved:
            cur.execute(
                "SELECT original_id, id FROM segment_original_id WHERE original_id = ANY(%s)",
                (unresolved,),
            )
            for orig_id, seg_id in cur.fetchall() or []:
                mapping[str(orig_id)] = int(seg_id)
    return mapping


@click.group("seq", context_settings=hap.CTX_SETTINGS, short_help="Manage node sequences")
def main():
    """Sequence operations: add/get/edit/delete."""


@main.command("add")
@click.option("--fasta", "fasta_path", required=True, type=click.Path(exists=True, path_type=Path))
def cmd_add(fasta_path: Path):
    """Bulk import sequences from FASTA/FASTQ."""
    try:
        with db.auto_connect() as conn:
            db.create_tables_if_not_exist(conn)
            records: List[Tuple[str, str]] = list(iter_fasta(fasta_path))
            if not records:
                click.echo("[WARN] No records found in FASTA/FASTQ", err=True)
                return
            ext_ids = [hdr for hdr, _ in records]
            ext_to_id = resolve_many(conn, ext_ids)
            if not ext_to_id:
                raise click.ClickException("None of the provided IDs could be resolved.")

            # query existing lengths and existing sequences
            ids = list(ext_to_id.values())
            length_map: Dict[int, Optional[int]] = {}
            with conn.cursor() as cur:
                cur.execute("SELECT id, length FROM segment WHERE id = ANY(%s)", (ids,))
                for seg_id, length in cur.fetchall() or []:
                    length_map[int(seg_id)] = int(length) if length is not None else None
                cur.execute("SELECT id FROM segment_sequence WHERE id = ANY(%s)", (ids,))
                existing_seq_ids = {int(r[0]) for r in (cur.fetchall() or [])}

            to_update_segment_length: List[Tuple[int, int]] = []
            rows: List[Tuple[int, str]] = []
            for hdr, seq_raw in records:
                seg_id = ext_to_id.get(hdr)
                if seg_id is None:
                    click.echo(f"[WARN] {hdr}: not found – skipped", err=True)
                    continue
                if seg_id in existing_seq_ids:
                    continue
                seq = _clean(seq_raw, hdr)
                if not seq:
                    continue
                seg_len = length_map.get(seg_id)
                if seg_len is None:
                    to_update_segment_length.append((seg_id, len(seq)))
                elif seg_len != len(seq):
                    click.echo(
                        f"[WARN] {hdr}: length mismatch (seg={seg_len}, seq={len(seq)}) – skipped",
                        err=True,
                    )
                    continue
                rows.append((seg_id, seq))

            if not rows:
                click.echo("[WARN] No valid sequences to import", err=True)
                return

            with conn.cursor() as cur:
                with cur.copy("COPY segment_sequence (id, segment_sequence) FROM STDIN WITH (FORMAT text, DELIMITER '\t')") as copy:
                    for seg_id, seq in rows:
                        copy.write(f"{seg_id}\t{seq}\n")
                if to_update_segment_length:
                    cur.executemany(
                        "UPDATE segment SET length = %s WHERE id = %s",
                        [(L, i) for (i, L) in ((i, L) for i, L in to_update_segment_length)],
                    )
            conn.commit()
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")


@main.command("get")
@click.argument("ids", nargs=-1)
@click.option("--regex", "regex_pat", help="Regex over semantic_id or original_id")
@click.option("--format", "outfmt", type=click.Choice(["tsv", "fasta"]), default="tsv")
def cmd_get(ids: Tuple[str, ...], regex_pat: Optional[str], outfmt: str):
    """Fetch sequences, default TSV (semantic_id, sequence)."""
    if ids and regex_pat:
        raise click.ClickException("Provide IDs or --regex, not both.")
    try:
        with db.auto_connect() as conn:
            db.create_tables_if_not_exist(conn)
            rows: List[Tuple[str, str]] = []
            with conn.cursor() as cur:
                if ids:
                    mapping = resolve_many(conn, list(ids))
                    if not mapping:
                        raise click.ClickException("No IDs resolved.")
                    id_list = list(mapping.values())
                    cur.execute(
                        """
                        SELECT s.semantic_id, ss.segment_sequence
                        FROM segment s JOIN segment_sequence ss ON s.id = ss.id
                        WHERE s.id = ANY(%s)
                        """,
                        (id_list,),
                    )
                    rows = [(str(a), str(b)) for a, b in cur.fetchall() or []]
                elif regex_pat:
                    cur.execute(
                        """
                        SELECT s.semantic_id, ss.segment_sequence
                        FROM segment s
                        LEFT JOIN segment_original_id so ON so.id = s.id
                        JOIN segment_sequence ss ON ss.id = s.id
                        WHERE s.semantic_id ~ %s OR so.original_id ~ %s
                        """,
                        (regex_pat, regex_pat),
                    )
                    rows = [(str(a), str(b)) for a, b in cur.fetchall() or []]
                else:
                    raise click.ClickException("Provide IDs or --regex.")
            if outfmt == "tsv":
                for sem_id, seq in rows:
                    click.echo(f"{sem_id}\t{seq}")
            else:
                for sem_id, seq in rows:
                    click.echo(f">{sem_id}")
                    click.echo(seq)
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")


@main.command("edit")
@click.argument("ext_id")
@click.option("--replace", "new_seq", required=True)
def cmd_edit(ext_id: str, new_seq: str):
    """Replace or set sequence for a single element."""
    seq = _clean(new_seq, ext_id)
    if not seq:
        return
    try:
        with db.auto_connect() as conn:
            db.create_tables_if_not_exist(conn)
            seg_id = resolve_one(conn, ext_id)
            if seg_id is None:
                raise click.ClickException(f"ID not found: {ext_id}")
            with conn.cursor() as cur:
                cur.execute("SELECT length FROM segment WHERE id = %s", (seg_id,))
                row = cur.fetchone()
                seg_len = int(row[0]) if row and row[0] is not None else None
                if seg_len is None:
                    cur.execute(
                        "UPDATE segment SET length = %s WHERE id = %s",
                        (len(seq), seg_id),
                    )
                elif seg_len != len(seq):
                    raise click.ClickException(
                        f"Length mismatch: segment has {seg_len}, new sequence {len(seq)}"
                    )
                cur.execute(
                    """
                    INSERT INTO segment_sequence (id, segment_sequence)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET segment_sequence = EXCLUDED.segment_sequence
                    """,
                    (seg_id, seq),
                )
            conn.commit()
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")


@main.command("delete")
@click.argument("ids", nargs=-1)
def cmd_delete(ids: Tuple[str, ...]):
    """Delete sequences for given IDs."""
    if not ids:
        raise click.ClickException("Provide at least one ID to delete.")
    try:
        with db.auto_connect() as conn:
            db.create_tables_if_not_exist(conn)
            mapping = resolve_many(conn, list(ids))
            if not mapping:
                click.echo("[WARN] No IDs resolved – nothing to delete", err=True)
                return
            id_list = list(mapping.values())
            with conn.cursor() as cur:
                cur.execute("DELETE FROM segment_sequence WHERE id = ANY(%s)", (id_list,))
            conn.commit()
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")