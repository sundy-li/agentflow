# Running State And Lock Design

**Goal:** Make the board reflect real running tasks and prevent duplicate task claims while the current process is still executing a task.

## Problem

- The board currently derives `Locked` entirely from `tasks.locked_by` / `tasks.locked_until`.
- Task locks expire after 300 seconds.
- Coding agent runs can last much longer than 300 seconds.
- Once the lock expires, the same task can be claimed again in the same process even though the original run is still alive.
- This causes two separate problems:
  - duplicate runs for the same task
  - board output that shows `idle` even while an unfinished run still exists

## Requirements

- Prevent duplicate claims only while the current process is still executing the task.
- After a service restart, previously unfinished runs must not block reclaiming the task.
- Board output should prefer actual run state over stale lock fields.
- Keep changes minimal.
- Avoid schema changes.

## Architecture

### In-Process Active Task Tracking

- `WorkerService` will maintain an in-memory set of active task ids for the current process.
- A task id is added immediately after a claim succeeds.
- The task id is removed in `finally`, after the worker finishes and releases the task lock.
- `WorkerService` exposes `active_task_ids()` so the scheduler can ask which tasks are already running in this process.

### Claim Exclusion

- `Repository.claim_next_task()` will accept an optional `exclude_task_ids` list.
- Candidate selection will exclude those task ids in SQL.
- `AgentScheduler` will pass `worker_service.active_task_ids()` when dispatching each worker slot.
- This prevents the same task from being claimed again while a local worker is still running, even if `locked_until` has already expired.

### Board Running State

- Add a repository query that returns the task ids with unfinished runs for a repo.
- `render_board()` will ask the repository for this set and use it when computing the `Locked` column.
- Running-state priority:
  1. unfinished run for the task => `running`
  2. otherwise, unexpired task lock => `running`
  3. otherwise => `idle`

This corrects the board for current-process and stale-lock drift without turning unfinished runs into a cross-process lock.

## Non-Goals

- No schema migration
- No heartbeat table
- No cross-process run ownership
- No cleanup of historical unfinished runs

## Testing

- Repository tests for `exclude_task_ids`
- CLI tests for unfinished-run-driven `running` state and expired-lock `idle`
- Scheduler integration test proving active task exclusion prevents duplicate claim in the same process
