import io
import logging

from app.config import AppSettings, CodexSettings, DatabaseSettings, RepoSettings, SchedulerSettings, UISettings
from app.main import create_app
from app.main import configure_app_logging


def test_configure_app_logging_uses_uvicorn_handlers():
    app_logger = logging.getLogger("app")
    uvicorn_logger = logging.getLogger("uvicorn.error")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)

    original_app_handlers = list(app_logger.handlers)
    original_app_level = app_logger.level
    original_app_propagate = app_logger.propagate
    original_uvicorn_handlers = list(uvicorn_logger.handlers)

    try:
        app_logger.handlers = []
        app_logger.setLevel(logging.NOTSET)
        app_logger.propagate = True
        uvicorn_logger.handlers = [handler]

        configure_app_logging()
        logging.getLogger("app.services.worker_service").info("hello from worker")

        assert app_logger.handlers == [handler]
        assert app_logger.level == logging.INFO
        assert app_logger.propagate is False
        assert "hello from worker" in stream.getvalue()
    finally:
        app_logger.handlers = original_app_handlers
        app_logger.setLevel(original_app_level)
        app_logger.propagate = original_app_propagate
        uvicorn_logger.handlers = original_uvicorn_handlers


def test_create_app_exposes_coding_agent_runner(tmp_path):
    settings = AppSettings(
        database=DatabaseSettings(path=str(tmp_path / "app.db")),
        scheduler=SchedulerSettings(enabled=False, poll_interval_seconds=60),
        codex=CodexSettings(command="codex", args=[], timeout_seconds=60),
        ui=UISettings(refresh_seconds=1),
        repos=[RepoSettings(name="demo", full_name="owner/repo", enabled=True)],
        run_logs_dir=str(tmp_path / "runs"),
    )

    app = create_app(settings=settings)

    assert app.state.coding_agent_runner is not None
    assert app.state.codex_runner is app.state.coding_agent_runner
