# Agentflow V1 (Single Repo) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python service that polls one GitHub repo, syncs label-driven issue/PR tasks into SQLite, runs local `codex` via bash PTY for implementation/review, and exposes a FastAPI board UI.

**Architecture:** A polling sync loop keeps GitHub labels and local DB state consistent. A scheduler picks runnable tasks from SQLite, dispatches `codex` jobs, and applies state transitions through a strict state machine. FastAPI serves both JSON APIs and a lightweight board page showing task columns and lifecycle history.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLite (`sqlite3`), Pydantic v2 (`pydantic-settings`), APScheduler, Jinja2 (templates), pytest.

## Scope (v1)

- Single GitHub repository (config supports list, only first enabled repo is processed)
- Label-driven lifecycle:
- `agent-issue` -> `agent-reviewable`
- `agent-reviewable` -> `agent-approved` (review pass)
- `agent-reviewable` -> `agent-changed` (review fail)
- `agent-changed` -> `agent-reviewable` (agent fixes)
- Use local `codex` command via PTY; no external LLM provider
- SQLite as source of truth for runtime status + event timeline
- FastAPI web board for status visibility

## Task 1: Project Scaffold + Health API

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/config.py`
- Create: `tests/smoke/test_health_api.py`

**Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_check():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/smoke/test_health_api.py -v`  
Expected: FAIL with import/module errors.

**Step 3: Write minimal implementation**

```python
from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(title="agentflow")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/smoke/test_health_api.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml app/ tests/smoke/test_health_api.py
git commit -m "chore: scaffold FastAPI app with health endpoint"
```

## Task 2: SQLite Schema + Data Access Layer

**Files:**
- Create: `migrations/001_init.sql`
- Create: `app/db.py`
- Create: `app/repository.py`
- Create: `tests/unit/test_repository.py`

**Step 1: Write the failing test**

Test should assert:
- DB initialization creates tables: `repos`, `tasks`, `task_events`, `runs`
- `upsert_task()` inserts then updates same `(repo_id, github_type, github_number)`
- `insert_task_event()` writes lifecycle records

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_repository.py -v`  
Expected: FAIL (missing DB layer).

**Step 3: Write minimal implementation**

- `migrations/001_init.sql` defines:
- `repos(id, name, full_name, enabled, created_at, updated_at)`
- `tasks(id, repo_id, github_type, github_number, title, url, labels_json, state, assignee, last_synced_at, locked_by, locked_until, created_at, updated_at, UNIQUE(repo_id, github_type, github_number))`
- `task_events(id, task_id, from_state, to_state, reason, actor, source, run_id, created_at)`
- `runs(id, task_id, run_type, prompt, command, exit_code, output_path, started_at, finished_at, created_at)`

- `app/db.py`: connection factory + migration runner.
- `app/repository.py`: CRUD/upsert methods used by services.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_repository.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add migrations/001_init.sql app/db.py app/repository.py tests/unit/test_repository.py
git commit -m "feat: add sqlite schema and repository layer"
```

## Task 3: Domain State Machine

**Files:**
- Create: `app/domain/state_machine.py`
- Create: `tests/unit/test_state_machine.py`

**Step 1: Write the failing test**

Cover allowed transitions:
- `agent-issue -> agent-reviewable`
- `agent-reviewable -> agent-approved`
- `agent-reviewable -> agent-changed`
- `agent-changed -> agent-reviewable`

Cover rejected transitions:
- `agent-issue -> agent-approved`
- `agent-approved -> agent-reviewable`

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_state_machine.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- Implement `TaskState` enum with canonical label values.
- Implement `can_transition(from_state, to_state) -> bool`.
- Implement `assert_transition(...)` raising `InvalidTransitionError`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_state_machine.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/domain/state_machine.py tests/unit/test_state_machine.py
git commit -m "feat: implement label lifecycle state machine"
```

## Task 4: GitHub `gh` Adapter (Read + Label Write)

**Files:**
- Create: `app/services/gh_client.py`
- Create: `tests/unit/test_gh_client.py`

**Step 1: Write the failing test**

Use monkeypatch for `subprocess.run` and validate:
- list issues command includes `gh issue list --label agent-issue`
- list PR command includes both `agent-reviewable` and `agent-changed`
- label update command uses `gh issue edit` or `gh pr edit` with add/remove labels

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_gh_client.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- `list_agent_issues(repo_full_name) -> list[dict]`
- `list_agent_prs(repo_full_name) -> list[dict]`
- `set_labels(repo_full_name, item_type, number, add_labels, remove_labels)`
- parse `--json` output deterministically

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_gh_client.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/gh_client.py tests/unit/test_gh_client.py
git commit -m "feat: add gh command adapter for issues and prs"
```

## Task 5: Sync Service (GitHub -> SQLite Consistency)

**Files:**
- Create: `app/services/sync_service.py`
- Create: `tests/unit/test_sync_service.py`

**Step 1: Write the failing test**

Test scenarios:
- New GitHub issue/PR appears -> inserted into `tasks`
- GitHub label changed -> local state updated via state machine
- Task missing on GitHub list -> remains but marked stale (not deleted)
- Event record inserted when state changes

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_sync_service.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- `sync_once(repo_config)`:
- fetch issues with `agent-issue`
- fetch PRs with `agent-reviewable` + `agent-changed`
- upsert tasks
- map labels -> canonical state
- write `task_events` when state diff detected

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_sync_service.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/sync_service.py tests/unit/test_sync_service.py
git commit -m "feat: sync github label tasks to sqlite"
```

## Task 6: PTY Codex Runner + Run Records

**Files:**
- Create: `app/services/codex_runner.py`
- Create: `tests/unit/test_codex_runner.py`

**Step 1: Write the failing test**

Cover:
- command built from config (`codex.command`, `codex.args`)
- PTY execution captures stdout/stderr to log file
- non-zero exit code is preserved
- `runs` table row created with `started_at`, `finished_at`, `exit_code`

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_codex_runner.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- `run_codex(task, mode)` where `mode in {"implement", "review", "fix"}`
- use `pty.openpty()` + `subprocess.Popen(...)`
- stream output to `data/runs/<run_id>.log`
- persist metadata in `runs`

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_codex_runner.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/codex_runner.py tests/unit/test_codex_runner.py
git commit -m "feat: add codex pty runner with persisted run logs"
```

## Task 7: Worker Orchestration + Label Transition Writing

**Files:**
- Create: `app/services/worker_service.py`
- Create: `tests/integration/test_worker_transitions.py`

**Step 1: Write the failing test**

Scenario A (`agent-issue`):
- pick runnable issue
- run codex implement
- on success: set GitHub label to `agent-reviewable`, update DB state + event

Scenario B (`agent-reviewable`):
- run codex review
- review pass -> `agent-approved`
- review fail -> `agent-changed`

Scenario C (`agent-changed`):
- run codex fix
- success -> `agent-reviewable`

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_worker_transitions.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- lock one task at a time (`locked_until`) to avoid double execution
- branch logic by current state
- call `codex_runner`
- call `gh_client.set_labels(...)`
- commit transition via repository + `task_events`

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_worker_transitions.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/worker_service.py tests/integration/test_worker_transitions.py
git commit -m "feat: orchestrate codex workflows and label transitions"
```

## Task 8: Scheduler Loop (Polling + Dispatch)

**Files:**
- Create: `app/services/scheduler.py`
- Modify: `app/main.py`
- Create: `tests/integration/test_scheduler_tick.py`

**Step 1: Write the failing test**

Test that one scheduler tick does:
- sync from GitHub
- dispatch one runnable task
- skip dispatch when no task

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_scheduler_tick.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- APScheduler interval job: `tick()`
- startup event starts scheduler
- shutdown event stops scheduler
- add config flag `scheduler.enabled` for tests

**Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_scheduler_tick.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/services/scheduler.py app/main.py tests/integration/test_scheduler_tick.py
git commit -m "feat: add polling scheduler for sync and execution"
```

## Task 9: FastAPI Board (API + HTML)

**Files:**
- Create: `app/api/routes_board.py`
- Create: `app/ui/templates/board.html`
- Create: `app/ui/static/board.js`
- Modify: `app/main.py`
- Create: `tests/smoke/test_board_api.py`

**Step 1: Write the failing test**

Cover endpoints:
- `GET /api/board` returns grouped columns by state
- `GET /api/tasks/{id}/events` returns lifecycle timeline
- `GET /board` returns HTML page

**Step 2: Run test to verify it fails**

Run: `pytest tests/smoke/test_board_api.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- `/api/board`: query tasks grouped by canonical states
- `/api/tasks/{id}/events`: ordered events
- `/board`: server-rendered shell + client polling JS
- frontend columns:
- `agent-issue`
- `agent-reviewable`
- `agent-changed`
- `agent-approved`

**Step 4: Run test to verify it passes**

Run: `pytest tests/smoke/test_board_api.py -v`  
Expected: PASS.

**Step 5: Commit**

```bash
git add app/api/routes_board.py app/ui/templates/board.html app/ui/static/board.js app/main.py tests/smoke/test_board_api.py
git commit -m "feat: add task board api and web ui"
```

## Task 10: Config, Runbook, and End-to-End Validation

**Files:**
- Create: `config/agentflow.example.yaml`
- Create: `README.md`
- Create: `tests/e2e/test_single_repo_happy_path.py`

**Step 1: Write the failing test**

E2E (mocked `gh` + mocked `codex`) should verify:
- issue enters DB as `agent-issue`
- worker transitions to `agent-reviewable`
- review transitions to `agent-approved` or `agent-changed`
- board API reflects transitions

**Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_single_repo_happy_path.py -v`  
Expected: FAIL.

**Step 3: Write minimal implementation**

- `config/agentflow.example.yaml`:
- DB path, poll interval, single repo config, codex command config
- README:
- setup, config, run commands, architecture, troubleshooting
- ensure app reads config path from env: `AGENTFLOW_CONFIG`

**Step 4: Run full validation**

Run: `pytest -v`  
Expected: all PASS.

Run: `uvicorn app.main:create_app --factory --reload`  
Expected: service starts, `/healthz` and `/board` available.

**Step 5: Commit**

```bash
git add config/agentflow.example.yaml README.md tests/e2e/test_single_repo_happy_path.py
git commit -m "docs: add config and runbook with e2e coverage"
```

## Implementation Notes

- Keep label mapping centralized in one module (avoid hardcoded strings across services).
- Treat GitHub labels as canonical business state; local DB must mirror them.
- Every state change must create a `task_events` row with `reason` and `source`.
- Runner failures must not silently change business state; keep task in current state and record run/event.
- All external calls (`gh`, `codex`) must be wrapped with timeout and structured logs.

## Acceptance Criteria (v1 Done)

- Service polls one repo and syncs matching issue/PR labels into SQLite.
- Service can run local `codex` for implement/review/fix flows through PTY.
- Labels are updated on GitHub according to workflow outcomes.
- DB contains complete lifecycle history and run logs.
- `/board` can visualize current columns and per-task history.
- Tests pass (`pytest -v`) and local start works with documented config.
