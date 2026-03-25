# PR Worktree Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove local git worktrees for tracked PRs after GitHub shows they are closed or merged, and retry cleanup automatically on later scheduler ticks if removal fails.

**Architecture:** Persist worktree metadata on tasks, propagate issue worktree paths to linked PR tasks during sync, and run a dedicated cleanup service from the scheduler after each sync. The cleanup service confirms GitHub PR state before running `git worktree remove`, records cleanup status on the task, and retries unfinished cleanups on later ticks.

**Tech Stack:** Python, SQLite, pytest, git CLI, GitHub CLI integration

---

### Task 1: Add failing cleanup and sync tests

**Files:**
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/unit/test_gh_client.py`
- Modify: `tests/integration/test_scheduler_tick.py`
- Modify: `tests/integration/test_worker_transitions.py`
- Create: `tests/unit/test_worktree_cleanup_service.py`

**Step 1: Write the failing tests**

- Cover `sync_once()` returning stale PR task ids.
- Cover propagation of `worktree_path` from an issue task to a linked PR task.
- Cover GitHub PR state lookup for open versus closed PRs.
- Cover cleanup success, cleanup retryable failure, missing workspace, and already-removed worktree cases.
- Cover scheduler invoking cleanup after sync and retrying on a later tick.
- Cover worker persistence of a discovered worktree path from run logs.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_sync_service.py tests/unit/test_gh_client.py tests/unit/test_worktree_cleanup_service.py tests/integration/test_scheduler_tick.py tests/integration/test_worker_transitions.py -q`

Expected: cleanup-related assertions fail because worktree metadata persistence and cleanup orchestration do not exist yet.

**Step 3: Write minimal implementation**

- Add task columns and repository helpers for worktree metadata and cleanup status.
- Persist worktree paths from worker run logs.
- Propagate issue worktree paths to linked PR tasks during sync.
- Add GitHub PR state lookup.
- Add `WorktreeCleanupService`.
- Wire cleanup into scheduler and app startup construction.

**Step 4: Re-run targeted tests**

Run the same pytest command and confirm it passes.

### Task 2: Verify broader scheduler and task behavior

**Files:**
- Modify: `app/db.py`
- Modify: `app/repository.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/services/sync_service.py`
- Modify: `app/services/gh_client.py`
- Modify: `app/services/scheduler.py`
- Modify: `app/main.py`
- Create: `app/services/worktree_cleanup_service.py`

**Step 1: Run focused regression checks**

Run: `uv run pytest -q tests/integration/test_scheduler_tick.py tests/integration/test_worker_transitions.py tests/unit/test_sync_service.py tests/unit/test_repository.py tests/unit/test_gh_client.py tests/unit/test_worktree_cleanup_service.py`

Expected: PASS

**Step 2: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS
