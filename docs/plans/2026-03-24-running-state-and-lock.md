# Running State And Lock Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the board show real running tasks and stop the current process from re-claiming a task while one of its workers is still executing it.

**Architecture:** Track active task ids in `WorkerService`, pass those ids into repository claim filtering, and compute board running state from unfinished runs first and unexpired task locks second. Keep the fix process-local so a service restart still allows reclaiming previously unfinished runs.

**Tech Stack:** Python, SQLite, pytest

---

### Task 1: Add failing repository tests for claim exclusion and running-task lookup

**Files:**
- Modify: `tests/unit/test_repository.py`
- Modify: `app/repository.py`

**Step 1: Write the failing test**

```python
def test_claim_next_task_skips_excluded_task_ids(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    first = repository.upsert_task(...)
    second = repository.upsert_task(...)

    claimed = repository.claim_next_task(
        repo_id,
        RUNNABLE_STATES,
        "worker-1",
        exclude_task_ids=[int(first["id"])],
    )

    assert claimed["id"] == second["id"]
```

Add another test for `list_running_task_ids(repo_id)` using an unfinished run.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_repository.py -q`
Expected: FAIL because `exclude_task_ids` and running-task lookup do not exist.

**Step 3: Write minimal implementation**

Add `exclude_task_ids` filtering to `claim_next_task()` and add a repo-scoped `list_running_task_ids()` helper.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_repository.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_repository.py app/repository.py
git commit -m "feat: add process-local claim exclusion support"
```

### Task 2: Add failing CLI tests for real running-state rendering

**Files:**
- Modify: `tests/unit/test_cli.py`
- Modify: `app/cli.py`

**Step 1: Write the failing test**

```python
def test_cli_board_marks_unfinished_run_as_running_without_lock(...):
    run_id = repository.create_run(...)
    output = ...
    assert "running" in output
```

Add another test where `locked_until` is in the past and no unfinished run exists, expecting `idle`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: FAIL because board status still uses lock fields only.

**Step 3: Write minimal implementation**

Make `render_board()` gather unfinished run task ids and update `_locked_status()` to prefer real running tasks, then valid unexpired locks.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_cli.py app/cli.py
git commit -m "fix: show real running tasks on board"
```

### Task 3: Add failing scheduler integration test for duplicate-claim prevention

**Files:**
- Modify: `tests/integration/test_scheduler_tick.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/services/scheduler.py`

**Step 1: Write the failing test**

```python
def test_scheduler_excludes_process_active_task_ids(...):
    ...
    assert claimed_task_ids == [first_task_id, second_task_id]
```

Simulate one active task already running in-process and verify the next dispatched worker does not re-claim it.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_scheduler_tick.py -q`
Expected: FAIL because scheduler does not ask the worker for active task ids and repository does not exclude them.

**Step 3: Write minimal implementation**

Add active task tracking to `WorkerService` and thread that data into scheduler dispatch and claim filtering.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_scheduler_tick.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/integration/test_scheduler_tick.py app/services/worker_service.py app/services/scheduler.py
git commit -m "fix: prevent duplicate claims while task is still running"
```

### Task 4: Run focused and full verification

**Files:**
- Modify: none
- Test: `tests/unit/test_repository.py`
- Test: `tests/unit/test_cli.py`
- Test: `tests/integration/test_scheduler_tick.py`

**Step 1: Run focused verification**

Run: `uv run pytest tests/unit/test_repository.py tests/unit/test_cli.py tests/integration/test_scheduler_tick.py -q`
Expected: PASS

**Step 2: Run full verification**

Run: `uv run pytest -q`
Expected: PASS

**Step 3: Verify requirements**

Checklist:
- board uses unfinished runs to show `running`
- expired lock without live run renders `idle`
- same process cannot re-claim a task while it is still executing
- restart semantics remain unchanged because active-task tracking is in memory only

**Step 4: Commit**

```bash
git add -A
git commit -m "fix: align running state with active runs"
```
