# GitHub State Sync Design

**Goal:** Make GitHub agent labels the authoritative task state, keep SQLite synchronized to those labels, and stop processing closed items while preserving local history.

## Decisions

- GitHub label state is the source of truth for open issues and open PRs.
- SQLite remains a local mirror used for scheduling, history, and UI.
- The worker continues to write results back to GitHub first. SQLite is only updated locally after the GitHub label update succeeds.
- The sync job is responsible for reconciling any drift by overwriting SQLite state with the GitHub label state.
- Closed items are not processed. If a tracked item is no longer visible in the open GitHub task lists, mark the SQLite row as `stale`.

## Scope

- Sync open issues across all agent labels.
- Sync open PRs across all agent labels.
- Keep `agent-approved` mirrored in SQLite even though it is not runnable.
- If an item loses all agent labels or is closed, mark the local task `stale`.

## Behavior

- Open issue/PR with an agent label:
- upsert it locally
- map labels to a state
- if the local state differs, update SQLite to match GitHub
- Open issue/PR not returned by GitHub sync:
- if it was previously tracked under an agent state, mark it `stale`
- Closed issue/PR:
- handled implicitly by the open-only GitHub queries above, then marked `stale` locally

## Prompt Alignment

- `prompts/review.md` should explain that `REVIEW_RESULT:PASS` maps to GitHub label `agent-approved` and `REVIEW_RESULT:FAIL` maps to `agent-changed`.
- Review prompt must still avoid branch or worktree instructions.

## Test Coverage

- `GHClient` lists all open agent-labeled issues and PRs, including `agent-approved`.
- `SyncService` treats GitHub as authoritative when SQLite disagrees.
- `SyncService` marks missing tracked tasks, including `agent-approved`, as `stale`.
- `review` prompt reflects the label-sync outcome.
