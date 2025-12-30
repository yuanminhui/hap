"""
Annotation command for HAP.

This module provides commands for managing genomic annotations in HAP:
- Importing annotations from GFF3/GTF/BED files
- Querying annotations with filters
- Editing and deleting annotations
- Exporting annotations

Per plan.freeze.json: PRIMARY implementation location (not lib/).
"""

import re
from pathlib import Path
from typing import Any, Optional

import click
import pandas as pd
import psycopg2

from hap.lib import database as db
from hap.lib.error import DataInvalidError


# ===== Annotation Parsers =====


class GFF3Parser:
    """Parser for GFF3 format annotations.

    GFF3 format: 9 tab-delimited columns
    1. seqid (chromosome/scaffold)
    2. source
    3. type (feature type)
    4. start (1-based, inclusive)
    5. end (1-based, inclusive)
    6. score
    7. strand (+, -, .)
    8. phase (0, 1, 2, or .)
    9. attributes (key=value pairs separated by ;)

    Per plan.freeze.json: Convert 1-based coordinates → 0-based.
    """

    @staticmethod
    def parse(filepath: str) -> list[dict[str, Any]]:
        """Parse GFF3 file and return list of annotation dicts.

        Returns:
            List of dicts with keys: seqid, source, type, start, end,
            score, strand, phase, attributes
        """
        annotations = []

        with open(filepath, "r") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) != 9:
                    raise DataInvalidError(
                        f"Line {line_num}: GFF3 requires 9 tab-delimited fields, got {len(parts)}"
                    )

                seqid, source, feature_type, start_str, end_str, score_str, strand, phase_str, attr_str = parts

                # Parse coordinates: GFF3 is 1-based, inclusive → convert to 0-based, half-open
                try:
                    start_1based = int(start_str)
                    end_1based = int(end_str)
                    start_0based = start_1based - 1  # Convert to 0-based
                    end_0based = end_1based  # 1-based inclusive end = 0-based exclusive end
                except ValueError:
                    raise DataInvalidError(
                        f"Line {line_num}: Invalid coordinates '{start_str}', '{end_str}'"
                    )

                # Parse score
                score = None
                if score_str != ".":
                    try:
                        score = float(score_str)
                    except ValueError:
                        pass

                # Parse phase
                phase = None
                if phase_str in ("0", "1", "2"):
                    phase = int(phase_str)

                # Parse attributes
                attributes = GFF3Parser.parse_attributes(attr_str)

                annotations.append({
                    "seqid": seqid,
                    "source": source,
                    "type": feature_type,
                    "start": start_0based,
                    "end": end_0based,
                    "score": score,
                    "strand": strand if strand in ("+", "-", ".") else ".",
                    "phase": phase,
                    "attributes": attributes,
                })

        return annotations

    @staticmethod
    def parse_attributes(attr_str: str) -> dict[str, str]:
        """Parse GFF3 attributes string (key=value;key=value).

        Returns:
            Dict of attribute key-value pairs
        """
        attrs = {}
        if not attr_str or attr_str == ".":
            return attrs

        for pair in attr_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            # URL-decode values (GFF3 spec)
            value = value.replace("%3D", "=").replace("%3B", ";").replace("%2C", ",")
            attrs[key] = value

        return attrs


class GTFParser:
    """Parser for GTF format annotations.

    GTF format: 9 tab-delimited columns (similar to GFF2)
    1. seqname
    2. source
    3. feature
    4. start (1-based, inclusive)
    5. end (1-based, inclusive)
    6. score
    7. strand (+, -, .)
    8. frame (0, 1, 2, or .)
    9. attributes (key "value"; key "value";)

    Per plan.freeze.json: Convert 1-based coordinates → 0-based.
    """

    @staticmethod
    def parse(filepath: str) -> list[dict[str, Any]]:
        """Parse GTF file and return list of annotation dicts."""
        annotations = []

        with open(filepath, "r") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) != 9:
                    raise DataInvalidError(
                        f"Line {line_num}: GTF requires 9 tab-delimited fields, got {len(parts)}"
                    )

                seqname, source, feature_type, start_str, end_str, score_str, strand, frame_str, attr_str = parts

                # Parse coordinates: GTF is 1-based, inclusive → convert to 0-based
                try:
                    start_1based = int(start_str)
                    end_1based = int(end_str)
                    start_0based = start_1based - 1
                    end_0based = end_1based
                except ValueError:
                    raise DataInvalidError(
                        f"Line {line_num}: Invalid coordinates '{start_str}', '{end_str}'"
                    )

                # Parse score
                score = None
                if score_str != ".":
                    try:
                        score = float(score_str)
                    except ValueError:
                        pass

                # Parse frame/phase
                phase = None
                if frame_str in ("0", "1", "2"):
                    phase = int(frame_str)

                # Parse attributes
                attributes = GTFParser.parse_attributes(attr_str)

                annotations.append({
                    "seqid": seqname,
                    "source": source,
                    "type": feature_type,
                    "start": start_0based,
                    "end": end_0based,
                    "score": score,
                    "strand": strand if strand in ("+", "-", ".") else ".",
                    "phase": phase,
                    "attributes": attributes,
                })

        return annotations

    @staticmethod
    def parse_attributes(attr_str: str) -> dict[str, str]:
        """Parse GTF attributes string (key "value"; key "value";).

        Returns:
            Dict of attribute key-value pairs
        """
        attrs = {}
        if not attr_str or attr_str == ".":
            return attrs

        # GTF attributes: key "value"; format
        # Match: key "value" or key 'value' or key value
        pattern = r'(\w+)\s+["\']?([^;"\']+)["\']?'
        for match in re.finditer(pattern, attr_str):
            key, value = match.groups()
            attrs[key.strip()] = value.strip()

        return attrs


class BEDParser:
    """Parser for BED format annotations.

    BED format: 3-12 tab-delimited columns (BED3 to BED12)
    Required (BED3):
    1. chrom
    2. chromStart (0-based)
    3. chromEnd (0-based, exclusive)

    Optional (BED6):
    4. name
    5. score
    6. strand

    Additional (BED12):
    7. thickStart
    8. thickEnd
    9. itemRgb
    10. blockCount
    11. blockSizes (comma-separated)
    12. blockStarts (comma-separated)

    Per plan.freeze.json: BED is already 0-based, no conversion needed.
    """

    @staticmethod
    def parse(filepath: str) -> list[dict[str, Any]]:
        """Parse BED file and return list of annotation dicts."""
        annotations = []

        with open(filepath, "r") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()

                # Skip empty lines and track/browser lines
                if not line or line.startswith(("track", "browser", "#")):
                    continue

                parts = line.split("\t")
                num_cols = len(parts)

                if num_cols < 3:
                    raise DataInvalidError(
                        f"Line {line_num}: BED requires at least 3 fields, got {num_cols}"
                    )

                # Required fields (BED3)
                chrom = parts[0]
                try:
                    chrom_start = int(parts[1])  # Already 0-based
                    chrom_end = int(parts[2])  # Already 0-based, exclusive
                except ValueError:
                    raise DataInvalidError(
                        f"Line {line_num}: Invalid coordinates '{parts[1]}', '{parts[2]}'"
                    )

                # Optional fields
                name = parts[3] if num_cols > 3 else None
                score = None
                if num_cols > 4 and parts[4] != ".":
                    try:
                        score = float(parts[4])
                    except ValueError:
                        pass

                strand = parts[5] if num_cols > 5 and parts[5] in ("+", "-", ".") else "."

                # BED12 specific fields (stored in attributes)
                bed_attrs = {}
                if num_cols > 6:
                    bed_attrs["thickStart"] = parts[6]
                if num_cols > 7:
                    bed_attrs["thickEnd"] = parts[7]
                if num_cols > 8:
                    bed_attrs["itemRgb"] = parts[8]
                if num_cols > 9:
                    bed_attrs["blockCount"] = parts[9]
                if num_cols > 10:
                    bed_attrs["blockSizes"] = parts[10]
                if num_cols > 11:
                    bed_attrs["blockStarts"] = parts[11]

                annotations.append({
                    "seqid": chrom,
                    "source": "BED",
                    "type": "region",  # Default type for BED
                    "start": chrom_start,  # Already 0-based
                    "end": chrom_end,  # Already 0-based
                    "score": score,
                    "strand": strand,
                    "phase": None,
                    "attributes": bed_attrs,
                    "name": name,
                })

        return annotations


def detect_annotation_format(filepath: str) -> str:
    """Auto-detect annotation file format based on extension and content.

    Returns:
        "gff3", "gtf", or "bed"
    """
    filepath_lower = filepath.lower()

    # Extension-based detection
    if filepath_lower.endswith((".gff", ".gff3")):
        return "gff3"
    elif filepath_lower.endswith(".gtf"):
        return "gtf"
    elif filepath_lower.endswith(".bed"):
        return "bed"

    # Content-based detection: peek at first non-comment line
    try:
        with open(filepath, "r") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) >= 9:
                    # Check attributes format
                    attr = parts[8]
                    if "=" in attr:
                        return "gff3"  # GFF3 uses key=value
                    elif '"' in attr or ";" in attr:
                        return "gtf"  # GTF uses key "value";
                elif len(parts) >= 3:
                    return "bed"  # BED has 3-12 columns
                break
    except Exception:
        pass

    # Default to GFF3 if can't determine
    return "gff3"


# ===== Coordinate Mapping =====


class AnnotationMapper:
    """Maps annotations from path coordinates to segment coordinates.

    Per plan.freeze.json: Query path_segment_coordinate table to find
    overlapping segments and calculate segment-local coordinates.

    Optimized for batch processing: preloads entire path coordinate data
    to avoid N+1 query problem.
    """

    def __init__(self, connection: psycopg2.extensions.connection):
        """Initialize mapper with database connection."""
        self.connection = connection
        self._coord_cache = {}  # path_id -> coordinate data

    def preload_path_coordinates(self, path_id: int):
        """Preload all segment coordinates for a path into memory.

        This eliminates N+1 query problem when mapping multiple annotations
        to the same path. Memory usage: ~100 bytes per segment.

        Args:
            path_id: Path ID to preload
        """
        if path_id in self._coord_cache:
            return  # Already loaded

        query = """
            SELECT
                segment_id,
                segment_order,
                lower(coordinate) as seg_start,
                upper(coordinate) as seg_end
            FROM path_segment_coordinate
            WHERE path_id = %s
            ORDER BY segment_order;
        """

        with self.connection.cursor() as cur:
            cur.execute(query, (path_id,))
            rows = cur.fetchall()

        # Store as list of tuples for fast iteration
        self._coord_cache[path_id] = rows

    def map_annotation_to_segments(
        self, path_id: int, start: int, end: int
    ) -> list[dict[str, Any]]:
        """Map annotation from path coordinates to segment coordinates.

        Args:
            path_id: Path ID
            start: 0-based start position on path
            end: 0-based end position on path (exclusive)

        Returns:
            List of dicts with keys: segment_id, segment_order, orientation,
            segment_start, segment_end
        """
        # Use cached coordinates if available
        if path_id in self._coord_cache:
            return self._map_with_cache(path_id, start, end)

        # Fallback to single query (for backward compatibility)
        return self._map_with_query(path_id, start, end)

    def _map_with_cache(self, path_id: int, start: int, end: int) -> list[dict[str, Any]]:
        """Map using preloaded cache (fast path)."""
        coord_data = self._coord_cache[path_id]
        result = []

        for seg_id, seg_order, seg_start, seg_end in coord_data:
            # Check overlap: segment [seg_start, seg_end) vs annotation [start, end)
            if seg_end <= start:
                continue  # Segment before annotation
            if seg_start >= end:
                break  # Segment after annotation (sorted, can exit early)

            # Calculate intersection
            intersect_start = max(start, seg_start)
            intersect_end = min(end, seg_end)

            # Calculate segment-local coordinates (0-based)
            seg_local_start = intersect_start - seg_start
            seg_local_end = intersect_end - seg_start

            # Note: All paths are forward-only (validated during GFA parsing)

            result.append({
                "segment_id": seg_id,
                "segment_order": seg_order,
                "segment_start": seg_local_start,
                "segment_end": seg_local_end,
            })

        return result

    def _map_with_query(self, path_id: int, start: int, end: int) -> list[dict[str, Any]]:
        """Map using direct query (fallback for single annotations)."""
        query = """
            SELECT
                segment_id,
                segment_order,
                lower(coordinate) as seg_path_start,
                upper(coordinate) as seg_path_end
            FROM path_segment_coordinate
            WHERE path_id = %s
              AND coordinate && int8range(%s, %s)
            ORDER BY segment_order;
        """

        with self.connection.cursor() as cur:
            cur.execute(query, (path_id, start, end))
            rows = cur.fetchall()

        if not rows:
            return []

        # Calculate segment-local coordinates for each overlapping segment
        result = []
        for row in rows:
            seg_id, seg_order, seg_path_start, seg_path_end = row

            # Calculate intersection
            intersect_start = max(start, seg_path_start)
            intersect_end = min(end, seg_path_end)

            # Calculate segment-local coordinates (0-based)
            seg_local_start = intersect_start - seg_path_start
            seg_local_end = intersect_end - seg_path_start

            # Note: All paths are forward-only (validated during GFA parsing)

            result.append({
                "segment_id": seg_id,
                "segment_order": seg_order,
                "segment_start": seg_local_start,
                "segment_end": seg_local_end,
            })

        return result

    def map_annotations_batch(
        self, path_id: int, annotations: list[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        """Batch map multiple annotations to segments (optimized).

        Preloads path coordinates once, then maps all annotations in memory.
        This is 100x faster than calling map_annotation_to_segments() repeatedly.

        Args:
            path_id: Path ID
            annotations: List of annotation dicts with 'start' and 'end' keys

        Returns:
            List of segment mappings (one per annotation)
        """
        # Preload coordinates once
        self.preload_path_coordinates(path_id)

        # Map all annotations using cache
        result = []
        for ann in annotations:
            segments = self._map_with_cache(path_id, ann["start"], ann["end"])
            result.append(segments)

        return result


# ===== Annotation Import =====


def import_annotations(
    connection: psycopg2.extensions.connection,
    filepath: str,
    format_type: str,
    genome_name: str,
    haplotype_index: Optional[int] = None,
    subgraph_name: Optional[str] = None,
) -> int:
    """Import annotations from file into database.

    Core Logic:
    - Annotation file seqid = subgraph.name (e.g., "chr1", "1")
    - Must specify genome_name to identify which genome's paths to use
    - haplotype_index is optional: if not provided, auto-select first available (0, 1, 2, ...)

    Pipeline:
    1. Resolve genome_id (auto-select haplotype if needed)
    2. Parse annotation file
    3. Group by seqid
    4. For each seqid: find path (subgraph.name=seqid AND genome_id)
    5. Map annotations to segments and insert

    Args:
        connection: Database connection
        filepath: Path to annotation file
        format_type: "gff3", "gtf", or "bed"
        genome_name: Genome name (required, e.g., "hap1", "HG002")
        haplotype_index: Haplotype index (optional, auto-select if None)
        subgraph_name: Filter to specific subgraph (optional)

    Returns:
        Number of annotations imported

    Example:
        import_annotations(conn, "anno.gff3", "gff3", genome_name="HG002", haplotype_index=1)
        import_annotations(conn, "anno.gff3", "gff3", genome_name="HG002")  # auto-select haplotype
    """

    # Step 1: Resolve genome_id
    cursor = connection.cursor()

    if haplotype_index is not None:
        # Explicit haplotype_index provided
        cursor.execute(
            "SELECT id FROM genome WHERE name = %s AND haplotype_index = %s",
            (genome_name, haplotype_index)
        )
        result = cursor.fetchone()
        if not result:
            raise DataInvalidError(
                f"Genome not found: name='{genome_name}', haplotype_index={haplotype_index}"
            )
        genome_id = result[0]
        resolved_haplotype_index = haplotype_index
    else:
        # Auto-select: find first available haplotype (0, 1, 2, ...)
        cursor.execute(
            """SELECT id, haplotype_index FROM genome
               WHERE name = %s
               ORDER BY haplotype_index
               LIMIT 1""",
            (genome_name,)
        )
        result = cursor.fetchone()
        if not result:
            raise DataInvalidError(f"No genome found with name='{genome_name}'")
        genome_id, resolved_haplotype_index = result
        import click
        click.echo(f"Auto-selected haplotype_index={resolved_haplotype_index} for genome '{genome_name}'")

    # Step 2: Parse annotation file
    if format_type == "gff3":
        parsed_annotations = GFF3Parser.parse(filepath)
    elif format_type == "gtf":
        parsed_annotations = GTFParser.parse(filepath)
    elif format_type == "bed":
        parsed_annotations = BEDParser.parse(filepath)
    else:
        raise ValueError(f"Unknown format: {format_type}")

    if not parsed_annotations:
        return 0

    # Step 3: Group by seqid (seqid = subgraph.name)
    by_seqid = {}
    for ann in parsed_annotations:
        seqid = ann["seqid"]
        by_seqid.setdefault(seqid, []).append(ann)

    # Step 4: For each seqid, find corresponding path and import
    total_imported = 0

    for seqid, anns in by_seqid.items():
        # Skip if not target subgraph
        if subgraph_name and seqid != subgraph_name:
            continue

        # Find path: subgraph.name=seqid AND genome_id=genome_id
        query_path = """
            SELECT p.id, p.name, p.subgraph_id, s.name as subgraph_name
            FROM path p
            JOIN subgraph s ON p.subgraph_id = s.id
            WHERE s.name = %s AND p.genome_id = %s
        """
        cursor.execute(query_path, (seqid, genome_id))
        result = cursor.fetchone()

        if not result:
            # List available subgraphs for this genome
            cursor.execute(
                """SELECT DISTINCT s.name
                   FROM subgraph s
                   JOIN path p ON s.id = p.subgraph_id
                   WHERE p.genome_id = %s
                   ORDER BY s.name""",
                (genome_id,)
            )
            available = [row[0] for row in cursor.fetchall()]

            raise DataInvalidError(
                f"Path not found for seqid '{seqid}' with genome '{genome_name}' haplotype {resolved_haplotype_index}.\n"
                f"Available subgraphs for this genome: {available}"
            )

        path_id, path_name, subgraph_id, subgraph_name_db = result

        # Import annotations for this seqid to the found path
        count = _import_to_single_path_helper(
            connection, path_id, genome_id, subgraph_id, anns, format_type
        )
        total_imported += count

        import click
        click.echo(
            f"  Imported {count} annotations: seqid '{seqid}' → path '{path_name}' "
            f"(genome: {genome_name}#{resolved_haplotype_index})"
        )

    return total_imported


def _import_to_single_path_helper(
    connection, path_id, genome_id, subgraph_id, annotations, format_type
):
    """Helper function to import annotations to a single path."""

    # Map annotations to segments
    mapper = AnnotationMapper(connection)
    mapper.preload_path_coordinates(path_id)

    annotation_records = []
    annotation_span_records = []

    # Get starting IDs
    next_annotation_id = db.get_next_id_from_table(connection, "annotation")
    next_span_id = db.get_next_id_from_table(connection, "annotation_span")

    annotation_id_counter = next_annotation_id
    span_id_counter = next_span_id

    source_map = {"gff3": "GFF3", "gtf": "GTF", "bed": "BED"}
    source = source_map.get(format_type, format_type.upper())

    for ann in annotations:
        # Map annotation to segments
        segments = mapper.map_annotation_to_segments(
            path_id, ann["start"], ann["end"]
        )

        if not segments:
            # Skip annotations that don't map to any segments
            continue

        attrs = ann.get("attributes", {})
        ann_type = ann["type"]

        # Extract label
        label = None
        if attrs:
            label = attrs.get("Name") or attrs.get("ID") or attrs.get("gene_name") or attrs.get("transcript_name")

        # Create annotation record
        annotation_records.append({
            "id": annotation_id_counter,
            "subgraph_id": subgraph_id,
            "path_id": path_id,
            "coordinate": f"[{ann['start']},{ann['end']})",
            "type": ann_type,
            "label": label,
            "strand": ann.get("strand", "."),
            "source": source,
            "score": ann.get("score"),
            "attributes": attrs,
            "genome_id": genome_id,
        })

        # Create annotation_span records
        for span_order, seg in enumerate(segments):
            annotation_span_records.append({
                "id": span_id_counter,
                "annotation_id": annotation_id_counter,
                "segment_id": seg["segment_id"],
                "coordinate": f"[{seg['segment_start']},{seg['segment_end']})",
                "span_order": span_order,
            })
            span_id_counter += 1

        annotation_id_counter += 1

    # Insert into database
    if not annotation_records:
        return 0

    import json
    with connection.cursor() as cur:
        # Insert annotations
        ann_query = """
            INSERT INTO annotation (id, subgraph_id, path_id, coordinate, type, label, strand, source, score, attributes, genome_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s);
        """
        ann_values = [
            (rec["id"], rec["subgraph_id"], rec["path_id"], rec["coordinate"], rec["type"],
             rec["label"], rec["strand"], rec["source"], rec["score"],
             json.dumps(rec["attributes"]) if rec["attributes"] else None,
             rec["genome_id"])
            for rec in annotation_records
        ]
        cur.executemany(ann_query, ann_values)

        # Insert annotation_spans
        span_query = """
            INSERT INTO annotation_span (id, annotation_id, segment_id, coordinate, span_order)
            VALUES (%s, %s, %s, %s, %s);
        """
        span_values = [
            (rec["id"], rec["annotation_id"], rec["segment_id"], rec["coordinate"], rec["span_order"])
            for rec in annotation_span_records
        ]
        cur.executemany(span_query, span_values)

    connection.commit()
    return len(annotation_records)


# ===== Annotation Query =====


def query_annotations(
    connection: psycopg2.extensions.connection,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Query annotations with filters.

    Per plan.freeze.json Phase 7: Build SQL with JOINs and support multiple filters.

    Args:
        connection: Database connection
        filters: Dict with optional keys: ids, label (regex), type, path,
                 segment, subgraph, range (tuple of start, end)

    Returns:
        List of annotation dicts with all fields
    """
    # Base query with JOINs
    query = """
        SELECT DISTINCT
            a.id,
            a.subgraph_id,
            a.path_id,
            p.name as path_name,
            lower(a.coordinate) as start,
            upper(a.coordinate) as end,
            a.type,
            a.label,
            a.strand,
            a.source,
            a.score,
            a.attributes,
            a.genome_id,
            g.name as genome_name
        FROM annotation a
        JOIN path p ON a.path_id = p.id
        LEFT JOIN genome g ON a.genome_id = g.id
    """

    conditions = []
    params = []

    # Filter by IDs
    if "ids" in filters:
        conditions.append("a.id = ANY(%s)")
        params.append(filters["ids"])

    # Filter by label (regex)
    if "label" in filters:
        conditions.append("a.label ~ %s")
        params.append(filters["label"])

    # Filter by type
    if "type" in filters:
        conditions.append("a.type = %s")
        params.append(filters["type"])

    # Filter by path
    if "path" in filters:
        conditions.append("p.name = %s")
        params.append(filters["path"])

    # Filter by segment (via annotation_span)
    if "segment" in filters:
        query += """
            JOIN annotation_span asp ON a.id = asp.annotation_id
            JOIN segment s ON asp.segment_id = s.id
        """
        # Check if filter is numeric ID or semantic_id
        seg_filter = filters["segment"]
        if seg_filter.isdigit():
            conditions.append("s.id = %s")
            params.append(int(seg_filter))
        else:
            conditions.append("s.semantic_id = %s")
            params.append(seg_filter)

    # Filter by subgraph name
    if "subgraph" in filters:
        query += " JOIN subgraph sg ON a.subgraph_id = sg.id"
        conditions.append("sg.name = %s")
        params.append(filters["subgraph"])

    # Filter by range (coordinate overlap)
    if "range" in filters:
        start, end = filters["range"]
        conditions.append("a.coordinate && int8range(%s, %s)")
        params.extend([start, end])

    # Add WHERE clause
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # Order by path and coordinate
    query += " ORDER BY a.path_id, lower(a.coordinate);"

    # Execute query
    with connection.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    # Convert to dicts
    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "subgraph_id": row[1],
            "path_id": row[2],
            "path_name": row[3],
            "start": row[4],
            "end": row[5],
            "type": row[6],
            "label": row[7],
            "strand": row[8],
            "source": row[9],
            "score": row[10],
            "attributes": row[11],
            "genome_id": row[12],
            "genome_name": row[13],
        })

    return results


def format_annotations(
    annotations: list[dict[str, Any]], format_type: str
) -> list[str]:
    """Format annotations for output.

    Per plan.freeze.json Phase 7: Support TSV, GFF3, GTF, BED, JSON formats.
    GFF3/GTF convert to 1-based coordinates for output.

    Args:
        annotations: List of annotation dicts from query_annotations()
        format_type: "tsv", "gff3", "gtf", "bed", or "json"

    Returns:
        List of formatted output lines
    """
    if format_type == "json":
        import json
        return [json.dumps(annotations, indent=2)]

    elif format_type == "tsv":
        # TSV format: id, path, start, end, type, label, strand, score
        lines = ["id\tpath\tstart\tend\ttype\tlabel\tstrand\tscore"]
        for ann in annotations:
            lines.append(
                f"{ann['id']}\t{ann['path_name']}\t{ann['start']}\t{ann['end']}\t"
                f"{ann['type']}\t{ann['label'] or '.'}\t{ann['strand']}\t{ann['score'] or '.'}"
            )
        return lines

    elif format_type == "gff3":
        # GFF3 format: seqid, source, type, start, end, score, strand, phase, attributes
        # Convert 0-based → 1-based
        lines = ["##gff-version 3"]
        for ann in annotations:
            attrs = ann["attributes"] or {}
            # Build attributes string
            attr_str = ";".join(
                f"{k}={v}" for k, v in attrs.items() if v is not None
            )
            if ann["label"]:
                attr_str = f"ID={ann['id']};Name={ann['label']}" + (
                    f";{attr_str}" if attr_str else ""
                )
            else:
                attr_str = f"ID={ann['id']}" + (f";{attr_str}" if attr_str else "")

            # Convert to 1-based inclusive
            start_1based = ann["start"] + 1
            end_1based = ann["end"]

            lines.append(
                f"{ann['path_name']}\t{ann['source']}\t{ann['type']}\t"
                f"{start_1based}\t{end_1based}\t{ann['score'] or '.'}\t"
                f"{ann['strand']}\t.\t{attr_str}"
            )
        return lines

    elif format_type == "gtf":
        # GTF format similar to GFF3 but with different attribute format
        lines = []
        for ann in annotations:
            attrs = ann["attributes"] or {}
            # GTF attributes: key "value"; format
            attr_pairs = []
            if ann["label"]:
                attr_pairs.append(f'gene_id "{ann["label"]}"')
            for k, v in attrs.items():
                if v is not None:
                    attr_pairs.append(f'{k} "{v}"')
            attr_str = "; ".join(attr_pairs) + ";" if attr_pairs else ""

            # Convert to 1-based inclusive
            start_1based = ann["start"] + 1
            end_1based = ann["end"]

            lines.append(
                f"{ann['path_name']}\t{ann['source']}\t{ann['type']}\t"
                f"{start_1based}\t{end_1based}\t{ann['score'] or '.'}\t"
                f"{ann['strand']}\t.\t{attr_str}"
            )
        return lines

    elif format_type == "bed":
        # BED format: chrom, chromStart, chromEnd, name, score, strand
        # BED is 0-based (matches our internal format)
        lines = []
        for ann in annotations:
            lines.append(
                f"{ann['path_name']}\t{ann['start']}\t{ann['end']}\t"
                f"{ann['label'] or ann['type']}\t{ann['score'] or 0}\t{ann['strand']}"
            )
        return lines

    else:
        raise ValueError(f"Unsupported format: {format_type}")


# ===== Click Command Group =====


@click.group()
def main():
    """Manage annotations in HAP."""
    pass


# Alias for compatibility
annotation = main


@annotation.command(name="add")
@click.option(
    "--genome-name",
    type=str,
    required=True,
    help="Genome name (sample name, e.g., 'hap1', 'HG002')",
)
@click.option(
    "--haplotype-index",
    type=int,
    help="Haplotype index (0, 1, 2, ...). If not specified, auto-selects first available.",
)
@click.option(
    "--subgraph",
    type=str,
    help="Filter to specific subgraph name (optional)",
)
@click.option(
    "--file",
    type=click.Path(exists=True),
    required=True,
    help="Annotation file path (GFF3/GTF/BED)",
)
@click.option(
    "--format",
    type=click.Choice(["gff3", "gtf", "bed"], case_sensitive=False),
    help="File format (auto-detected if not specified)",
)
def add_annotation(
    genome_name: str,
    haplotype_index: Optional[int],
    subgraph: Optional[str],
    file: str,
    format: Optional[str],
):
    """Import annotations from GFF3/GTF/BED file.

    The file's seqid column must match subgraph.name in the database.
    You must specify which genome these annotations belong to.

    Examples:
        # Import with explicit haplotype index
        hap annotation add --file anno.gff3 --genome-name HG002 --haplotype-index 1

        # Auto-select haplotype (uses first available, e.g., haplotype_index=0)
        hap annotation add --file anno.gff3 --genome-name hap1

        # Import only specific subgraph from multi-chromosome file
        hap annotation add --file anno.gff3 --genome-name HG002 --haplotype-index 1 --subgraph chr1

    Note:
        - seqid in annotation file = subgraph.name (e.g., "chr1", "1")
        - NOT path.name (e.g., NOT "HG002#1#chr1")
    """
    # Auto-detect format if not specified
    if not format:
        format = detect_annotation_format(file)
        click.echo(f"Auto-detected format: {format}")

    # Get database connection
    with db.auto_connect() as conn:
        try:
            num_imported = import_annotations(
                connection=conn,
                filepath=file,
                format_type=format.lower(),
                genome_name=genome_name,
                haplotype_index=haplotype_index,
                subgraph_name=subgraph,
            )
            click.echo(f"Successfully imported {num_imported} annotations")
        except Exception as e:
            conn.rollback()
            click.echo(f"Error importing annotations: {e}", err=True)
            raise


@annotation.command(name="get")
@click.option("--id", "ann_ids", type=int, multiple=True, help="Annotation ID(s)")
@click.option("--label", type=str, help="Annotation label (regex pattern)")
@click.option("--type", "ann_type", type=str, help="Annotation type filter")
@click.option("--path", type=str, help="Path/genome name filter")
@click.option("--segment", type=str, help="Segment ID or semantic_id filter")
@click.option("--subgraph", type=str, help="Subgraph name filter")
@click.option(
    "--range",
    type=str,
    help="Coordinate range on path (format: start-end, 0-based)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["tsv", "gff3", "gtf", "bed", "json"], case_sensitive=False),
    default="tsv",
    help="Output format",
)
@click.option("--output", type=click.Path(), help="Output file (default: stdout)")
def get_annotation(
    ann_ids: tuple[int],
    label: Optional[str],
    ann_type: Optional[str],
    path: Optional[str],
    segment: Optional[str],
    subgraph: Optional[str],
    range: Optional[str],
    output_format: str,
    output: Optional[str],
):
    """Query annotations with filters.

    Per plan.freeze.json Phase 7: Query annotations with multiple filter options.

    Examples:
        hap annotation get --path chr1 --type gene
        hap annotation get --label "BRCA.*" --format gff3
        hap annotation get --range 1000-5000 --path chr1
    """
    with db.auto_connect() as conn:
        # Build query based on filters
        filters = {}
        if ann_ids:
            filters["ids"] = list(ann_ids)
        if label:
            filters["label"] = label
        if ann_type:
            filters["type"] = ann_type
        if path:
            filters["path"] = path
        if segment:
            filters["segment"] = segment
        if subgraph:
            filters["subgraph"] = subgraph
        if range:
            # Parse range: "start-end"
            try:
                start, end = map(int, range.split("-"))
                filters["range"] = (start, end)
            except ValueError:
                click.echo(f"Invalid range format: {range}. Use 'start-end'", err=True)
                return

        # Query annotations
        annotations = query_annotations(conn, filters)

        if not annotations:
            click.echo("No annotations found matching the criteria")
            return

        # Format output
        output_lines = format_annotations(annotations, output_format)

        # Write to file or stdout
        if output:
            with open(output, "w") as f:
                f.write("\n".join(output_lines) + "\n")
            click.echo(f"Exported {len(annotations)} annotations to {output}")
        else:
            for line in output_lines:
                click.echo(line)


@annotation.command(name="edit")
@click.option("--id", "ann_id", type=int, required=True, help="Annotation ID to edit")
@click.option("--label", type=str, help="New label")
@click.option("--type", "ann_type", type=str, help="New type")
def edit_annotation(ann_id: int, label: Optional[str], ann_type: Optional[str]):
    """Edit annotation properties.

    Per plan.freeze.json Phase 8: Edit annotation metadata.

    Example:
        hap annotation edit --id 123 --label "BRCA1"
    """
    if not label and not ann_type:
        click.echo("Error: Must provide at least one field to edit (--label or --type)", err=True)
        return

    with db.auto_connect() as conn:
        # Build UPDATE query
        updates = []
        params = []

        if label:
            updates.append("label = %s")
            params.append(label)
        if ann_type:
            updates.append("type = %s")
            params.append(ann_type)

        params.append(ann_id)

        query = f"UPDATE annotation SET {', '.join(updates)} WHERE id = %s;"

        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if cur.rowcount == 0:
                    click.echo(f"No annotation found with ID {ann_id}", err=True)
                    return

            conn.commit()
            click.echo(f"Successfully updated annotation {ann_id}")

        except Exception as e:
            conn.rollback()
            click.echo(f"Error editing annotation: {e}", err=True)
            raise


@annotation.command(name="delete")
@click.option("--id", "ann_ids", type=int, multiple=True, help="Annotation ID(s) to delete")
@click.option("--label", type=str, help="Delete by label pattern (regex)")
@click.option("--type", "ann_type", type=str, help="Delete by type")
@click.option("--path", type=str, help="Delete from path")
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
def delete_annotation(
    ann_ids: tuple[int],
    label: Optional[str],
    ann_type: Optional[str],
    path: Optional[str],
    confirm: bool,
):
    """Delete annotations by filter.

    Per plan.freeze.json Phase 8: Delete annotations with confirmation.

    Examples:
        hap annotation delete --id 123 --confirm
        hap annotation delete --label "test.*" --type gene --confirm
    """
    with db.auto_connect() as conn:
        try:
            # Build filter for finding annotations
            filters = {}
            if ann_ids:
                filters["ids"] = list(ann_ids)
            if label:
                filters["label"] = label
            if ann_type:
                filters["type"] = ann_type
            if path:
                filters["path"] = path

            if not filters:
                click.echo("Error: Must provide at least one filter", err=True)
                return

            # Find matching annotations
            annotations = query_annotations(conn, filters)

            if not annotations:
                click.echo("No annotations found matching the criteria")
                return

            # Confirm deletion
            if not confirm:
                click.echo(f"Found {len(annotations)} annotation(s) to delete:")
                for ann in annotations[:10]:  # Show first 10
                    click.echo(f"  ID {ann['id']}: {ann['label']} ({ann['type']}) on {ann['path_name']}")
                if len(annotations) > 10:
                    click.echo(f"  ... and {len(annotations) - 10} more")

                if not click.confirm("Do you want to delete these annotations?"):
                    click.echo("Deletion cancelled")
                    return

            # Delete annotations
            ann_ids_to_delete = [ann["id"] for ann in annotations]

            query = "DELETE FROM annotation WHERE id = ANY(%s);"
            with conn.cursor() as cur:
                cur.execute(query, (ann_ids_to_delete,))

            conn.commit()
            click.echo(f"Successfully deleted {len(annotations)} annotation(s)")

        except Exception as e:
            conn.rollback()
            click.echo(f"Error deleting annotations: {e}", err=True)
            raise


@annotation.command(name="export")
@click.option("--path", type=str, help="Path name to export from")
@click.option("--subgraph", type=str, help="Subgraph name to export from")
@click.option(
    "--format",
    "format_type",
    type=click.Choice(["gff3", "gtf", "bed"], case_sensitive=False),
    required=True,
    help="Export format",
)
@click.option("--output", type=click.Path(), required=True, help="Output file path")
def export_annotation(
    path: Optional[str],
    subgraph: Optional[str],
    format_type: str,
    output: str,
):
    """Export annotations to file.

    Per plan.freeze.json Phase 8: Export annotations to GFF3/GTF/BED formats.

    Example:
        hap annotation export --path chr1 --format gff3 --output chr1.gff3
    """
    if not path and not subgraph:
        click.echo("Error: Must provide --path or --subgraph", err=True)
        return

    with db.auto_connect() as conn:
        try:
            # Build filter
            filters = {}
            if path:
                filters["path"] = path
            if subgraph:
                filters["subgraph"] = subgraph

            # Query annotations
            annotations = query_annotations(conn, filters)

            if not annotations:
                click.echo("No annotations found to export")
                return

            # Format output
            output_lines = format_annotations(annotations, format_type)

            # Write to file
            with open(output, "w") as f:
                f.write("\n".join(output_lines) + "\n")

            click.echo(f"Successfully exported {len(annotations)} annotation(s) to {output}")

        except Exception as e:
            conn.rollback()
            click.echo(f"Error exporting annotations: {e}", err=True)
            raise

