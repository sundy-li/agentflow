from app.config import CodexSettings
from app.repository import Repository
from app.services.codex_runner import CodexRunner


def test_codex_runner_records_run_and_output(tmp_path, repository: Repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=3,
        title="Run task",
        url="https://example.com/issue/3",
        labels=["agent-issue"],
        state="agent-issue",
    )
    run_logs = tmp_path / "runs"
    settings = CodexSettings(
        command="python3",
        args=["-c", "print('hello from codex');"],
        timeout_seconds=20,
    )
    runner = CodexRunner(repository, settings, str(run_logs))
    task_with_repo = dict(task)
    task_with_repo["repo_full_name"] = "sundy-li/agentflow"
    task_with_repo["repo_forked"] = "sundy-li/agentflow-fork"
    task_with_repo["repo_default_branch"] = "main"
    result = runner.run_codex(task_with_repo, mode="implement")

    assert result.exit_code == 0
    assert result.result == "success"
    run_row = repository.get_run(result.run_id)
    assert run_row is not None
    assert run_row["exit_code"] == 0
    assert run_row["output_path"]
    assert "Push the branch to fork repository 'sundy-li/agentflow-fork'" in run_row["prompt"]
    assert "targeting 'main'" in run_row["prompt"]


def test_codex_runner_handles_nonzero_exit(tmp_path, repository: Repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=4,
        title="Review task",
        url="https://example.com/pr/4",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    run_logs = tmp_path / "runs"
    settings = CodexSettings(
        command="python3",
        args=["-c", "import sys; sys.exit(2)"],
        timeout_seconds=20,
    )
    runner = CodexRunner(repository, settings, str(run_logs))
    result = runner.run_codex(task, mode="review")

    assert result.exit_code == 2
    run_row = repository.get_run(result.run_id)
    assert run_row["result"] == "failed"
