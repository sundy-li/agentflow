# Issue PR Follow-Up Design

## Summary

When an `agent-issue` implement run exits successfully, the worker must verify that an open PR linked with `Fixes #<issue>` now exists. If not, the worker should run Codex one more time with a PR-only follow-up prompt that tells it to push the existing branch and create the missing PR.

## Decisions

- Keep the GitHub issue state as `agent-issue`; do not introduce a new GitHub label.
- Add a local `blocked_reason` field on tasks so the scheduler can stop retrying issues that already had an implementation run plus one PR follow-up run and still do not have a linked PR.
- Preserve `blocked_reason` across syncs until GitHub reports a linked open PR for the issue. Once a linked PR appears, clear the block and store the concrete PR numbers locally.
- Show blocked tasks as `blocked` in the CLI board status column so local state is visible.

## Flow

1. Run normal implement prompt.
2. If the run fails, keep existing failure behavior.
3. If the run succeeds, query GitHub for open PRs linked to the issue.
4. If a linked PR exists, persist `has_open_linked_pr=True` and the linked PR numbers.
5. If no linked PR exists, run one more implement-mode Codex invocation with a PR-only follow-up prompt.
6. Query GitHub again.
7. If a linked PR exists, persist it and finish.
8. If no linked PR exists, set `blocked_reason` and stop future claims until sync observes a linked PR.
