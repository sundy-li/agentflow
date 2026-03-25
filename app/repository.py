import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.constants import AGENT_APPROVED, AGENT_CHANGED, AGENT_ISSUE, AGENT_REVIEWABLE, MISSING_PR_AFTER_IMPLEMENT
from app.db import connect_db


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class Repository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def ensure_repo(self, name: str, full_name: str, enabled: bool = True) -> int:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO repos(name, full_name, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(full_name)
                DO UPDATE SET
                  name = excluded.name,
                  enabled = excluded.enabled,
                  updated_at = excluded.updated_at
                """,
                (name, full_name, int(enabled), now, now),
            )
            row = conn.execute(
                "SELECT id FROM repos WHERE full_name = ?",
                (full_name,),
            ).fetchone()
            conn.commit()
        return int(row["id"])

    def get_repo_by_full_name(self, full_name: str) -> Optional[Dict]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM repos WHERE full_name = ?",
                (full_name,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_task(
        self,
        repo_id: int,
        github_type: str,
        github_number: int,
        title: str,
        url: str,
        labels: List[str],
        state: str,
        pr_head_sha: Optional[str] = None,
        pr_last_push_observed_at: Optional[str] = None,
        assignee: Optional[str] = None,
        last_synced_at: Optional[str] = None,
        is_stale: bool = False,
        github_state: str = "open",
        has_open_linked_pr: bool = False,
        linked_pr_numbers: Optional[List[int]] = None,
        blocked_reason: Optional[str] = None,
    ) -> Dict:
        now = utc_now()
        labels_json = json.dumps(sorted(set(labels)))
        linked_pr_numbers_json = json.dumps(sorted({int(number) for number in linked_pr_numbers or []}))
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                  repo_id, github_type, github_number, title, url,
                  labels_json, state, github_state, pr_head_sha, pr_last_push_observed_at,
                  assignee, is_stale, last_synced_at, has_open_linked_pr, linked_pr_numbers_json, blocked_reason,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id, github_type, github_number)
                DO UPDATE SET
                  title = excluded.title,
                  url = excluded.url,
                  labels_json = excluded.labels_json,
                  state = excluded.state,
                  github_state = excluded.github_state,
                  pr_head_sha = excluded.pr_head_sha,
                  pr_last_push_observed_at = excluded.pr_last_push_observed_at,
                  assignee = excluded.assignee,
                  is_stale = excluded.is_stale,
                  last_synced_at = excluded.last_synced_at,
                  has_open_linked_pr = excluded.has_open_linked_pr,
                  linked_pr_numbers_json = excluded.linked_pr_numbers_json,
                  blocked_reason = excluded.blocked_reason,
                  updated_at = excluded.updated_at
                """,
                (
                    repo_id,
                    github_type,
                    github_number,
                    title,
                    url,
                    labels_json,
                    state,
                    github_state,
                    pr_head_sha,
                    pr_last_push_observed_at,
                    assignee,
                    int(is_stale),
                    last_synced_at,
                    int(has_open_linked_pr),
                    linked_pr_numbers_json,
                    blocked_reason,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE repo_id = ? AND github_type = ? AND github_number = ?
                """,
                (repo_id, github_type, github_number),
            ).fetchone()
            conn.commit()
        return self._task_row_to_dict(row)

    def get_task(self, task_id: int) -> Optional[Dict]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._task_row_to_dict(row) if row else None

    def get_task_by_key(self, repo_id: int, github_type: str, github_number: int) -> Optional[Dict]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE repo_id = ? AND github_type = ? AND github_number = ?
                """,
                (repo_id, github_type, github_number),
            ).fetchone()
        return self._task_row_to_dict(row) if row else None

    def list_tasks(self, repo_id: int) -> List[Dict]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE repo_id = ? ORDER BY id ASC",
                (repo_id,),
            ).fetchall()
        return [self._task_row_to_dict(row) for row in rows]

    def list_board_tasks(self, repo_id: int) -> List[Dict]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE repo_id = ?
                  AND COALESCE(github_state, 'open') = 'open'
                ORDER BY
                  CASE state
                    WHEN 'agent-issue' THEN 1
                    WHEN 'agent-reviewable' THEN 2
                    WHEN 'agent-changed' THEN 3
                    WHEN 'agent-approved' THEN 4
                    ELSE 99
                  END,
                  updated_at DESC,
                  id DESC
                """,
                (repo_id,),
            ).fetchall()
        tasks = [self._task_row_to_dict(row) for row in rows]
        visible_pr_numbers = {
            int(task["github_number"])
            for task in tasks
            if task["github_type"] == "pr" and task["state"] in {AGENT_REVIEWABLE, AGENT_CHANGED, AGENT_APPROVED}
        }
        return [
            task
            for task in tasks
            if not (
                task["github_type"] == "issue"
                and task["state"] == AGENT_ISSUE
                and bool(set(task.get("linked_pr_numbers", [])) & visible_pr_numbers)
            )
        ]

    def insert_task_event(
        self,
        task_id: int,
        from_state: Optional[str],
        to_state: Optional[str],
        reason: str,
        actor: str,
        source: str,
        run_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO task_events(task_id, from_state, to_state, reason, actor, source, run_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, from_state, to_state, reason, actor, source, run_id, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def transition_task(
        self,
        task_id: int,
        to_state: str,
        reason: str,
        actor: str,
        source: str,
        run_id: Optional[int] = None,
    ) -> Dict:
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        from_state = task["state"]
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET state = ?, is_stale = 0, updated_at = ?
                WHERE id = ?
                """,
                (to_state, now, task_id),
            )
            conn.execute(
                """
                INSERT INTO task_events(task_id, from_state, to_state, reason, actor, source, run_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, from_state, to_state, reason, actor, source, run_id, now),
            )
            conn.commit()
        updated = self.get_task(task_id)
        return updated if updated else task

    def set_task_stale(self, task_id: int, is_stale: bool) -> None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET is_stale = ?, updated_at = ? WHERE id = ?",
                (int(is_stale), now, task_id),
            )
            conn.commit()

    def set_task_github_state(self, task_id: int, github_state: str, is_stale: Optional[bool] = None) -> Dict:
        now = utc_now()
        normalized = (github_state or "open").strip().lower() or "open"
        parameters = [normalized, now, now, task_id]
        stale_clause = ""
        if is_stale is not None:
            stale_clause = ", is_stale = ?"
            parameters.insert(1, int(is_stale))
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET github_state = ?{0},
                    last_synced_at = ?,
                    updated_at = ?
                WHERE id = ?
                """.format(stale_clause),
                parameters,
            )
            conn.commit()
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        return task

    def set_task_linked_prs(self, task_id: int, linked_pr_numbers: Optional[List[int]]) -> Dict:
        now = utc_now()
        normalized = sorted({int(number) for number in linked_pr_numbers or []})
        has_open_linked_pr = int(bool(normalized))
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET has_open_linked_pr = ?,
                    linked_pr_numbers_json = ?,
                    blocked_reason = CASE WHEN ? = 1 THEN NULL ELSE blocked_reason END,
                    blocked_until = CASE WHEN ? = 1 THEN NULL ELSE blocked_until END,
                    updated_at = ?
                WHERE id = ?
                """,
                (has_open_linked_pr, json.dumps(normalized), has_open_linked_pr, has_open_linked_pr, now, task_id),
            )
            conn.commit()
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        return task

    def set_task_blocked_reason(
        self,
        task_id: int,
        blocked_reason: Optional[str],
        blocked_until: Optional[str] = None,
    ) -> Dict:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET blocked_reason = ?, blocked_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (blocked_reason, blocked_until, now, task_id),
            )
            conn.commit()
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        return task

    def set_task_worktree_path(self, task_id: int, worktree_path: str) -> Dict:
        normalized = (worktree_path or "").strip()
        if not normalized:
            task = self.get_task(task_id)
            if task is None:
                raise ValueError("Task not found: {0}".format(task_id))
            return task

        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET worktree_path = ?,
                    worktree_cleanup_attempted_at = NULL,
                    worktree_cleanup_error = NULL,
                    worktree_removed_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (normalized, now, task_id),
            )
            conn.commit()
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        return task

    def mark_task_worktree_cleanup_failed(self, task_id: int, error: str) -> Dict:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET worktree_cleanup_attempted_at = ?,
                    worktree_cleanup_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, error, now, task_id),
            )
            conn.commit()
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        return task

    def mark_task_worktree_removed(self, task_id: int) -> Dict:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET worktree_cleanup_attempted_at = ?,
                    worktree_cleanup_error = NULL,
                    worktree_removed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, now, task_id),
            )
            conn.commit()
        task = self.get_task(task_id)
        if task is None:
            raise ValueError("Task not found: {0}".format(task_id))
        return task

    def list_pr_tasks_pending_worktree_cleanup(self, repo_id: int) -> List[Dict]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE repo_id = ?
                  AND github_type = 'pr'
                  AND is_stale = 1
                  AND worktree_removed_at IS NULL
                  AND worktree_path IS NOT NULL
                  AND worktree_path != ''
                ORDER BY updated_at ASC, id ASC
                """,
                (repo_id,),
            ).fetchall()
        return [self._task_row_to_dict(row) for row in rows]

    def mark_tasks_ready_for_retry(self, repo_id: int, blocked_reason: str) -> int:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET blocked_until = NULL, updated_at = ?
                WHERE repo_id = ? AND blocked_reason = ?
                """,
                (now, repo_id, blocked_reason),
            )
            conn.commit()
        return max(int(cursor.rowcount), 0)

    def claim_next_task(
        self,
        repo_id: int,
        states: List[str],
        worker_id: str,
        lock_seconds: int = 300,
        review_latency_hours: float = 0,
        exclude_task_ids: Optional[List[int]] = None,
    ) -> Optional[Dict]:
        if not states:
            return None
        now = utc_now()
        lock_until = (datetime.utcnow() + timedelta(seconds=lock_seconds)).replace(microsecond=0).isoformat() + "Z"
        placeholders = ",".join(["?"] * len(states))
        latency_filter = ""
        exclude_filter = ""
        recoverable_blocked_reason = MISSING_PR_AFTER_IMPLEMENT
        parameters = [repo_id] + list(states) + [recoverable_blocked_reason, now, now]
        excluded_ids = sorted({int(task_id) for task_id in (exclude_task_ids or [])})
        if excluded_ids:
            exclude_filter = " AND id NOT IN ({0})".format(",".join(["?"] * len(excluded_ids)))
            parameters.extend(excluded_ids)
        if float(review_latency_hours) > 0:
            review_ready_before = (
                datetime.utcnow() - timedelta(hours=float(review_latency_hours))
            ).replace(microsecond=0).isoformat() + "Z"
            latency_filter = """
                  AND (
                    state != ?
                    OR github_type != 'pr'
                    OR pr_last_push_observed_at IS NULL
                    OR pr_last_push_observed_at <= ?
                  )
            """
            parameters.extend([AGENT_REVIEWABLE, review_ready_before])

        with connect_db(self.db_path) as conn:
            candidate = conn.execute(
                """
                SELECT id FROM tasks
                WHERE repo_id = ?
                  AND state IN ({0})
                  AND COALESCE(github_state, 'open') = 'open'
                  AND is_stale = 0
                  AND (github_type != 'issue' OR has_open_linked_pr = 0)
                  AND (
                    blocked_reason IS NULL
                    OR (
                      github_type = 'issue'
                      AND blocked_reason = ?
                      AND (blocked_until IS NULL OR blocked_until < ?)
                    )
                  )
                  AND (locked_until IS NULL OR locked_until < ?)
                  {2}
                  {1}
                ORDER BY
                  CASE WHEN blocked_reason = ? THEN 0 ELSE 1 END,
                  updated_at ASC,
                  id ASC
                LIMIT 1
                """.format(placeholders, latency_filter, exclude_filter),
                parameters + [recoverable_blocked_reason],
            ).fetchone()
            if candidate is None:
                return None

            updated = conn.execute(
                """
                UPDATE tasks
                SET locked_by = ?, locked_until = ?, updated_at = ?
                WHERE id = ? AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker_id, lock_until, now, int(candidate["id"]), now),
            )
            if updated.rowcount != 1:
                return None
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(candidate["id"]),)).fetchone()
            conn.commit()
        return self._task_row_to_dict(row) if row else None

    def release_task_lock(self, task_id: int) -> None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET locked_by = NULL, locked_until = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
            conn.commit()

    def clear_task_locks(self, repo_id: int) -> int:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE tasks
                SET locked_by = NULL, locked_until = NULL, updated_at = ?
                WHERE repo_id = ? AND (locked_by IS NOT NULL OR locked_until IS NOT NULL)
                """,
                (now, repo_id),
            )
            conn.commit()
        return max(int(cursor.rowcount), 0)

    def create_run(
        self,
        task_id: int,
        run_type: str,
        prompt: str,
        command: str,
        started_at: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> int:
        now = started_at or utc_now()
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs(task_id, run_type, prompt, command, output_path, started_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, run_type, prompt, command, output_path, now, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        exit_code: int,
        output_path: str,
        result: str,
        finished_at: Optional[str] = None,
    ) -> None:
        now = finished_at or utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                UPDATE runs
                SET exit_code = ?, output_path = ?, result = ?, finished_at = ?
                WHERE id = ?
                """,
                (exit_code, output_path, result, now, run_id),
            )
            conn.commit()

    def get_run(self, run_id: int) -> Optional[Dict]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def get_run_details(self, run_id: int) -> Optional[Dict]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT
                  runs.*,
                  tasks.repo_id,
                  tasks.github_type,
                  tasks.github_number,
                  tasks.title
                FROM runs
                JOIN tasks ON tasks.id = runs.task_id
                WHERE runs.id = ?
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_running_task_ids(self, repo_id: int) -> List[int]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT tasks.id
                FROM tasks
                JOIN runs ON runs.task_id = tasks.id
                WHERE tasks.repo_id = ?
                  AND runs.finished_at IS NULL
                """,
                (repo_id,),
            ).fetchall()
        return [int(row["id"]) for row in rows]

    def list_runs(self, repo_id: int, limit: int = 50) -> List[Dict]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                  runs.*,
                  tasks.github_type,
                  tasks.github_number,
                  tasks.title
                FROM runs
                JOIN tasks ON tasks.id = runs.task_id
                WHERE tasks.repo_id = ?
                ORDER BY runs.id DESC
                LIMIT ?
                """,
                (repo_id, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_task_runs(self, task_id: int, limit: int = 10) -> List[Dict]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM runs
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_task_events(self, task_id: int) -> List[Dict]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC",
                (task_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _task_row_to_dict(row) -> Dict:
        task = dict(row)
        labels_json = task.get("labels_json") or "[]"
        task["labels"] = json.loads(labels_json)
        task["is_stale"] = bool(task.get("is_stale"))
        task["github_state"] = (task.get("github_state") or "open").strip().lower() or "open"
        task["has_open_linked_pr"] = bool(task.get("has_open_linked_pr"))
        linked_pr_numbers_json = task.get("linked_pr_numbers_json") or "[]"
        task["linked_pr_numbers"] = [int(number) for number in json.loads(linked_pr_numbers_json)]
        return task
