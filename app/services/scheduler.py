import logging
import os
import inspect
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(
        self,
        sync_service,
        worker_service,
        repo_cfg,
        worktree_cleanup_service=None,
        interval_seconds: int = 60,
        enabled: bool = True,
        max_parallel_tasks: int = 4,
        review_latency_hours: float = 0,
        shutdown_timeout_seconds: float = 5.0,
        force_exit_fn: Optional[Callable[[int], None]] = None,
    ):
        self.sync_service = sync_service
        self.worker_service = worker_service
        self.repo_cfg = repo_cfg
        self.worktree_cleanup_service = worktree_cleanup_service
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.max_parallel_tasks = max(1, int(max_parallel_tasks))
        self.review_latency_hours = max(0.0, float(review_latency_hours))
        self.shutdown_timeout_seconds = max(0.0, float(shutdown_timeout_seconds))
        self._force_exit_fn = force_exit_fn or os._exit
        self.scheduler = BackgroundScheduler()
        self._executor = ThreadPoolExecutor(max_workers=self.max_parallel_tasks, thread_name_prefix="agentflow-task")
        self._shutdown_event = threading.Event()
        self._inflight_lock = threading.Lock()
        self._inflight_futures = set()
        self._started = False

    def start(self) -> None:
        if not self.enabled or self.repo_cfg is None or not self.repo_cfg.enabled:
            return
        if self._started:
            return
        self.scheduler.add_job(
            self.tick,
            "interval",
            seconds=self.interval_seconds,
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
            id="agentflow-tick",
            replace_existing=True,
        )
        self.scheduler.start()
        self._started = True
        logger.info(
            "scheduler started repo=%s interval_seconds=%s max_parallel_tasks=%s review_latency_hours=%s",
            getattr(self.repo_cfg, "full_name", None),
            self.interval_seconds,
            self.max_parallel_tasks,
            self.review_latency_hours,
        )

    def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False
        worker_shutdown = getattr(self.worker_service, "shutdown", None)
        if callable(worker_shutdown):
            worker_shutdown()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if not self._wait_for_workers_to_stop():
            logger.warning(
                "scheduler shutdown timed out repo=%s active_workers=%s forcing process exit",
                getattr(self.repo_cfg, "full_name", None),
                self._active_worker_count(),
            )
            self._force_exit_fn(1)
        self._prune_finished_workers()

    def tick(self) -> Dict:
        if self.repo_cfg is None or not self.repo_cfg.enabled or self._shutdown_event.is_set():
            return {"synced": False, "executed": False, "executed_count": 0}
        logger.info("scheduler tick started repo=%s", self.repo_cfg.full_name)
        self._prune_finished_workers()
        sync_summary = self.sync_service.sync_once(self.repo_cfg)
        self._run_worktree_cleanup(sync_summary)
        if self._shutdown_event.is_set():
            return {"synced": True, "executed": False, "executed_count": 0}
        self._prune_finished_workers()
        executed_count = self._dispatch_worker_batch()
        result = {"synced": True, "executed": executed_count > 0, "executed_count": executed_count}
        logger.info(
            "scheduler tick completed repo=%s executed=%s executed_count=%s active_workers=%s",
            self.repo_cfg.full_name,
            result["executed"],
            executed_count,
            self._active_worker_count(),
        )
        return result

    def _run_worktree_cleanup(self, sync_summary: Optional[Dict]) -> None:
        if self.worktree_cleanup_service is None or self._shutdown_event.is_set():
            return
        stale_pr_task_ids = []
        if isinstance(sync_summary, dict):
            stale_pr_task_ids = list(sync_summary.get("stale_pr_task_ids") or [])
        try:
            self.worktree_cleanup_service.cleanup_repo(self.repo_cfg, stale_pr_task_ids=stale_pr_task_ids)
        except Exception:
            logger.exception(
                "scheduler worktree cleanup failed repo=%s stale_pr_task_ids=%s",
                getattr(self.repo_cfg, "full_name", None),
                stale_pr_task_ids,
            )

    def _dispatch_worker_batch(self) -> int:
        if self._shutdown_event.is_set():
            return 0
        available_slots = max(0, self.max_parallel_tasks - self._active_worker_count())
        dispatched = 0
        for _ in range(available_slots):
            if self._shutdown_event.is_set():
                break
            try:
                active_task_ids = []
                active_task_ids_fn = getattr(self.worker_service, "active_task_ids", None)
                if callable(active_task_ids_fn):
                    active_task_ids = list(active_task_ids_fn())
                process_one = self.worker_service.process_one
                parameters = inspect.signature(process_one).parameters
                submit_kwargs = {"review_latency_hours": self.review_latency_hours}
                if "exclude_task_ids" in parameters:
                    submit_kwargs["exclude_task_ids"] = active_task_ids
                future = self._executor.submit(process_one, self.repo_cfg, **submit_kwargs)
            except RuntimeError:
                logger.info("scheduler executor is shutting down repo=%s", getattr(self.repo_cfg, "full_name", None))
                break
            with self._inflight_lock:
                self._inflight_futures.add(future)
            dispatched += 1
        return dispatched

    def _active_worker_count(self) -> int:
        with self._inflight_lock:
            return sum(1 for future in self._inflight_futures if not future.done())

    def _prune_finished_workers(self) -> None:
        completed = []
        with self._inflight_lock:
            for future in list(self._inflight_futures):
                if future.done():
                    self._inflight_futures.discard(future)
                    completed.append(future)
        for future in completed:
            self._log_worker_result(future)

    def _log_worker_result(self, future: Future) -> None:
        try:
            result = future.result()
        except Exception:
            logger.exception("scheduler worker failed repo=%s", getattr(self.repo_cfg, "full_name", None))
            return
        if result is None:
            logger.info("scheduler worker completed repo=%s task=none", getattr(self.repo_cfg, "full_name", None))
            return
        logger.info(
            "scheduler worker completed repo=%s task_id=%s state=%s",
            getattr(self.repo_cfg, "full_name", None),
            result.get("id"),
            result.get("state"),
        )

    def _wait_for_workers_to_stop(self) -> bool:
        deadline = time.monotonic() + self.shutdown_timeout_seconds
        while True:
            self._prune_finished_workers()
            if self._active_worker_count() == 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
