from pathlib import Path

import pytest

from app.db import run_migrations
from app.repository import Repository


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "agentflow.db"
    run_migrations(str(path))
    return str(path)


@pytest.fixture
def repository(db_path: str) -> Repository:
    return Repository(db_path)

