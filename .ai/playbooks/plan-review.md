# /plan-review "<slug>"
Do a focused gate review of the plan against our rubrics, but return only MUST-FIX / SHOULD / QUESTIONS (short).

## Inputs
- <slug>

## Behavior
- Read `plan.onepager.md`, `plan.freeze.json`, original `requirements.md`.
- Score internally but only *print*:
  - MUST-FIX: (blocking, list 1–7 items max, with precise fix hints)
  - SHOULD: (non-blocking)
  - QUESTIONS: (clarifications)
- If MUST-FIX>0: patch `audit.md` and propose concrete edits (file+line anchors).
- If MUST-FIX==0: print next step `/plan-freeze "<slug>"`.

## Don’ts
- No essay. No boilerplate. No restatement of requirements.
