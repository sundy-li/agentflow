from fastapi.testclient import TestClient

from app.config import AppSettings, CodexSettings, DatabaseSettings, RepoSettings, SchedulerSettings, UISettings
from app.repository import Repository
from app.services.codex_runner import RunResult
from app.services.worker_service import WorkerService
from app.main import create_app


class FakeGH:
    def __init__(self):
        self.updated = []

    def set_labels(self, repo_full_name, item_type, number, add_labels, remove_labels):
        self.updated.append(
            {
                "repo_full_name": repo_full_name,
                "item_type": item_type,
                "number": number,
                "add_labels": add_labels,
                "remove_labels": remove_labels,
            }
        )


class FakeRunner:
    def __init__(self):
        self.results = [
            RunResult(run_id=1, exit_code=0, output_path="/tmp/1.log", result="success"),
            RunResult(run_id=2, exit_code=0, output_path="/tmp/2.log", result="pass"),
        ]
        self.index = 0

    def run_codex(self, task, mode):
        result = self.results[self.index]
        self.index += 1
        return result


def test_single_repo_happy_path(tmp_path):
    settings = AppSettings(
        database=DatabaseSettings(path=str(tmp_path / "e2e.db")),
        scheduler=SchedulerSettings(enabled=False, poll_interval_seconds=60),
        codex=CodexSettings(command="codex", args=[], timeout_seconds=60),
        ui=UISettings(refresh_seconds=1),
        repos=[RepoSettings(name="demo", full_name="owner/repo", enabled=True)],
        run_logs_dir=str(tmp_path / "runs"),
    )
    app = create_app(settings=settings)
    repository: Repository = app.state.repository
    repo_id = repository.ensure_repo("demo", "owner/repo")
    issue_task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=100,
        title="Implement feature",
        url="https://example.com/issue/100",
        labels=["agent-issue"],
        state="agent-issue",
    )
    pr_task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=101,
        title="Review PR",
        url="https://example.com/pr/101",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )

    fake_gh = FakeGH()
    fake_runner = FakeRunner()
    worker = WorkerService(repository, fake_gh, fake_runner)

    worker.process_one(settings.repos[0])
    # Keep issue task from being selected again in this test.
    repository.set_task_stale(issue_task["id"], True)
    worker.process_one(settings.repos[0])

    updated_issue = repository.get_task(issue_task["id"])
    updated_pr = repository.get_task(pr_task["id"])
    assert updated_issue["state"] == "agent-reviewable"
    assert updated_pr["state"] == "agent-approved"

    client = TestClient(app)
    board = client.get("/api/board").json()
    assert any(task["number"] == 100 for task in board["columns"]["agent-reviewable"])
    assert any(task["number"] == 101 for task in board["columns"]["agent-approved"])
    assert len(fake_gh.updated) == 2

