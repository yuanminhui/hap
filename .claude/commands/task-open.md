# /task-open "<slug>"
Create a task from a full requirements document, persist it, and scaffold planning files.

## Inputs
- <slug>: short id, kebab-case.
- A *requirements* block pasted by the user.

## What to do
1) Persist user-provided full requirements as:
   - `internal/playbooks/plan-<slug>.md` (raw source of truth)
   - `internal/_generated/tasks/<YYYY-MM-DD>-<slug>/requirements.md` (frozen copy)

2) Write tiny stubs to the same task folder:
   - `plan.onepager.md`   (empty skeleton)
   - `plan.freeze.json`   (empty skeleton with fields)
   - `audit.md`           (empty skeleton with MUST-FIX / SHOULD / QUESTIONS placeholders)
   - `trace.md`           (to append decisions/links)

3) Return the path list and *next commands* to run.

## Constraints
- Do *not* paraphrase or shorten the requirements.
- If no block provided, ask the user to paste one.

## Output schema (in the Chat)
- Print the created file paths.
- Print the next command: `/plan-draft "<slug>"`