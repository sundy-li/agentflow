# Parallel Scheduler And Recovery Design

**Goal:** Run multiple tasks in parallel per scheduling cycle, and resume unfinished tasks after service restart by clearing stale local locks.

## Decisions

- Add scheduler-level parallelism through configuration.
- Default parallelism is `4`.
- Keep the existing SQLite lock acquisition model as the single task-dispatch authority.
- On service startup, clear persisted locks for the active repo so unfinished tasks can be scheduled again immediately.

## Runtime Model

- Each scheduler tick does one GitHub sync.
- After sync, the scheduler starts up to `max_parallel_tasks` concurrent `process_one()` calls.
- Each call still claims work via SQLite, so duplicate task execution remains prevented by the database update guard.
- The scheduler waits for the batch to finish before the next tick can run.

## Restart Recovery

- Startup recovery only clears `locked_by` and `locked_until` for tasks in the active repo.
- Task state is not changed during recovery.
- This assumes single-instance deployment, which the user explicitly accepted.

## Test Coverage

- Config default for `max_parallel_tasks` is `4`.
- Scheduler dispatches up to the configured parallelism.
- Startup recovery clears stale task locks for the active repo.
