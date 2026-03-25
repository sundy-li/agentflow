import threading
import time
from datetime import datetime, timedelta

from app.cli import main
from app.db import connect_db, run_migrations
from app.repository import Repository


class FakeBoardSyncService:
    def __init__(self, repository, updater=None, error=None):
        self.repository = repository
        self.updater = updater
        self.error = error
        self.calls = 0

    def sync_once(self, repo_cfg):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.updater is not None:
            self.updater(self.repository, repo_cfg)
        return {"issues": 0, "prs": 0, "stale": 0, "stale_pr_task_ids": []}


def test_cli_board_renders_tasks_by_state(tmp_path, capsys):
    db_path = tmp_path / "agentflow.db"
    config_path = tmp_path / "agentflow.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=1,
        title="Implement feature",
        url="https://example.com/issue/1",
        labels=["agent-issue"],
        state="agent-issue",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=2,
        title="Pending review",
        url="https://example.com/pr/2",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    with connect_db(str(db_path)) as conn:
        locked_until = (datetime.utcnow() + timedelta(minutes=10)).replace(microsecond=0).isoformat() + "Z"
        conn.execute(
            "UPDATE tasks SET locked_by = ?, locked_until = ? WHERE id = ?",
            ("worker-1", locked_until, int(issue["id"])),
        )
        conn.commit()

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Repo: owner/repo" in output
    assert "[agent-issue]" in output
    assert "[agent-reviewable]" in output
    assert "[agent-changed]" in output
    assert "[agent-approved]" in output
    assert "Implement feature" in output
    assert "running" in output


def test_cli_board_marks_unfinished_run_as_running_without_lock(tmp_path, capsys):
    db_path = tmp_path / "agentflow.db"
    config_path = tmp_path / "agentflow.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=13,
        title="Unfinished run task",
        url="https://example.com/issue/13",
        labels=["agent-issue"],
        state="agent-issue",
    )
    log_path = tmp_path / "run.log"
    log_path.write_text("running\n", encoding="utf-8")
    repository.create_run(task["id"], "implement", "prompt", "cmd", output_path=str(log_path))

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Unfinished run task" in output
    assert "running" in output


def test_cli_board_treats_expired_lock_without_run_as_idle(tmp_path, capsys):
    db_path = tmp_path / "expired.db"
    config_path = tmp_path / "expired.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=14,
        title="Expired lock task",
        url="https://example.com/issue/14",
        labels=["agent-issue"],
        state="agent-issue",
    )
    with connect_db(str(db_path)) as conn:
        expired_at = (datetime.utcnow() - timedelta(minutes=10)).replace(microsecond=0).isoformat() + "Z"
        conn.execute(
            "UPDATE tasks SET locked_by = ?, locked_until = ? WHERE id = ?",
            ("worker-1", expired_at, int(task["id"])),
        )
        conn.commit()

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Expired lock task" in output
    assert "idle" in output


def test_cli_board_marks_blocked_tasks(tmp_path, capsys):
    db_path = tmp_path / "blocked.db"
    config_path = tmp_path / "blocked.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=15,
        title="Blocked task",
        url="https://example.com/issue/15",
        labels=["agent-issue"],
        state="agent-issue",
        blocked_reason="missing_pr_after_implement",
    )

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Blocked task" in output
    assert "blocked" in output


def test_cli_board_uses_config_path(tmp_path, capsys):
    db_path = tmp_path / "other.db"
    config_path = tmp_path / "other.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: another/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "another/repo")
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=9,
        title="Config selected",
        url="https://example.com/issue/9",
        labels=["agent-issue"],
        state="agent-issue",
    )

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "another/repo" in output


def test_cli_board_hides_closed_or_merged_tasks(tmp_path, capsys):
    db_path = tmp_path / "closed.db"
    config_path = tmp_path / "closed.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=201,
        title="Open issue",
        url="https://example.com/issue/201",
        labels=["agent-issue"],
        state="agent-issue",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=202,
        title="Closed issue",
        url="https://example.com/issue/202",
        labels=["agent-issue"],
        state="agent-issue",
        github_state="closed",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=203,
        title="Merged pr",
        url="https://example.com/pr/203",
        labels=["agent-approved"],
        state="agent-approved",
        github_state="merged",
    )

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Open issue" in output
    assert "Closed issue" not in output
    assert "Merged pr" not in output


def test_cli_board_syncs_before_render(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "sync-first.db"
    config_path = tmp_path / "sync-first.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    stale_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=301,
        title="Should disappear after sync",
        url="https://example.com/issue/301",
        labels=["agent-issue"],
        state="agent-issue",
    )
    with connect_db(str(db_path)) as conn:
        conn.execute(
            "UPDATE tasks SET is_stale = 1, github_state = 'open' WHERE id = ?",
            (int(stale_issue["id"]),),
        )
        conn.commit()

    sync_holder = {}

    def factory(repository, gh_client):
        service = FakeBoardSyncService(
            repository,
            updater=lambda repo, _repo_cfg: repo.set_task_github_state(int(stale_issue["id"]), "closed", is_stale=False),
        )
        sync_holder["service"] = service
        return service

    monkeypatch.setattr("app.cli.GHClient", lambda: object())
    monkeypatch.setattr("app.cli.SyncService", factory)

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert sync_holder["service"].calls == 1
    assert "Should disappear after sync" not in output


def test_cli_board_warns_and_falls_back_when_sync_fails(tmp_path, capsys, monkeypatch):
    db_path = tmp_path / "sync-fail.db"
    config_path = tmp_path / "sync-fail.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=302,
        title="Local board fallback",
        url="https://example.com/issue/302",
        labels=["agent-issue"],
        state="agent-issue",
    )

    monkeypatch.setattr("app.cli.GHClient", lambda: object())
    monkeypatch.setattr(
        "app.cli.SyncService",
        lambda repository, gh_client: FakeBoardSyncService(repository, error=RuntimeError("boom")),
    )

    exit_code = main(["--config", str(config_path), "board"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Local board fallback" in captured.out
    assert "Warning: board sync failed" in captured.err


def test_cli_runs_renders_running_and_finished_runs(tmp_path, capsys):
    db_path = tmp_path / "runs.db"
    config_path = tmp_path / "runs.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=10,
        title="Tracked run",
        url="https://example.com/issue/10",
        labels=["agent-issue"],
        state="agent-issue",
    )
    log1 = tmp_path / "1.log"
    log1.write_text("run one\n", encoding="utf-8")
    run1 = repository.create_run(task["id"], "implement", "prompt", "cmd", output_path=str(log1))
    repository.finish_run(run1, 0, str(log1), "success")

    log2 = tmp_path / "2.log"
    log2.write_text("run two\n", encoding="utf-8")
    repository.create_run(task["id"], "review", "prompt", "cmd", output_path=str(log2))

    exit_code = main(["--config", str(config_path), "runs"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Run" in output
    assert "running" in output
    assert "done" in output
    assert str(run1) in output


def test_cli_inspect_prints_run_output(tmp_path, capsys):
    db_path = tmp_path / "inspect.db"
    config_path = tmp_path / "inspect.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=11,
        title="Inspect me",
        url="https://example.com/issue/11",
        labels=["agent-issue"],
        state="agent-issue",
    )
    log_path = tmp_path / "inspect.log"
    log_path.write_text("hello inspect\n", encoding="utf-8")
    run_id = repository.create_run(task["id"], "implement", "prompt", "cmd", output_path=str(log_path))
    repository.finish_run(run_id, 0, str(log_path), "success")

    exit_code = main(["--config", str(config_path), "inspect", str(run_id)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Run: {0}".format(run_id) in output
    assert "hello inspect" in output


def test_cli_inspect_follow_streams_until_run_finishes(tmp_path, capsys):
    db_path = tmp_path / "follow.db"
    config_path = tmp_path / "follow.yaml"
    run_migrations(str(db_path))
    config_path.write_text(
        "\n".join(
            [
                "database:",
                "  path: {0}".format(db_path),
                "scheduler:",
                "  enabled: false",
                "repos:",
                "  - name: demo",
                "    full_name: owner/repo",
                "    enabled: true",
            ]
        ),
        encoding="utf-8",
    )
    repository = Repository(str(db_path))
    repo_id = repository.ensure_repo("demo", "owner/repo")
    task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=12,
        title="Follow me",
        url="https://example.com/issue/12",
        labels=["agent-issue"],
        state="agent-issue",
    )
    log_path = tmp_path / "follow.log"
    log_path.write_text("line1\n", encoding="utf-8")
    run_id = repository.create_run(task["id"], "implement", "prompt", "cmd", output_path=str(log_path))

    def writer():
        time.sleep(0.2)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write("line2\n")
        repository.finish_run(run_id, 0, str(log_path), "success")

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        exit_code = main(["--config", str(config_path), "inspect", str(run_id), "--follow"])
    finally:
        thread.join(timeout=2)

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "line1" in output
    assert "line2" in output
