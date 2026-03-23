# Parallel Scheduler And Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add configurable parallel task execution with a default of four concurrent tasks, and recover unfinished tasks after restart by clearing stale locks.

**Architecture:** Extend scheduler settings with `max_parallel_tasks`, keep `process_one()` as the single-task unit of work, and run a bounded batch of those units in parallel inside each scheduler tick. Add startup lock recovery for the active repo before scheduling begins.

**Tech Stack:** Python 3.10+, APScheduler, `concurrent.futures`, pytest, FastAPI lifespan.

---

### Task 1: Add failing tests for scheduler parallelism and config defaults

**Files:**
- Create: `tests/unit/test_config.py`
- Modify: `tests/integration/test_scheduler_tick.py`

**Step 1: Write the failing test**

Add assertions for:
- `load_settings()` defaults `scheduler.max_parallel_tasks` to `4`
- `tick()` dispatches up to the configured parallelism
- `tick()` returns the executed task count

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py tests/integration/test_scheduler_tick.py -q`
Expected: FAIL because the config field and batch scheduler behavior do not exist yet.

**Step 3: Write minimal implementation**

- Add `max_parallel_tasks` to scheduler config
- Update scheduler tick execution model

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py tests/integration/test_scheduler_tick.py -q`
Expected: PASS.

### Task 2: Add failing test for restart lock recovery

**Files:**
- Modify: `app/main.py`
- Modify: `app/repository.py`
- Create or modify: `tests/integration/test_startup_recovery.py`

**Step 1: Write the failing test**

Cover:
- a previously locked runnable task exists in SQLite
- app startup clears the lock for the active repo

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_startup_recovery.py -q`
Expected: FAIL before lock recovery exists.

**Step 3: Write minimal implementation**

- add repository helper to clear repo locks
- call it during app startup before scheduler execution

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_startup_recovery.py -q`
Expected: PASS.

### Task 3: Verify full suite

**Files:**
- Modify: `config/agentflow.example.yaml`
- Modify: `config/agentflow.yaml`
- Modify: `app/config.py`
- Modify: `app/services/scheduler.py`
- Modify: `app/main.py`
- Modify: `app/repository.py`

**Step 1: Write the failing test**

Covered by Tasks 1 and 2.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py tests/integration/test_scheduler_tick.py tests/integration/test_startup_recovery.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- wire through config and startup recovery
- keep existing worker behavior intact

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
