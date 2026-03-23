# PR Review Latency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Delay `agent-reviewable` PR reviews until a configurable number of hours has elapsed since the most recently observed PR head push.

**Architecture:** Extend PR sync payloads with `headRefOid`, persist the observed head SHA and the local observation timestamp in SQLite, and enforce the latency window inside `claim_next_task()` so reviewable PRs do not enter the review worker too early.

**Tech Stack:** Python 3.10+, SQLite, FastAPI config, pytest.

---

### Task 1: Add failing tests for config and GitHub PR payloads

**Files:**
- Modify: `tests/unit/test_config.py`
- Modify: `tests/unit/test_gh_client.py`

**Step 1: Write the failing test**

Add assertions for:
- `scheduler.review_latency_hours` defaults to `0`
- PR list queries include `headRefOid`
- normalized PR payloads expose `head_sha`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_gh_client.py -q`
Expected: FAIL because the config field and PR head SHA payload do not exist yet.

**Step 3: Write minimal implementation**

- add config field
- add `headRefOid` to PR JSON query and normalization

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_gh_client.py -q`
Expected: PASS.

### Task 2: Add failing tests for sync persistence and claim latency

**Files:**
- Modify: `tests/unit/test_sync_service.py`
- Modify: `tests/unit/test_repository.py`

**Step 1: Write the failing test**

Add assertions for:
- sync stores first-seen PR head SHA and observed push time
- sync preserves observed push time when SHA is unchanged
- sync refreshes observed push time when SHA changes
- reviewable PRs are blocked until latency expires
- non-review review tasks remain claimable

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_sync_service.py tests/unit/test_repository.py -q`
Expected: FAIL before persistence and claim filtering are implemented.

**Step 3: Write minimal implementation**

- extend task schema and repository writes
- update sync service to manage PR push observation metadata
- update claim logic with review latency

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_sync_service.py tests/unit/test_repository.py -q`
Expected: PASS.

### Task 3: Wire scheduler and verify full suite

**Files:**
- Modify: `app/config.py`
- Modify: `app/services/scheduler.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/db.py`
- Modify: `migrations/001_init.sql`
- Modify: `config/agentflow.example.yaml`
- Modify: `config/agentflow.yaml`

**Step 1: Write the failing test**

Covered by Tasks 1 and 2.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_gh_client.py tests/unit/test_sync_service.py tests/unit/test_repository.py -q`
Expected: FAIL before wiring is complete.

**Step 3: Write minimal implementation**

- wire review latency config through scheduler to worker to repository claim
- ensure migrations upgrade existing databases safely

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
