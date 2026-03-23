# PR Review Latency Design

**Goal:** Delay PR review execution until a configurable latency window has elapsed since the most recently observed PR head push.

## Decisions

- Use GitHub PR `headRefOid` as the signal for a new push.
- Record the local observation time when the PR head SHA first appears or changes.
- Apply latency only to `agent-reviewable` PR tasks.
- Issues and `agent-changed` fix tasks remain immediately runnable.

## Data Model

- Add `pr_head_sha` to `tasks`.
- Add `pr_last_push_observed_at` to `tasks`.
- Preserve these values across ordinary syncs when the head SHA is unchanged.

## Scheduling Behavior

- Add `scheduler.review_latency_hours` with default `0`.
- A reviewable PR is claimable only when:
- it is not stale
- it is unlocked
- `pr_last_push_observed_at` is null, or
- `pr_last_push_observed_at <= now - review_latency_hours`

## Sync Behavior

- Sync PRs with `headRefOid`.
- On first observation, save the SHA and set `pr_last_push_observed_at` to sync time.
- On subsequent syncs:
- if SHA is unchanged, preserve `pr_last_push_observed_at`
- if SHA changed, update `pr_last_push_observed_at` to current sync time

## Upgrade Strategy

- Fresh databases get the new columns from the base schema.
- Existing databases are upgraded in `run_migrations()` by checking `tasks` columns and adding any missing review-latency columns.

## Test Coverage

- Config default for `review_latency_hours`
- PR query requests `headRefOid`
- Sync stores and refreshes `pr_head_sha` and `pr_last_push_observed_at`
- Claim filtering blocks reviewable PRs until latency expires
