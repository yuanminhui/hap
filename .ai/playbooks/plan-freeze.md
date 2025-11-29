# /plan-freeze "<slug>"
Freeze the plan; stamp it immutable; produce a short CHANGELOG note.

## Behavior
- Validate no MUST-FIX remain in `audit.md`.
- Freeze `plan.onepager.md` and `plan.freeze.json` (append a frozen banner + datetime).
- Generate `CHANGELOG.plan.md` in the same task folder (what changed during draft→freeze).

## Next
Print `/start-impl "<slug>"`
