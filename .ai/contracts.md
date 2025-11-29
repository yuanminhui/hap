# Contracts (Minimal)

## Model
- HAP = RST (Region <-> Segment levels) with wrapper segments; multi-zoom index exists.
- Subgraph: fully connected component; one HAP has many subgraphs.
- Annotation mapped to segment(s) by internal coordinate.

## Ingestion Output (DB)
- Upsert pangenome/subgraph/region/segment/annotation with stable IDs.
- Store per-level scale thresholds used for wrapping.
- Build metadata (tool version, build_id, source files, timestamps).

## Non-Goals
- No UI rendering logic here.
- No HTTP endpoints here.
- No ad-hoc files as long-term storage (DB is truth).
