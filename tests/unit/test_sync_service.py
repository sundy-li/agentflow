from app.config import RepoSettings
from app.db import connect_db
from app.services.sync_service import SyncService


class FakeGHClient:
    def __init__(self, issues, prs, open_pr_links=None, issue_states=None, pr_states=None):
        self._issues = issues
        self._prs = prs
        self._open_pr_links = open_pr_links or []
        self._issue_states = issue_states or {}
        self._pr_states = pr_states or {}

    def list_agent_issues(self, repo_full_name):
        return list(self._issues)

    def list_agent_prs(self, repo_full_name):
        return list(self._prs)

    def list_open_pr_links(self, repo_full_name):
        return list(self._open_pr_links)

    def get_issue_state(self, repo_full_name, number):
        value = self._issue_states.get(int(number), "open")
        if isinstance(value, Exception):
            raise value
        return value

    def get_pr_state(self, repo_full_name, number):
        value = self._pr_states.get(int(number), "open")
        if isinstance(value, Exception):
            raise value
        return value


def test_sync_service_upserts_transitions_and_marks_stale(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    existing_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=2,
        title="Tracked issue",
        url="https://example.com/issue/2",
        labels=["agent-issue"],
        state="agent-issue",
    )
    existing_pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=7,
        title="Old PR",
        url="https://example.com/pr/7",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    stale_task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=99,
        title="Stale task",
        url="https://example.com/issue/99",
        labels=["agent-issue"],
        state="agent-issue",
    )
    stale_approved_task = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=88,
        title="Closed approved task",
        url="https://example.com/pr/88",
        labels=["agent-approved"],
        state="agent-approved",
    )

    gh = FakeGHClient(
        issues=[
            {
                "number": 1,
                "title": "New issue",
                "url": "https://example.com/issue/1",
                "labels": ["agent-issue"],
                "assignee": "bob",
            },
            {
                "number": 2,
                "title": "Tracked issue",
                "url": "https://example.com/issue/2",
                "labels": ["agent-approved"],
                "assignee": None,
            },
        ],
        prs=[
            {
                "number": 7,
                "title": "Old PR",
                "url": "https://example.com/pr/7",
                "labels": ["agent-changed"],
                "assignee": None,
                "head_sha": "sha-2",
            }
        ],
    )

    service = SyncService(repository, gh)
    summary = service.sync_once(repo_cfg)

    assert summary["issues"] == 2
    assert summary["prs"] == 1
    assert summary["stale"] == 2

    issue = repository.get_task_by_key(repo_id, "issue", 1)
    assert issue is not None
    assert issue["state"] == "agent-issue"
    assert issue["github_state"] == "open"

    approved_issue = repository.get_task_by_key(repo_id, "issue", 2)
    assert approved_issue["state"] == "agent-approved"
    assert approved_issue["github_state"] == "open"

    pr = repository.get_task_by_key(repo_id, "pr", 7)
    assert pr["state"] == "agent-changed"
    assert pr["github_state"] == "open"
    assert pr["pr_head_sha"] == "sha-2"
    assert pr["pr_last_push_observed_at"] is not None

    stale = repository.get_task(stale_task["id"])
    assert stale["is_stale"] is True

    stale_approved = repository.get_task(stale_approved_task["id"])
    assert stale_approved["is_stale"] is True

    issue_events = repository.get_task_events(existing_issue["id"])
    assert any(event["reason"] == "sync_label_override" for event in issue_events)

    events = repository.get_task_events(existing_pr["id"])
    assert any(event["reason"] == "sync_label_change" for event in events)


def test_sync_service_tracks_pr_head_sha_changes(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    first = FakeGHClient(
        issues=[],
        prs=[
            {
                "number": 5,
                "title": "Review me",
                "url": "https://example.com/pr/5",
                "labels": ["agent-reviewable"],
                "assignee": None,
                "head_sha": "sha-1",
            }
        ],
    )
    service = SyncService(repository, first)
    service.sync_once(repo_cfg)

    pr = repository.get_task_by_key(repo_id, "pr", 5)
    assert pr["pr_head_sha"] == "sha-1"
    first_observed = pr["pr_last_push_observed_at"]
    assert first_observed is not None

    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=5,
        title="Review me",
        url="https://example.com/pr/5",
        labels=["agent-reviewable"],
        state="agent-reviewable",
        last_synced_at=pr["last_synced_at"],
        is_stale=False,
    )

    from app.db import connect_db

    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET pr_head_sha = ?, pr_last_push_observed_at = ? WHERE repo_id = ? AND github_type = 'pr' AND github_number = ?",
            ("sha-1", "2000-01-01T00:00:00Z", repo_id, 5),
        )
        conn.commit()

    second = FakeGHClient(
        issues=[],
        prs=[
            {
                "number": 5,
                "title": "Review me",
                "url": "https://example.com/pr/5",
                "labels": ["agent-reviewable"],
                "assignee": None,
                "head_sha": "sha-1",
            }
        ],
    )
    SyncService(repository, second).sync_once(repo_cfg)
    unchanged = repository.get_task_by_key(repo_id, "pr", 5)
    assert unchanged["pr_last_push_observed_at"] == "2000-01-01T00:00:00Z"

    third = FakeGHClient(
        issues=[],
        prs=[
            {
                "number": 5,
                "title": "Review me",
                "url": "https://example.com/pr/5",
                "labels": ["agent-reviewable"],
                "assignee": None,
                "head_sha": "sha-2",
            }
        ],
    )
    SyncService(repository, third).sync_once(repo_cfg)
    changed = repository.get_task_by_key(repo_id, "pr", 5)
    assert changed["pr_head_sha"] == "sha-2"
    assert changed["pr_last_push_observed_at"] != "2000-01-01T00:00:00Z"


def test_sync_service_marks_issue_blocked_when_open_pr_links_it(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=8,
        title="Linked issue",
        url="https://example.com/issue/8",
        labels=["agent-issue"],
        state="agent-issue",
    )

    service = SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 8,
                    "title": "Linked issue",
                    "url": "https://example.com/issue/8",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[],
            open_pr_links=[{"number": 101, "linked_issue_numbers": [8]}],
        ),
    )

    service.sync_once(repo_cfg)

    issue = repository.get_task_by_key(repo_id, "issue", 8)
    assert issue is not None
    assert issue["state"] == "agent-issue"
    assert issue["has_open_linked_pr"] is True
    assert issue["linked_pr_numbers"] == [101]


def test_sync_service_preserves_blocked_issue_until_linked_pr_is_observed(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=9,
        title="Blocked issue",
        url="https://example.com/issue/9",
        labels=["agent-issue"],
        state="agent-issue",
        blocked_reason="missing_pr_after_implement",
    )

    service = SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 9,
                    "title": "Blocked issue",
                    "url": "https://example.com/issue/9",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[],
            open_pr_links=[],
        ),
    )
    service.sync_once(repo_cfg)

    blocked = repository.get_task_by_key(repo_id, "issue", 9)
    assert blocked is not None
    assert blocked["blocked_reason"] == "missing_pr_after_implement"
    assert blocked["has_open_linked_pr"] is False

    SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 9,
                    "title": "Blocked issue",
                    "url": "https://example.com/issue/9",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[],
            open_pr_links=[{"number": 201, "linked_issue_numbers": [9]}],
        ),
    ).sync_once(repo_cfg)

    unblocked = repository.get_task_by_key(repo_id, "issue", 9)
    assert unblocked is not None
    assert unblocked["blocked_reason"] is None
    assert unblocked["has_open_linked_pr"] is True
    assert unblocked["linked_pr_numbers"] == [201]


def test_sync_service_returns_stale_pr_task_ids_and_propagates_issue_worktree(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=21,
        title="Linked issue",
        url="https://example.com/issue/21",
        labels=["agent-issue"],
        state="agent-issue",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=31,
        title="Live PR",
        url="https://example.com/pr/31",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    stale_pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=32,
        title="Closed PR",
        url="https://example.com/pr/32",
        labels=["agent-approved"],
        state="agent-approved",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=33,
        title="Stale issue",
        url="https://example.com/issue/33",
        labels=["agent-issue"],
        state="agent-issue",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET worktree_path = ? WHERE id = ?",
            ("/tmp/repo/.worktrees/issue-21", int(issue["id"])),
        )
        conn.commit()

    summary = SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 21,
                    "title": "Linked issue",
                    "url": "https://example.com/issue/21",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[
                {
                    "number": 31,
                    "title": "Live PR",
                    "url": "https://example.com/pr/31",
                    "labels": ["agent-reviewable"],
                    "assignee": None,
                    "head_sha": "sha-31",
                }
            ],
            open_pr_links=[{"number": 31, "linked_issue_numbers": [21]}],
        ),
    ).sync_once(repo_cfg)

    synced_pr = repository.get_task_by_key(repo_id, "pr", 31)

    assert summary["stale_pr_task_ids"] == [int(stale_pr["id"])]
    assert synced_pr is not None
    assert synced_pr["worktree_path"] == "/tmp/repo/.worktrees/issue-21"


def test_sync_service_backfills_issue_worktree_from_recent_run_before_pr_propagation(repository, tmp_path):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=22,
        title="Linked issue with historical run",
        url="https://example.com/issue/22",
        labels=["agent-issue"],
        state="agent-issue",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=34,
        title="Live PR",
        url="https://example.com/pr/34",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    log_path = tmp_path / "historical-implement.log"
    expected_worktree = "/tmp/repo/.worktrees/issue-22-20260324-1200"
    log_path.write_text(
        "\n".join(
            [
                "OpenAI Codex",
                "/usr/bin/zsh -lc 'git status --short --branch' in {0}".format(expected_worktree),
                "x" * 130000,
            ]
        ),
        encoding="utf-8",
    )
    previous_run = repository.create_run(issue["id"], "implement", "prompt", "cmd", output_path=str(log_path))
    repository.finish_run(previous_run, 0, str(log_path), "success")

    summary = SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 22,
                    "title": "Linked issue with historical run",
                    "url": "https://example.com/issue/22",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[
                {
                    "number": 34,
                    "title": "Live PR",
                    "url": "https://example.com/pr/34",
                    "labels": ["agent-reviewable"],
                    "assignee": None,
                    "head_sha": "sha-34",
                }
            ],
            open_pr_links=[{"number": 34, "linked_issue_numbers": [22]}],
        ),
    ).sync_once(repo_cfg)

    synced_issue = repository.get_task_by_key(repo_id, "issue", 22)
    synced_pr = repository.get_task_by_key(repo_id, "pr", 34)

    assert summary["stale_pr_task_ids"] == []
    assert synced_issue is not None
    assert synced_pr is not None
    assert synced_issue["worktree_path"] == expected_worktree
    assert synced_pr["worktree_path"] == expected_worktree


def test_sync_service_replaces_invalid_worktree_paths_from_recent_run_before_pr_propagation(repository, tmp_path):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=23,
        title="Linked issue with invalid worktree",
        url="https://example.com/issue/23",
        labels=["agent-issue"],
        state="agent-issue",
    )
    pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=35,
        title="Live PR",
        url="https://example.com/pr/35",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET worktree_path = ?, worktree_removed_at = ? WHERE id IN (?, ?)",
            (
                "\\n\\n- Existing branch: issue-23-20260324-1200",
                "2026-03-24T00:00:00Z",
                int(issue["id"]),
                int(pr["id"]),
            ),
        )
        conn.commit()

    log_path = tmp_path / "historical-invalid.log"
    expected_worktree = "/tmp/repo/.worktrees/issue-23-20260324-1200"
    log_path.write_text(
        "/usr/bin/zsh -lc 'git status --short --branch' in {0}\n".format(expected_worktree),
        encoding="utf-8",
    )
    previous_run = repository.create_run(issue["id"], "implement", "prompt", "cmd", output_path=str(log_path))
    repository.finish_run(previous_run, 0, str(log_path), "success")

    SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 23,
                    "title": "Linked issue with invalid worktree",
                    "url": "https://example.com/issue/23",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[
                {
                    "number": 35,
                    "title": "Live PR",
                    "url": "https://example.com/pr/35",
                    "labels": ["agent-reviewable"],
                    "assignee": None,
                    "head_sha": "sha-35",
                }
            ],
            open_pr_links=[{"number": 35, "linked_issue_numbers": [23]}],
        ),
    ).sync_once(repo_cfg)

    synced_issue = repository.get_task_by_key(repo_id, "issue", 23)
    synced_pr = repository.get_task_by_key(repo_id, "pr", 35)

    assert synced_issue is not None
    assert synced_pr is not None
    assert synced_issue["worktree_path"] == expected_worktree
    assert synced_pr["worktree_path"] == expected_worktree
    assert synced_pr["worktree_removed_at"] is None


def test_sync_service_replaces_worktree_path_with_appended_prompt_text_before_pr_propagation(repository, tmp_path):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=24,
        title="Linked issue with appended prompt text",
        url="https://example.com/issue/24",
        labels=["agent-issue"],
        state="agent-issue",
    )
    pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=36,
        title="Live PR",
        url="https://example.com/pr/36",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    expected_worktree = "/tmp/repo/.worktrees/issue-24-20260324-1200"
    invalid_worktree = expected_worktree + "    - Existing worktree: " + expected_worktree
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET worktree_path = ?, worktree_removed_at = ? WHERE id IN (?, ?)",
            (
                invalid_worktree,
                "2026-03-24T00:00:00Z",
                int(issue["id"]),
                int(pr["id"]),
            ),
        )
        conn.commit()

    log_path = tmp_path / "historical-appended.log"
    log_path.write_text(
        "/usr/bin/zsh -lc 'git status --short --branch' in {0}\n".format(expected_worktree),
        encoding="utf-8",
    )
    previous_run = repository.create_run(issue["id"], "implement", "prompt", "cmd", output_path=str(log_path))
    repository.finish_run(previous_run, 0, str(log_path), "success")

    SyncService(
        repository,
        FakeGHClient(
            issues=[
                {
                    "number": 24,
                    "title": "Linked issue with appended prompt text",
                    "url": "https://example.com/issue/24",
                    "labels": ["agent-issue"],
                    "assignee": None,
                }
            ],
            prs=[
                {
                    "number": 36,
                    "title": "Live PR",
                    "url": "https://example.com/pr/36",
                    "labels": ["agent-reviewable"],
                    "assignee": None,
                    "head_sha": "sha-36",
                }
            ],
            open_pr_links=[{"number": 36, "linked_issue_numbers": [24]}],
        ),
    ).sync_once(repo_cfg)

    synced_issue = repository.get_task_by_key(repo_id, "issue", 24)
    synced_pr = repository.get_task_by_key(repo_id, "pr", 36)

    assert synced_issue is not None
    assert synced_pr is not None
    assert synced_issue["worktree_path"] == expected_worktree
    assert synced_pr["worktree_path"] == expected_worktree
    assert synced_pr["worktree_removed_at"] is None


def test_sync_service_marks_disappeared_items_closed_or_merged(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=51,
        title="issue",
        url="https://example.com/issue/51",
        labels=["agent-issue"],
        state="agent-issue",
    )
    pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=52,
        title="pr",
        url="https://example.com/pr/52",
        labels=["agent-approved"],
        state="agent-approved",
    )

    summary = SyncService(
        repository,
        FakeGHClient(
            issues=[],
            prs=[],
            issue_states={51: "closed"},
            pr_states={52: "merged"},
        ),
    ).sync_once(repo_cfg)

    closed_issue = repository.get_task(int(issue["id"]))
    merged_pr = repository.get_task(int(pr["id"]))

    assert summary["stale"] == 0
    assert closed_issue["github_state"] == "closed"
    assert merged_pr["github_state"] == "merged"
    assert closed_issue["is_stale"] is False
    assert merged_pr["is_stale"] is False


def test_sync_service_keeps_open_state_when_remote_state_lookup_fails(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=61,
        title="issue",
        url="https://example.com/issue/61",
        labels=["agent-issue"],
        state="agent-issue",
    )

    summary = SyncService(
        repository,
        FakeGHClient(
            issues=[],
            prs=[],
            issue_states={61: RuntimeError("gh down")},
        ),
    ).sync_once(repo_cfg)

    updated_issue = repository.get_task(int(issue["id"]))

    assert summary["stale"] == 1
    assert updated_issue["github_state"] == "open"
    assert updated_issue["is_stale"] is True
