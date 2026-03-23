from typing import Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler


class AgentScheduler:
    def __init__(
        self,
        sync_service,
        worker_service,
        repo_cfg,
        interval_seconds: int = 60,
        enabled: bool = True,
    ):
        self.sync_service = sync_service
        self.worker_service = worker_service
        self.repo_cfg = repo_cfg
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.scheduler = BackgroundScheduler()
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
            max_instances=1,
            coalesce=True,
            id="agentflow-tick",
            replace_existing=True,
        )
        self.scheduler.start()
        self._started = True

    def shutdown(self) -> None:
        if self._started:
            self.scheduler.shutdown(wait=False)
            self._started = False

    def tick(self) -> Dict:
        if self.repo_cfg is None or not self.repo_cfg.enabled:
            return {"synced": False, "executed": False}
        self.sync_service.sync_once(self.repo_cfg)
        executed = self.worker_service.process_one(self.repo_cfg) is not None
        return {"synced": True, "executed": executed}

