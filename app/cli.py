import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.config import get_active_repo, load_settings
from app.constants import AGENT_APPROVED, AGENT_CHANGED, AGENT_ISSUE, AGENT_REVIEWABLE
from app.db import run_migrations
from app.repository import Repository
from app.services.gh_client import GHClient
from app.services.sync_service import SyncService

STATE_ORDER = [
    AGENT_ISSUE,
    AGENT_REVIEWABLE,
    AGENT_CHANGED,
    AGENT_APPROVED,
]

TABLE_COLUMNS = [
    ("ID", 4),
    ("Type", 5),
    ("#", 5),
    ("Title", 32),
    ("Assignee", 12),
    ("Stale", 5),
    ("Locked", 7),
    ("Updated", 20),
]

RUN_TABLE_COLUMNS = [
    ("Run", 5),
    ("Status", 7),
    ("Mode", 10),
    ("Task", 10),
    ("Title", 32),
    ("Started", 20),
    ("Result", 10),
]


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agentflow")
    parser.add_argument("--config", help="Path to agentflow YAML config")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("board", help="Show the local task board from SQLite")
    subparsers.add_parser("runs", help="Show persisted Codex runs from SQLite")
    inspect_parser = subparsers.add_parser("inspect", help="Show output for a persisted Codex run")
    inspect_parser.add_argument("run_id", type=int, help="Run ID from the runs table")
    inspect_parser.add_argument("--follow", action="store_true", help="Follow live output until the run finishes")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    settings = load_settings(args.config)
    run_migrations(settings.database.path)
    repository = Repository(settings.database.path)
    if args.command == "board":
        active_repo = get_active_repo(settings)
        if active_repo is None or not active_repo.enabled:
            print("No active repo configured.")
            return 1
        sync_board(repository, active_repo)
        print(render_board(repository, active_repo))
        return 0
    if args.command == "runs":
        active_repo = get_active_repo(settings)
        if active_repo is None or not active_repo.enabled:
            print("No active repo configured.")
            return 1
        print(render_runs(repository, active_repo))
        return 0
    if args.command == "inspect":
        return inspect_run(repository, args.run_id, follow=args.follow)

    raise ValueError("Unsupported command: {0}".format(args.command))


def render_board(repository: Repository, repo_cfg) -> str:
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
    tasks = repository.list_board_tasks(repo_id)
    running_task_ids = set(repository.list_running_task_ids(repo_id))
    grouped: Dict[str, List[Dict]] = {state: [] for state in STATE_ORDER}
    for task in tasks:
        grouped.setdefault(task["state"], []).append(task)

    lines = ["Repo: {0}".format(repo_cfg.full_name)]
    for state in STATE_ORDER:
        state_tasks = grouped.get(state, [])
        lines.append("")
        lines.append("[{0}] {1} tasks".format(state, len(state_tasks)))
        lines.extend(_render_task_table(state_tasks, running_task_ids))
    return "\n".join(lines)


def sync_board(repository: Repository, repo_cfg) -> None:
    try:
        SyncService(repository, GHClient()).sync_once(repo_cfg)
    except Exception as exc:
        print("Warning: board sync failed: {0}".format(exc), file=sys.stderr)


def render_runs(repository: Repository, repo_cfg) -> str:
    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
    runs = repository.list_runs(repo_id)
    lines = ["Repo: {0}".format(repo_cfg.full_name), "", "Runs ({0})".format(len(runs))]
    lines.extend(_render_run_table(runs))
    return "\n".join(lines)


def inspect_run(repository: Repository, run_id: int, follow: bool = False, poll_interval_seconds: float = 0.1) -> int:
    run = repository.get_run_details(run_id)
    if run is None:
        print("Run not found: {0}".format(run_id))
        return 1

    print("Run: {0}".format(run["id"]))
    print("Status: {0}".format(_run_status(run)))
    print("Mode: {0}".format(run["run_type"]))
    print("Task: {0}#{1}".format(run["github_type"], run["github_number"]))
    print("Result: {0}".format(run.get("result") or "-"))
    print("Output: {0}".format(run.get("output_path") or "-"))
    print("")
    _stream_run_output(repository, run_id, follow=follow, poll_interval_seconds=poll_interval_seconds)
    return 0


def _render_task_table(tasks: Iterable[Dict], running_task_ids: Optional[set] = None) -> List[str]:
    header = " ".join(_pad(label, width) for label, width in TABLE_COLUMNS)
    divider = " ".join("-" * width for _, width in TABLE_COLUMNS)
    lines = [header, divider]
    for task in tasks:
        lines.append(
            " ".join(
                [
                    _pad(str(task["id"]), 4),
                    _pad(task["github_type"], 5),
                    _pad(str(task["github_number"]), 5),
                    _pad(_truncate(task["title"], 32), 32),
                    _pad(task.get("assignee") or "-", 12),
                    _pad("yes" if task.get("is_stale") else "no", 5),
                    _pad(_locked_status(task, running_task_ids), 7),
                    _pad((task.get("updated_at") or "")[:20], 20),
                ]
            )
        )
    return lines


def _render_run_table(runs: Iterable[Dict]) -> List[str]:
    header = " ".join(_pad(label, width) for label, width in RUN_TABLE_COLUMNS)
    divider = " ".join("-" * width for _, width in RUN_TABLE_COLUMNS)
    lines = [header, divider]
    for run in runs:
        lines.append(
            " ".join(
                [
                    _pad(str(run["id"]), 5),
                    _pad(_run_status(run), 7),
                    _pad(run["run_type"], 10),
                    _pad("{0}#{1}".format(run["github_type"], run["github_number"]), 10),
                    _pad(_truncate(run["title"], 32), 32),
                    _pad((run.get("started_at") or "")[:20], 20),
                    _pad(run.get("result") or "-", 10),
                ]
            )
        )
    return lines


def _stream_run_output(
    repository: Repository,
    run_id: int,
    follow: bool,
    poll_interval_seconds: float,
) -> None:
    offset = 0
    while True:
        run = repository.get_run_details(run_id)
        if run is None:
            break
        offset = _print_output_delta(run.get("output_path"), offset)
        if not follow:
            break
        output_path = run.get("output_path")
        if run.get("finished_at") and _output_size(output_path) <= offset:
            break
        time.sleep(poll_interval_seconds)


def _print_output_delta(output_path: Optional[str], offset: int) -> int:
    if not output_path:
        return offset
    path = Path(output_path)
    if not path.exists():
        return offset
    with path.open("rb") as fh:
        fh.seek(offset)
        data = fh.read()
    if not data:
        return offset
    sys.stdout.write(data.decode("utf-8", errors="ignore"))
    sys.stdout.flush()
    return offset + len(data)


def _output_size(output_path: Optional[str]) -> int:
    if not output_path:
        return 0
    path = Path(output_path)
    if not path.exists():
        return 0
    return path.stat().st_size


def _locked_status(task: Dict, running_task_ids: Optional[set] = None) -> str:
    if running_task_ids and int(task["id"]) in running_task_ids:
        return "running"
    if task.get("blocked_reason"):
        return "blocked"
    locked_until = task.get("locked_until")
    if locked_until and _parse_utc_timestamp(locked_until) > datetime.now(timezone.utc):
        return "running"
    return "idle"


def _run_status(run: Dict) -> str:
    if run.get("finished_at"):
        return "done"
    return "running"


def _truncate(value: str, width: int) -> str:
    if len(value) <= width:
        return value
    return value[: width - 3] + "..."


def _pad(value: str, width: int) -> str:
    return value.ljust(width)


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
