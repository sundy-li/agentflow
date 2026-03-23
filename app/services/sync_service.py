from typing import Dict, Iterable, List, Set, Tuple

from app.constants import AGENT_CHANGED, AGENT_ISSUE, AGENT_REVIEWABLE
from app.domain.state_machine import TaskState, assert_transition, state_from_labels
from app.repository import Repository, utc_now


class SyncService:
    def __init__(self, repository: Repository, gh_client):
        self.repository = repository
        self.gh_client = gh_client

    def sync_once(self, repo_cfg) -> Dict:
        repo_id = self.repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
        seen: Set[Tuple[str, int]] = set()
        summary = {"issues": 0, "prs": 0, "stale": 0}

        for issue in self.gh_client.list_agent_issues(repo_cfg.full_name):
            self._sync_item(repo_id, "issue", issue)
            seen.add(("issue", int(issue["number"])))
            summary["issues"] += 1

        for pr in self.gh_client.list_agent_prs(repo_cfg.full_name):
            self._sync_item(repo_id, "pr", pr)
            seen.add(("pr", int(pr["number"])))
            summary["prs"] += 1

        tracked_states = {AGENT_ISSUE, AGENT_REVIEWABLE, AGENT_CHANGED}
        for task in self.repository.list_tasks(repo_id):
            key = (task["github_type"], int(task["github_number"]))
            if key in seen:
                continue
            if task["state"] in tracked_states and not task["is_stale"]:
                self.repository.set_task_stale(int(task["id"]), True)
                self.repository.insert_task_event(
                    int(task["id"]),
                    task["state"],
                    task["state"],
                    reason="sync_mark_stale",
                    actor="syncer",
                    source="github-sync",
                )
                summary["stale"] += 1
        return summary

    def _sync_item(self, repo_id: int, github_type: str, payload: Dict) -> None:
        labels = payload.get("labels", [])
        mapped = state_from_labels(labels)
        if mapped is None:
            mapped = TaskState.AGENT_ISSUE if github_type == "issue" else None
        if mapped is None:
            return

        now = utc_now()
        number = int(payload["number"])
        existing = self.repository.get_task_by_key(repo_id, github_type, number)
        current_state = existing["state"] if existing else mapped.value

        task = self.repository.upsert_task(
            repo_id=repo_id,
            github_type=github_type,
            github_number=number,
            title=payload.get("title", ""),
            url=payload.get("url", ""),
            labels=labels,
            state=current_state,
            assignee=payload.get("assignee"),
            last_synced_at=now,
            is_stale=False,
        )

        if existing is None:
            self.repository.insert_task_event(
                int(task["id"]),
                from_state=None,
                to_state=mapped.value,
                reason="sync_discovered",
                actor="syncer",
                source="github-sync",
            )
            if current_state != mapped.value:
                self.repository.transition_task(
                    int(task["id"]),
                    mapped.value,
                    reason="sync_label_change",
                    actor="syncer",
                    source="github-sync",
                )
            return

        if existing["state"] == mapped.value:
            return

        reason = "sync_label_change"
        try:
            assert_transition(existing["state"], mapped.value)
        except Exception:
            reason = "sync_label_override"

        self.repository.transition_task(
            int(task["id"]),
            mapped.value,
            reason=reason,
            actor="syncer",
            source="github-sync",
        )

