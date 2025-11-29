# Agent Brief — hap (backend)

## Mission
You are the backend CLI + data ingestion program for the HAP model.
- Input: pangenome graph formats (currently GFA; vg/odgi can be added later).
- Output: a **HAP** (hierarchical pangenome) persisted in **PostgreSQL** with tables for `pangenome`, `subgraph`, `region`, `segment`, `annotation`, sequence bundles, and mapping/meta tables.
- Downstream: **Haprose (SvelteKit)** reads this **same PostgreSQL** directly **inside its server-side API endpoints**.

## Ground Truth (short)
- Use the HAP model exactly as designed: **Region–Segment Tree (RST)** with wrapper segments for nested variation levels and stable multi-zoom indexing.
- The **database is the single source of truth** once built/imported. `hap` mutates DB; Haprose performs **read-only queries** from its own server runtime.
- Ingestion must be **idempotent** and **resumable** for large datasets.

## What You May/May Not Do
- ✅ Add/modify CLI commands under `src/hap/commands/` (e.g., `build`, `sequence`, `annotate`) and their `lib/*` helpers.
- ✅ Write migrations/SQL (`sql/`) if schema expands; keep **backward compatible** when possible.
- ✅ Add tests in `tests/`; wire `nox` sessions; update docs when CLI flags or schema change.
- ❌ Do not bypass the schema; all persistence must be schema-compliant.

## I/O Contracts (essentials)
- Input GFA: streaming parse; validate nodes/edges/paths; collect path→genome names.
- Construct HAP:
  - Build `subgraph` partitions (e.g., connected components or chromosome splits).
  - Emit multi-level RST (wrapper segments created by scale thresholds).
  - Optionally map annotations to `segment` coordinates.
- Persist:
  - Bulk insert, deduplicate by natural keys, maintain referential integrity.
  - Record build metadata/version; **rebuild-safe** by `pangenome.version` / `build_id`.

## Quality Bars
- `ruff`, `mypy` (strict in lib), `pytest -q` must pass.
- `bandit -q` clean (or justified).
- Performance: streaming parse + batched writes; avoid O(N^2).

## Commit/PR Rules (short)
- Conventional commits; small atomic changes; tests/docs updated; `nox -s all` green.
