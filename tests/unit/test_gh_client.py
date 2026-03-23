import json
from types import SimpleNamespace

from app.services.gh_client import GHClient


def test_gh_client_builds_expected_commands(monkeypatch):
    commands = []

    issue_payload = [
        {
            "number": 1,
            "title": "Issue",
            "url": "https://example.com/1",
            "labels": [{"name": "agent-issue"}],
            "assignees": [{"login": "alice"}],
            "updatedAt": "2026-03-23T00:00:00Z",
        }
    ]
    pr_payload = [
        {
            "number": 2,
            "title": "PR",
            "url": "https://example.com/2",
            "labels": [{"name": "agent-reviewable"}],
            "assignees": [],
            "updatedAt": "2026-03-23T00:00:00Z",
        }
    ]

    def fake_run(command, capture_output, text, check, timeout):
        commands.append(command)
        if command[:3] == ["gh", "issue", "list"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(issue_payload), stderr="")
        if command[:3] == ["gh", "pr", "list"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(pr_payload), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    client = GHClient(timeout_seconds=1)

    issues = client.list_agent_issues("owner/repo")
    prs = client.list_agent_prs("owner/repo")
    client.set_labels(
        "owner/repo",
        "pr",
        2,
        add_labels=["agent-approved"],
        remove_labels=["agent-reviewable"],
    )

    assert issues[0]["number"] == 1
    assert prs[0]["number"] == 2
    issue_commands = [cmd for cmd in commands if cmd[:3] == ["gh", "issue", "list"]]
    pr_commands = [cmd for cmd in commands if cmd[:3] == ["gh", "pr", "list"]]
    edit_commands = [cmd for cmd in commands if cmd[:3] == ["gh", "pr", "edit"]]

    assert issue_commands
    assert "--label" in issue_commands[0]
    assert "agent-issue" in issue_commands[0]
    assert len(pr_commands) == 2
    assert any("agent-reviewable" in cmd for cmd in pr_commands)
    assert any("agent-changed" in cmd for cmd in pr_commands)
    assert edit_commands

