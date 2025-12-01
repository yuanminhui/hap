# Plan Changelog: HAP Annotation Attachment & Manipulation

**Task ID**: hap-annotation-attachment-manipulation
**Frozen**: 2025-11-30 22:31:19 UTC
**Status**: Ready for implementation

## Major Changes from Initial Draft to Freeze

### 1. Database Schema Redesign (Critical)

**Initial Design**:
- Format-based tables: `annotation_gff3_attributes`, `annotation_gtf_attributes`, `annotation_bed_attributes`
- Annotation table with path coordinates: `path_start`, `path_end`
- Missing coordinate range field

**Final Design**:
- **Type-based tables**: `annotation_gene`, `annotation_repeat`, `annotation_regulatory`, `annotation_variant`
- **Annotation table fields**:
  - `subgraph_id` (NOT NULL, FK to subgraph)
  - `path_id` (NOT NULL, FK to path)
  - `coordinate` (INT8RANGE NOT NULL) - path-level coordinates, 0-based
  - `type` (VARCHAR(50) NOT NULL)
  - `label` (VARCHAR(200))
  - `strand` (CHAR(1), CHECK('+', '-', '.'))
  - `attributes` (JSONB) - flexible storage for format-specific data
  - `genome_id` (INTEGER, FK to genome)
  - `created_at` (TIMESTAMP DEFAULT NOW())
- **Indexes**: GIST index on `coordinate` for range queries

**Rationale**: Type-based design aligns with annotation semantics (gene vs repeat) rather than file format (GFF3 vs GTF). Coordinate field uses INT8RANGE consistent with existing segment design.

---

### 2. Path Validation Scope Refinement

**Initial Design**:
- Validate path references exist in segments at build time

**Final Design**:
- **Build time**: Only validate path lines exist in GFA (P/W/O/U depending on version)
- **Import time**: Validate annotation file path names exist in target HAP

**Rationale**: Separation of concerns - GFA structural validation at build, annotation-specific validation at import.

---

### 3. Annotation Span Generation Policy

**Initial Design**:
- Generate `annotation_span` only for multi-segment annotations

**Final Design**:
- **Generate for ALL annotations** (single-segment and multi-segment)

**Rationale**: Consistency and simplification - uniform handling of all annotations regardless of segment count.

---

### 4. Implementation Location

**Initial Design**:
- Primary implementation in `src/hap/lib/annotation.py`
- Data classes in `src/hap/lib/elements.py`

**Final Design**:
- **Primary implementation**: `src/hap/commands/annotation.py`
- **Optional**: `src/hap/lib/annotation.py` for shared utilities only
- **No data classes** in elements.py unless necessary

**Rationale**: Follows existing codebase pattern (see `sequence.py` command structure).

---

### 5. Coordinate System Standardization

**Initial Design**:
- Unclear handling of 1-based (GFF3/GTF) vs 0-based coordinates

**Final Design**:
- **Internal storage**: All 0-based (consistent with segment coordinates)
- **GFF3/GTF import**: Convert 1-based → 0-based
- **GFF3/GTF export**: Convert 0-based → 1-based
- **BED**: Already 0-based, no conversion

**Rationale**: Unified internal representation matching existing segment coordinate system.

---

### 6. Query Interface Simplification

**Initial Design**:
- Filters: `--name`, `--level`, `--strand`, etc.

**Final Design**:
- **Removed**: `--level` (not in schema), `--strand` (stored but not filtered)
- **Renamed**: `--name` → `--label`
- **Retained**: `--id`, `--type`, `--segment`, `--path`, `--hap`, `--subgraph`, `--range`

**Rationale**: Align with actual annotation table fields; remove filters for fields that don't support meaningful queries.

---

### 7. ID Generation Strategy

**Initial Design**:
- Auto-increment or hash-based

**Final Design**:
- **Batch pre-generation**: `get_next_id_from_table() + range()` pattern

**Rationale**: Consistent with existing codebase pattern for bulk inserts.

---

### 8. Path Uniqueness Constraint

**Initial Design**:
- Unspecified

**Final Design**:
- **UNIQUE(subgraph_id, name)** constraint on path table

**Rationale**: Path names unique per subgraph (minimum); prevents duplicates while allowing flexibility.

---

### 9. Source→Genome Rename Scope

**Initial Design**:
- SQL schema changes only

**Final Design**:
- SQL schema changes
- **Python code updates**: Grep all .py files for `source` references and update

**Rationale**: Comprehensive rename across entire codebase for consistency.

---

### 10. Schema Migration Approach

**Initial Design**:
- Create migration script with DROP/CREATE

**Final Design**:
- **Direct modification** of `src/sql/create_tables.sql`

**Rationale**: Simplified approach for development phase; no existing production data to migrate.

---

## Key Decisions Finalized

1. **Annotation positioning**: Two-level coordinate system with range types
   - Path-level: `annotation.coordinate` (INT8RANGE, 0-based)
   - Segment-level: `annotation_span.coordinate` (INT4RANGE, 0-based)
   - Path-segment mapping: `path_segment_coordinate.coordinate` (INT8RANGE, 0-based)

2. **Type-specific tables**: Minimal essential fields only
   - `annotation_gene`: gene_id, transcript_id, biotype, phase, parent
   - `annotation_repeat`: repeat_class, family, subfamily
   - `annotation_regulatory`: regulatory_class, bound_moiety
   - `annotation_variant`: ref_allele, alt_allele, variant_type

3. **Coordinate conversion**: All GFF3/GTF 1-based → 0-based on import

4. **Span generation**: ALL annotations get spans (no special handling for single-segment)

5. **Path validation**: Existence check only at build; content validation at annotation import

---

## Validation Status

- ✅ All MUST-FIX items resolved (audit.md)
- ✅ All SHOULD items addressed (audit.md)
- ✅ All QUESTIONS answered (audit.md)
- ✅ Suggestions.md requirements incorporated (12/12)
- ✅ Database schema self-consistent
- ✅ Coordinate system unified (0-based internal)
- ✅ Implementation location clarified (commands/ primary)

---

## Next Steps

Execute `/start-impl "hap-annotation-attachment-manipulation"` to begin implementation.

**Estimated LOC**: ~2500-3000 lines
- Database schema: ~150 lines SQL
- GFA path validation: ~200 lines
- Annotation parsers (GFF3/GTF/BED): ~800 lines
- Coordinate mapping: ~400 lines
- CRUD commands: ~600 lines
- Test data: ~200 lines (annotations)
- Tests: ~500 lines

**Priority**: High (foundational feature for pangenome annotation support)
