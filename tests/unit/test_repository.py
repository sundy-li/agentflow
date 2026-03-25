import sqlite3

from app.db import connect_db
from app.constants import RUNNABLE_STATES


def test_init_schema_creates_core_tables(db_path):
    with connect_db(db_path) as conn:
        names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {"repos", "tasks", "task_events", "runs"}.issubset(names)

    with connect_db(db_path) as conn:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
    assert {
        "pr_head_sha",
        "pr_last_push_observed_at",
        "blocked_reason",
        "blocked_until",
        "github_state",
        "worktree_path",
        "worktree_cleanup_attempted_at",
        "worktree_cleanup_error",
        "worktree_removed_at",
    }.issubset(columns)


def test_upsert_task_and_event(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")

    created = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=12,
        title="initial",
        url="https://example.com/12",
        labels=["agent-issue"],
        state="agent-issue",
    )
    updated = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=12,
        title="changed",
        url="https://example.com/12",
        labels=["agent-issue"],
        state="agent-issue",
    )
    assert created["id"] == updated["id"]
    assert updated["title"] == "changed"

    event_id = repository.insert_task_event(
        task_id=updated["id"],
        from_state="agent-issue",
        to_state="agent-reviewable",
        reason="unit-test",
        actor="tester",
        source="pytest",
    )
    assert isinstance(event_id, int)
    events = repository.get_task_events(updated["id"])
    assert events[-1]["to_state"] == "agent-reviewable"


def test_claim_next_task_blocks_reviewable_pr_until_latency_expires(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    review_pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=20,
        title="review pr",
        url="https://example.com/pr/20",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=21,
        title="issue",
        url="https://example.com/issue/21",
        labels=["agent-issue"],
        state="agent-issue",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET pr_head_sha = ?, pr_last_push_observed_at = ? WHERE id = ?",
            ("sha-1", "2999-01-01T00:00:00Z", int(review_pr["id"])),
        )
        conn.commit()

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-1", review_latency_hours=1)

    assert claimed is not None
    assert claimed["id"] == issue["id"]


def test_claim_next_task_allows_reviewable_pr_after_latency_expires(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    review_pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=22,
        title="review pr",
        url="https://example.com/pr/22",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET pr_head_sha = ?, pr_last_push_observed_at = ? WHERE id = ?",
            ("sha-2", "2000-01-01T00:00:00Z", int(review_pr["id"])),
        )
        conn.commit()

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-2", review_latency_hours=1)

    assert claimed is not None
    assert claimed["id"] == review_pr["id"]


def test_claim_next_task_skips_issue_with_open_linked_pr(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    blocked_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=30,
        title="blocked issue",
        url="https://example.com/issue/30",
        labels=["agent-issue"],
        state="agent-issue",
        has_open_linked_pr=True,
        linked_pr_numbers=[200],
    )
    ready_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=31,
        title="ready issue",
        url="https://example.com/issue/31",
        labels=["agent-issue"],
        state="agent-issue",
    )

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-1")

    assert claimed is not None
    assert claimed["id"] == ready_issue["id"]
    assert claimed["id"] != blocked_issue["id"]


def test_claim_next_task_skips_closed_or_merged_tasks(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    closed_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=130,
        title="closed issue",
        url="https://example.com/issue/130",
        labels=["agent-issue"],
        state="agent-issue",
        github_state="closed",
    )
    merged_pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=131,
        title="merged pr",
        url="https://example.com/pr/131",
        labels=["agent-reviewable"],
        state="agent-reviewable",
        github_state="merged",
    )
    ready_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=132,
        title="ready issue",
        url="https://example.com/issue/132",
        labels=["agent-issue"],
        state="agent-issue",
    )

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-1")

    assert claimed is not None
    assert claimed["id"] == ready_issue["id"]
    assert claimed["id"] not in {closed_issue["id"], merged_pr["id"]}


def test_claim_next_task_skips_blocked_issue(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    blocked_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=32,
        title="blocked issue",
        url="https://example.com/issue/32",
        labels=["agent-issue"],
        state="agent-issue",
        blocked_reason="manual_block",
    )
    ready_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=33,
        title="ready issue",
        url="https://example.com/issue/33",
        labels=["agent-issue"],
        state="agent-issue",
    )

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-1")

    assert claimed is not None
    assert claimed["id"] == ready_issue["id"]
    assert claimed["id"] != blocked_issue["id"]


def test_claim_next_task_skips_missing_pr_block_until_due(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    blocked_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=34,
        title="delivery pending",
        url="https://example.com/issue/34",
        labels=["agent-issue"],
        state="agent-issue",
        blocked_reason="missing_pr_after_implement",
    )
    ready_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=35,
        title="ready issue",
        url="https://example.com/issue/35",
        labels=["agent-issue"],
        state="agent-issue",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET blocked_until = ? WHERE id = ?",
            ("2999-01-01T00:00:00Z", int(blocked_issue["id"])),
        )
        conn.commit()

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-1")

    assert claimed is not None
    assert claimed["id"] == ready_issue["id"]


def test_claim_next_task_retries_due_missing_pr_block_before_new_issue(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    blocked_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=36,
        title="delivery retry",
        url="https://example.com/issue/36",
        labels=["agent-issue"],
        state="agent-issue",
        blocked_reason="missing_pr_after_implement",
    )
    ready_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=37,
        title="ready issue",
        url="https://example.com/issue/37",
        labels=["agent-issue"],
        state="agent-issue",
    )
    with connect_db(repository.db_path) as conn:
        conn.execute(
            "UPDATE tasks SET blocked_until = ?, updated_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00Z", "2000-01-01T00:00:00Z", int(blocked_issue["id"])),
        )
        conn.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            ("2999-01-01T00:00:00Z", int(ready_issue["id"])),
        )
        conn.commit()

    claimed = repository.claim_next_task(repo_id, RUNNABLE_STATES, "worker-1")

    assert claimed is not None
    assert claimed["id"] == blocked_issue["id"]


def test_claim_next_task_skips_excluded_task_ids(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    first = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=40,
        title="first",
        url="https://example.com/issue/40",
        labels=["agent-issue"],
        state="agent-issue",
    )
    second = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=41,
        title="second",
        url="https://example.com/issue/41",
        labels=["agent-issue"],
        state="agent-issue",
    )

    claimed = repository.claim_next_task(
        repo_id,
        RUNNABLE_STATES,
        "worker-1",
        exclude_task_ids=[int(first["id"])],
    )

    assert claimed is not None
    assert claimed["id"] == second["id"]


def test_list_board_tasks_hides_issue_with_open_linked_pr(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=42,
        title="hidden issue",
        url="https://example.com/issue/42",
        labels=["agent-issue"],
        state="agent-issue",
        has_open_linked_pr=True,
        linked_pr_numbers=[43],
    )
    reviewable_pr = repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=43,
        title="linked pr",
        url="https://example.com/pr/43",
        labels=["agent-reviewable"],
        state="agent-reviewable",
    )

    board_tasks = repository.list_board_tasks(repo_id)

    assert [task["id"] for task in board_tasks] == [reviewable_pr["id"]]


def test_list_board_tasks_hides_closed_or_merged_tasks(repository):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    open_issue = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=44,
        title="open issue",
        url="https://example.com/issue/44",
        labels=["agent-issue"],
        state="agent-issue",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=45,
        title="closed issue",
        url="https://example.com/issue/45",
        labels=["agent-issue"],
        state="agent-issue",
        github_state="closed",
    )
    repository.upsert_task(
        repo_id=repo_id,
        github_type="pr",
        github_number=46,
        title="merged pr",
        url="https://example.com/pr/46",
        labels=["agent-approved"],
        state="agent-approved",
        github_state="merged",
    )

    board_tasks = repository.list_board_tasks(repo_id)

    assert [task["id"] for task in board_tasks] == [open_issue["id"]]


def test_list_running_task_ids_returns_tasks_with_unfinished_runs(repository, tmp_path):
    repo_id = repository.ensure_repo("demo", "owner/repo")
    running_task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=50,
        title="running task",
        url="https://example.com/issue/50",
        labels=["agent-issue"],
        state="agent-issue",
    )
    finished_task = repository.upsert_task(
        repo_id=repo_id,
        github_type="issue",
        github_number=51,
        title="finished task",
        url="https://example.com/issue/51",
        labels=["agent-issue"],
        state="agent-issue",
    )
    running_log = tmp_path / "running.log"
    running_log.write_text("running\n", encoding="utf-8")
    repository.create_run(running_task["id"], "implement", "prompt", "cmd", output_path=str(running_log))

    finished_log = tmp_path / "finished.log"
    finished_log.write_text("done\n", encoding="utf-8")
    run_id = repository.create_run(finished_task["id"], "implement", "prompt", "cmd", output_path=str(finished_log))
    repository.finish_run(run_id, 0, str(finished_log), "success")

    running_task_ids = repository.list_running_task_ids(repo_id)

    assert int(running_task["id"]) in running_task_ids
    assert int(finished_task["id"]) not in running_task_ids
