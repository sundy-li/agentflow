import threading

from app.config import RepoSettings
from app.constants import RUNNABLE_STATES
from app.repository import Repository
from app.services.scheduler import AgentScheduler
from app.services.worker_service import WorkerService


class FakeSyncService:
    def __init__(self, results=None):
        self.calls = 0
        self.results = list(results or [{"issues": 0, "prs": 0, "stale": 0, "stale_pr_task_ids": []}])

    def sync_once(self, repo_cfg):
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        return dict(self.results[index])


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


class FakeCleanupService:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = set(failures or [])

    def cleanup_repo(self, repo_cfg, stale_pr_task_ids=None):
        call_number = len(self.calls) + 1
        self.calls.append(
            {
                "repo": repo_cfg.full_name,
                "stale_pr_task_ids": list(stale_pr_task_ids or []),
            }
        )
        if call_number in self.failures:
            raise RuntimeError("cleanup failed")
        return {"attempted": len(stale_pr_task_ids or [])}


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


class FakeClaimingRepository:
    def __init__(self):
        self.exclude_history = []
        self.next_task_id = 1

    def ensure_repo(self, name, full_name, enabled=True):
        return 1

    def claim_next_task(self, repo_id, states, worker_id, review_latency_hours=0, exclude_task_ids=None):
        self.exclude_history.append(list(exclude_task_ids or []))
        return None


class PassthroughRunner:
    def run_task(self, task, mode):
        return {"id": task["id"]}


class BlockingRunner:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def run_task(self, task, mode):
        self.started.set()
        self.release.wait(timeout=2)
        return type(
            "Result",
            (),
            {"run_id": 1, "exit_code": 0, "output_path": "/tmp/test.log", "result": "success"},
        )()

    def shutdown(self):
        self.release.set()


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


def test_scheduler_tick_invokes_worktree_cleanup_after_sync():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService(results=[{"issues": 0, "prs": 1, "stale": 1, "stale_pr_task_ids": [9]}])
    worker = FakeWorkerService(returns_task=False)
    cleanup = FakeCleanupService()
    scheduler = AgentScheduler(
        sync,
        worker,
        repo_cfg,
        interval_seconds=1,
        enabled=True,
        max_parallel_tasks=1,
        worktree_cleanup_service=cleanup,
    )

    scheduler.tick()
    scheduler.shutdown()

    assert cleanup.calls == [{"repo": "owner/repo", "stale_pr_task_ids": [9]}]


def test_scheduler_tick_cleanup_failure_does_not_block_worker_dispatch():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService(results=[{"issues": 0, "prs": 1, "stale": 1, "stale_pr_task_ids": [9]}])
    worker = FakeWorkerService(returns_task=True)
    cleanup = FakeCleanupService(failures={1})
    scheduler = AgentScheduler(
        sync,
        worker,
        repo_cfg,
        interval_seconds=1,
        enabled=True,
        max_parallel_tasks=1,
        worktree_cleanup_service=cleanup,
    )

    result = scheduler.tick()
    scheduler.shutdown()

    assert len(cleanup.calls) == 1
    assert worker.calls == 1
    assert result["executed_count"] == 1


def test_scheduler_tick_calls_cleanup_on_later_ticks_for_retry():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    sync = FakeSyncService(
        results=[
            {"issues": 0, "prs": 1, "stale": 1, "stale_pr_task_ids": [9]},
            {"issues": 0, "prs": 0, "stale": 0, "stale_pr_task_ids": []},
        ]
    )
    worker = FakeWorkerService(returns_task=False)
    cleanup = FakeCleanupService(failures={1})
    scheduler = AgentScheduler(
        sync,
        worker,
        repo_cfg,
        interval_seconds=1,
        enabled=True,
        max_parallel_tasks=1,
        worktree_cleanup_service=cleanup,
    )

    scheduler.tick()
    scheduler.tick()
    scheduler.shutdown()

    assert len(cleanup.calls) == 2


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


def test_scheduler_passes_active_task_ids_to_claims():
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repository = FakeClaimingRepository()
    worker = WorkerService(repository, gh_client=object(), coding_agent_runner=PassthroughRunner())
    worker._register_active_task(42)
    scheduler = AgentScheduler(FakeSyncService(), worker, repo_cfg, interval_seconds=1, enabled=True, max_parallel_tasks=1)

    scheduler.tick()
    scheduler.shutdown()

    assert repository.exclude_history
    assert repository.exclude_history[0] == [42]


def test_worker_active_task_ids_prevent_duplicate_claim_with_expired_lock(repository: Repository):
    repo_cfg = RepoSettings(name="demo", full_name="owner/repo", enabled=True)
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name)
    first = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=60,
        title="first",
        url="https://example.com/issue/60",
        labels=["agent-issue"],
        state="agent-issue",
    )
    second = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=61,
        title="second",
        url="https://example.com/issue/61",
        labels=["agent-issue"],
        state="agent-issue",
    )
    runner = BlockingRunner()
    gh = type("GH", (), {"set_labels": lambda *args, **kwargs: None})()
    worker = WorkerService(repository, gh, runner)
    worker._register_active_task(int(first["id"]))

    claimed = repository.claim_next_task(
        repo_id,
        RUNNABLE_STATES,
        worker.worker_id,
        exclude_task_ids=worker.active_task_ids(),
    )

    assert claimed is not None
    assert claimed["id"] == second["id"]
