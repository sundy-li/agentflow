from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.config import AppSettings, CodexSettings, DatabaseSettings, RepoSettings, SchedulerSettings, UISettings
from app.db import connect_db, run_migrations
from app.main import create_app
from app.repository import Repository


def test_app_startup_clears_stale_locks_for_active_repo(tmp_path):
    db_path = tmp_path / "startup.db"
    run_migrations(str(db_path))
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=101,
        title="Recover me",
        url="https://example.com/issue/101",
        labels=["agent-issue"],
        state="agent-issue",
    )
    locked_until = (datetime.utcnow() + timedelta(minutes=30)).replace(microsecond=0).isoformat() + "Z"
    with connect_db(str(db_path)) as conn:
        conn.execute(
            "UPDATE tasks SET locked_by = ?, locked_until = ? WHERE id = ?",
            ("old-worker", locked_until, int(task["id"])),
        )
        conn.commit()

    settings = AppSettings(
        database=DatabaseSettings(path=str(db_path)),
        scheduler=SchedulerSettings(enabled=False, poll_interval_seconds=60),
        codex=CodexSettings(command="codex", args=[], timeout_seconds=60),
        ui=UISettings(refresh_seconds=1),
        repos=[RepoSettings(name="demo", full_name="owner/repo", enabled=True)],
        run_logs_dir=str(tmp_path / "runs"),
    )
    app = create_app(settings=settings)

    with TestClient(app):
        recovered = app.state.repository.get_task(task["id"])
        assert recovered["locked_by"] is None
        assert recovered["locked_until"] is None
