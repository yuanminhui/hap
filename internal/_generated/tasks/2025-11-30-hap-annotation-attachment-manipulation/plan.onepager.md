# One-Page Plan: HAP Annotation Attachment & Manipulation

## Overview

Implement comprehensive annotation support for HAP (Hierarchical Pangenome) toolkit, including database schema design, GFA path validation, annotation file parsing (GFF3, GTF, BED), coordinate mapping through path-segment relationships, and full CRUD operations via a new `annotation` command.

## Goals

1. **Database Schema**: Design and implement complete annotation data model
   - Rename `source` table to `genome` across codebase
   - Create `path` table for genome paths from GFA W/P lines
   - Create `path_segment_coordinate` table for path-to-segment mapping
   - Redesign `annotation` table with core fields (subgraph_id, path_id, coordinate INT8RANGE, type, label, strand, attributes JSONB, genome_id, created_at)
   - Create type-specific annotation tables (annotation_gene, annotation_repeat, annotation_regulatory, annotation_variant)
   - Create `annotation_span` table for ALL annotations (annotation-to-segment many-to-many, coordinate INT4RANGE on segment)

2. **GFA Path Validation**: Extend build command with path validation
   - Validate path lines exist in GFA (P/W for GFA 1.x, O/U for GFA 2.x)
   - When importing annotations: validate path names in annotation files exist in target HAP
   - Validate path format and content correctness
   - Generate `path_segment_coordinate` during build process

3. **Annotation Import**: Implement annotation file parsing and import
   - Support GFF3, GTF, BED formats
   - Parse common and format-specific fields
   - Convert coordinates: GFF3/GTF (1-based) → internal (0-based); BED already 0-based
   - Map genomic coordinates to segment-based coordinates via `path_segment_coordinate`
   - Generate `annotation_span` for ALL annotations (single or multi-segment)
   - Support import during build (`--annotations` flag) and post-build (`annotation add`)

4. **Annotation Command**: Implement comprehensive annotation management CLI
   - Add: Import annotations from files with validation
   - Get/Query: Filter by name/id, type, segment, path/genome, hap, subgraph, range
   - Edit: Update annotation properties
   - Delete: Remove annotations by filters
   - Export: Output annotations in various formats (convert 0-based back to 1-based for GFF3/GTF)

5. **Test Data**: Create realistic mock annotation data for `new-mini-example.gfa`
   - Cover multiple annotation types (gene, CDS, exon, mRNA, etc.)
   - Include multiple formats (GFF3, GTF, BED)
   - Reflect realistic pangenome annotation patterns

## Non-Goals

- Annotation visualization (out of scope for this iteration)
- Annotation analysis tools (e.g., variant effect prediction)
- Support for non-standard annotation formats beyond GFF3/GTF/BED
- Real-time annotation update/sync with external databases

## Definition of Done

- [ ] Database schema updated with all new tables and relationships
- [ ] All references to `source` renamed to `genome` throughout codebase
- [ ] GFA path validation integrated into build command with comprehensive tests
- [ ] Path-segment coordinate generation working for all GFA versions
- [ ] Annotation parsers implemented for GFF3, GTF, and BED formats
- [ ] `build` command accepts `--annotations` parameter
- [ ] `annotation` command fully functional with all subcommands
- [ ] Coordinate mapping from genome paths to segments working correctly
- [ ] Mock annotation data created for `new-mini-example.gfa`
- [ ] All unit tests passing
- [ ] Integration tests covering end-to-end workflows
- [ ] Documentation updated

## Key Components

### Database Schema Changes
- **File**: `src/sql/create_tables.sql`
- **Changes**: Rename source→genome (update Python code too), add path (UNIQUE per subgraph), path_segment_coordinate, redesign annotation (subgraph_id, path_id, coordinate INT8RANGE, type, label, strand, attributes JSONB, genome_id, created_at), add annotation_gene/repeat/regulatory/variant, add annotation_span (for ALL annotations)

### Core Library Modules
- **OPTIONAL**: `src/hap/lib/annotation.py` - Shared parsing utilities only (if needed)
- **MODIFY**: `src/hap/lib/gfa.py` - Add path validation methods
- **MODIFY**: `src/hap/lib/database.py` - Update for new schema
- **NO CHANGE**: `src/hap/lib/elements.py` - Do not add Path/Annotation classes unless necessary

### Commands
- **MODIFY**: `src/hap/commands/build.py` - Add --annotations parameter, path validation, path_segment_coordinate generation
- **NEW**: `src/hap/commands/annotation.py` - Full CRUD operations (PRIMARY implementation location, not lib)

### Test Data
- **NEW**: `data/mini-example/new-mini-example.annotations.gff3`
- **NEW**: `data/mini-example/new-mini-example.annotations.gtf`
- **NEW**: `data/mini-example/new-mini-example.annotations.bed`

## Implementation Steps

### Phase 1: Database Schema & Migration
1. Design annotation table: subgraph_id, path_id, coordinate (INT8RANGE), type, label, strand, attributes (JSONB), genome_id, created_at
2. Design type-specific tables: annotation_gene, annotation_repeat, annotation_regulatory, annotation_variant
3. Update `src/sql/create_tables.sql` directly (no drop/create migration)
4. Create Python code update script for source→genome rename
5. Add UNIQUE constraint: path(subgraph_id, name)
6. Update `src/hap/lib/database.py` for schema changes

### Phase 2: Path Validation & Extraction
1. Implement GFA path line existence validation (all versions: 1.0 P, 1.1/1.2 W, 2.0 O/U)
2. Do NOT validate segment associations at build time
3. Add path name validation for annotation imports (check path exists in HAP)
4. Add path parsing methods to `src/hap/lib/gfa.py`
5. Integrate validation into build command's `validate_gfa()`
6. Implement path_segment_coordinate generation in `build.py`
7. Test with sample GFA files including new-mini-example.gfa

### Phase 3: Annotation Parsing
1. Create `src/hap/commands/annotation.py` as primary implementation
2. Optionally create `src/hap/lib/annotation.py` for shared utilities only
3. Implement GFF3 parser with 1-based → 0-based coordinate conversion
4. Implement GTF parser with 1-based → 0-based coordinate conversion
5. Implement BED parser (already 0-based, no conversion needed)
6. Do NOT create Path/Annotation data classes unless necessary
7. Add unit tests for each parser with coordinate conversion tests

### Phase 4: Annotation Import & Coordinate Mapping
1. Implement coordinate mapping: annotation (path-based) → segment-based (via path_segment_coordinate)
2. Generate annotation_span records for ALL annotations (single and multi-segment)
3. Use batch ID pre-generation pattern: get_next_id_from_table() + range()
4. Add annotation import to build command (--annotations parameter)
5. Create `annotation add` subcommand for post-build import
6. Implement validation (check path/genome exists, coordinates valid)
7. Verify segment_original_id exists for normal segments (wrapper/deletion excluded)

### Phase 5: Annotation Query & CRUD
1. Implement `annotation get` with filtering (id, type, label, segment, path, hap, subgraph, range)
2. Remove level from query filters
3. Implement `annotation edit` for updating properties
4. Implement `annotation delete` with filters
5. Implement `annotation export` with 0-based → 1-based conversion for GFF3/GTF
6. Add comprehensive SQL queries with proper indexing

### Phase 6: Test Data & Documentation
1. Analyze new-mini-example.gfa graph structure
2. Create realistic mock annotations covering:
   - Genes, CDS, exons, mRNAs (GFF3/GTF)
   - Regulatory regions, repeats (BED)
   - Multi-segment features
   - Both strands
3. Document command usage and examples
4. Final integration testing

## Dependencies

### External Libraries
- Standard library only (no new dependencies)
- Use existing psycopg2 for database operations

### Internal Modules
- `src/hap/lib/gfa.py` - Extend with path validation
- `src/hap/lib/database.py` - Schema updates
- `src/hap/lib/elements.py` - No changes (don't add classes unless necessary)
- `src/hap/commands/build.py` - Add annotation import, update source→genome references
- `src/hap/commands/sequence.py` - Reference for command structure

### Data Files
- `data/mini-example/new-mini-example.gfa` - Base for test annotations

## Testing Strategy

### Unit Tests
- GFA path line parsing (P, W, O, U lines for different versions)
- Path validation logic (segment existence, format correctness)
- Annotation file parsers (GFF3, GTF, BED)
- Coordinate mapping algorithms (path→segment, single/multi-segment)
- Database query filters
- Data class serialization

### Integration Tests
- End-to-end: build with --annotations
- Post-build: annotation add to existing HAP
- Query with complex filters (range overlap, regex, multi-level)
- Export and re-import (format round-trip)
- Multi-segment annotation spanning

### Test Coverage
- All GFA versions (1.0, 1.1, 1.2, 2.0)
- All annotation formats (GFF3, GTF, BED3-12) with coordinate conversion validation
- Coordinate systems: 1-based (GFF3/GTF) ↔ 0-based (internal) round-trip
- Edge cases: reverse strand, gaps, nested features, phase
- Error handling: invalid coordinates, missing paths, format errors

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Complex coordinate mapping across multi-segment annotations | High | Implement comprehensive unit tests, validate with known examples |
| GFA version variations (1.0/1.1/1.2/2.0 path formats) | Medium | Version-specific parsers, test each version |
| Large annotation files (GB-sized GFF3) | Medium | Streaming parsers, batch inserts, progress indicators |
| Database migration complexity (source→genome) | High | Thorough migration script, pre/post validation, test database |
| Annotation format ambiguities | Medium | Use standard parsers, document supported features, clear errors |

## Data Flow

### Annotation Import Flow
```
User Input (GFF3/GTF/BED file + target HAP/path)
  ↓
Parse file → extract common + format-specific fields
  ↓
Validate: path/genome exists, coordinates within range
  ↓
For each annotation:
  Query path_segment_coordinate for genomic range
  → Map to segments (may span multiple)
  → Calculate segment-local coordinates
  → Generate annotation_span records
  ↓
Insert: annotation → format_attributes → annotation_span
  ↓
Return import summary (counts, errors)
```

### Annotation Query Flow
```
User filters (id, name, segment, path, range, level)
  ↓
Build SQL with JOINs:
  annotation ← annotation_span → segment → path_segment_coordinate → path
  ↓
Apply filters (coordinate overlap, level range, regex)
  ↓
Format output (TSV, GFF3, GTF, BED, JSON)
```

## Open Questions & Decisions

1. **Path naming**: Follow PanSN strictly or allow arbitrary names?
   - **Decision**: Allow flexibility; enforce UNIQUE per subgraph (minimum)

2. **Annotation IDs**: Auto-increment, hash, or user-provided?
   - **Decision**: Batch pre-generation using get_next_id_from_table() + range() pattern

3. **Multi-path annotations**: Support spanning multiple paths?
   - **Decision**: Not in v1; separate annotation per path

4. **Hierarchical features** (gene→transcript→exon): JSONB or tables?
   - **Decision**: JSONB in attributes; type-specific tables for common fields

5. **Versioning**: Track annotation updates?
   - **Decision**: Add created_at only (no full versioning in v1)

6. **Coordinate system**: GFF3/GTF 1-based vs internal 0-based
   - **Decision**: Convert to 0-based on import; convert back on GFF3/GTF export

---

**PLAN FROZEN**: 2025-11-30 22:31:19 UTC

This plan is now immutable. All design decisions finalized based on requirements and suggestions.md feedback.
