# /start-impl "<slug>"
Start implementation *strictly* following `plan.freeze.json`.

## Behavior
- Create a feature branch: `feat/<slug>`
- For hap: restrict to CLI/ingestion code paths (`src/hap/commands/*`, `src/hap/lib/*`, `sql/*`, tests).
- No scope creep: refuse any change not in the freeze; if needed, open `/plan-change "<slug>"`.
- Generate minimal commits (Conventional Commits).
- First commit: scaffolds/tests & failing tests (“red”).
- Then: implementation; then green tests.

## Outputs
- Short checklist: tests, ruff/mypy/bandit, perf smoke (time/rows).
- Open a PR (or tell the exact git commands if no integration).
