# PR Worktree Cleanup Design

## Summary

When the scheduler discovers that a tracked pull request has been closed or merged, it should remove the local git worktree associated with that PR by running `git worktree remove <path>`. This cleanup must be retried automatically on later ticks if it fails, and it must never delete the branch.

## Decisions

- Keep worktree cleanup as a scheduler-side responsibility instead of mixing shell side effects into `SyncService`.
- Persist worktree cleanup metadata on `tasks` so retries do not depend on historical run logs remaining available.
- Confirm the current GitHub PR state before cleanup. A PR disappearing from the open labeled list is not sufficient because labels may change while the PR is still open.
- Store the worktree path on issue tasks from agent logs, then propagate it to the linked PR task during sync so stale PR cleanup has a stable source of truth.
- Retry cleanup on every later scheduler tick until the worktree is removed or is already absent from git worktree registration.
- Never force-remove a worktree and never delete the branch.

## Data Model

Add these optional columns to `tasks`:

- `worktree_path`
- `worktree_cleanup_attempted_at`
- `worktree_cleanup_error`
- `worktree_removed_at`

## Flow

1. Worker runs implementation or fix work and inspects the run log for a worktree path.
2. If a worktree path is found, persist it on the current task.
3. When issue sync observes linked PR numbers, propagate the issue's persisted worktree path to the corresponding PR task if that PR task does not already have one.
4. Sync continues to mark unseen tracked PRs as `is_stale = true` and returns the stale PR task ids for the current tick.
5. Scheduler invokes a dedicated worktree cleanup service after sync.
6. Cleanup service loads stale PR tasks that still have `worktree_path` and no `worktree_removed_at`.
7. For each candidate, confirm the PR state from GitHub.
8. If the PR is still open, skip cleanup.
9. If the PR is closed or merged, run `git -C <repo workspace> worktree remove <worktree_path>`.
10. On success, mark the worktree as removed and clear cleanup errors.
11. On failure, persist the error and retry on later ticks.

## Error Handling

- Missing repo workspace is a retriable cleanup failure.
- If the worktree path is no longer present in `git worktree list --porcelain`, treat it as already cleaned up and mark success.
- Cleanup failures must not block sync or worker dispatch in the same tick.

## Testing

- `SyncService` tests cover stale PR detection and worktree propagation from issue to PR.
- `WorktreeCleanupService` tests cover GitHub state gating, successful removal, already-removed worktrees, missing workspace, and retryable failures.
- Scheduler integration tests cover cleanup execution after sync, retry on later ticks, and non-blocking behavior when cleanup fails.
