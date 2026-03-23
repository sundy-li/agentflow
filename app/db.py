import sqlite3
from pathlib import Path
from typing import Optional


TASK_OPTIONAL_COLUMNS = {
    "pr_head_sha": "TEXT",
    "pr_last_push_observed_at": "TEXT",
    "has_open_linked_pr": "INTEGER NOT NULL DEFAULT 0",
    "linked_pr_numbers_json": "TEXT NOT NULL DEFAULT '[]'",
}


def connect_db(db_path: str) -> sqlite3.Connection:
    database_file = Path(db_path)
    database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_file), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def run_migrations(db_path: str, migrations_dir: Optional[str] = None) -> None:
    directory = Path(migrations_dir or "migrations")
    if not directory.exists():
        raise FileNotFoundError("Migrations directory not found: {0}".format(directory))

    with connect_db(db_path) as conn:
        for migration in sorted(directory.glob("*.sql")):
            sql = migration.read_text(encoding="utf-8")
            conn.executescript(sql)
        _ensure_task_columns(conn)
        conn.commit()


def _ensure_task_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if not columns:
        return
    for name, column_type in TASK_OPTIONAL_COLUMNS.items():
        if name in columns:
            continue
        conn.execute("ALTER TABLE tasks ADD COLUMN {0} {1}".format(name, column_type))
