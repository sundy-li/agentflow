from typing import Dict, Iterable, List, Set, Tuple

from app.constants import STATE_LABELS
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
        open_pr_links = self.gh_client.list_open_pr_links(repo_cfg.full_name)
        linked_issue_numbers_to_prs = self._group_open_pr_links(open_pr_links)

        for issue in self.gh_client.list_agent_issues(repo_cfg.full_name):
            issue_payload = dict(issue)
            issue_payload["linked_pr_numbers"] = linked_issue_numbers_to_prs.get(int(issue["number"]), [])
            issue_payload["has_open_linked_pr"] = bool(issue_payload["linked_pr_numbers"])
            self._sync_item(repo_id, "issue", issue_payload)
            seen.add(("issue", int(issue["number"])))
            summary["issues"] += 1

        for pr in self.gh_client.list_agent_prs(repo_cfg.full_name):
            self._sync_item(repo_id, "pr", pr)
            seen.add(("pr", int(pr["number"])))
            summary["prs"] += 1

        tracked_states = set(STATE_LABELS)
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
        pr_head_sha = None
        pr_last_push_observed_at = None
        if github_type == "pr":
            observed_head_sha = payload.get("head_sha") or (existing.get("pr_head_sha") if existing else None)
            previous_head_sha = existing.get("pr_head_sha") if existing else None
            previous_observed_at = existing.get("pr_last_push_observed_at") if existing else None
            pr_head_sha = observed_head_sha
            if observed_head_sha and observed_head_sha != previous_head_sha:
                pr_last_push_observed_at = now
            else:
                pr_last_push_observed_at = previous_observed_at

        task = self.repository.upsert_task(
            repo_id=repo_id,
            github_type=github_type,
            github_number=number,
            title=payload.get("title", ""),
            url=payload.get("url", ""),
            labels=labels,
            state=current_state,
            pr_head_sha=pr_head_sha,
            pr_last_push_observed_at=pr_last_push_observed_at,
            assignee=payload.get("assignee"),
            last_synced_at=now,
            is_stale=False,
            has_open_linked_pr=bool(payload.get("has_open_linked_pr", False)),
            linked_pr_numbers=payload.get("linked_pr_numbers", []),
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

    @staticmethod
    def _group_open_pr_links(open_pr_links: Iterable[Dict]) -> Dict[int, List[int]]:
        linked_issue_numbers_to_prs: Dict[int, List[int]] = {}
        for pr in open_pr_links:
            pr_number = int(pr["number"])
            for issue_number in pr.get("linked_issue_numbers", []):
                linked_issue_numbers_to_prs.setdefault(int(issue_number), []).append(pr_number)
        for issue_number, pr_numbers in linked_issue_numbers_to_prs.items():
            linked_issue_numbers_to_prs[issue_number] = sorted(set(pr_numbers))
        return linked_issue_numbers_to_prs
