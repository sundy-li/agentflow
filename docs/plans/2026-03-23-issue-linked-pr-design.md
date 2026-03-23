# Issue Linked PR Design

**Goal:** Keep issue labels unchanged after implementation work starts, rely on PR labels for downstream workflow, and skip issues that already have an open PR linked via `Fixes/Closes/Resolves`.

## Decisions

- Issue tasks stay in local state `agent-issue`; worker implementation success must not relabel or transition the issue itself.
- New implementation PRs must include `Fixes #<issue_number>` in the PR description so GitHub closes the issue on merge.
- Sync computes issue-to-open-PR links from GitHub open PR bodies and stores a local `has_open_linked_pr` flag on issue tasks.
- Task claiming skips issue tasks where `has_open_linked_pr` is true.
- Closed PRs do not block issue processing.
- GitHub remains authoritative: sync rewrites the linked-PR flag from current open PR data each cycle.

## Validation

- Issue implementation success leaves the issue in `agent-issue` and makes no GitHub label edit.
- `claim_next_task()` skips issues that have an open linked PR.
- Sync clears the linked-PR block when the open PR disappears.
- Implement prompt tells Codex to include `Fixes #<issue_number>` in the new PR body.
