import threading
import time
from pathlib import Path

import pytest

from app.config import CodexSettings
from app.repository import Repository
from app.services.codex_runner import CodexRunner


def test_build_prompt_uses_worktree_template_for_implement_mode():
    prompt = CodexRunner._build_prompt(
        {
            "title": "Run task",
            "url": "https://example.com/issue/3",
            "github_number": 3,
            "repo_full_name": "sundy-li/agentflow",
            "repo_forked": "sundy-li/agentflow-fork",
            "repo_default_branch": "main",
        },
        mode="implement",
    )

    assert "Implement the GitHub issue." in prompt
    assert "Title: Run task" in prompt
    assert "URL: https://example.com/issue/3" in prompt
    assert "Use git worktree to create a dedicated worktree" in prompt
    assert "Create a PR from fork 'sundy-li/agentflow-fork'" in prompt
    assert "Fixes #3" in prompt


def test_build_prompt_uses_worktree_template_for_fix_mode():
    prompt = CodexRunner._build_prompt(
        {
            "title": "Fix task",
            "url": "https://example.com/pr/5",
            "repo_full_name": "sundy-li/agentflow",
            "repo_forked": "sundy-li/agentflow-fork",
            "repo_default_branch": "main",
        },
        mode="fix",
    )

    assert "Address requested changes for this task." in prompt
    assert "Title: Fix task" in prompt
    assert "Use git worktree to reuse or create a dedicated worktree" in prompt
    assert "Ensure PR targets upstream 'sundy-li/agentflow' branch 'main'." in prompt


def test_build_prompt_does_not_require_worktree_for_review_mode():
    prompt = CodexRunner._build_prompt(
        {
            "title": "Review task",
            "url": "https://example.com/pr/4",
            "repo_full_name": "sundy-li/agentflow",
            "repo_default_branch": "main",
        },
        mode="review",
    )

    assert "Review this pull request and decide pass/fail." in prompt
    assert "Respond with REVIEW_RESULT:PASS or REVIEW_RESULT:FAIL." in prompt
    assert "REVIEW_RESULT:PASS maps to GitHub label 'agent-approved'" in prompt
    assert "git worktree" not in prompt


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
    assert "Use git worktree to create a dedicated worktree" in run_row["prompt"]
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


def test_codex_runner_uses_repo_workspace_as_cwd(tmp_path, repository: Repository, monkeypatch):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=7,
        title="Workspace task",
        url="https://example.com/issue/7",
        labels=["agent-issue"],
        state="agent-issue",
    )
    task_with_repo = dict(task)
    task_with_repo["repo_workspace"] = str(workspace)

    captured = {}

    def fake_run_with_pty(command, log_file, timeout_seconds, cwd=None):
        captured["cwd"] = cwd
        log_file.write(b"workspace ok\n")
        return 0

    monkeypatch.setattr(CodexRunner, "_run_with_pty", staticmethod(fake_run_with_pty))
    runner = CodexRunner(repository, CodexSettings(command="codex", args=[], timeout_seconds=20), str(tmp_path / "runs"))

    result = runner.run_codex(task_with_repo, mode="implement")

    assert result.exit_code == 0
    assert captured["cwd"] == str(workspace)


def test_run_with_pty_attaches_terminal_to_stdin(tmp_path, repository: Repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=8,
        title="TTY task",
        url="https://example.com/issue/8",
        labels=["agent-issue"],
        state="agent-issue",
    )
    run_logs = tmp_path / "runs"
    settings = CodexSettings(
        command="python3",
        args=["-c", "import os,sys; print('stdin_tty=' + str(os.isatty(0))); sys.exit(0 if os.isatty(0) else 1)"],
        timeout_seconds=20,
    )
    runner = CodexRunner(repository, settings, str(run_logs))

    result = runner.run_codex(task, mode="implement")

    assert result.exit_code == 0
    log_text = Path(result.output_path).read_text(encoding="utf-8")
    assert "stdin_tty=True" in log_text


def test_codex_runner_uses_exec_subcommand_for_codex_cli(tmp_path, repository: Repository, monkeypatch):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=9,
        title="CLI mode task",
        url="https://example.com/issue/9",
        labels=["agent-issue"],
        state="agent-issue",
    )
    captured = {}

    def fake_run_with_pty(command, log_file, timeout_seconds, cwd=None):
        captured["command"] = command
        log_file.write(b"ok\n")
        return 0

    monkeypatch.setattr(CodexRunner, "_run_with_pty", staticmethod(fake_run_with_pty))
    runner = CodexRunner(
        repository,
        CodexSettings(
            command="codex",
            args=["--dangerously-bypass-approvals-and-sandbox"],
            timeout_seconds=20,
        ),
        str(tmp_path / "runs"),
    )

    result = runner.run_codex(task, mode="implement")

    assert result.exit_code == 0
    assert captured["command"][0] == "codex"
    assert captured["command"][1] == "exec"
    assert "--dangerously-bypass-approvals-and-sandbox" in captured["command"]


def test_codex_runner_shutdown_stops_active_run(tmp_path, repository: Repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=10,
        title="Shutdown task",
        url="https://example.com/issue/10",
        labels=["agent-issue"],
        state="agent-issue",
    )
    runner = CodexRunner(
        repository,
        CodexSettings(
            command="python3",
            args=["-c", "import time; print('started', flush=True); time.sleep(30)"],
            timeout_seconds=60,
        ),
        str(tmp_path / "runs"),
    )
    shutdown = runner.shutdown
    result_holder = {}

    thread = threading.Thread(target=lambda: result_holder.setdefault("result", runner.run_codex(task, mode="implement")))
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        runs = repository.list_runs(repo_id, limit=1)
        if runs and runs[0]["finished_at"] is None:
            break
        time.sleep(0.05)

    shutdown()
    thread.join(timeout=5)

    assert not thread.is_alive()
    result = result_holder["result"]
    run_row = repository.get_run(result.run_id)
    assert run_row is not None
    assert run_row["finished_at"] is not None
    assert run_row["result"] == "failed"
    assert "shutdown requested" in Path(result.output_path).read_text(encoding="utf-8")
