# CodingAgentRunner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `CodexRunner` with a generic `CodingAgentRunner`, add support for `codex`, `claude code`, and `opencode`, and let `implement`, `fix`, and `review` select different coding agent profiles.

**Architecture:** Add profile-based agent configuration and mode-to-profile routing in `app/config.py`, then update the runner to resolve a profile for each mode and compose the correct non-interactive CLI invocation for each tool. Preserve existing prompt rendering, PTY execution, run logging, and review result parsing.

**Tech Stack:** Python, Pydantic, pytest, FastAPI

---

### Task 1: Add failing config tests for agent profiles and routing

**Files:**
- Modify: `tests/unit/test_config.py`
- Modify: `app/config.py`

**Step 1: Write the failing test**

```python
def test_load_settings_supports_task_specific_coding_agents(tmp_path):
    config_path = tmp_path / "agentflow.yaml"
    config_path.write_text(
        \"\"\"
coding_agents:
  default:
    kind: codex
    command: codex
  claude:
    kind: claude_code
    command: claude
task_agents:
  implement: claude
repos:
  - enabled: false
\"\"\",
        encoding=\"utf-8\",
    )

    settings = load_settings(str(config_path))

    assert settings.resolve_agent_for_mode(\"implement\").kind == \"claude_code\"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: FAIL because the new config models and resolver do not exist yet.

**Step 3: Write minimal implementation**

```python
class CodingAgentSettings(BaseModel):
    kind: Literal[\"codex\", \"claude_code\", \"opencode\"] = \"codex\"
    command: str
    args: List[str] = Field(default_factory=list)
    timeout_seconds: int = 1800
```

Add `coding_agents`, `task_agents`, and a resolver on `AppSettings`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_config.py app/config.py
git commit -m "feat: add coding agent profile config"
```

### Task 2: Add failing runner tests for command composition and mode selection

**Files:**
- Modify: `tests/unit/test_codex_runner.py`
- Create: `app/services/coding_agent_runner.py`

**Step 1: Write the failing test**

```python
def test_compose_command_supports_claude_code():
    command = CodingAgentRunner._compose_command(
        prompt=\"Review this change\",
        agent_settings=CodingAgentSettings(kind=\"claude_code\", command=\"claude\"),
    )
    assert command == [\"claude\", \"--print\", \"Review this change\"]
```

Add one test per tool kind and one test that verifies `implement` and `review` resolve different profiles.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: FAIL because `CodingAgentRunner` and the new config-aware composition path do not exist.

**Step 3: Write minimal implementation**

```python
if agent_settings.kind == \"codex\":
    tokens.extend([agent_settings.command, \"exec\"])
elif agent_settings.kind == \"claude_code\":
    tokens.extend([agent_settings.command, \"--print\"])
elif agent_settings.kind == \"opencode\":
    tokens.extend([agent_settings.command, \"run\"])
```

Keep prompt rendering and result parsing unchanged.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_codex_runner.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/unit/test_codex_runner.py app/services/coding_agent_runner.py
git commit -m "feat: add multi-agent coding runner"
```

### Task 3: Rename app wiring from CodexRunner to CodingAgentRunner

**Files:**
- Modify: `app/main.py`
- Modify: `tests/unit/test_main.py`
- Modify: any imports referencing `app.services.codex_runner`

**Step 1: Write the failing test**

```python
def test_create_app_exposes_coding_agent_runner():
    app = create_app(settings)
    assert app.state.coding_agent_runner is not None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_main.py -q`
Expected: FAIL because the app still wires `CodexRunner`.

**Step 3: Write minimal implementation**

```python
from app.services.coding_agent_runner import CodingAgentRunner

coding_agent_runner = CodingAgentRunner(...)
worker_service = WorkerService(repository, gh_client, coding_agent_runner)
app.state.coding_agent_runner = coding_agent_runner
app.state.codex_runner = coding_agent_runner
```

Keep `app.state.codex_runner` as a compatibility alias if tests or callers still expect it.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_main.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add app/main.py tests/unit/test_main.py
git commit -m "refactor: wire coding agent runner into app"
```

### Task 4: Update worker and integration tests to prove per-mode agent routing

**Files:**
- Modify: `app/services/worker_service.py`
- Modify: `tests/integration/test_worker_transitions.py`

**Step 1: Write the failing test**

```python
assert runner.calls[0][\"mode\"] == \"implement\"
assert runner.calls[0][\"agent_kind\"] == \"claude_code\"
```

Capture the resolved agent kind inside the fake runner call payload.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_worker_transitions.py -q`
Expected: FAIL because the runner does not expose resolved profile selection yet.

**Step 3: Write minimal implementation**

Expose a small helper on the runner to resolve the agent profile for a mode, and use it in tests or recorded run metadata.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_worker_transitions.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/worker_service.py tests/integration/test_worker_transitions.py
git commit -m "test: cover mode-specific coding agent routing"
```

### Task 5: Update docs and example config

**Files:**
- Modify: `README.md`
- Modify: `config/agentflow.example.yaml`

**Step 1: Write the failing test**

No automated test. Use documentation verification by reading the files after editing.

**Step 2: Run check to verify current docs are outdated**

Run: `rg -n "CodexRunner|codex command|codex:" README.md config/agentflow.example.yaml`
Expected: matches show single-agent wording that must be updated.

**Step 3: Write minimal implementation**

Document:
- the three supported tools
- `coding_agents`
- `task_agents`
- legacy `codex:` compatibility

**Step 4: Run check to verify docs are updated**

Run: `sed -n '1,220p' README.md && sed -n '1,220p' config/agentflow.example.yaml`
Expected: docs describe the new multi-agent configuration.

**Step 5: Commit**

```bash
git add README.md config/agentflow.example.yaml
git commit -m "docs: add coding agent configuration examples"
```

### Task 6: Run end-to-end verification

**Files:**
- Modify: none
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_codex_runner.py`
- Test: `tests/integration/test_worker_transitions.py`
- Test: `tests/unit/test_main.py`

**Step 1: Run focused verification**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_codex_runner.py tests/integration/test_worker_transitions.py tests/unit/test_main.py -q`
Expected: PASS

**Step 2: Run broader regression coverage**

Run: `uv run pytest -q`
Expected: PASS or a clearly identified unrelated failure.

**Step 3: Verify requirements**

Checklist:
- `CodexRunner` replaced by `CodingAgentRunner`
- `codex`, `claude code`, and `opencode` supported
- `implement`, `fix`, `review` can use different agents
- legacy `codex:` config still works

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: support configurable coding agents per task mode"
```
