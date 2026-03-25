import logging
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from app.constants import MISSING_PR_AFTER_IMPLEMENT, RUNNABLE_STATES, STATE_LABELS
from app.domain.state_machine import TaskState, assert_transition
from app.repository import Repository

logger = logging.getLogger(__name__)

BLOCKED_PR_RETRY_DELAY_SECONDS = 900
WORKTREE_PATTERNS = [
    re.compile(r"worktree(?: 路径是| 位于|:)\s*[`']?([^`\n']+)[`']?"),
]
WORKTREE_PATH_PATTERN = re.compile(r"/[^\s'\"`\)\x1b]*/\.worktrees/[^\s'\"`\)\x1b]+")
WORKTREE_CWD_PATTERN = re.compile(r"\bin\s+(" + WORKTREE_PATH_PATTERN.pattern + r")")
BRANCH_PATTERNS = [
    re.compile(r"(?:分支是|branch:)\s*[`']?([A-Za-z0-9._/-]+)[`']?"),
]
COMMIT_PATTERNS = [
    re.compile(r"(?:实现提交是|本地提交是|implementation commit:)\s*[`']?([0-9a-f]{7,40})[`']?"),
]


class WorkerService:
    def __init__(self, repository: Repository, gh_client, coding_agent_runner, worker_id: str = "agentflow-worker"):
        self.repository = repository
        self.gh_client = gh_client
        self.coding_agent_runner = coding_agent_runner
        self.codex_runner = coding_agent_runner
        self.worker_id = worker_id
        self._active_task_ids = set()
        self._active_task_ids_lock = threading.Lock()

    def process_one(self, repo_cfg, review_latency_hours: float = 0, exclude_task_ids=None) -> Optional[Dict]:
        repo_id = self.repository.ensure_repo(repo_cfg.name, repo_cfg.full_name, repo_cfg.enabled)
        task = self.repository.claim_next_task(
            repo_id,
            RUNNABLE_STATES,
            self.worker_id,
            review_latency_hours=review_latency_hours,
            exclude_task_ids=exclude_task_ids,
        )
        if task is None:
            return None

        self._register_active_task(int(task["id"]))
        try:
            runner_task = self._with_repo_context(task, repo_cfg)
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
                return self._handle_issue_task(repo_cfg.full_name, task, runner_task)
            if state == TaskState.AGENT_REVIEWABLE:
                return self._handle_reviewable_task(repo_cfg.full_name, task, runner_task)
            if state == TaskState.AGENT_CHANGED:
                return self._handle_changed_task(repo_cfg.full_name, task, runner_task)
            return task
        finally:
            self.repository.release_task_lock(int(task["id"]))
            self._unregister_active_task(int(task["id"]))

    def shutdown(self) -> None:
        shutdown = getattr(self.coding_agent_runner, "shutdown", None)
        if callable(shutdown):
            shutdown()

    def _handle_issue_task(self, repo_full_name: str, task: Dict, runner_task: Dict) -> Dict:
        if task.get("blocked_reason") == MISSING_PR_AFTER_IMPLEMENT:
            return self._recover_blocked_issue_task(repo_full_name, task, runner_task)

        logger.info("worker=%s running implement for task id=%s issue#%s", self.worker_id, task["id"], task["github_number"])
        run = self._run_agent(runner_task, mode="implement")
        logger.info(
            "worker=%s coding agent finished task id=%s mode=implement run_id=%s exit_code=%s result=%s",
            self.worker_id,
            task["id"],
            run.run_id,
            run.exit_code,
            run.result,
        )
        if run.exit_code != 0:
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

        linked_pr_numbers = self._linked_pr_numbers_for_issue(repo_full_name, int(task["github_number"]))
        if linked_pr_numbers:
            return self._record_issue_implement_success(task, linked_pr_numbers, run.run_id)

        followup = self._run_pr_followup(task, runner_task)
        if followup.exit_code == 0:
            linked_pr_numbers = self._linked_pr_numbers_for_issue(repo_full_name, int(task["github_number"]))
            if linked_pr_numbers:
                return self._record_issue_implement_success(task, linked_pr_numbers, followup.run_id)

        self.repository.insert_task_event(
            int(task["id"]),
            task["state"],
            task["state"],
            reason="worker_implement_missing_pr_blocked",
            actor=self.worker_id,
            source="worker",
            run_id=followup.run_id,
        )
        return self._block_issue_for_retry(int(task["id"]))

    def _handle_reviewable_task(self, repo_full_name: str, task: Dict, runner_task: Dict) -> Dict:
        logger.info("worker=%s running review for task id=%s pr#%s", self.worker_id, task["id"], task["github_number"])
        run = self._run_agent(runner_task, mode="review")
        logger.info(
            "worker=%s coding agent finished task id=%s mode=review run_id=%s exit_code=%s result=%s",
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

    def _handle_changed_task(self, repo_full_name: str, task: Dict, runner_task: Dict) -> Dict:
        logger.info("worker=%s running fix for task id=%s pr#%s", self.worker_id, task["id"], task["github_number"])
        run = self._run_agent(runner_task, mode="fix")
        logger.info(
            "worker=%s coding agent finished task id=%s mode=fix run_id=%s exit_code=%s result=%s",
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

    def _recover_blocked_issue_task(self, repo_full_name: str, task: Dict, runner_task: Dict) -> Dict:
        linked_pr_numbers = self._linked_pr_numbers_for_issue(repo_full_name, int(task["github_number"]))
        if linked_pr_numbers:
            return self._record_issue_delivery_success(task, linked_pr_numbers, reason="worker_pr_followup_recovered")

        followup = self._run_pr_followup(task, runner_task)
        if followup.exit_code == 0:
            linked_pr_numbers = self._linked_pr_numbers_for_issue(repo_full_name, int(task["github_number"]))
            if linked_pr_numbers:
                return self._record_issue_delivery_success(
                    task,
                    linked_pr_numbers,
                    run_id=followup.run_id,
                    reason="worker_pr_followup_recovered",
                )

        self.repository.insert_task_event(
            int(task["id"]),
            task["state"],
            task["state"],
            reason="worker_pr_followup_retry_blocked",
            actor=self.worker_id,
            source="worker",
            run_id=followup.run_id,
        )
        return self._block_issue_for_retry(int(task["id"]))

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

    def _record_issue_implement_success(self, task: Dict, linked_pr_numbers: List[int], run_id: int) -> Dict:
        return self._record_issue_delivery_success(
            task,
            linked_pr_numbers,
            run_id=run_id,
            reason="worker_implement_success",
        )

    def _record_issue_delivery_success(
        self,
        task: Dict,
        linked_pr_numbers: List[int],
        run_id: Optional[int] = None,
        reason: str = "worker_implement_success",
    ) -> Dict:
        updated = self.repository.set_task_linked_prs(int(task["id"]), linked_pr_numbers)
        self.repository.insert_task_event(
            int(task["id"]),
            task["state"],
            task["state"],
            reason=reason,
            actor=self.worker_id,
            source="worker",
            run_id=run_id,
        )
        return updated

    def _linked_pr_numbers_for_issue(self, repo_full_name: str, issue_number: int) -> List[int]:
        open_pr_links = self.gh_client.list_open_pr_links(repo_full_name)
        linked_pr_numbers = []
        for pr in open_pr_links:
            if int(issue_number) not in {int(number) for number in pr.get("linked_issue_numbers", [])}:
                continue
            linked_pr_numbers.append(int(pr["number"]))
        return sorted(set(linked_pr_numbers))

    def _run_pr_followup(self, task: Dict, runner_task: Dict):
        followup_task = dict(runner_task)
        followup_task["pr_followup_only"] = True
        delivery_context = self._build_issue_delivery_context(task, runner_task)
        if delivery_context:
            followup_task["delivery_context"] = delivery_context
        followup = self._run_agent(followup_task, mode="implement")
        logger.info(
            "worker=%s coding agent finished task id=%s mode=implement-followup run_id=%s exit_code=%s result=%s",
            self.worker_id,
            task["id"],
            followup.run_id,
            followup.exit_code,
            followup.result,
        )
        return followup

    def _block_issue_for_retry(self, task_id: int) -> Dict:
        blocked_until = (datetime.utcnow() + timedelta(seconds=BLOCKED_PR_RETRY_DELAY_SECONDS)).replace(microsecond=0).isoformat() + "Z"
        return self.repository.set_task_blocked_reason(task_id, MISSING_PR_AFTER_IMPLEMENT, blocked_until=blocked_until)

    def _build_issue_delivery_context(self, task: Dict, runner_task: Dict) -> str:
        lines = []
        metadata = self._load_recent_delivery_metadata(int(task["id"]))
        if metadata.get("worktree"):
            lines.append("- Existing worktree: {0}".format(metadata["worktree"]))
        if metadata.get("branch"):
            lines.append("- Existing branch: {0}".format(metadata["branch"]))
        if metadata.get("commit"):
            lines.append("- Existing commit: {0}".format(metadata["commit"]))
        if metadata.get("output_path"):
            lines.append("- Previous run log: {0}".format(metadata["output_path"]))
        if not lines:
            return ""
        return (
            "Previous delivery context:\n"
            + "\n".join(lines)
            + "\nPrefer continuing from this local git state. If the previous agent session cannot be resumed directly, reuse this worktree, branch, and commit."
        )

    def _load_recent_delivery_metadata(self, task_id: int) -> Dict[str, str]:
        metadata: Dict[str, str] = {}
        for run in self.repository.list_task_runs(task_id, limit=10):
            output_path = run.get("output_path")
            if output_path and "output_path" not in metadata:
                metadata["output_path"] = output_path
            metadata.setdefault("worktree", self._extract_worktree_from_log(output_path))
            log_text = self._read_log_tail(output_path)
            if not log_text:
                continue
            metadata.setdefault("branch", self._match_first(log_text, BRANCH_PATTERNS))
            metadata.setdefault("commit", self._match_first(log_text, COMMIT_PATTERNS))
            if metadata.get("worktree") and metadata.get("branch") and metadata.get("commit"):
                break
        return {key: value for key, value in metadata.items() if value}

    @staticmethod
    def _match_first(text: str, patterns) -> str:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return match.group(1).strip()
        return ""

    @classmethod
    def _extract_worktree_path(cls, text: str) -> str:
        worktree = cls._match_first(text, WORKTREE_PATTERNS)
        if cls._is_worktree_path(worktree):
            return worktree
        matches = list(WORKTREE_CWD_PATTERN.finditer(text or ""))
        if matches:
            return matches[-1].group(1).strip()
        return ""

    @staticmethod
    def _is_worktree_path(value: str) -> bool:
        candidate = (value or "").strip()
        return bool(WORKTREE_PATH_PATTERN.fullmatch(candidate))

    @staticmethod
    def _read_log_tail(output_path: Optional[str], max_bytes: int = 120000) -> str:
        if not output_path:
            return ""
        path = Path(output_path)
        if not path.exists():
            return ""
        data = path.read_bytes()
        return data[-max_bytes:].decode("utf-8", errors="ignore")

    @staticmethod
    def _read_log(output_path: Optional[str]) -> str:
        if not output_path:
            return ""
        path = Path(output_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")

    @classmethod
    def _extract_worktree_from_log(cls, output_path: Optional[str]) -> str:
        log_text = cls._read_log_tail(output_path)
        worktree = cls._extract_worktree_path(log_text)
        if worktree:
            return worktree
        full_log = cls._read_log(output_path)
        if not full_log or full_log == log_text:
            return ""
        return cls._extract_worktree_path(full_log)

    @staticmethod
    def _with_repo_context(task: Dict, repo_cfg) -> Dict:
        payload = dict(task)
        payload["repo_full_name"] = repo_cfg.full_name
        payload["repo_forked"] = getattr(repo_cfg, "forked", None)
        payload["repo_workspace"] = getattr(repo_cfg, "workspace", None)
        payload["repo_default_branch"] = getattr(repo_cfg, "default_branch", "main")
        return payload

    def _run_agent(self, task: Dict, mode: str) -> Dict:
        runner = self.coding_agent_runner
        run_task = getattr(runner, "run_task", None)
        if callable(run_task):
            result = run_task(task, mode=mode)
        else:
            result = runner.run_codex(task, mode=mode)
        self._persist_worktree_from_run(int(task["id"]), getattr(result, "output_path", None))
        return result

    def _persist_worktree_from_run(self, task_id: int, output_path: Optional[str]) -> None:
        worktree = self._extract_worktree_from_log(output_path)
        if not worktree:
            return
        self.repository.set_task_worktree_path(task_id, worktree)

    def active_task_ids(self):
        with self._active_task_ids_lock:
            return sorted(self._active_task_ids)

    def _register_active_task(self, task_id: int) -> None:
        with self._active_task_ids_lock:
            self._active_task_ids.add(int(task_id))

    def _unregister_active_task(self, task_id: int) -> None:
        with self._active_task_ids_lock:
            self._active_task_ids.discard(int(task_id))
