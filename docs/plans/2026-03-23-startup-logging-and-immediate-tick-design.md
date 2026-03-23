# Startup Logging And Immediate Tick Design

**Goal:** Make application INFO logs visible under Uvicorn and run the first scheduler tick immediately at service startup.

## Decisions

- Reuse Uvicorn's error logger handlers for the `app` logger namespace.
- Keep application logs at `INFO` by default.
- Schedule the interval job with an immediate `next_run_time` so the first tick runs as soon as the scheduler starts.
- Add scheduler INFO logs for start and tick summaries.

## Why

- Worker logs already exist, but they are not visible because the `app.*` logger hierarchy does not have a configured handler under the current Uvicorn launch path.
- The scheduler currently waits `poll_interval_seconds` before the first run, which makes startup look idle even when runnable tasks exist.

## Validation

- `configure_app_logging()` attaches `app` logger to Uvicorn handlers.
- `AgentScheduler.start()` sets a non-null immediate `next_run_time`.
