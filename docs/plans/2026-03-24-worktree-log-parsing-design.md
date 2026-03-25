# Worktree Log Parsing Design

## Summary

`WorktreeCleanupService` only cleans stale PR tasks that already have a persisted `worktree_path`. In the current system, some implementation runs create the correct local worktree, but `WorkerService` fails to persist that path because it only inspects the tail of the run log and only recognizes a narrow set of phrases.

## Problem

- Large run logs can push the first worktree mention out of the last `120000` bytes.
- Real run logs often mention the active worktree as an execution working directory like `in /repo/.worktrees/issue-9-...`, not as `worktree 路径是 ...`.
- Follow-up prompts also reuse persisted delivery context with `Existing worktree: ...`, which the current parser ignores.
- When `worktree_path` stays empty on the issue task, sync cannot propagate it to the PR task, so merged PR cleanup never runs.

## Options

### Option 1: Read the entire log and match any `.worktrees` path

Pros:
- Simple to implement.

Cons:
- Easy to capture the wrong worktree when the log inspects other branches or historical worktrees.

### Option 2: Extend parsing with explicit formats and execution-cwd extraction, with full-log fallback

Pros:
- Covers the real formats already present in logs.
- Keeps matching biased toward the active task worktree instead of any arbitrary historical path.
- Limits full-log reads to cases where tail parsing fails.

Cons:
- Slightly more parsing code.

### Option 3: Change prompts so the agent must always print a canonical `worktree 路径是 ...` line

Pros:
- Clear long-term contract.

Cons:
- Does not repair historical runs.
- Still fragile if agents ignore the format.

## Decision

Choose Option 2.

Keep the existing explicit phrases, add support for `Existing worktree: ...`, and extract the active worktree from execution records that run `in /.../.worktrees/...`. Preserve tail scanning as the fast path, but fall back to the full log when the tail does not contain a usable worktree path.

To repair already-missed tasks, let sync recover an issue task's missing `worktree_path` from its recent run logs before propagating the path to linked PR tasks.

## Scope

- Fix persistence of implementation/fix worktree paths on issue tasks.
- Improve delivery-context worktree recovery from recent logs.
- Backfill missing issue `worktree_path` values from recent run logs during sync so historical merged PRs can enter cleanup.
- Do not add cleanup support for review-only `/tmp/...` worktrees in this change.

## Testing

- Add a failing test for an implementation log where the worktree only appears early in the file and only as an execution cwd.
- Add a failing test for recent delivery metadata that only exposes `Existing worktree: ...`.
- Add a failing sync test proving a linked PR inherits a recovered issue worktree path from historical run logs.
- Re-run the focused worker and cleanup tests after the minimal implementation change.
