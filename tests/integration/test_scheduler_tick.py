from app.config import RepoSettings
from app.services.scheduler import AgentScheduler


class FakeSyncService:
    def __init__(self):
        self.calls = 0

    def sync_once(self, repo_cfg):
        self.calls += 1
        return {"issues": 0, "prs": 0, "stale": 0}


class FakeWorkerService:
    def __init__(self, returns_task=True):
        self.calls = 0
        self.returns_task = returns_task

    def process_one(self, repo_cfg):
        self.calls += 1
        if self.returns_task:
            return {"id": 1}
        return None


def test_scheduler_tick_runs_sync_and_dispatch():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService()
    worker = FakeWorkerService(returns_task=True)
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True)

    result = scheduler.tick()
    assert result["synced"] is True
    assert result["executed"] is True
    assert sync.calls == 1
    assert worker.calls == 1


def test_scheduler_tick_skips_when_repo_disabled():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=False)
    sync = FakeSyncService()
    worker = FakeWorkerService(returns_task=False)
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True)

    result = scheduler.tick()
    assert result == {"synced": False, "executed": False}
    assert sync.calls == 0
    assert worker.calls == 0

