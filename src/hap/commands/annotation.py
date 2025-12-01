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


# ===== Click Command Group =====


@click.group()
def annotation():
    """Manage annotations in HAP."""
    pass


# Placeholder for future subcommands (add, get, edit, delete, export)
# Will be implemented in Phase 5-6
