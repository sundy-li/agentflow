import sqlite3
from pathlib import Path
from typing import Optional


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
        conn.commit()

