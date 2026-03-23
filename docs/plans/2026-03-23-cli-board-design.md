# CLI Board Design

**Goal:** Provide a local CLI command that reads SQLite task state and prints a board-style task listing grouped by workflow state.

## Decisions

- Add a dedicated module entry point at `app/cli.py`.
- Read only local SQLite data; do not trigger GitHub sync.
- Default to the enabled repo from config.
- Show whether a task is currently executing by deriving a `running`/`idle` label from lock fields.

## Command Shape

- `uv run python -m app.cli board`
- Optional:
- `--config /path/to/agentflow.yaml`

## Output Shape

- Print repo name first.
- Print one section per state:
- `agent-issue`
- `agent-reviewable`
- `agent-changed`
- `agent-approved`
- Each section contains a plain-text table with fixed columns:
- `ID`
- `Type`
- `#`
- `Title`
- `Assignee`
- `Stale`
- `Locked`
- `Updated`

## Behavior

- Empty state sections still render with `0 tasks`.
- Long titles are truncated for table readability.
- If no active repo is configured, CLI exits with a non-zero code and a clear message.

## Test Coverage

- board output includes grouped task sections
- locked tasks render as `running`
- `--config` is honored
