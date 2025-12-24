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
                orientation,
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

        for seg_id, seg_order, orientation, seg_start, seg_end in coord_data:
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

            # Handle reverse orientation: flip coordinates
            if orientation == "-":
                segment_length = seg_end - seg_start
                seg_local_start, seg_local_end = (
                    segment_length - seg_local_end,
                    segment_length - seg_local_start,
                )

            result.append({
                "segment_id": seg_id,
                "segment_order": seg_order,
                "orientation": orientation,
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
                orientation,
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
            seg_id, seg_order, orientation, seg_path_start, seg_path_end = row

            # Calculate intersection
            intersect_start = max(start, seg_path_start)
            intersect_end = min(end, seg_path_end)

            # Calculate segment-local coordinates (0-based)
            seg_local_start = intersect_start - seg_path_start
            seg_local_end = intersect_end - seg_path_start

            # Handle reverse orientation: flip coordinates
            if orientation == "-":
                segment_length = seg_path_end - seg_path_start
                seg_local_start, seg_local_end = (
                    segment_length - seg_local_end,
                    segment_length - seg_local_start,
                )

            result.append({
                "segment_id": seg_id,
                "segment_order": seg_order,
                "orientation": orientation,
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
    hap_name: Optional[str] = None,
    path_name: Optional[str] = None,
    subgraph_id: Optional[int] = None,
) -> int:
    """Import annotations from file into database.

    Per plan.freeze.json: Complete pipeline:
    1. Validate target (hap/path/subgraph exists)
    2. Parse annotation file
    3. Map each annotation to segments
    4. Generate annotation_span records for ALL annotations
    5. Insert into annotation, annotation_span, and type-specific tables

    Args:
        connection: Database connection
        filepath: Path to annotation file
        format_type: "gff3", "gtf", or "bed"
        hap_name: HAP name (optional)
        path_name: Path name (required)
        subgraph_id: Subgraph ID (optional)

    Returns:
        Number of annotations imported
    """
    if not path_name:
        raise ValueError("path_name is required for annotation import")

    # Step 1: Validate and get path info
    query_path = """
        SELECT p.id, p.subgraph_id, p.genome_id
        FROM path p
        WHERE p.name = %s
    """
    params = [path_name]

    if subgraph_id is not None:
        query_path += " AND p.subgraph_id = %s"
        params.append(subgraph_id)

    with connection.cursor() as cur:
        cur.execute(query_path, params)
        path_row = cur.fetchone()

    if not path_row:
        raise DataInvalidError(f"Path '{path_name}' not found in database")

    path_id, resolved_subgraph_id, genome_id = path_row

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

    # Step 3: Map annotations to segments (OPTIMIZED: batch processing)
    mapper = AnnotationMapper(connection)

    # Preload path coordinates once for all annotations
    mapper.preload_path_coordinates(path_id)

    annotation_records = []
    annotation_gene_records = []
    annotation_span_records = []

    # Get starting IDs for batch insert
    next_annotation_id = db.get_next_id_from_table(connection, "annotation")
    next_span_id = db.get_next_id_from_table(connection, "annotation_span")

    annotation_id_counter = next_annotation_id
    span_id_counter = next_span_id

    # Determine source from format_type
    source_map = {"gff3": "GFF3", "gtf": "GTF", "bed": "BED"}
    source = source_map.get(format_type, format_type.upper())

    # Mapping: GFF3/GTF ID string -> annotation.id (for parent_id resolution)
    id_string_to_annotation_id = {}
    # Mapping: ID string -> gene_id (for inheritance)
    id_to_gene_id = {}

    for ann in parsed_annotations:
        # Map annotation to segments (using preloaded cache)
        segments = mapper.map_annotation_to_segments(
            path_id, ann["start"], ann["end"]
        )

        if not segments:
            # Skip annotations that don't map to any segments
            continue

        attrs = ann.get("attributes", {})
        ann_type = ann["type"]
        feature_id = attrs.get("ID")

        # Create annotation record
        annotation_records.append({
            "id": annotation_id_counter,
            "subgraph_id": resolved_subgraph_id,
            "path_id": path_id,
            "coordinate": f"[{ann['start']},{ann['end']})",
            "type": ann_type,
            "label": ann.get("name") or attrs.get("Name") or feature_id,
            "strand": ann["strand"],
            "source": source,
            "score": ann.get("score"),
            "attributes": attrs,
            "genome_id": genome_id,
        })

        # Map feature_kind from GFF3/GTF type
        feature_kind_map = {
            "gene": "gene",
            "mRNA": "transcript",
            "transcript": "transcript",
            "lncRNA": "transcript",
            "lncRNA_gene": "gene",
            "miRNA": "transcript",
            "miRNA_gene": "gene",
            "tRNA": "transcript",
            "rRNA": "transcript",
            "snoRNA": "transcript",
            "snRNA": "transcript",
            "ncRNA": "transcript",
            "ncRNA_gene": "gene",
            "exon": "exon",
            "CDS": "cds",
            "five_prime_UTR": "utr5",
            "three_prime_UTR": "utr3",
            "intron": "intron",
        }
        feature_kind = feature_kind_map.get(ann_type)

        if feature_kind:
            # Extract parent_id from attributes (GFF3 Parent field)
            parent_string = attrs.get("Parent")
            parent_annotation_id = id_string_to_annotation_id.get(parent_string)

            # Extract gene_id and transcript_id
            gene_id = None
            transcript_id = None
            biotype = attrs.get("biotype") or attrs.get("gene_type")
            phase = ann.get("phase")

            if feature_kind == "gene":
                # Gene level: extract gene_id from ID
                gene_id = feature_id or attrs.get("gene_id")
                # Store for children to inherit
                if feature_id:
                    id_to_gene_id[feature_id] = gene_id
            elif feature_kind == "transcript":
                # Transcript level: extract transcript_id, inherit gene_id
                transcript_id = feature_id or attrs.get("transcript_id")
                gene_id = attrs.get("gene_id") or id_to_gene_id.get(parent_string)
                # Store for children
                if feature_id:
                    id_to_gene_id[feature_id] = gene_id
            else:
                # Exon/CDS/UTR level: inherit both gene_id and transcript_id from parent
                gene_id = id_to_gene_id.get(parent_string)
                # Transcript_id is the parent if parent is a transcript
                if parent_string:
                    # Check if parent is transcript-level
                    transcript_id = parent_string  # Simplified: assume direct parent is transcript

            annotation_gene_records.append({
                "annotation_id": annotation_id_counter,
                "feature_kind": feature_kind,
                "gene_id": gene_id,
                "transcript_id": transcript_id,
                "parent_id": parent_annotation_id,
                "biotype": biotype,
                "phase": phase,
            })

        # Create annotation_span records for ALL annotations
        for span_order, seg in enumerate(segments):
            annotation_span_records.append({
                "id": span_id_counter,
                "annotation_id": annotation_id_counter,
                "segment_id": seg["segment_id"],
                "coordinate": f"[{seg['segment_start']},{seg['segment_end']})",
                "span_order": span_order,
            })
            span_id_counter += 1

        # Store ID mapping for parent resolution
        if feature_id:
            id_string_to_annotation_id[feature_id] = annotation_id_counter

        annotation_id_counter += 1

    if not annotation_records:
        return 0

    # Step 4: Bulk insert using pandas + COPY
    df_annotation = pd.DataFrame(annotation_records)
    df_span = pd.DataFrame(annotation_span_records)

    # Convert JSONB attributes to string for COPY
    df_annotation["attributes"] = df_annotation["attributes"].apply(
        lambda x: pd.io.json.dumps(x) if x else None
    )

    # Insert annotations
    db.copy_from_df(
        connection,
        df_annotation,
        "annotation",
        columns=[
            "id",
            "subgraph_id",
            "path_id",
            "coordinate",
            "type",
            "label",
            "strand",
            "source",
            "score",
            "attributes",
            "genome_id",
        ],
    )

    # Insert annotation_gene records
    if annotation_gene_records:
        df_gene = pd.DataFrame(annotation_gene_records)
        db.copy_from_df(
            connection,
            df_gene,
            "annotation_gene",
            columns=["annotation_id", "feature_kind", "gene_id", "transcript_id", "parent_id", "biotype", "phase"],
        )

    # Insert annotation_spans
    db.copy_from_df(
        connection,
        df_span,
        "annotation_span",
        columns=["id", "annotation_id", "segment_id", "coordinate", "span_order"],
    )

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
    "--hap",
    type=str,
    help="HAP name (optional)",
)
@click.option(
    "--path",
    type=str,
    required=True,
    help="Path name (required)",
)
@click.option(
    "--subgraph",
    type=int,
    help="Subgraph ID (optional)",
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
    hap: Optional[str],
    path: str,
    subgraph: Optional[int],
    file: str,
    format: Optional[str],
):
    """Import annotations from GFF3/GTF/BED file.

    Per plan.freeze.json: Add annotations to a specific path.
    Annotations are mapped from path coordinates to segment coordinates.

    Example:
        hap annotation add --path chr1 --file annotations.gff3
    """
    # Auto-detect format if not specified
    if not format:
        format = detect_annotation_format(file)
        click.echo(f"Auto-detected format: {format}")

    # Get database connection
    conn = db.get_connection()

    try:
        num_imported = import_annotations(
            connection=conn,
            filepath=file,
            format_type=format.lower(),
            hap_name=hap,
            path_name=path,
            subgraph_id=subgraph,
        )
        click.echo(f"Successfully imported {num_imported} annotations")
    except Exception as e:
        conn.rollback()
        click.echo(f"Error importing annotations: {e}", err=True)
        raise
    finally:
        conn.close()


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
    conn = db.get_connection()

    try:
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

    finally:
        conn.close()


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

    conn = db.get_connection()

    try:
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
    finally:
        conn.close()


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
    conn = db.get_connection()

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
    finally:
        conn.close()


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

    conn = db.get_connection()

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

    finally:
        conn.close()
