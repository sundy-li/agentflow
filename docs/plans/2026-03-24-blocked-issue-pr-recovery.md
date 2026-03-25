# Blocked Issue PR Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically resume blocked issue delivery work so restarts and later scheduler ticks can finish push/PR creation without re-running implementation.

**Architecture:** Missing-PR blocks become recoverable through a `blocked_until` timestamp. Startup clears that timestamp for missing-PR blocks, scheduler claims due blocked issues, and worker runs a PR-only recovery path using best-effort previous delivery context from recent runs and local worktrees.

**Tech Stack:** Python, SQLite, pytest

---

### Task 1: Add failing recovery tests

**Files:**
- Modify: `tests/unit/test_repository.py`
- Modify: `tests/integration/test_worker_transitions.py`
- Modify: `tests/integration/test_startup_recovery.py`
- Modify: `tests/unit/test_codex_runner.py`

**Step 1: Write failing tests**

- Blocked missing-PR issues are skipped until due, then claimable.
- Due blocked issues are retried via PR-follow-up only, not full implement.
- Startup makes missing-PR blocks immediately retryable.
- Follow-up prompt contains previous delivery context when available.

**Step 2: Run targeted tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_repository.py tests/integration/test_worker_transitions.py tests/integration/test_startup_recovery.py tests/unit/test_codex_runner.py`

### Task 2: Implement recoverable blocked delivery

**Files:**
- Modify: `app/db.py`
- Modify: `app/repository.py`
- Modify: `app/main.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/services/coding_agent_runner.py`
- Modify: `prompts/implement_pr_followup.md`

**Step 1: Add retry timestamp support**

- Add `blocked_until` task column.
- Add repository helpers to set/clear blocked retry timestamps.
- Allow due missing-PR blocks to be claimed again.

**Step 2: Add worker recovery path**

- Detect blocked missing-PR issues.
- Re-check linked PRs before retrying.
- Run PR-follow-up only with previous delivery context.
- Re-block with a later retry time on failure.

**Step 3: Enable startup recovery**

- During app startup, clear retry timestamps for missing-PR blocks in the active repo.

**Step 4: Re-run targeted tests**

Run the same targeted pytest command and confirm it passes.

### Task 3: Verify broader behavior

**Files:**
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/integration/test_scheduler_tick.py`

**Step 1: Run focused affected-area checks**

Run: `uv run pytest -q tests/integration/test_scheduler_tick.py tests/integration/test_worker_transitions.py tests/integration/test_startup_recovery.py tests/unit/test_repository.py tests/unit/test_sync_service.py tests/unit/test_codex_runner.py`

**Step 2: Run the full suite**

Run: `uv run pytest -q`
