CREATE TABLE IF NOT EXISTS repos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  full_name TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_id INTEGER NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  github_type TEXT NOT NULL CHECK (github_type IN ('issue', 'pr')),
  github_number INTEGER NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  labels_json TEXT NOT NULL DEFAULT '[]',
  state TEXT NOT NULL,
  pr_head_sha TEXT,
  pr_last_push_observed_at TEXT,
  assignee TEXT,
  is_stale INTEGER NOT NULL DEFAULT 0,
  last_synced_at TEXT,
  locked_by TEXT,
  locked_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(repo_id, github_type, github_number)
);

CREATE INDEX IF NOT EXISTS idx_tasks_repo_state ON tasks(repo_id, state);
CREATE INDEX IF NOT EXISTS idx_tasks_repo_lock ON tasks(repo_id, locked_until);

CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  from_state TEXT,
  to_state TEXT,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  source TEXT NOT NULL,
  run_id INTEGER,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id, id);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  run_type TEXT NOT NULL,
  prompt TEXT NOT NULL,
  command TEXT NOT NULL,
  exit_code INTEGER,
  output_path TEXT,
  result TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_task_id ON runs(task_id, id);
