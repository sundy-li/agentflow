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
    assert {"pr_head_sha", "pr_last_push_observed_at"}.issubset(columns)


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
