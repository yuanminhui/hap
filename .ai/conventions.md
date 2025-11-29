# Conventions

## Language/Style
- Python ≥3.10; prefer `dataclasses`/`pydantic` (v2) for I/O models.
- Functional core, imperative shell for CLI; isolate DB writes.

## Errors & Logging
- Raise typed exceptions in `hap.lib.error`.
- CLI prints human messages; logs use `structlog` (json) at INFO+, disable in tests.

## Commits & Branches
- `feat:`, `fix:`, `build:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Feature branches: `feat/<area>-<slug>`. PR < 400 lines diff.

## Testing
- Unit for pure functions (parsers, mappers).
- Integration for DB (mark `@pytest.mark.db`): uses ephemeral schema `hap_test_<uuid>`.
- Golden tests for GFA→HAP (mini fixtures).
