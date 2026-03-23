# AGENTS.md

This file defines project-level conventions for local coding agents working in this repository.

## Project Goal

Build and run a label-driven GitHub task agent:

- Poll GitHub issues/PRs by labels
- Execute implementation/review work via local `codex`
- Persist lifecycle state in SQLite
- Expose a FastAPI board for visibility

## Core Workflow

Task state lifecycle:

- `agent-issue -> agent-reviewable`
- `agent-reviewable -> agent-approved`
- `agent-reviewable -> agent-changed`
- `agent-changed -> agent-reviewable`

## Repository Configuration

Use `config/agentflow.yaml`:

- `repos[].full_name`: upstream repo (for example `sundy-li/agentflow`)
- `repos[].forked`: fork repo used for push
- `repos[].default_branch`: upstream PR target branch (default `main`)

When implementation/fix tasks create or update branches, push to `forked` and open/update PR against upstream `default_branch`.

## Local Development

Install deps:

```bash
uv sync --dev
```

Run tests:

```bash
uv run pytest -q
```

Run server:

```bash
AGENTFLOW_CONFIG=config/agentflow.yaml uv run uvicorn app.main:create_app --factory --reload
```

## Delivery Rules

- Keep changes minimal and test-backed.
- Do not hardcode repository names in business logic; use config.
- Prefer deterministic commands and avoid interactive tooling in automation.
- Use `main` as the default branch for pushes/PR base unless explicitly overridden.
