CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    project TEXT NOT NULL,
    preset TEXT NOT NULL,
    cwd TEXT NOT NULL,
    argv_json TEXT NOT NULL,
    args_json TEXT NOT NULL DEFAULT '{}',
    required_capabilities_json TEXT NOT NULL,
    state TEXT NOT NULL,
    requested_by_email TEXT,
    requested_by_name TEXT,
    zulip_message_id BIGINT,
    zulip_stream_id BIGINT,
    zulip_topic TEXT,
    zulip_sender_email TEXT,
    created_at TEXT NOT NULL,
    claimed_at TEXT,
    heartbeat_at TEXT,
    finished_at TEXT,
    runner_id TEXT,
    exit_code INTEGER,
    summary TEXT,
    result_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS jobs_state_created_idx
    ON jobs (state, created_at);

CREATE INDEX IF NOT EXISTS jobs_runner_state_idx
    ON jobs (runner_id, state);

CREATE TABLE IF NOT EXISTS job_attempts (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    runner_id TEXT NOT NULL,
    state TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    exit_code INTEGER,
    summary TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS job_attempts_job_started_idx
    ON job_attempts (job_id, started_at DESC);

CREATE TABLE IF NOT EXISTS runners (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    version TEXT,
    capabilities_json TEXT NOT NULL,
    concurrency_limit INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    current_job_id TEXT,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS runners_status_seen_idx
    ON runners (status, last_seen_at);

CREATE TABLE IF NOT EXISTS github_event_dedupe (
    delivery_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_bindings (
    topic_key TEXT PRIMARY KEY,
    stream_name TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_records (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    action TEXT NOT NULL,
    release_id TEXT,
    artifact_root TEXT,
    manifest_path TEXT,
    requested_by_email TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    state TEXT NOT NULL,
    summary TEXT
);
