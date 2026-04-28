CREATE TABLE IF NOT EXISTS ledger_entries (
    id TEXT PRIMARY KEY,
    stream_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    posted_at TEXT,
    requested_by_email TEXT,
    requested_by_name TEXT,
    zulip_message_id BIGINT,
    content_markdown TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ledger_entries_created_idx
    ON ledger_entries (created_at DESC);

CREATE INDEX IF NOT EXISTS ledger_entries_state_created_idx
    ON ledger_entries (state, created_at DESC);
