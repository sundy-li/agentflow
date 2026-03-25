import logging
from pathlib import Path

from app.config import RepoSettings
from app.constants import RUNNABLE_STATES
from app.db import connect_db
from app.repository import Repository
from app.services.coding_agent_runner import RunResult
from app.services.worker_service import WorkerService


class FakeGH:
    def __init__(self, open_pr_link_responses=None):
        self.calls = []
        self.open_pr_link_responses = list(open_pr_link_responses or [[]])
        self.link_queries = 0

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

    def list_open_pr_links(self, repo_full_name):
        index = min(self.link_queries, len(self.open_pr_link_responses) - 1)
        self.link_queries += 1
        return list(self.open_pr_link_responses[index])


class FakeRunner:
    def __init__(self, results):
        self.results = list(results)
        self.index = 0
        self.calls = []

    def run_task(self, task, mode):
        self.calls.append({"task": dict(task), "mode": mode})
        result = self.results[self.index]
        self.index += 1
        return result

    def run_codex(self, task, mode):
        return self.run_task(task, mode)


def test_issue_task_success_records_linked_pr_without_retry(repository: Repository):
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
    gh = FakeGH(open_pr_link_responses=[[{"number": 101, "linked_issue_numbers": [10]}]])
    runner = FakeRunner([RunResult(run_id=1, exit_code=0, output_path="/tmp/1.log", result="success")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    assert processed["state"] == "agent-issue"
    assert processed["has_open_linked_pr"] is True
    assert processed["linked_pr_numbers"] == [101]
    assert processed["blocked_reason"] is None
    assert gh.calls == []
    assert len(runner.calls) == 1
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
    gh = FakeGH(open_pr_link_responses=[[{"number": 301, "linked_issue_numbers": [13]}]])
    runner = FakeRunner([RunResult(run_id=2, exit_code=1, output_path="/tmp/2.log", result="failed")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    assert processed["state"] == "agent-changed"
    assert gh.calls[0]["add_labels"] == ["agent-changed"]


def test_issue_task_retries_once_to_create_pull_request(repository: Repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", forked="my-user/agentflow", default_branch="main", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=14,
        title="Needs PR",
        url="https://example.com/issue/14",
        labels=["agent-issue"],
        state="agent-issue",
    )
    gh = FakeGH(open_pr_link_responses=[[], [{"number": 202, "linked_issue_numbers": [14]}]])
    runner = FakeRunner(
        [
            RunResult(run_id=5, exit_code=0, output_path="/tmp/5.log", result="success"),
            RunResult(run_id=6, exit_code=0, output_path="/tmp/6.log", result="success"),
        ]
    )
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)

    assert processed["has_open_linked_pr"] is True
    assert processed["linked_pr_numbers"] == [202]
    assert processed["blocked_reason"] is None
    assert len(runner.calls) == 2
    assert runner.calls[1]["task"]["pr_followup_only"] is True


def test_issue_task_is_blocked_when_followup_still_has_no_pull_request(repository: Repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", forked="my-user/agentflow", default_branch="main", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=15,
        title="Still missing PR",
        url="https://example.com/issue/15",
        labels=["agent-issue"],
        state="agent-issue",
    )
    gh = FakeGH(open_pr_link_responses=[[], []])
    runner = FakeRunner(
        [
            RunResult(run_id=7, exit_code=0, output_path="/tmp/7.log", result="success"),
            RunResult(run_id=8, exit_code=0, output_path="/tmp/8.log", result="success"),
        ]
    )
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-2")

    assert processed["blocked_reason"] == "missing_pr_after_implement"
    assert processed["has_open_linked_pr"] is False
    assert claimed is None
    events = repository.get_task_events(int(task["id"]))
    assert any(event["reason"] == "worker_implement_missing_pr_blocked" for event in events)


def test_blocked_issue_retries_pr_followup_with_previous_delivery_context(repository: Repository, tmp_path):
    repo_workspace = tmp_path / "repo"
    repo_workspace.mkdir()
    repo_cfg = RepoSettings(
        name="demo",
        full_name="owner/repo",
        forked="my-user/agentflow",
        default_branch="main",
        workspace=str(repo_workspace),
        enabled=True,
    )
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=16,
        title="Recover delivery",
        url="https://example.com/issue/16",
        labels=["agent-issue"],
        state="agent-issue",
        blocked_reason="missing_pr_after_implement",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET blocked_until = ? WHERE id = ?",
            ("2000-01-01T00:00:00Z", int(task["id"])),
        )
        conn.commit()

    previous_log = tmp_path / "previous-followup.log"
    previous_log.write_text(
        "\n".join(
            [
                "worktree 路径是 `/tmp/demo/.worktrees/issue-16-20260324-1200`",
                "分支是 `issue-16-20260324-1200`",
                "本地提交是 `0123456789abcdef0123456789abcdef01234567`",
            ]
        ),
        encoding="utf-8",
    )
    previous_run = repository.create_run(task["id"], "implement", "prompt", "cmd", output_path=str(previous_log))
    repository.finish_run(previous_run, 0, str(previous_log), "success")

    gh = FakeGH(open_pr_link_responses=[[], [{"number": 303, "linked_issue_numbers": [16]}]])
    runner = FakeRunner([RunResult(run_id=9, exit_code=0, output_path="/tmp/9.log", result="success")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)

    assert processed["blocked_reason"] is None
    assert processed["linked_pr_numbers"] == [303]
    assert len(runner.calls) == 1
    assert runner.calls[0]["task"]["pr_followup_only"] is True
    assert "issue-16-20260324-1200" in runner.calls[0]["task"]["delivery_context"]
    assert "/tmp/demo/.worktrees/issue-16-20260324-1200" in runner.calls[0]["task"]["delivery_context"]
    assert "0123456789abcdef0123456789abcdef01234567" in runner.calls[0]["task"]["delivery_context"]


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
    gh = FakeGH(open_pr_link_responses=[[{"number": 301, "linked_issue_numbers": [13]}]])
    runner = FakeRunner([RunResult(run_id=3, exit_code=0, output_path="/tmp/3.log", result="success")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    assert processed["state"] == "agent-reviewable"
    assert gh.calls[0]["add_labels"] == ["agent-reviewable"]


def test_issue_task_persists_worktree_path_from_run_log(repository: Repository, tmp_path):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", forked="my-user/agentflow", default_branch="main", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=17,
        title="Issue with worktree",
        url="https://example.com/issue/17",
        labels=["agent-issue"],
        state="agent-issue",
    )
    log_path = tmp_path / "implement.log"
    log_path.write_text(
        "worktree 路径是 `/tmp/demo/.worktrees/issue-17-20260324-1200`\n",
        encoding="utf-8",
    )
    gh = FakeGH(open_pr_link_responses=[[{"number": 304, "linked_issue_numbers": [17]}]])
    runner = FakeRunner([RunResult(run_id=10, exit_code=0, output_path=str(log_path), result="success")])
    worker = WorkerService(repository, gh, runner)

    processed = worker.process_one(repo_cfg)
    updated = repository.get_task(int(task["id"]))

    assert processed["linked_pr_numbers"] == [304]
    assert updated["worktree_path"] == "/tmp/demo/.worktrees/issue-17-20260324-1200"


def test_issue_task_persists_worktree_path_from_long_log_when_only_exec_cwd_mentions_it(repository: Repository, tmp_path):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", forked="my-user/agentflow", default_branch="main", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=18,
        title="Issue with long log",
        url="https://example.com/issue/18",
        labels=["agent-issue"],
        state="agent-issue",
    )
    expected_worktree = "/tmp/demo/.worktrees/issue-18-20260324-1200"
    log_path = tmp_path / "long-implement.log"
    log_path.write_text(
        "\n".join(
            [
                "OpenAI Codex",
                "exec",
                "/usr/bin/zsh -lc 'git status --short --branch' in {0}".format(expected_worktree),
                "succeeded",
                "x" * 130000,
            ]
        ),
        encoding="utf-8",
    )
    gh = FakeGH(open_pr_link_responses=[[{"number": 305, "linked_issue_numbers": [18]}]])
    runner = FakeRunner([RunResult(run_id=11, exit_code=0, output_path=str(log_path), result="success")])
    worker = WorkerService(repository, gh, runner)

    worker.process_one(repo_cfg)
    updated = repository.get_task(int(task["id"]))

    assert updated["worktree_path"] == expected_worktree


def test_load_recent_delivery_metadata_extracts_existing_worktree_from_followup_prompt(repository: Repository, tmp_path):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=19,
        title="Issue with followup prompt",
        url="https://example.com/issue/19",
        labels=["agent-issue"],
        state="agent-issue",
    )
    previous_log = tmp_path / "followup.log"
    previous_log.write_text(
        "\n".join(
            [
                "Previous delivery context:",
                "- Existing worktree: /tmp/demo/.worktrees/issue-19-20260324-1200",
                "- Previous run log: data/runs/example.log",
            ]
        ),
        encoding="utf-8",
    )
    previous_run = repository.create_run(task["id"], "implement", "prompt", "cmd", output_path=str(previous_log))
    repository.finish_run(previous_run, 0, str(previous_log), "success")

    worker = WorkerService(repository, FakeGH(), FakeRunner([]))
    metadata = worker._load_recent_delivery_metadata(int(task["id"]))

    assert metadata["worktree"] == "/tmp/demo/.worktrees/issue-19-20260324-1200"


def test_extract_worktree_path_ignores_followup_prompt_text_without_real_path():
    text = (
        "Previous delivery context:\\n"
        "- Existing worktree: \\n\\n"
        "- Existing branch: issue-20-20260324-1200\\n"
        "- Existing commit: 0123456789abcdef0123456789abcdef01234567"
    )

    assert WorkerService._extract_worktree_path(text) == ""


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
    gh = FakeGH(open_pr_link_responses=[[{"number": 301, "linked_issue_numbers": [13]}]])
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
