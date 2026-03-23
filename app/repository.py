import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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
        assignee: Optional[str] = None,
        last_synced_at: Optional[str] = None,
        is_stale: bool = False,
    ) -> Dict:
        now = utc_now()
        labels_json = json.dumps(sorted(set(labels)))
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tasks(
                  repo_id, github_type, github_number, title, url,
                  labels_json, state, assignee, is_stale, last_synced_at,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo_id, github_type, github_number)
                DO UPDATE SET
                  title = excluded.title,
                  url = excluded.url,
                  labels_json = excluded.labels_json,
                  state = excluded.state,
                  assignee = excluded.assignee,
                  is_stale = excluded.is_stale,
                  last_synced_at = excluded.last_synced_at,
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
                    assignee,
                    int(is_stale),
                    last_synced_at,
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
        return [self._task_row_to_dict(row) for row in rows]

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

    def claim_next_task(self, repo_id: int, states: List[str], worker_id: str, lock_seconds: int = 300) -> Optional[Dict]:
        if not states:
            return None
        now = utc_now()
        lock_until = (datetime.utcnow() + timedelta(seconds=lock_seconds)).replace(microsecond=0).isoformat() + "Z"
        placeholders = ",".join(["?"] * len(states))

        with connect_db(self.db_path) as conn:
            candidate = conn.execute(
                """
                SELECT id FROM tasks
                WHERE repo_id = ?
                  AND state IN ({0})
                  AND is_stale = 0
                  AND (locked_until IS NULL OR locked_until < ?)
                ORDER BY updated_at ASC, id ASC
                LIMIT 1
                """.format(placeholders),
                [repo_id] + list(states) + [now],
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

    def create_run(self, task_id: int, run_type: str, prompt: str, command: str, started_at: Optional[str] = None) -> int:
        now = started_at or utc_now()
        with connect_db(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO runs(task_id, run_type, prompt, command, started_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, run_type, prompt, command, now, now),
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
        return task

