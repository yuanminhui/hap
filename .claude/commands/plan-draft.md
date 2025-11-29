# /plan-draft "<slug>"
Read the frozen requirements and produce a *concrete, feasible* plan draft.

## Inputs
- <slug>

## Behavior
1) Read:
   - `internal/_generated/tasks/*-<slug>/requirements.md` (frozen copy)
   - `internal/playbooks/plan-<slug>.md` (source of truth)
2) Produce:
   - `internal/_generated/tasks/*-<slug>/plan.onepager.md`
     (goals & non-goals, DoD, scope, interfaces, data flow, risks, rollout)
   - `internal/_generated/tasks/*-<slug>/plan.freeze.json`
     (stable machine-readable spec; no TODOs; no “maybe”)
3) The plan must be executable, with *exact* file paths, db touch points, CLI flags, testable invariants.

## Don’ts
- Don’t contradict the requirements.
- Don’t leave placeholders; propose defaults with justification.

## Next
Return scorecard request: `/plan-review "<slug>"`
