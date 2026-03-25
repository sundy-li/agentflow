# Worktree Log Parsing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist implementation worktree paths reliably enough for stale PR cleanup to remove merged issue worktrees, including tasks that already missed persistence in older runs.

**Architecture:** Keep `worktree_path` persistence inside `WorkerService`, but replace the narrow single-regex lookup with a small extraction helper that prefers explicit worktree formats, understands execution working-directory lines, and falls back from tail-only reads to a full-log scan when needed. During sync, recover missing issue worktree paths from recent run logs before propagating them to linked PR tasks.

**Tech Stack:** Python, pytest, SQLite-backed repository helpers

---

### Task 1: Add failing log-parsing tests

**Files:**
- Modify: `tests/integration/test_worker_transitions.py`

**Step 1: Write the failing tests**

- Add a test where the run log contains the active worktree only once near the start of the file as `... in /tmp/demo/.worktrees/...`, followed by more than `120000` bytes of filler.
- Add a test where recent delivery metadata only exposes `- Existing worktree: /tmp/demo/.worktrees/...`.
- Add a sync test where an issue task has no stored `worktree_path` but a recent successful run log still exposes it, and verify the linked PR receives that path.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/integration/test_worker_transitions.py -k worktree`

Expected: FAIL because the current parser only checks the log tail and only recognizes `worktree 路径是|位于|:`.

### Task 2: Implement the minimal parser fix

**Files:**
- Modify: `app/services/worker_service.py`
- Modify: `app/services/sync_service.py`

**Step 1: Add worktree extraction helpers**

- Keep the existing explicit patterns.
- Add support for `Existing worktree:`.
- Parse execution cwd lines that run in `/.worktrees/...`.
- Fall back to reading the full log only when tail parsing does not find a worktree.

**Step 2: Use the helper in both persistence paths**

- Update `_persist_worktree_from_run()`.
- Update `_load_recent_delivery_metadata()` for the `worktree` field.
- Update sync propagation to recover missing issue worktree paths from recent runs before copying them to PR tasks.

**Step 3: Re-run the focused test**

Run: `uv run pytest -q tests/integration/test_worker_transitions.py -k worktree && uv run pytest -q tests/unit/test_sync_service.py -k backfills_issue_worktree`

Expected: PASS

### Task 3: Verify cleanup-facing regressions

**Files:**
- Modify: none unless failures expose an integration gap

**Step 1: Run worker and cleanup regressions**

Run: `uv run pytest -q tests/integration/test_worker_transitions.py tests/unit/test_sync_service.py tests/unit/test_worktree_cleanup_service.py`

Expected: PASS
