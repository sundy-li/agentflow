# Startup Logging And Immediate Tick Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Surface application INFO logs under the existing Uvicorn startup command and trigger the first scheduler tick immediately on startup.

**Architecture:** Add a small logging bridge in `app.main` that binds the `app` logger namespace to Uvicorn's console handlers, then update the scheduler interval job to start with `next_run_time=datetime.now()`. Emit concise scheduler INFO logs so idle and active polling are visible.

**Tech Stack:** Python 3.10+, `logging`, APScheduler, pytest.

---

### Task 1: Add failing tests for logging bridge and immediate first tick

**Files:**
- Modify: `tests/integration/test_scheduler_tick.py`
- Create: `tests/unit/test_main.py`

**Step 1: Write the failing test**

Add assertions for:
- `configure_app_logging()` attaches handlers and INFO level to the `app` logger
- `AgentScheduler.start()` schedules the interval job with `next_run_time`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_main.py tests/integration/test_scheduler_tick.py -q`
Expected: FAIL because the logging bridge and immediate start are not implemented.

**Step 3: Write minimal implementation**

- add logging bridge in `app.main`
- add immediate `next_run_time` and scheduler logs

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_main.py tests/integration/test_scheduler_tick.py -q`
Expected: PASS.

### Task 2: Verify full suite

**Files:**
- Modify: `app/main.py`
- Modify: `app/services/scheduler.py`

**Step 1: Write the failing test**

Covered by Task 1.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_main.py tests/integration/test_scheduler_tick.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- keep existing startup flow intact apart from logging visibility and immediate first tick

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
