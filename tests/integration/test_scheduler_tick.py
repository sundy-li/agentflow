import threading

from app.config import RepoSettings
from app.services.scheduler import AgentScheduler


class FakeSyncService:
    def __init__(self):
        self.calls = 0

    def sync_once(self, repo_cfg):
        self.calls += 1
        return {"issues": 0, "prs": 0, "stale": 0}


class FakeWorkerService:
    def __init__(self, returns_task=True, barrier_parties=None):
        self.calls = 0
        self.returns_task = returns_task
        self.barrier = threading.Barrier(barrier_parties) if barrier_parties else None
        self.thread_ids = []

    def process_one(self, repo_cfg, review_latency_hours=0):
        self.calls += 1
        self.thread_ids.append(threading.get_ident())
        if self.barrier is not None:
            self.barrier.wait(timeout=1)
        if self.returns_task:
            return {"id": self.calls}
        return None


class BlockingWorkerService:
    def __init__(self):
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()
        self.shutdown_calls = 0

    def process_one(self, repo_cfg, review_latency_hours=0):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
        return {"id": self.calls}

    def shutdown(self):
        self.shutdown_calls += 1
        self.release.set()


class StubbornWorkerService:
    def __init__(self):
        self.started = threading.Event()
        self.shutdown_calls = 0

    def process_one(self, repo_cfg, review_latency_hours=0):
        self.started.set()
        threading.Event().wait(timeout=2)
        return {"id": 1}

    def shutdown(self):
        self.shutdown_calls += 1


class FakeBackgroundScheduler:
    def __init__(self):
        self.jobs = []
        self.started = False
        self.shutdown_called = False

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, "kwargs": kwargs})

    def start(self):
        self.started = True

    def shutdown(self, wait=False):
        self.shutdown_called = True


def test_scheduler_tick_runs_sync_and_dispatch():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService()
    worker = FakeWorkerService(returns_task=True, barrier_parties=3)
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True, max_parallel_tasks=3)

    result = scheduler.tick()
    assert result["synced"] is True
    assert result["executed"] is True
    assert result["executed_count"] == 3
    assert sync.calls == 1
    assert worker.calls == 3
    assert len(set(worker.thread_ids)) == 3


def test_scheduler_tick_skips_when_repo_disabled():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=False)
    sync = FakeSyncService()
    worker = FakeWorkerService(returns_task=False)
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True)

    result = scheduler.tick()
    assert result == {"synced": False, "executed": False, "executed_count": 0}
    assert sync.calls == 0
    assert worker.calls == 0


def test_scheduler_start_schedules_immediate_first_tick():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService()
    worker = FakeWorkerService(returns_task=False)
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True)
    fake_background = FakeBackgroundScheduler()
    scheduler.scheduler = fake_background

    scheduler.start()

    assert fake_background.started is True
    assert len(fake_background.jobs) == 1
    job = fake_background.jobs[0]
    assert job["trigger"] == "interval"
    assert job["kwargs"]["next_run_time"] is not None


def test_scheduler_tick_does_not_block_on_running_workers():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService()
    worker = BlockingWorkerService()
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True, max_parallel_tasks=1)
    result_holder = {}

    thread = threading.Thread(target=lambda: result_holder.setdefault("result", scheduler.tick()))
    thread.start()
    worker.started.wait(timeout=1)
    thread.join(timeout=0.2)
    still_running_before_release = thread.is_alive()
    worker.release.set()
    thread.join(timeout=1)
    scheduler.shutdown()

    assert still_running_before_release is False
    assert not thread.is_alive()
    assert result_holder["result"]["executed_count"] == 1


def test_scheduler_shutdown_stops_running_workers():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService()
    worker = BlockingWorkerService()
    scheduler = AgentScheduler(sync, worker, repo_cfg, interval_seconds=1, enabled=True, max_parallel_tasks=1)

    scheduler.tick()
    worker.started.wait(timeout=1)

    scheduler.shutdown()
    completed = worker.release.wait(timeout=0.2)

    assert worker.shutdown_calls == 1
    assert completed is True


def test_scheduler_shutdown_forces_exit_when_workers_do_not_stop():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService()
    worker = StubbornWorkerService()
    forced = {}
    scheduler = AgentScheduler(
        sync,
        worker,
        repo_cfg,
        interval_seconds=1,
        enabled=True,
        max_parallel_tasks=1,
        shutdown_timeout_seconds=0.05,
        force_exit_fn=lambda code: forced.setdefault("code", code),
    )

    scheduler.tick()
    worker.started.wait(timeout=1)
    scheduler.shutdown()

    assert worker.shutdown_calls == 1
    assert forced["code"] == 1
