from app.config import RepoSettings
from app.services.sync_service import SyncService


class FakeGHClient:
    def __init__(self, issues, prs, open_pr_links=None):
        self._issues = issues
        self._prs = prs
        self._open_pr_links = open_pr_links or []

    def list_agent_issues(self, repo_full_name):
        return list(self._issues)

    def list_agent_prs(self, repo_full_name):
        return list(self._prs)

    def list_open_pr_links(self, repo_full_name):
        return list(self._open_pr_links)


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

    approved_issue = repository.get_task_by_key(repo_id, "issue", 2)
    assert approved_issue["state"] == "agent-approved"

    pr = repository.get_task_by_key(repo_id, "pr", 7)
    assert pr["state"] == "agent-changed"
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
