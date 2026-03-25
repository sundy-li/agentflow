# Blocked Issue PR Recovery Design

## Summary

`blocked_reason=missing_pr_after_implement` should no longer behave like a terminal failure. It should mean "implementation exists locally but PR delivery is incomplete". Agentflow must automatically retry the PR-delivery step after restart and during later scheduler ticks.

## Decisions

- Keep the existing local block marker, but add a retry timestamp so blocked tasks can become runnable again.
- On application startup, immediately mark missing-PR blocks as ready for retry so a restart can resume delivery work.
- When retrying a blocked issue, skip the normal implement prompt and run only the PR follow-up path.
- Best-effort session reuse will be implemented as delivery-context reuse: previous worktree, branch, commit, and run log path are injected into the follow-up prompt when they can be discovered.

## Flow

1. Initial implement succeeds but no linked PR is observed.
2. Worker runs one immediate PR follow-up attempt.
3. If PR is still missing, task remains blocked with `blocked_reason=missing_pr_after_implement` and a `blocked_until` retry timestamp.
4. Scheduler skips the task until `blocked_until` is due.
5. On startup, missing-PR blocks are made immediately retryable.
6. When a blocked task is claimed again, worker first checks whether a PR now exists.
7. If not, worker runs a PR-only follow-up prompt with previous delivery context.
8. If PR creation succeeds, block is cleared; otherwise, the task is re-blocked with a later retry timestamp.
