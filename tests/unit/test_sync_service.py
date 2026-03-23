from app.config import RepoSettings
from app.services.sync_service import SyncService


class FakeGHClient:
    def __init__(self, issues, prs):
        self._issues = issues
        self._prs = prs

    def list_agent_issues(self, repo_full_name):
        return list(self._issues)

    def list_agent_prs(self, repo_full_name):
        return list(self._prs)


def test_sync_service_upserts_transitions_and_marks_stale(repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)

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

    gh = FakeGHClient(
        issues=[
            {
                "number": 1,
                "title": "New issue",
                "url": "https://example.com/issue/1",
                "labels": ["agent-issue"],
                "assignee": "bob",
            }
        ],
        prs=[
            {
                "number": 7,
                "title": "Old PR",
                "url": "https://example.com/pr/7",
                "labels": ["agent-changed"],
                "assignee": None,
            }
        ],
    )

    service = SyncService(repository, gh)
    summary = service.sync_once(repo_cfg)

    assert summary["issues"] == 1
    assert summary["prs"] == 1
    assert summary["stale"] == 1

    issue = repository.get_task_by_key(repo_id, "issue", 1)
    assert issue is not None
    assert issue["state"] == "agent-issue"

    pr = repository.get_task_by_key(repo_id, "pr", 7)
    assert pr["state"] == "agent-changed"

    stale = repository.get_task(stale_task["id"])
    assert stale["is_stale"] is True

    events = repository.get_task_events(existing_pr["id"])
    assert any(event["reason"] == "sync_label_change" for event in events)

