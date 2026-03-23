# Runs Inspect And Async Scheduler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add CLI commands to inspect persisted Codex runs and refactor the scheduler so worker execution does not block future ticks.

**Architecture:** Extend the CLI with `runs` and `inspect` subcommands that read the local `runs` table and associated log files. Persist `output_path` at run creation so running logs are discoverable. Refactor scheduler dispatch to use a persistent executor and a tracked set of in-flight futures, so `tick()` only syncs and dispatches available slots rather than waiting for Codex completion.

**Tech Stack:** Python 3.10+, `argparse`, SQLite repository layer, `ThreadPoolExecutor`, pytest.

---

### Task 1: Add failing CLI tests for runs and inspect

**Files:**
- Modify: `tests/unit/test_cli.py`

**Step 1: Write the failing test**

Add assertions for:
- `runs` prints running and completed runs
- `inspect <run_id>` prints the stored log
- `inspect <run_id> --follow` streams appended content until the run is marked finished

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: FAIL because the commands do not exist yet.

**Step 3: Write minimal implementation**

- add repository helpers for listing runs
- add CLI commands and log tailing
- persist `output_path` at run creation time

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: PASS.

### Task 2: Add failing test for non-blocking scheduler dispatch

**Files:**
- Modify: `tests/integration/test_scheduler_tick.py`

**Step 1: Write the failing test**

Add assertion that a tick returns promptly even when one dispatched worker is still blocked.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_scheduler_tick.py -q`
Expected: FAIL because tick currently waits on worker completion.

**Step 3: Write minimal implementation**

- use a persistent executor
- track in-flight worker futures
- dispatch only available slots

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_scheduler_tick.py -q`
Expected: PASS.

### Task 3: Verify full suite

**Files:**
- Modify: `app/cli.py`
- Modify: `app/repository.py`
- Modify: `app/services/codex_runner.py`
- Modify: `app/services/scheduler.py`
- Modify: `README.md`

**Step 1: Write the failing test**

Covered by Tasks 1 and 2.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py tests/integration/test_scheduler_tick.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- wire new CLI commands
- make scheduler dispatch non-blocking

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
