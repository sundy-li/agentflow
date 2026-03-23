# Workspace And Worker Logging Design

**Goal:** Allow each repo to specify an absolute workspace directory for Codex execution, and add minimal worker logs that show which task is being processed.

## Decisions

- Add `repos[].workspace` as an optional absolute path.
- `CodexRunner` will run the `codex` subprocess with `cwd=workspace` when the field is present.
- If `workspace` is absent, Codex keeps the current process working directory behavior.
- Add standard-library `logging` to `WorkerService` with concise `INFO` messages for claimed and executing tasks.

## Logging Scope

- Log when a task is claimed:
- worker id
- repo
- task id
- issue/pr number
- state
- title
- Log before running implement/review/fix
- Log Codex result summary after each run

## Validation

- Repo config accepts optional absolute workspace path
- Codex subprocess receives the workspace path as `cwd`
- Worker logs include the task identifier and mode
