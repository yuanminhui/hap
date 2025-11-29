# Code Review Rubric

- API/CLI: args validated; help text clear; idempotent behavior documented.
- Data Model: conforms to HAP; wrapper-level math deterministic; no silent drops.
- DB Access: batched IO; parameterized SQL; indexes in place; transactions narrow.
- Perf: streaming parse (GFA); memory bound known; O(N) or O(N log N) only.
- Test: unit & integration meaningful; fixtures small but realistic; ensures replay.
- Docs: README/CHANGELOG updated; migration explained.
