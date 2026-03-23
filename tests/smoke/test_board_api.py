from fastapi.testclient import TestClient

from app.config import AppSettings, CodexSettings, DatabaseSettings, RepoSettings, SchedulerSettings, UISettings
from app.main import create_app


def test_board_api_and_page(tmp_path):
    db_path = tmp_path / "board.db"
    settings = AppSettings(
        database=DatabaseSettings(path=str(db_path)),
        scheduler=SchedulerSettings(enabled=False, poll_interval_seconds=60),
        codex=CodexSettings(command="codex", args=[], timeout_seconds=60),
        ui=UISettings(refresh_seconds=1),
        repos=[RepoSettings(name="demo", full_name="owner/repo", enabled=True)],
        run_logs_dir=str(tmp_path / "runs"),
    )
    app = create_app(settings=settings)
    repository = app.state.repository
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=21,
        title="Board task",
        url="https://example.com/21",
        labels=["agent-issue"],
        state="agent-issue",
    )
    repository.insert_task_event(
        task_id=task["id"],
        from_state=None,
        to_state="agent-issue",
        reason="seed",
        actor="test",
        source="pytest",
    )

    client = TestClient(app)
    board_response = client.get("/api/board")
    assert board_response.status_code == 200
    data = board_response.json()
    assert data["repo"] == "owner/repo"
    assert len(data["columns"]["agent-issue"]) == 1

    event_response = client.get("/api/tasks/{0}/events".format(task["id"]))
    assert event_response.status_code == 200
    assert event_response.json()["events"][0]["reason"] == "seed"

    page_response = client.get("/board")
    assert page_response.status_code == 200
    assert "Agentflow Board" in page_response.text

