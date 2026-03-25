# GitHub State Filtering Design

## Summary

Track the remote lifecycle of every issue and pull request separately from the local workflow state. Closed or merged GitHub items must remain in SQLite for history, but they must not appear on the board and must never be claimed for new work.

## Decisions

- Add a `github_state` task field that is fully owned by GitHub sync.
- Keep local workflow `state` unchanged. It still models `agent-issue`, `agent-reviewable`, `agent-changed`, and `agent-approved`.
- Use `github_state='open'` for active queue items.
- Use `github_state='closed'` for closed issues and PRs.
- Use `github_state='merged'` for merged PRs.
- Preserve closed or merged tasks in SQLite so runs, events, and worktree cleanup history remain intact.
- Filter non-open tasks out of board queries and task claiming.

## Flow

1. Sync fetches open agent issues and open agent PRs from GitHub.
2. Any item returned in those open lists is persisted with `github_state='open'`.
3. For tracked tasks that disappear from the open agent lists, sync checks the remote GitHub state directly.
4. If GitHub reports `closed` or `merged`, sync updates `github_state` to that terminal state.
5. If GitHub still reports `open`, sync falls back to the current stale-marking behavior.
6. Board queries return only tasks with `github_state='open'`.
7. Claim queries return only tasks with `github_state='open'`.

## Error Handling

- If direct GitHub state lookup fails, keep the local `github_state` unchanged and continue with the current stale-marking behavior.
- Closed and merged tasks remain available for history and cleanup processing; they are only removed from active board and claim paths.

## Testing

- Repository tests verify board and claim filters on `github_state`.
- Sync tests verify remote state overwrite for open, closed, and merged items.
- GH client tests verify direct issue and PR state lookups.
- CLI and board API tests verify closed and merged tasks are hidden.
