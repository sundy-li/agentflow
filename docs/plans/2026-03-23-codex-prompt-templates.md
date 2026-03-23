# Codex Prompt Templates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Load Codex prompts from editable Markdown files and require `git worktree` usage for implementation and fix tasks.

**Architecture:** `CodexRunner` keeps orchestration responsibility but stops owning prompt prose. It loads a mode-specific template from `prompts/`, prepares a small context payload, and renders `{{variable}}` placeholders into the final prompt string.

**Tech Stack:** Python 3.11, pathlib, regex, pytest.

---

### Task 1: Add failing prompt-template tests

**Files:**
- Modify: `tests/unit/test_codex_runner.py`
- Test: `tests/unit/test_codex_runner.py`

**Step 1: Write the failing test**

Add assertions for:
- `implement` prompt contains rendered task data and `git worktree` instruction
- `fix` prompt contains rendered task data and `git worktree` instruction
- `review` prompt omits `git worktree`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: FAIL because templates do not exist and prompt rendering is still hardcoded.

**Step 3: Write minimal implementation**

- Add prompt template files under `prompts/`
- Update `app/services/codex_runner.py` to read the templates and render placeholders

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: PASS.

### Task 2: Add default prompt templates

**Files:**
- Create: `prompts/implement.md`
- Create: `prompts/fix.md`
- Create: `prompts/review.md`

**Step 1: Write the failing test**

Covered by Task 1.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: FAIL until the templates are present and rendered.

**Step 3: Write minimal implementation**

- Put default wording into the Markdown files
- Include fork/upstream/base-branch guidance in `implement` and `fix`
- Include explicit `git worktree` branch-isolation guidance only in `implement` and `fix`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: PASS.

### Task 3: Verify targeted and full test suites

**Files:**
- Modify: `app/services/codex_runner.py`
- Modify: `tests/unit/test_codex_runner.py`

**Step 1: Write the failing test**

Covered by Task 1.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: FAIL before implementation.

**Step 3: Write minimal implementation**

- Keep `run_codex()` behavior unchanged outside prompt generation
- Ensure stored run prompt still reflects the rendered Markdown template

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: PASS.
