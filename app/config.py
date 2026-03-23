import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


class DatabaseSettings(BaseModel):
    path: str = "data/agentflow.db"


class SchedulerSettings(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = 60
    max_parallel_tasks: int = Field(default=4, ge=1)
    review_latency_hours: float = Field(default=0, ge=0)


class CodexSettings(BaseModel):
    command: str = "codex"
    args: List[str] = Field(default_factory=list)
    timeout_seconds: int = 1800


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
    ui: UISettings = Field(default_factory=UISettings)
    repos: List[RepoSettings] = Field(default_factory=list)
    run_logs_dir: str = "data/runs"


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
