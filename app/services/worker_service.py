import logging
from typing import Dict, Optional

from app.constants import RUNNABLE_STATES, STATE_LABELS
from app.domain.state_machine import TaskState, assert_transition
from app.repository import Repository

logger = logging.getLogger(__name__)


class WorkerService:
    def __init__(self, repository: Repository, gh_client, codex_runner, worker_id: str = "agentflow-worker"):
        self.repository = repository
        self.gh_client = gh_client
        self.codex_runner = codex_runner
        self.worker_id = worker_id

    def process_one(self, repo_cfg, review_latency_hours: float = 0) -> Optional[Dict]:
        repo_id = self.repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
        task = self.repository.claim_next_task(
            repo_id,
            RUNNABLE_STATES,
            self.worker_id,
            review_latency_hours=review_latency_hours,
        )
        if task is None:
            return None

        try:
            codex_task = self._with_repo_context(task, repo_cfg)
            state = TaskState(task["state"])
            logger.info(
                "worker=%s claimed task id=%s %s#%s state=%s title=%s",
                self.worker_id,
                task["id"],
                task["github_type"],
                task["github_number"],
                task["state"],
                task["title"],
            )
            if state == TaskState.AGENT_ISSUE:
                return self._handle_issue_task(repo_cfg.full_name, task, codex_task)
            if state == TaskState.AGENT_REVIEWABLE:
                return self._handle_reviewable_task(repo_cfg.full_name, task, codex_task)
            if state == TaskState.AGENT_CHANGED:
                return self._handle_changed_task(repo_cfg.full_name, task, codex_task)
            return task
        finally:
            self.repository.release_task_lock(int(task["id"]))

    def shutdown(self) -> None:
        shutdown = getattr(self.codex_runner, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def _handle_issue_task(self, repo_full_name: str, task: Dict, codex_task: Dict) -> Dict:
        logger.info("worker=%s running implement for task id=%s issue#%s", self.worker_id, task["id"], task["github_number"])
        run = self.codex_runner.run_codex(codex_task, mode="implement")
        logger.info(
            "worker=%s codex finished task id=%s mode=implement run_id=%s exit_code=%s result=%s",
            self.worker_id,
            task["id"],
            run.run_id,
            run.exit_code,
            run.result,
        )
        if run.exit_code == 0:
            updated = self.repository.set_task_linked_prs(int(task["id"]), None)
            self.repository.insert_task_event(
                int(task["id"]),
                task["state"],
                task["state"],
                reason="worker_implement_success",
                actor=self.worker_id,
                source="worker",
                run_id=run.run_id,
            )
            return updated
        self.repository.insert_task_event(
            int(task["id"]),
            task["state"],
            task["state"],
            reason="worker_implement_failed",
            actor=self.worker_id,
            source="worker",
            run_id=run.run_id,
        )
        return task

    def _handle_reviewable_task(self, repo_full_name: str, task: Dict, codex_task: Dict) -> Dict:
        logger.info("worker=%s running review for task id=%s pr#%s", self.worker_id, task["id"], task["github_number"])
        run = self.codex_runner.run_codex(codex_task, mode="review")
        logger.info(
            "worker=%s codex finished task id=%s mode=review run_id=%s exit_code=%s result=%s",
            self.worker_id,
            task["id"],
            run.run_id,
            run.exit_code,
            run.result,
        )
        to_state = TaskState.AGENT_APPROVED
        reason = "worker_review_passed"
        if run.exit_code != 0 or run.result in ("failed", "fail", "timeout"):
            to_state = TaskState.AGENT_CHANGED
            reason = "worker_review_failed"
        return self._apply_transition(
            repo_full_name=repo_full_name,
            task=task,
            to_state=to_state,
            reason=reason,
            run_id=run.run_id,
        )

    def _handle_changed_task(self, repo_full_name: str, task: Dict, codex_task: Dict) -> Dict:
        logger.info("worker=%s running fix for task id=%s pr#%s", self.worker_id, task["id"], task["github_number"])
        run = self.codex_runner.run_codex(codex_task, mode="fix")
        logger.info(
            "worker=%s codex finished task id=%s mode=fix run_id=%s exit_code=%s result=%s",
            self.worker_id,
            task["id"],
            run.run_id,
            run.exit_code,
            run.result,
        )
        if run.exit_code == 0:
            return self._apply_transition(
                repo_full_name=repo_full_name,
                task=task,
                to_state=TaskState.AGENT_REVIEWABLE,
                reason="worker_fix_success",
                run_id=run.run_id,
            )
        self.repository.insert_task_event(
            int(task["id"]),
            task["state"],
            task["state"],
            reason="worker_fix_failed",
            actor=self.worker_id,
            source="worker",
            run_id=run.run_id,
        )
        return task

    def _apply_transition(
        self,
        repo_full_name: str,
        task: Dict,
        to_state: TaskState,
        reason: str,
        run_id: int,
    ) -> Dict:
        current_state = TaskState(task["state"])
        assert_transition(current_state, to_state)
        remove_labels = [label for label in STATE_LABELS if label != to_state.value]
        try:
            self.gh_client.set_labels(
                repo_full_name=repo_full_name,
                item_type=task["github_type"],
                number=int(task["github_number"]),
                add_labels=[to_state.value],
                remove_labels=remove_labels,
            )
        except Exception:
            self.repository.insert_task_event(
                int(task["id"]),
                current_state.value,
                current_state.value,
                reason="worker_label_update_failed",
                actor=self.worker_id,
                source="worker",
                run_id=run_id,
            )
            return task

        return self.repository.transition_task(
            int(task["id"]),
            to_state.value,
            reason=reason,
            actor=self.worker_id,
            source="worker",
            run_id=run_id,
        )

    @staticmethod
    def _with_repo_context(task: Dict, repo_cfg) -> Dict:
        payload = dict(task)
        payload["repo_full_name"] = repo_cfg.full_name
        payload["repo_forked"] = getattr(repo_cfg, "forked", None)
        payload["repo_workspace"] = getattr(repo_cfg, "workspace", None)
        payload["repo_default_branch"] = getattr(repo_cfg, "default_branch", "main")
        return payload
