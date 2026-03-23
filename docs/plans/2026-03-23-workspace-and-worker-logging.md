# Workspace And Worker Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Execute Codex in a repo-specific absolute workspace directory and emit basic worker logs showing which task is being handled.

**Architecture:** Extend `RepoSettings` with an optional `workspace` field, pass that value through worker task context into `CodexRunner`, and run the subprocess with `cwd=workspace` when available. Add a module logger in `WorkerService` for claim and run lifecycle messages.

**Tech Stack:** Python 3.10+, `logging`, `subprocess`, pytest.

---

### Task 1: Add failing tests for workspace execution and logging

**Files:**
- Modify: `tests/unit/test_codex_runner.py`
- Create or modify: `tests/integration/test_worker_transitions.py`

**Step 1: Write the failing test**

Add assertions for:
- repo workspace is passed to Codex subprocess `cwd`
- worker emits task-identifying log lines when processing a task

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_runner.py tests/integration/test_worker_transitions.py -q`
Expected: FAIL because workspace is not part of repo config or task context, and no worker logs exist.

**Step 3: Write minimal implementation**

- extend repo config and task context
- update Codex subprocess launch to use `cwd`
- add worker logger messages

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_codex_runner.py tests/integration/test_worker_transitions.py -q`
Expected: PASS.

### Task 2: Wire config examples and verify full suite

**Files:**
- Modify: `app/config.py`
- Modify: `app/services/worker_service.py`
- Modify: `app/services/codex_runner.py`
- Modify: `config/agentflow.example.yaml`

**Step 1: Write the failing test**

Covered by Task 1.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_runner.py tests/integration/test_worker_transitions.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- document `workspace` in config example
- keep behavior unchanged when workspace is unset

**Step 4: Run test to verify it passes**

Run: `uv run pytest -q`
Expected: PASS.
