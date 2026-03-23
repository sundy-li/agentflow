import json
from types import SimpleNamespace

from app.constants import STATE_LABELS
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
            "headRefOid": "sha-1",
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
    assert prs[0]["head_sha"] == "sha-1"
    issue_commands = [cmd for cmd in commands if cmd[:3] == ["gh", "issue", "list"]]
    pr_commands = [cmd for cmd in commands if cmd[:3] == ["gh", "pr", "list"]]
    edit_commands = [cmd for cmd in commands if cmd[:3] == ["gh", "pr", "edit"]]

    assert issue_commands
    assert len(issue_commands) == len(STATE_LABELS)
    assert len(pr_commands) == len(STATE_LABELS)
    for label in STATE_LABELS:
        assert any(label in cmd for cmd in issue_commands)
        assert any(label in cmd for cmd in pr_commands)
    assert any("headRefOid" in cmd[cmd.index("--json") + 1] for cmd in pr_commands)
    assert edit_commands


def test_gh_client_lists_open_pr_links(monkeypatch):
    commands = []
    pr_payload = [
        {
            "number": 10,
            "body": "Implements parser fix.\n\nFixes #123\nResolves owner/repo#124\nCloses other/repo#999",
        }
    ]

    def fake_run(command, capture_output, text, check, timeout):
        commands.append(command)
        if command[:3] == ["gh", "pr", "list"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(pr_payload), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    client = GHClient(timeout_seconds=1)

    links = client.list_open_pr_links("owner/repo")

    assert links == [{"number": 10, "linked_issue_numbers": [123, 124]}]
    assert commands[0][:3] == ["gh", "pr", "list"]
    assert "--state" in commands[0]
    assert "open" in commands[0]
    assert "body" in commands[0][commands[0].index("--json") + 1]
