from typing import Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.constants import AGENT_APPROVED, AGENT_CHANGED, AGENT_ISSUE, AGENT_REVIEWABLE
from app.repository import utc_now

router = APIRouter()


def _task_view(task: Dict) -> Dict:
    return {
        "id": task["id"],
        "type": task["github_type"],
        "number": task["github_number"],
        "title": task["title"],
        "url": task["url"],
        "state": task["state"],
        "assignee": task.get("assignee"),
        "labels": task.get("labels", []),
        "is_stale": bool(task.get("is_stale")),
        "updated_at": task.get("updated_at"),
    }


@router.get("/api/board")
def get_board(request: Request) -> Dict:
    repository = request.app.state.repository
    repo_cfg = request.app.state.active_repo
    columns = {
        AGENT_ISSUE: [],
        AGENT_REVIEWABLE: [],
        AGENT_CHANGED: [],
        AGENT_APPROVED: [],
    }
    if repo_cfg is None:
        return {"repo": None, "columns": columns, "updated_at": utc_now()}

    repo_id = repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
    tasks = repository.list_board_tasks(repo_id)
    for task in tasks:
        columns.setdefault(task["state"], []).append(_task_view(task))

    return {
        "repo": repo_cfg.full_name,
        "columns": columns,
        "updated_at": utc_now(),
    }


@router.get("/api/tasks/{task_id}/events")
def get_task_events(task_id: int, request: Request) -> Dict:
    repository = request.app.state.repository
    events = repository.get_task_events(task_id)
    return {"task_id": task_id, "events": events}


@router.get("/board", response_class=HTMLResponse)
def board_page(request: Request):
    templates = request.app.state.templates
    repo_cfg = request.app.state.active_repo
    repo_name = repo_cfg.full_name if repo_cfg else "N/A"
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            "repo_name": repo_name,
            "refresh_seconds": request.app.state.settings.ui.refresh_seconds,
        },
    )
