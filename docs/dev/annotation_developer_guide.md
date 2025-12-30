# HAP Annotation System - Developer Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Schema](#database-schema)
3. [Code Structure](#code-structure)
4. [API Reference](#api-reference)
5. [Coordinate System](#coordinate-system)
6. [Testing Guide](#testing-guide)
7. [Contributing](#contributing)

## Architecture Overview

### High-Level Architecture

```
┌─────────────────┐
│  CLI Commands   │ (annotation.py)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   Parser Layer  │ (GFF3Parser, GTFParser, BEDParser)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Mapper Layer   │ (AnnotationMapper)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   Database      │ (PostgreSQL)
└─────────────────┘
```

### Key Design Principles

1. **Coordinate System Abstraction**: Internal 0-based, auto-convert at boundaries
2. **seqid Resolution**: seqid + genome → unique path
3. **Batch Operations**: ID pre-generation for efficient bulk inserts
4. **Format Agnostic**: Unified internal representation

## Database Schema

### Core Tables

#### genome
```sql
CREATE TABLE genome (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(30) NOT NULL,                    -- Sample name
  haplotype_index SMALLINT NOT NULL DEFAULT 0,  -- Haplotype index
  haplotype_origin VARCHAR(10) CHECK(
    haplotype_origin IN ('provided', 'parsed', 'assumed')
  ),
  description TEXT,
  clade_id INTEGER REFERENCES clade(id),
  UNIQUE(name, haplotype_index)
);
```

**Key Concepts**:
- `(name, haplotype_index)` is the natural key
- `haplotype_origin` tracks data provenance
- Multiple haplotypes per sample supported

#### path
```sql
CREATE TABLE path (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name VARCHAR(100) NOT NULL,           -- PanSN format: sample#hap#seq
  genome_id INTEGER NOT NULL REFERENCES genome(id),
  subgraph_id INTEGER NOT NULL REFERENCES subgraph(id),
  UNIQUE(subgraph_id, name)
);
```

**Key Concepts**:
- `name` follows PanSN: "sample#haplotype#sequence"
- Unique per subgraph (same name can exist in different subgraphs)
- Links genome to subgraph

#### annotation
```sql
CREATE TABLE annotation (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  subgraph_id INTEGER NOT NULL REFERENCES subgraph(id),
  path_id INTEGER NOT NULL REFERENCES path(id),
  coordinate INT8RANGE NOT NULL,        -- 0-based, half-open [start, end)
  type VARCHAR(50) NOT NULL,
  label VARCHAR(100),
  strand CHAR(1) CHECK(strand IN ('+', '-', '.')),
  source VARCHAR(50),
  score REAL,
  attributes JSONB,
  genome_id INTEGER NOT NULL REFERENCES genome(id),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_annotation_type ON annotation(type);
CREATE INDEX idx_annotation_label ON annotation(label);
CREATE INDEX idx_annotation_path ON annotation(path_id);
CREATE INDEX idx_annotation_coordinate ON annotation USING GIST(coordinate);
```

**Key Concepts**:
- `coordinate` is INT8RANGE for efficient range queries
- `attributes` stores format-specific data as JSON
- Indexed for common query patterns

#### annotation_span
```sql
CREATE TABLE annotation_span (
  id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  annotation_id INTEGER NOT NULL REFERENCES annotation(id) ON DELETE CASCADE,
  segment_id INTEGER NOT NULL REFERENCES segment(id),
  coordinate INT4RANGE NOT NULL,        -- Segment-local coordinates
  span_order SMALLINT NOT NULL,         -- Order within annotation
  UNIQUE(annotation_id, span_order)
);

CREATE INDEX idx_annotation_span_annotation ON annotation_span(annotation_id);
CREATE INDEX idx_annotation_span_segment ON annotation_span(segment_id);
```

**Key Concepts**:
- Maps annotations to segments
- `span_order` preserves feature order
- Enables multi-segment annotations

### Data Flow

```
GFF3/GTF/BED File
       ↓
    Parser
       ↓
  {seqid, start, end, ...}  (1-based or 0-based)
       ↓
 Coordinate Converter
       ↓
  {seqid, start, end, ...}  (0-based, half-open)
       ↓
  Path Resolver (seqid + genome → path_id)
       ↓
 Annotation Mapper (path coords → segment coords)
       ↓
Database: annotation + annotation_span
```

## Code Structure

### File Organization

```
src/hap/commands/annotation.py
├── Parsers
│   ├── GFF3Parser
│   ├── GTFParser
│   └── BEDParser
├── Coordinate Mapping
│   └── AnnotationMapper
├── Core Functions
│   ├── import_annotations()
│   ├── query_annotations()
│   ├── format_annotations()
│   └── _import_to_single_path_helper()
└── CLI Commands
    ├── add_annotation()
    ├── get_annotation()
    ├── edit_annotation()
    ├── delete_annotation()
    └── export_annotation()
```

### Key Classes

#### GFF3Parser

```python
class GFF3Parser:
    @staticmethod
    def parse(filepath: str) -> list[dict]:
        """Parse GFF3 file, convert 1-based → 0-based."""
        # Returns: [{
        #   'seqid': str,
        #   'start': int,     # 0-based
        #   'end': int,       # 0-based, exclusive
        #   'type': str,
        #   'strand': str,
        #   'score': float,
        #   'attributes': dict
        # }, ...]
```

**Coordinate Conversion**:
- Input: 1-based inclusive `[start, end]`
- Output: 0-based half-open `[start-1, end)`

#### AnnotationMapper

```python
class AnnotationMapper:
    def __init__(self, connection):
        self.connection = connection
        self.path_coords_cache = {}

    def preload_path_coordinates(self, path_id: int):
        """Cache path_segment_coordinate for a path."""

    def map_annotation_to_segments(
        self, path_id: int, start: int, end: int
    ) -> list[dict]:
        """Map path coordinates to segment coordinates."""
        # Returns: [{
        #   'segment_id': int,
        #   'segment_start': int,  # Local to segment
        #   'segment_end': int
        # }, ...]
```

**Mapping Algorithm**:
1. Load path_segment_coordinate for path
2. Find segments overlapping [start, end)
3. Calculate local coordinates within each segment
4. Return segment mapping list

## API Reference

### import_annotations()

```python
def import_annotations(
    connection: psycopg2.extensions.connection,
    filepath: str,
    format_type: str,
    genome_name: str,
    haplotype_index: Optional[int] = None,
    subgraph_name: Optional[str] = None,
) -> int:
    """Import annotations from file.

    Args:
        connection: Database connection
        filepath: Path to annotation file
        format_type: "gff3", "gtf", or "bed"
        genome_name: Genome name (required)
        haplotype_index: Haplotype index (optional, auto-selects if None)
        subgraph_name: Limit to specific subgraph (optional)

    Returns:
        Number of annotations imported

    Raises:
        DataInvalidError: If genome not found or path resolution fails
    """
```

**Usage Example**:
```python
from hap.lib import database as db
from hap.commands.annotation import import_annotations

with db.auto_connect() as conn:
    count = import_annotations(
        conn,
        "annotations.gff3",
        "gff3",
        genome_name="HG002",
        haplotype_index=1
    )
    print(f"Imported {count} annotations")
```

### query_annotations()

```python
def query_annotations(
    connection: psycopg2.extensions.connection,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Query annotations with filters.

    Args:
        connection: Database connection
        filters: Filter dictionary with keys:
            - id: int or list[int]
            - type: str
            - label: str (regex pattern)
            - path: str
            - subgraph: str
            - segment: str
            - range: str (format: "start-end")

    Returns:
        List of annotation dictionaries with keys:
            - id, path_name, start, end, type, label,
              strand, score, source, attributes
    """
```

**Usage Example**:
```python
from hap.commands.annotation import query_annotations

filters = {
    "type": "gene",
    "path": "HG002#1#chr1",
    "range": "100000-200000"
}

annotations = query_annotations(conn, filters)
for ann in annotations:
    print(f"{ann['label']}: {ann['start']}-{ann['end']}")
```

### format_annotations()

```python
def format_annotations(
    annotations: list[dict[str, Any]],
    format_type: str
) -> list[str]:
    """Format annotations for output.

    Args:
        annotations: List from query_annotations()
        format_type: "tsv", "gff3", "gtf", "bed", or "json"

    Returns:
        List of formatted output lines

    Note:
        GFF3/GTF automatically convert 0-based → 1-based
    """
```

## Coordinate System

### Internal Representation

HAP internally uses **0-based, half-open** coordinates `[start, end)`:

```
Sequence: A T C G A T C G
Position: 0 1 2 3 4 5 6 7
          ↑       ↑
      start=0   end=4

Feature covers: A T C G (positions 0, 1, 2, 3)
Coordinate: [0, 4)
Length: end - start = 4
```

### Conversion Rules

#### GFF3/GTF → Internal

```python
# Input (1-based inclusive): start=1000, end=2000
internal_start = gff_start - 1  # 999
internal_end = gff_end          # 2000
# Result: [999, 2000) covers same bases as [1000, 2000] in GFF3
```

#### Internal → GFF3/GTF

```python
# Internal: start=999, end=2000
gff_start = internal_start + 1  # 1000
gff_end = internal_end          # 2000
# Result: [1000, 2000] in GFF3
```

#### BED (no conversion needed)

```python
# BED is already 0-based, half-open
internal_start = bed_start
internal_end = bed_end
```

### Path-to-Segment Mapping

```
Path coordinates:         [100, 300)
                          ↓
Path-segment mapping:     seg1: [0, 150) → path [0, 150)
                          seg2: [0, 100) → path [150, 250)
                          seg3: [0, 50)  → path [250, 300)
                          ↓
Annotation [100, 300) spans:
  - seg1: local [100, 150)  (50 bases)
  - seg2: local [0, 100)    (100 bases)
  - seg3: local [0, 50)     (50 bases)

Total: 200 bases
```

## Testing Guide

### Unit Testing

Create tests in `tests/unit/test_annotation.py`:

```python
import pytest
from hap.commands.annotation import GFF3Parser

def test_gff3_coordinate_conversion():
    """Test 1-based → 0-based conversion."""
    # Create test GFF3 file
    with open("/tmp/test.gff3", "w") as f:
        f.write("##gff-version 3\n")
        f.write("chr1\ttest\tgene\t1000\t2000\t.\t+\t.\tID=test\n")

    # Parse
    result = GFF3Parser.parse("/tmp/test.gff3")

    assert len(result) == 1
    assert result[0]['start'] == 999   # 1-based → 0-based
    assert result[0]['end'] == 2000
    assert result[0]['type'] == 'gene'
```

### Integration Testing

Run the integration test suite:

```bash
# Full test suite
./tests/integration/test_annotation_system.sh

# Quick smoke test
./tests/integration/quick_test.sh
```

### Performance Testing

```python
import time
from hap.commands.annotation import import_annotations

def test_import_performance():
    """Test large file import."""
    start = time.time()

    with db.auto_connect() as conn:
        count = import_annotations(
            conn,
            "large_genome.gff3",
            "gff3",
            genome_name="HG002",
            haplotype_index=1
        )

    duration = time.time() - start
    rate = count / duration

    print(f"Imported {count} annotations in {duration:.2f}s")
    print(f"Rate: {rate:.0f} annotations/second")
```

### Database Testing

```sql
-- Test data integrity
SELECT COUNT(*) FROM annotation
WHERE path_id NOT IN (SELECT id FROM path);
-- Should return 0

-- Test coordinate consistency
SELECT id, coordinate, (coordinate).lower, (coordinate).upper
FROM annotation
WHERE (coordinate).lower >= (coordinate).upper;
-- Should return 0 rows

-- Test annotation_span integrity
SELECT a.id, COUNT(s.id) as span_count
FROM annotation a
LEFT JOIN annotation_span s ON a.id = s.annotation_id
GROUP BY a.id
HAVING COUNT(s.id) = 0;
-- Annotations should have at least one span
```

## Contributing

### Code Style

Follow the existing code style:
- Type hints for all function parameters and returns
- Docstrings in Google format
- Maximum line length: 88 characters (Black default)

### Adding New Format Support

To add a new annotation format:

1. **Create Parser Class**:
```python
class NewFormatParser:
    @staticmethod
    def parse(filepath: str) -> list[dict]:
        """Parse new format file."""
        annotations = []
        # Parse logic here
        return annotations
```

2. **Add to import_annotations()**:
```python
if format_type == "newformat":
    parsed_annotations = NewFormatParser.parse(filepath)
```

3. **Add to format_annotations()**:
```python
elif format_type == "newformat":
    # Format output
    return formatted_lines
```

4. **Add Tests**:
```python
def test_newformat_import():
    # Test implementation
```

### Submitting Changes

1. Create feature branch: `git checkout -b feature/new-feature`
2. Make changes and add tests
3. Run test suite: `./tests/integration/test_annotation_system.sh`
4. Commit with descriptive message
5. Push and create pull request

## Common Pitfalls

### 1. Coordinate System Confusion

❌ **Wrong**:
```python
# Treating internal coordinates as 1-based
gff_start = internal_start  # Missing conversion!
```

✅ **Correct**:
```python
gff_start = internal_start + 1  # Convert to 1-based
```

### 2. Missing Genome Specification

❌ **Wrong**:
```python
# Trying to import without genome
import_annotations(conn, "anno.gff3", "gff3")  # Missing genome_name!
```

✅ **Correct**:
```python
import_annotations(conn, "anno.gff3", "gff3", genome_name="HG002")
```

### 3. seqid vs path.name

❌ **Wrong**:
```python
# Using path.name in annotation file
# GFF3 file: seqid = "HG002#1#chr1"
```

✅ **Correct**:
```python
# Using subgraph.name in annotation file
# GFF3 file: seqid = "chr1"
# Then specify genome during import
```

## Debugging Tips

### Enable SQL Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Path Resolution

```sql
-- Find path for genome + subgraph
SELECT p.id, p.name, g.name as genome, s.name as subgraph
FROM path p
JOIN genome g ON p.genome_id = g.id
JOIN subgraph s ON p.subgraph_id = s.id
WHERE g.name = 'HG002'
  AND g.haplotype_index = 1
  AND s.name = 'chr1';
```

### Verify Coordinate Mapping

```sql
-- Check path_segment_coordinate
SELECT *
FROM path_segment_coordinate
WHERE path_id = (
  SELECT id FROM path WHERE name = 'HG002#1#chr1'
)
ORDER BY path_start;
```

### Trace Import Errors

```python
try:
    import_annotations(...)
except Exception as e:
    import traceback
    traceback.print_exc()
    # Check error message for details
```

## Resources

- **Main Documentation**: `docs/annotation_user_guide.md`
- **Schema**: `src/sql/create_tables.sql`
- **Examples**: `data/mini-example/`
- **Tests**: `tests/integration/`

---

**Version**: 1.0
**Last Updated**: 2025-12-29
