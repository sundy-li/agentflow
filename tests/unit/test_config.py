import pytest

from app.config import load_settings


def test_scheduler_parallelism_defaults_to_four(tmp_path):
    config_path = tmp_path / "agentflow.yaml"
    config_path.write_text("repos:\n  - enabled: false\n", encoding="utf-8")

    settings = load_settings(str(config_path))

    assert settings.scheduler.max_parallel_tasks == 4
    assert settings.scheduler.review_latency_hours == 0


def test_load_settings_uses_legacy_codex_config_as_default_agent(tmp_path):
    config_path = tmp_path / "agentflow.yaml"
    config_path.write_text(
        "\n".join(
            [
                "codex:",
                "  command: custom-codex",
                "  args: [--fast]",
                "  timeout_seconds: 123",
                "repos:",
                "  - enabled: false",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))
    agent = settings.resolve_agent_for_mode("implement")

    assert agent.kind == "codex"
    assert agent.command == "custom-codex"
    assert agent.args == ["--fast"]
    assert agent.timeout_seconds == 123


def test_load_settings_supports_task_specific_coding_agents(tmp_path):
    config_path = tmp_path / "agentflow.yaml"
    config_path.write_text(
        "\n".join(
            [
                "codex:",
                "  command: legacy-codex",
                "  args: []",
                "  timeout_seconds: 1800",
                "coding_agents:",
                "  default:",
                "    kind: codex",
                "    command: codex",
                "    args: [--dangerously-bypass-approvals-and-sandbox]",
                "    timeout_seconds: 1800",
                "  claude:",
                "    kind: claude_code",
                "    command: claude",
                "    args: [--output-format, text]",
                "    timeout_seconds: 900",
                "  opencode:",
                "    kind: opencode",
                "    command: opencode",
                "    args: [--agent, reviewer]",
                "    timeout_seconds: 600",
                "task_agents:",
                "  implement: claude",
                "  fix: opencode",
                "  review: default",
                "repos:",
                "  - enabled: false",
            ]
        ),
        encoding="utf-8",
    )

    settings = load_settings(str(config_path))

    implement_agent = settings.resolve_agent_for_mode("implement")
    fix_agent = settings.resolve_agent_for_mode("fix")
    review_agent = settings.resolve_agent_for_mode("review")

    assert implement_agent.kind == "claude_code"
    assert implement_agent.command == "claude"
    assert fix_agent.kind == "opencode"
    assert fix_agent.args == ["--agent", "reviewer"]
    assert review_agent.kind == "codex"
    assert review_agent.command == "codex"


def test_load_settings_rejects_unknown_task_agent_reference(tmp_path):
    config_path = tmp_path / "agentflow.yaml"
    config_path.write_text(
        "\n".join(
            [
                "coding_agents:",
                "  default:",
                "    kind: codex",
                "    command: codex",
                "task_agents:",
                "  review: missing",
                "repos:",
                "  - enabled: false",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing"):
        load_settings(str(config_path))
