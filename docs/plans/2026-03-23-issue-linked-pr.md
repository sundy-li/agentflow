# Issue Linked PR Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep issue labels unchanged, drive workflow state from PR labels only, and stop re-processing issues already linked by an open PR.

**Architecture:** Extend GitHub sync to inspect open PR bodies for `Fixes/Closes/Resolves` issue references and persist a local linked-PR flag on issue tasks. Update task claiming and worker behavior so successful issue implementation leaves the issue unchanged while PR-based workflow continues on the PR itself.

**Tech Stack:** Python 3.10+, SQLite repository layer, GitHub CLI integration, pytest.

---

### Task 1: Add failing tests for linked PR detection and issue preservation

**Files:**
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/integration/test_worker_transitions.py`
- Modify: `tests/unit/test_codex_runner.py`
- Modify: `tests/unit/test_repository.py`

**Step 1: Write the failing test**

Add assertions for:
- sync marks an `agent-issue` task as blocked when an open PR body contains `Fixes #<issue>`
- repository task claiming skips blocked issue tasks
- worker implementation success keeps issue state as `agent-issue` and makes no GitHub label edit
- implement prompt includes `Fixes #<issue_number>`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sync_service.py tests/integration/test_worker_transitions.py tests/unit/test_codex_runner.py tests/unit/test_repository.py -q`
Expected: FAIL because linked-PR tracking and issue-preserving behavior do not exist yet.

**Step 3: Write minimal implementation**

- add repository fields for linked open PR tracking
- parse linked issue numbers from open PR bodies
- update worker issue success behavior
- update implement prompt context/template

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sync_service.py tests/integration/test_worker_transitions.py tests/unit/test_codex_runner.py tests/unit/test_repository.py -q`
Expected: PASS.

### Task 2: Add GitHub client coverage for open PR body fetching

**Files:**
- Modify: `tests/unit/test_gh_client.py`
- Modify: `app/services/gh_client.py`

**Step 1: Write the failing test**

Add assertions that:
- `list_open_pr_links()` requests open PRs with `body`
- the method returns parsed linked issue numbers

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gh_client.py -q`
Expected: FAIL because the method does not exist yet.

**Step 3: Write minimal implementation**

- add a GitHub client helper that lists open PRs and extracts linked issue numbers from PR bodies

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_gh_client.py -q`
Expected: PASS.

### Task 3: Verify full suite

**Files:**
- Modify: `app/repository.py`
- Modify: `app/db.py`
- Modify: `app/services/sync_service.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/services/codex_runner.py`
- Modify: `prompts/implement.md`

**Step 1: Write the failing test**

Covered by Tasks 1 and 2.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sync_service.py tests/integration/test_worker_transitions.py tests/unit/test_codex_runner.py tests/unit/test_repository.py tests/unit/test_gh_client.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- persist linked open PR flags on tasks
- skip blocked issues during claim
- keep issue labels/state unchanged after implementation success
- instruct Codex to create PRs with `Fixes #issue`

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
