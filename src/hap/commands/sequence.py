from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

import click
import psycopg2

import hap
from hap.lib import database as db
from hap.lib.io import _clean, iter_fasta


def resolve_one(conn, ext_id: str) -> Optional[int]:
    """Resolve an external identifier to internal segment.id.

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
        return int(row[0]) if row else None


def resolve_many(conn, ext_ids: List[str]) -> Dict[str, int]:
    """Resolve many external identifiers to internal ids.

    Returns mapping of provided ext_id -> segment.id for those that resolve.
    """
    mapping: Dict[str, int] = {}
    if not ext_ids:
        return mapping
    # Use single round trips where reasonable
    with conn.cursor() as cur:
        cur.execute(
            "SELECT semantic_id, id FROM segment WHERE semantic_id = ANY(%s)",
            (ext_ids,),
        )
        for sid, iid in cur.fetchall() or []:
            mapping[sid] = int(iid)
        unresolved = [e for e in ext_ids if e not in mapping]
        if unresolved:
            cur.execute(
                "SELECT original_id, id FROM segment_original_id WHERE original_id = ANY(%s)",
                (unresolved,),
            )
            for oid, iid in cur.fetchall() or []:
                mapping[oid] = int(iid)
    return mapping


@click.group("seq", context_settings=hap.CTX_SETTINGS)
def main():
    """Manage segment sequences (import, query, edit, delete)."""


@main.command("add")
@click.option("--fasta", "fasta_path", required=True, type=click.Path(exists=True, path_type=Path))
def cmd_add(fasta_path: Path):
    """Bulk import sequences from FASTA/FASTQ.

    Headers are semantic_id or original node id.
    """
    try:
        with db.auto_connect() as conn:
            records: List[Tuple[str, str]] = list(iter_fasta(fasta_path))
            if not records:
                click.echo("[WARN] No records found in input.", err=True)
                return
            ext_ids = [h for h, _ in records]
            id_map = resolve_many(conn, ext_ids)
            if not id_map:
                raise click.ClickException("No IDs resolved against database.")

            # Fetch lengths and existing sequence ids
            ids = list({id_map.get(h) for h in ext_ids if h in id_map})
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, length FROM segment WHERE id = ANY(%s)", (ids,)
                )
                lengths = {int(i): int(l) if l is not None else None for i, l in cur.fetchall() or []}
                cur.execute(
                    "SELECT id FROM segment_sequence WHERE id = ANY(%s)", (ids,)
                )
                existing = {int(i[0]) for i in cur.fetchall() or []}

            # Write temp TSV for COPY
            from hap.lib import fileutil

            (tmp_tsv,) = fileutil.create_tmp_files(1)
            try:
                written = 0
                with open(tmp_tsv, "w") as out:
                    for hdr, raw in records:
                        seg_id = id_map.get(hdr)
                        if seg_id is None or seg_id in existing:
                            continue
                        cleaned = _clean(raw, hdr)
                        if not cleaned:
                            continue
                        seg_len = lengths.get(seg_id)
                        if seg_len is not None and seg_len != len(cleaned):
                            click.echo(
                                f"[WARN] {hdr}: length {len(cleaned)} != segment.length {seg_len} – skipped",
                                err=True,
                            )
                            continue
                        # If seg_len is None (shouldn't happen), accept and optionally update length
                        out.write(f"{seg_id}\t{cleaned}\n")
                        written += 1
                if written == 0:
                    click.echo("[WARN] No valid rows to import.", err=True)
                    return
                with conn.cursor() as cur:
                    with open(tmp_tsv) as f:
                        cur.copy_from(f, "segment_sequence", sep="\t", null="")
                conn.commit()
                click.echo(f"Imported {written} sequences.")
            finally:
                fileutil.remove_files([tmp_tsv])
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")


@main.command("get")
@click.argument("ids", nargs=-1)
@click.option("--regex", "regex_pat", help="Regex to match semantic_id or original_id")
@click.option("--format", "fmt", type=click.Choice(["tsv", "fasta"]), default="tsv")
def cmd_get(ids: Tuple[str, ...], regex_pat: Optional[str], fmt: str):
    """Query sequences by IDs or regex (on semantic_id/original_id)."""
    try:
        with db.auto_connect() as conn, conn.cursor() as cur:
            rows: List[Tuple[str, str]] = []
            if ids and regex_pat:
                raise click.ClickException("Provide either IDs or --regex, not both.")
            if ids:
                id_map = resolve_many(conn, list(ids))
                if not id_map:
                    raise click.ClickException("None of the IDs resolved.")
                int_ids = list(id_map.values())
                cur.execute(
                    """
                    SELECT s.semantic_id, ss.segment_sequence
                    FROM segment s JOIN segment_sequence ss ON ss.id = s.id
                    WHERE s.id = ANY(%s)
                    ORDER BY s.semantic_id
                    """,
                    (int_ids,),
                )
                rows = [(sid, seq) for sid, seq in cur.fetchall() or []]
            elif regex_pat:
                cur.execute(
                    """
                    SELECT s.semantic_id, ss.segment_sequence
                    FROM segment s
                    JOIN segment_sequence ss ON ss.id = s.id
                    WHERE s.semantic_id ~ %s
                       OR s.id IN (SELECT id FROM segment_original_id WHERE original_id ~ %s)
                    ORDER BY s.semantic_id
                    """,
                    (regex_pat, regex_pat),
                )
                rows = [(sid, seq) for sid, seq in cur.fetchall() or []]
            else:
                raise click.ClickException("Provide IDs or --regex.")

            if fmt == "tsv":
                for sid, seq in rows:
                    click.echo(f"{sid}\t{seq}")
            else:
                for sid, seq in rows:
                    click.echo(f">{sid}")
                    click.echo(seq)
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")


@main.command("edit")
@click.argument("identifier", nargs=1)
@click.option("--replace", "seq_text", required=True)
def cmd_edit(identifier: str, seq_text: str):
    """Replace sequence for a single segment by semantic_id/original_id."""
    cleaned = _clean(seq_text, identifier)
    if not cleaned:
        return
    try:
        with db.auto_connect() as conn:
            seg_id = resolve_one(conn, identifier)
            if seg_id is None:
                raise click.ClickException(f"Identifier not found: {identifier}")
            with conn.cursor() as cur:
                # Length rule
                cur.execute("SELECT length FROM segment WHERE id = %s", (seg_id,))
                row = cur.fetchone()
                seg_len = int(row[0]) if row and row[0] is not None else None
                if seg_len is not None and seg_len != len(cleaned):
                    raise click.ClickException(
                        f"Length mismatch: {len(cleaned)} vs segment.length {seg_len}"
                    )
                if seg_len is None:
                    cur.execute(
                        "UPDATE segment SET length = %s WHERE id = %s",
                        (len(cleaned), seg_id),
                    )
                cur.execute(
                    """
                    INSERT INTO segment_sequence (id, segment_sequence)
                    VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET segment_sequence = EXCLUDED.segment_sequence
                    """,
                    (seg_id, cleaned),
                )
            conn.commit()
            click.echo("Updated 1 sequence.")
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")


@main.command("delete")
@click.argument("ids", nargs=-1)
def cmd_delete(ids: Tuple[str, ...]):
    """Delete sequences by semantic_id/original_id identifiers."""
    if not ids:
        raise click.ClickException("Provide at least one identifier.")
    try:
        with db.auto_connect() as conn:
            id_map = resolve_many(conn, list(ids))
            if not id_map:
                click.echo("[WARN] None of the IDs resolved.", err=True)
                return
            int_ids = list(id_map.values())
            with conn.cursor() as cur:
                cur.execute("DELETE FROM segment_sequence WHERE id = ANY(%s)", (int_ids,))
                affected = cur.rowcount or 0
            conn.commit()
            click.echo(f"Deleted {affected} sequences.")
    except psycopg2.Error as e:
        raise click.ClickException(f"Database error: {e}")