# CodingAgentRunner Design

**Goal:** Replace `CodexRunner` with a generic `CodingAgentRunner` that can run `codex`, `claude code`, or `opencode`, and allow `implement`, `fix`, and `review` to use different coding agents.

## Scope

- Rename the primary runner abstraction from `CodexRunner` to `CodingAgentRunner`.
- Support three CLI kinds:
  - `codex`
  - `claude_code`
  - `opencode`
- Add config-driven routing so `implement`, `fix`, and `review` can each select a different coding agent profile.
- Preserve backward compatibility with the existing top-level `codex:` config.

## Architecture

### Runner

- Introduce `CodingAgentRunner` as the concrete subprocess runner.
- Keep the current responsibilities:
  - render prompts from `prompts/`
  - create `runs` rows
  - execute via PTY
  - capture logs
  - derive review result
  - support shutdown
- Move agent selection into the runner so `WorkerService` continues to pass only `mode`.

### Config

- Keep existing `codex:` config as a legacy fallback profile.
- Add `coding_agents:` as a map of named agent profiles.
- Add `task_agents:` as a mode-to-profile mapping.
- Resolution order for a mode:
  1. `task_agents.<mode>` if configured
  2. `coding_agents.default` if configured
  3. legacy `codex:` converted into an implicit default profile
- Invalid `task_agents` references should fail during config validation, not during task execution.

## Config Shape

```yaml
codex:
  command: codex
  args: []
  timeout_seconds: 1800

coding_agents:
  default:
    kind: codex
    command: codex
    args: []
    timeout_seconds: 1800
  claude:
    kind: claude_code
    command: claude
    args: []
    timeout_seconds: 1800
  opencode:
    kind: opencode
    command: opencode
    args: []
    timeout_seconds: 1800

task_agents:
  implement: claude
  fix: opencode
  review: default
```

## Command Mapping

- `codex`:
  - command: `codex exec <prompt>`
- `claude_code`:
  - command: `claude --print <prompt>`
- `opencode`:
  - command: `opencode run <prompt>`

`args` remain profile-specific extra arguments appended after the tool-specific non-interactive tokens and before the prompt.

## Worker Flow

- `WorkerService` remains state-driven:
  - issue => `implement`
  - reviewable PR => `review`
  - changed PR => `fix`
- It does not branch on tool kind.
- It may keep the existing `run_codex(...)` call signature for a small diff, but the preferred end state is `run_task(...)` or `run_agent(...)`.

## Error Handling

- Unsupported profile `kind` raises a config validation error.
- Missing referenced profile in `task_agents` raises a config validation error.
- Missing binary still surfaces as a logged `FileNotFoundError` and failed run, unchanged from today.
- Timeout and review result parsing remain unchanged.

## Testing

- Config tests:
  - legacy `codex:` still loads
  - new `coding_agents` + `task_agents` override legacy config
  - invalid profile references fail
- Runner tests:
  - command composition for `codex`, `claude_code`, `opencode`
  - mode-specific profile selection
  - prompt generation, cwd, log capture, timeout, shutdown regressions
- Integration tests:
  - worker still routes states to `implement` / `review` / `fix`
  - selected agent profile changes by mode
- Docs:
  - `README.md`
  - `config/agentflow.example.yaml`

## Non-Goals

- No per-tool prompt template split in this change.
- No database schema changes.
- No changes to task lifecycle semantics.
