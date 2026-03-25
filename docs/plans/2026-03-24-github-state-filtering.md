# GitHub State Filtering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep closed or merged GitHub issues and pull requests in SQLite for history while excluding them from board output and all active task claiming.

**Architecture:** Add a GitHub-owned `github_state` column to tasks, set it to `open` for actively synced items, and update it to `closed` or `merged` when direct GitHub state lookup confirms a terminal remote state. Repository board and claim queries filter on `github_state='open'`, while sync preserves history and stale behavior when remote status is still open or temporarily unavailable.

**Tech Stack:** Python, SQLite, pytest, GitHub CLI integration

---

### Task 1: Add failing tests for github state filtering

**Files:**
- Modify: `tests/unit/test_repository.py`
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/unit/test_gh_client.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/smoke/test_board_api.py`

**Step 1: Write the failing tests**

- Cover board filtering for `github_state='closed'` and `github_state='merged'`.
- Cover claim filtering for non-open tasks.
- Cover sync persisting `github_state='open'` for open items.
- Cover sync overwriting to `closed` or `merged` when a tracked task disappears from the open lists and GitHub confirms the terminal state.
- Cover sync fallback behavior when GitHub state lookup fails.
- Cover direct issue state lookup in the GH client.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/unit/test_repository.py tests/unit/test_sync_service.py tests/unit/test_gh_client.py tests/unit/test_cli.py tests/smoke/test_board_api.py`

Expected: FAIL because `github_state` does not exist and board/claim filtering does not use remote lifecycle state.

**Step 3: Write minimal implementation**

- Add `github_state` schema support and repository helpers.
- Update task upsert paths to persist `github_state`.
- Add direct GitHub issue state lookup and reuse existing PR state lookup.
- Update sync to overwrite terminal GitHub states.
- Filter board and claim queries to `github_state='open'`.

**Step 4: Re-run targeted tests**

Run the same pytest command and confirm it passes.

### Task 2: Verify broader queue and scheduler behavior

**Files:**
- Modify: `app/db.py`
- Modify: `app/repository.py`
- Modify: `app/services/sync_service.py`
- Modify: `app/services/gh_client.py`
- Modify: `app/cli.py`

**Step 1: Run focused regression checks**

Run: `uv run pytest -q tests/integration/test_scheduler_tick.py tests/integration/test_worker_transitions.py tests/unit/test_repository.py tests/unit/test_sync_service.py tests/unit/test_gh_client.py tests/unit/test_cli.py tests/smoke/test_board_api.py`

Expected: PASS

**Step 2: Run the full suite**

Run: `uv run pytest -q`

Expected: PASS
