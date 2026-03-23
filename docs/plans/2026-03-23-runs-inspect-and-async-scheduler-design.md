# Runs Inspect And Async Scheduler Design

**Goal:** Add CLI commands for viewing run history and Codex output, while making scheduler ticks non-blocking so long-running Codex jobs do not block future dispatch cycles.

## Decisions

- Add `runs` and `inspect` commands to `app.cli`.
- Persist run log path at run creation time so running jobs can be inspected live.
- `inspect <run_id> --follow` tails the persisted log file until the run finishes and no new output is appended.
- Refactor scheduler dispatch to submit worker jobs to a persistent thread pool and return immediately.
- Keep `max_instances=1` for the tick job; once tick becomes quick, skipped-tick warnings from long-running worker jobs should stop.

## Validation

- CLI `runs` shows running and completed runs.
- CLI `inspect` prints saved Codex output.
- CLI `inspect --follow` can stream output for a run that is still in progress.
- Scheduler tick returns without waiting for blocked workers to finish.
