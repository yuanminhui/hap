# Audit: HAP Annotation Attachment & Manipulation

## MUST-FIX
<!-- Critical issues that must be addressed -->

**None** - All must-fix items have been addressed.

## SHOULD

### RESOLVED

1. **~~Missing PRD.md reference~~** - RESOLVED
   - **Suggestion #1**: Redesign based on annotation type, not file format
   - **Action**: Schema redesigned with type-specific tables (annotation_gene, annotation_repeat, annotation_regulatory, annotation_variant)

2. **~~Annotation.source field ambiguity~~** - RESOLVED
   - **Suggestion #6**: "Annotation中的source项如果指的是注释的提供来源（文献/研究/工具/批次等），则无需重命名"
   - **Action**: Removed source field from annotation table; annotation provenance in attributes JSONB

3. **~~Path generation integration point unclear~~** - RESOLVED
   - **Suggestion #2**: Validate path lines exist in GFA, validate annotation path names in HAP
   - **Action**: Clarified in phase 2 tasks - path validation at build, path name validation at annotation import

4. **~~Missing code rename tasks~~** - RESOLVED
   - **Suggestion #1, #4**: Update Python code for source→genome rename
   - **Action**: Added task "Create Python code update script for source→genome rename (grep all .py files)"

5. **~~Query filter "level" not mapped~~** - RESOLVED
   - **Suggestion #7**: "去除level项的筛选"
   - **Action**: Removed --level from annotation get filters

6. **~~ID generation strategy not specified~~** - RESOLVED
   - **Suggestion #8**: "采取同样的方式" (batch pre-generation)
   - **Action**: Added task "Use batch ID pre-generation pattern: get_next_id_from_table() + range()"

## QUESTIONS

### RESOLVED

1. **~~Existing annotation table~~** - RESOLVED
   - **Suggestion #9**: "直接修改create_tables.sql中的表设计即可，无需drop/create"
   - **Action**: Updated task to "Update src/sql/create_tables.sql directly (no drop/create migration)"

2. **~~Path uniqueness~~** - RESOLVED
   - **Suggestion #10**: "Path至少在subraph中唯一，可能在整个泛基因组即hap中唯一"
   - **Action**: Added UNIQUE constraint: path(subgraph_id, name)

3. **~~Annotation coordinates~~** - RESOLVED
   - **Suggestion #11**: "需要统一0-based和1-based坐标系为0-based（需要与现有segment坐标系一致）"
   - **Action**: Convert GFF3/GTF 1-based → internal 0-based; convert back on export

4. **~~Segment_original_id mapping~~** - RESOLVED
   - **Suggestion #12**: "对于正常结点，理应具有segement_original_id，只有在build时生成的wrapper segment和deletion segment没有该属性"
   - **Action**: Added validation task "Verify segment_original_id exists for normal segments (wrapper/deletion excluded)"

## REMAINING ITEMS

**None** - All audit items have been resolved through suggestions.md
