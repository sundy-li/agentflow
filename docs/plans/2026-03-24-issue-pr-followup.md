# Issue PR Follow-Up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop repeated implement retries for issues after a successful code change by requiring a linked PR, retrying PR creation once, and locally blocking tasks that still have no PR.

**Architecture:** The worker becomes responsible for verifying linked PR creation immediately after an implement success. Repository state gains a local `blocked_reason` field that scheduler claims exclude and sync only clears when a linked PR is observed. A follow-up prompt reuses the implement agent to push/create the missing PR without redoing the feature work.

**Tech Stack:** Python, SQLite, pytest

---

### Task 1: Add failing worker and repository tests

**Files:**
- Modify: `tests/integration/test_worker_transitions.py`
- Modify: `tests/unit/test_repository.py`
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/test_codex_runner.py`
- Modify: `tests/e2e/test_single_repo_happy_path.py`

**Step 1: Write failing tests**

- Cover immediate linked-PR success with no retry.
- Cover one PR follow-up retry and success.
- Cover local blocking when both checks still show no linked PR.
- Cover scheduler claim filtering for blocked tasks.
- Cover sync clearing the block only after a linked PR appears.
- Cover CLI rendering `blocked`.
- Cover PR follow-up prompt content.

**Step 2: Run targeted tests to verify they fail**

Run: `uv run pytest -q tests/integration/test_worker_transitions.py tests/unit/test_repository.py tests/unit/test_sync_service.py tests/unit/test_cli.py tests/unit/test_codex_runner.py tests/e2e/test_single_repo_happy_path.py`

**Step 3: Implement minimal production changes**

- Add `blocked_reason` task column and repository helpers.
- Update claim filtering and linked-PR persistence.
- Add worker verification and one retry with a follow-up prompt.
- Preserve/clear blocks correctly during sync.
- Render blocked status in CLI.

**Step 4: Re-run targeted tests**

Run the same targeted pytest command and confirm it passes.

### Task 2: Verify broader behavior

**Files:**
- Modify: `app/repository.py`
- Modify: `app/db.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/services/sync_service.py`
- Modify: `app/services/coding_agent_runner.py`
- Modify: `app/services/gh_client.py`
- Modify: `app/cli.py`
- Create: `prompts/implement_pr_followup.md`

**Step 1: Run focused broader checks**

Run: `uv run pytest -q tests/integration/test_scheduler_tick.py tests/integration/test_worker_transitions.py tests/unit/test_sync_service.py tests/unit/test_repository.py`

**Step 2: Run the full suite if the focused checks pass**

Run: `uv run pytest -q`
