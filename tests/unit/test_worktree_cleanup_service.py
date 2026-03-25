from app.config import RepoSettings
from app.db import connect_db
from app.services.worktree_cleanup_service import WorktreeCleanupService


class FakeGHClient:
    def __init__(self, pr_states):
        self.pr_states = dict(pr_states)
        self.calls = []

    def get_pr_state(self, repo_full_name, number):
        self.calls.append({"repo_full_name": repo_full_name, "number": number})
        return self.pr_states[int(number)]


class RecordingGitRunner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, command, cwd):
        self.calls.append({"command": list(command), "cwd": cwd})
        result = self.results[len(self.calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result


def _mark_stale_pr(repository, task_id, worktree_path):
    with connect_db(repository.db_path) as conn:
        conn.execute(
            """
            UPDATE tasks
            SET is_stale = 1,
                worktree_path = ?
            WHERE id = ?
            """,
            (worktree_path, int(task_id)),
        )
        conn.commit()


def test_cleanup_service_removes_closed_pr_worktree_and_marks_success(repository, tmp_path):
    repo_workspace = tmp_path / "repo"
    repo_workspace.mkdir()
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", workspace=str(repo_workspace), enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=41,
        title="Closed PR",
        url="https://example.com/pr/41",
        labels=["agent-approved"],
        state="agent-approved",
    )
    _mark_stale_pr(repository, task["id"], "/tmp/repo/.worktrees/pr-41")

    gh = FakeGHClient({41: "closed"})
    git_runner = RecordingGitRunner(
        [
            "worktree /tmp/repo/.worktrees/pr-41\nHEAD abcdef\nbranch refs/heads/pr-41\n",
            "",
        ]
    )
    service = WorktreeCleanupService(repository, gh, git_runner=git_runner)

    service.cleanup_repo(repo_cfg, stale_pr_task_ids=[int(task["id"])])

    updated = repository.get_task(int(task["id"]))
    assert updated["worktree_removed_at"] is not None
    assert updated["worktree_cleanup_error"] is None
    assert [call["command"][:4] for call in git_runner.calls] == [
        ["git", "worktree", "list", "--porcelain"],
        ["git", "worktree", "remove", "/tmp/repo/.worktrees/pr-41"],
    ]


def test_cleanup_service_marks_missing_workspace_as_retryable_failure(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", workspace=None, enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=42,
        title="Merged PR",
        url="https://example.com/pr/42",
        labels=["agent-approved"],
        state="agent-approved",
    )
    _mark_stale_pr(repository, task["id"], "/tmp/repo/.worktrees/pr-42")

    service = WorktreeCleanupService(repository, FakeGHClient({42: "merged"}), git_runner=RecordingGitRunner([]))

    service.cleanup_repo(repo_cfg, stale_pr_task_ids=[int(task["id"])])

    updated = repository.get_task(int(task["id"]))
    assert updated["worktree_removed_at"] is None
    assert updated["worktree_cleanup_attempted_at"] is not None
    assert "workspace" in (updated["worktree_cleanup_error"] or "")


def test_cleanup_service_retries_failed_removal_on_later_tick(repository, tmp_path):
    repo_workspace = tmp_path / "repo"
    repo_workspace.mkdir()
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", workspace=str(repo_workspace), enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=43,
        title="Merged PR",
        url="https://example.com/pr/43",
        labels=["agent-approved"],
        state="agent-approved",
    )
    _mark_stale_pr(repository, task["id"], "/tmp/repo/.worktrees/pr-43")

    git_runner = RecordingGitRunner(
        [
            "worktree /tmp/repo/.worktrees/pr-43\n",
            RuntimeError("worktree busy"),
            "worktree /tmp/repo/.worktrees/pr-43\n",
            "",
        ]
    )
    service = WorktreeCleanupService(repository, FakeGHClient({43: "merged"}), git_runner=git_runner)

    service.cleanup_repo(repo_cfg, stale_pr_task_ids=[int(task["id"])])
    first = repository.get_task(int(task["id"]))
    service.cleanup_repo(repo_cfg, stale_pr_task_ids=[])
    second = repository.get_task(int(task["id"]))

    assert first["worktree_removed_at"] is None
    assert "busy" in (first["worktree_cleanup_error"] or "")
    assert second["worktree_removed_at"] is not None
    assert second["worktree_cleanup_error"] is None


def test_cleanup_service_marks_already_removed_worktree_without_remove_call(repository, tmp_path):
    repo_workspace = tmp_path / "repo"
    repo_workspace.mkdir()
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", workspace=str(repo_workspace), enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=44,
        title="Closed PR",
        url="https://example.com/pr/44",
        labels=["agent-approved"],
        state="agent-approved",
    )
    _mark_stale_pr(repository, task["id"], "/tmp/repo/.worktrees/pr-44")

    git_runner = RecordingGitRunner(["worktree /tmp/repo/.worktrees/some-other\n"])
    service = WorktreeCleanupService(repository, FakeGHClient({44: "closed"}), git_runner=git_runner)

    service.cleanup_repo(repo_cfg, stale_pr_task_ids=[int(task["id"])])

    updated = repository.get_task(int(task["id"]))
    assert updated["worktree_removed_at"] is not None
    assert len(git_runner.calls) == 1
