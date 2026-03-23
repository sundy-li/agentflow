import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes_board import router as board_router
from app.config import AppSettings, get_active_repo, load_settings
from app.db import run_migrations
from app.repository import Repository
from app.services.codex_runner import CodexRunner
from app.services.gh_client import GHClient
from app.services.scheduler import AgentScheduler
from app.services.sync_service import SyncService
from app.services.worker_service import WorkerService


def configure_app_logging() -> None:
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        app_logger.setLevel(logging.INFO)
        app_logger.propagate = False
        return

    uvicorn_logger = logging.getLogger("uvicorn.error")
    if uvicorn_logger.handlers:
        app_logger.handlers = list(uvicorn_logger.handlers)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False


def recover_active_repo_locks(repository: Repository, active_repo) -> None:
    if active_repo is None or not active_repo.enabled:
        return
    repo_id = repository.ensure_repo(active_repo.name, active_repo.full_name, active_repo.enabled)
    repository.clear_task_locks(repo_id)


def create_app(settings: Optional[AppSettings] = None) -> FastAPI:
    configure_app_logging()
    app_settings = settings or load_settings()
    run_migrations(app_settings.database.path)

    repository = Repository(app_settings.database.path)
    gh_client = GHClient()
    sync_service = SyncService(repository, gh_client)
    codex_runner = CodexRunner(repository, app_settings.codex, app_settings.run_logs_dir)
    worker_service = WorkerService(repository, gh_client, codex_runner)
    active_repo = get_active_repo(app_settings)
    scheduler_service = AgentScheduler(
        sync_service=sync_service,
        worker_service=worker_service,
        repo_cfg=active_repo,
        interval_seconds=app_settings.scheduler.poll_interval_seconds,
        enabled=app_settings.scheduler.enabled,
        max_parallel_tasks=app_settings.scheduler.max_parallel_tasks,
        review_latency_hours=app_settings.scheduler.review_latency_hours,
    )

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        recover_active_repo_locks(repository, active_repo)
        scheduler_service.start()
        yield
        scheduler_service.shutdown()

    app = FastAPI(title="agentflow", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")
    app.include_router(board_router)

    app.state.settings = app_settings
    app.state.repository = repository
    app.state.gh_client = gh_client
    app.state.sync_service = sync_service
    app.state.codex_runner = codex_runner
    app.state.worker_service = worker_service
    app.state.scheduler_service = scheduler_service
    app.state.active_repo = active_repo
    app.state.templates = Jinja2Templates(directory="app/ui/templates")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    return app
