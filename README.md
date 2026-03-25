# agentflow

Label-driven GitHub agent orchestration service.
[中文](./AGENTFLOW_ZH.md)

## What It Does

- Polls one configured GitHub repo using `gh` CLI
- Syncs `agent-issue`, `agent-reviewable`, and `agent-changed` tasks into SQLite
- Runs local coding agent CLIs via PTY for implement/review/fix workflows
- Writes lifecycle transitions and execution runs to DB
- Exposes FastAPI board:
- `GET /board`
- `GET /api/board`
- `GET /api/tasks/{id}/events`

## State Lifecycle

- `agent-issue -> agent-reviewable`
- `agent-reviewable -> agent-approved`
- `agent-reviewable -> agent-changed`
- `agent-changed -> agent-reviewable`

## Quick Start

1. Install dependencies with `uv`:

```bash
uv sync --dev
```

2. Create config:

```bash
mkdir -p config
cp config/agentflow.example.yaml config/agentflow.yaml
```

`repos` supports:
- `full_name`: upstream repo (for example `sundy-li/agentflow`)
- `forked`: fork repo used for push (for example `your-user/agentflow`)
- `default_branch`: PR target branch (default `main`)

Coding agent config supports:
- `coding_agents`: named agent profiles
- `task_agents`: per-mode routing for `implement`, `fix`, and `review`
- legacy `codex:` remains supported as the fallback default profile

Supported agent kinds:
- `codex`
- `claude_code`
- `opencode`

3. Run service:

```bash
AGENTFLOW_CONFIG=config/agentflow.yaml uv run uvicorn app.main:create_app --factory --port 8000
```

Local CLI board:

```bash
uv run python -m app.cli board --config config/agentflow.yaml
```

4. Open:
- `http://127.0.0.1:8000/healthz`
- `http://127.0.0.1:8000/board`

## Notes

- `gh` must already be authenticated (`gh auth status`).
- At least one configured coding agent command must be available in `PATH`.
- Run logs are written into `run_logs_dir`.

## Test

```bash
uv run pytest -v
```
