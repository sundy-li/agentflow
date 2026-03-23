import logging

from app.config import RepoSettings
from app.repository import Repository
from app.services.codex_runner import RunResult
from app.services.worker_service import WorkerService


class FakeGH:
    def __init__(self):
        self.calls = []

    def set_labels(self, repo_full_name, item_type, number, add_labels, remove_labels):
        self.calls.append(
            {
                "repo_full_name": repo_full_name,
                "item_type": item_type,
                "number": number,
                "add_labels": add_labels,
                "remove_labels": remove_labels,
            }
        )


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.index = 0
        self.calls = []

    def run_codex(self, task, mode):
        self.calls.append({"task": dict(task), "mode": mode})
        result = self.results[self.index]
        self.index += 1
        return result


def test_issue_task_success_keeps_issue_label_state_and_blocks_requeue_until_sync(repository: Repository):
    repo_cfg = RepoSettings(
        name="demo",
        full_name="owner/repo",
        forked="my-user/agentflow",
        default_branch="main",
        enabled=True,
    )
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=10,
        title="Issue",
        url="https://example.com/issue/10",
        labels=["agent-issue"],
        state="agent-issue",
    )
    gh = FakeGH()
    runner = FakeRunner([RunResult(run_id=1, exit_code=0, output_path="/tmp/1.log", result="success")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    assert processed["state"] == "agent-issue"
    assert processed["has_open_linked_pr"] is True
    assert gh.calls == []
    assert runner.calls[0]["task"]["repo_full_name"] == "owner/repo"
    assert runner.calls[0]["task"]["repo_forked"] == "my-user/agentflow"
    assert runner.calls[0]["task"]["repo_default_branch"] == "main"


def test_reviewable_task_moves_to_changed_on_failed_review(repository: Repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=11,
        title="PR",
        url="https://example.com/pr/11",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    gh = FakeGH()
    runner = FakeRunner([RunResult(run_id=2, exit_code=1, output_path="/tmp/2.log", result="failed")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    assert processed["state"] == "agent-changed"
    assert gh.calls[0]["add_labels"] == ["agent-changed"]


def test_changed_task_returns_to_reviewable_after_fix(repository: Repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=12,
        title="Fix PR",
        url="https://example.com/pr/12",
        labels=["agent-changed"],
        state="agent-changed",
    )
    gh = FakeGH()
    runner = FakeRunner([RunResult(run_id=3, exit_code=0, output_path="/tmp/3.log", result="success")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    assert processed["state"] == "agent-reviewable"
    assert gh.calls[0]["add_labels"] == ["agent-reviewable"]


def test_worker_logs_claimed_task(repository: Repository, caplog):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=13,
        title="Logged issue",
        url="https://example.com/issue/13",
        labels=["agent-issue"],
        state="agent-issue",
    )
    gh = FakeGH()
    runner = FakeRunner([RunResult(run_id=4, exit_code=0, output_path="/tmp/4.log", result="success")])
    worker = WorkerService(repository, gh, runner)

    app_logger = logging.getLogger("app")
    app_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="app"):
            worker.process_one(repo_cfg)
    finally:
        app_logger.removeHandler(caplog.handler)

    assert "claimed task" in caplog.text
    assert "#13" in caplog.text
    assert "implement" in caplog.text
