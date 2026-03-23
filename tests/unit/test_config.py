from pathlib import Path

from app.config import load_settings


def test_scheduler_parallelism_defaults_to_four(tmp_path):
    config_path = tmp_path / "agentflow.yaml"
    config_path.write_text("repos:\n  - enabled: false\n", encoding="utf-8")

    settings = load_settings(str(config_path))

    assert settings.scheduler.max_parallel_tasks == 4
    assert settings.scheduler.review_latency_hours == 0
