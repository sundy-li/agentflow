# GitHub State Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Synchronize SQLite task state to GitHub agent labels for all open items, and mark closed or untracked items as stale locally.

**Architecture:** Expand GitHub listing to fetch all open items carrying any agent state label. Keep `WorkerService` as the write path to GitHub, and use `SyncService` as the reconciliation layer that forces SQLite back to GitHub state when drift exists.

**Tech Stack:** Python 3.10+, `gh`, pytest.

---

### Task 1: Add failing tests for GitHub-open-item coverage and stale handling

**Files:**
- Modify: `tests/unit/test_gh_client.py`
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/unit/test_codex_runner.py`

**Step 1: Write the failing test**

Add assertions for:
- issue sync queries all agent labels, including `agent-approved`
- PR sync queries all agent labels, including `agent-approved`
- missing tracked `agent-approved` task becomes `stale`
- GitHub label overrides conflicting SQLite state
- review prompt explains PASS/FAIL to GitHub label mapping

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gh_client.py tests/unit/test_sync_service.py tests/unit/test_codex_runner.py -q`
Expected: FAIL because current GitHub listing and prompt text do not cover the new rules.

**Step 3: Write minimal implementation**

- Update `GHClient` listing methods
- Update `SyncService` stale tracking and reconciliation rules
- Update `prompts/review.md`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_gh_client.py tests/unit/test_sync_service.py tests/unit/test_codex_runner.py -q`
Expected: PASS.

### Task 2: Verify no regression in worker-driven transitions

**Files:**
- Modify: `app/services/gh_client.py`
- Modify: `app/services/sync_service.py`
- Modify: `prompts/review.md`

**Step 1: Write the failing test**

Covered by Task 1.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gh_client.py tests/unit/test_sync_service.py tests/unit/test_codex_runner.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Preserve `WorkerService` write-first-to-GitHub behavior
- Let `SyncService` correct local drift afterward

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
