# Slash-like Commands (for Chat)

- /task-open "<slug>"
- /plan-review "<slug>"
- /start-task "<slug>"
  -> create feature branch, scaffold tests, run nox sessions
- /fix "<short>"
  -> propose minimal patch set for failing tests
- /check
  -> run: nox -s lint,type,tests  (explain failing logs tersely)
- /pack
  -> build wheel, export dist/, write RELEASE_NOTES.md delta
