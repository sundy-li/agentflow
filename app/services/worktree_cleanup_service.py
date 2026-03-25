import logging
import subprocess
from typing import Dict, List, Optional

from app.repository import Repository

logger = logging.getLogger(__name__)


class WorktreeCleanupService:
    def __init__(self, repository: Repository, gh_client, git_runner=None):
        self.repository = repository
        self.gh_client = gh_client
        self.git_runner = git_runner

    def cleanup_repo(self, repo_cfg, stale_pr_task_ids: Optional[List[int]] = None) -> Dict:
        repo_id = self.repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
        prioritized_ids = {int(task_id) for task_id in (stale_pr_task_ids or [])}
        candidates = self.repository.list_pr_tasks_pending_worktree_cleanup(repo_id)
        candidates.sort(key=lambda task: (0 if int(task["id"]) in prioritized_ids else 1, task.get("updated_at") or "", int(task["id"])))

        summary = {"attempted": 0, "removed": 0, "failed": 0, "skipped_open": 0}
        for task in candidates:
            try:
                state = self.gh_client.get_pr_state(repo_cfg.full_name, int(task["github_number"]))
                if state == "open":
                    summary["skipped_open"] += 1
                    continue
                if state not in {"closed", "merged"}:
                    raise RuntimeError("unexpected PR state: {0}".format(state))

                summary["attempted"] += 1
                self._cleanup_task(repo_cfg, task)
            except Exception as exc:
                self.repository.mark_task_worktree_cleanup_failed(int(task["id"]), str(exc))
                self.repository.insert_task_event(
                    int(task["id"]),
                    task["state"],
                    task["state"],
                    reason="worktree_cleanup_failed",
                    actor="worktree-cleanup",
                    source="scheduler",
                )
                summary["failed"] += 1
                logger.warning(
                    "worktree cleanup failed repo=%s pr=%s path=%s error=%s",
                    repo_cfg.full_name,
                    task["github_number"],
                    task.get("worktree_path"),
                    exc,
                )
                continue

            self.repository.mark_task_worktree_removed(int(task["id"]))
            self.repository.insert_task_event(
                int(task["id"]),
                task["state"],
                task["state"],
                reason="worktree_cleanup_succeeded",
                actor="worktree-cleanup",
                source="scheduler",
            )
            summary["removed"] += 1
        return summary

    def _cleanup_task(self, repo_cfg, task: Dict) -> None:
        workspace = (getattr(repo_cfg, "workspace", None) or "").strip()
        if not workspace:
            raise RuntimeError("repo workspace is required for worktree cleanup")

        worktree_path = (task.get("worktree_path") or "").strip()
        if not worktree_path:
            raise RuntimeError("task worktree_path is missing")

        if not self._is_registered_worktree(workspace, worktree_path):
            return

        self._run_git(["git", "worktree", "remove", worktree_path], cwd=workspace)

    def _is_registered_worktree(self, workspace: str, worktree_path: str) -> bool:
        output = self._run_git(["git", "worktree", "list", "--porcelain"], cwd=workspace)
        for line in output.splitlines():
            if not line.startswith("worktree "):
                continue
            if line.split(" ", 1)[1].strip() == worktree_path:
                return True
        return False

    def _run_git(self, command: List[str], cwd: str) -> str:
        if self.git_runner is not None:
            return self.git_runner(command, cwd)

        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "git command failed"
            raise RuntimeError(error)
        return result.stdout.strip()
