import sqlite3

from app.db import connect_db


def test_init_schema_creates_core_tables(db_path):
    with connect_db(db_path) as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"repos", "tasks", "task_events", "runs"}.issubset(names)


def test_upsert_task_and_event(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")

    created = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=12,
        title="initial",
        url="https://example.com/12",
        labels=["agent-issue"],
        state="agent-issue",
    )
    updated = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=12,
        title="changed",
        url="https://example.com/12",
        labels=["agent-issue"],
        state="agent-issue",
    )
    assert created["id"] == updated["id"]
    assert updated["title"] == "changed"

    event_id = repository.insert_task_event(
        task_id=updated["id"],
        from_state="agent-issue",
        to_state="agent-reviewable",
        reason="unit-test",
        actor="tester",
        source="pytest",
    )
    assert isinstance(event_id, int)
    events = repository.get_task_events(updated["id"])
    assert events[-1]["to_state"] == "agent-reviewable"

