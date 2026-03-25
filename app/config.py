import os
from pathlib import Path
from typing import Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator


class DatabaseSettings(BaseModel):
    path: str = "data/agentflow.db"


class SchedulerSettings(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = 60
    max_parallel_tasks: int = Field(default=4, ge=1)
    review_latency_hours: float = Field(default=0, ge=0)


class CodingAgentSettings(BaseModel):
    kind: Literal["codex", "claude_code", "opencode"] = "codex"
    command: str = "codex"
    args: List[str] = Field(default_factory=list)
    timeout_seconds: int = 1800


class CodexSettings(CodingAgentSettings):
    kind: Literal["codex"] = "codex"


class TaskAgentSettings(BaseModel):
    implement: Optional[str] = None
    fix: Optional[str] = None
    review: Optional[str] = None

    def get_profile_name(self, mode: str) -> Optional[str]:
        if mode not in {"implement", "fix", "review"}:
            raise ValueError("Unsupported task mode: {0}".format(mode))
        return getattr(self, mode)


class UISettings(BaseModel):
    refresh_seconds: int = 5


class RepoSettings(BaseModel):
    name: str = "default"
    full_name: str = "owner/repo"
    forked: Optional[str] = None
    workspace: Optional[str] = None
    default_branch: str = "main"
    enabled: bool = False


class AppSettings(BaseModel):
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    codex: CodexSettings = Field(default_factory=CodexSettings)
    coding_agents: Dict[str, CodingAgentSettings] = Field(default_factory=dict)
    task_agents: TaskAgentSettings = Field(default_factory=TaskAgentSettings)
    ui: UISettings = Field(default_factory=UISettings)
    repos: List[RepoSettings] = Field(default_factory=list)
    run_logs_dir: str = "data/runs"

    @model_validator(mode="after")
    def validate_task_agents(self):
        for mode in ("implement", "fix", "review"):
            profile_name = self.task_agents.get_profile_name(mode)
            if profile_name is None:
                continue
            if profile_name in self.coding_agents:
                continue
            if profile_name == "default":
                continue
            raise ValueError("task_agents.{0} references unknown coding agent profile '{1}'".format(mode, profile_name))
        return self

    def resolve_agent_for_mode(self, mode: str) -> CodingAgentSettings:
        profile_name = self.task_agents.get_profile_name(mode)
        if profile_name is not None:
            if profile_name == "default":
                default_profile = self.coding_agents.get("default")
                if default_profile is not None:
                    return default_profile
                return self.codex
            try:
                return self.coding_agents[profile_name]
            except KeyError as err:
                raise ValueError("Unknown coding agent profile '{0}' for mode '{1}'".format(profile_name, mode)) from err

        default_profile = self.coding_agents.get("default")
        if default_profile is not None:
            return default_profile
        return self.codex


def load_settings(config_path: Optional[str] = None) -> AppSettings:
    path = config_path or os.getenv("AGENTFLOW_CONFIG", "config/agentflow.yaml")
    source = {}
    config_file = Path(path)
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as file_obj:
            loaded = yaml.safe_load(file_obj) or {}
        if not isinstance(loaded, dict):
            raise ValueError("Config YAML must be a mapping object.")
        source = loaded

    settings = AppSettings.model_validate(source)
    if not settings.repos:
        settings.repos = [RepoSettings()]
    return settings


def get_active_repo(settings: AppSettings) -> Optional[RepoSettings]:
    for repo in settings.repos:
        if repo.enabled:
            return repo
    return None
