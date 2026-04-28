use std::sync::Arc;

use async_trait::async_trait;
use chrono::{SecondsFormat, Utc};
use tokio_postgres::{types::ToSql, Client, NoTls, Row};

use crate::dispatch::store::DispatchStore;
use crate::dispatch::types::{
    HealthSnapshot, JobCompletion, JobKind, JobRecord, JobSpec, JobState, JsonMap,
    LedgerEntryRecord, LedgerEntryReservation, LedgerEntryState, RunnerRecord, RunnerRegistration,
    ZulipContext,
};

#[derive(Clone)]
pub struct PgStore {
    client: Arc<Client>,
}

impl PgStore {
    pub async fn connect(database_url: &str) -> anyhow::Result<Self> {
        let (client, connection) = tokio_postgres::connect(database_url, NoTls).await?;
        tokio::spawn(async move {
            if let Err(error) = connection.await {
                eprintln!("dispatch postgres connection failed: {error}");
            }
        });
        Ok(Self {
            client: Arc::new(client),
        })
    }

    pub fn client(&self) -> &Client {
        &self.client
    }

    async fn one(&self, text: &str, values: &[&(dyn ToSql + Sync)]) -> anyhow::Result<Option<Row>> {
        Ok(self.client.query_opt(text, values).await?)
    }

    async fn many(&self, text: &str, values: &[&(dyn ToSql + Sync)]) -> anyhow::Result<Vec<Row>> {
        Ok(self.client.query(text, values).await?)
    }

    async fn exec(&self, text: &str, values: &[&(dyn ToSql + Sync)]) -> anyhow::Result<u64> {
        Ok(self.client.execute(text, values).await?)
    }
}

fn now_iso() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn create_job_id() -> String {
    let stamp = now_iso()
        .chars()
        .filter(|ch| !matches!(ch, '-' | ':' | '.' | 'T' | 'Z'))
        .take(14)
        .collect::<String>();
    format!(
        "job-{stamp}-{}",
        &uuid::Uuid::new_v4().simple().to_string()[..8]
    )
}

fn create_attempt_id() -> String {
    format!(
        "attempt-{}",
        &uuid::Uuid::new_v4().simple().to_string()[..12]
    )
}

fn parse_json_map(raw: Option<String>) -> JsonMap {
    raw.and_then(|value| serde_json::from_str(&value).ok())
        .unwrap_or_default()
}

fn parse_json_vec(raw: Option<String>) -> Vec<String> {
    raw.and_then(|value| serde_json::from_str(&value).ok())
        .unwrap_or_default()
}

fn parse_job_kind(raw: &str) -> anyhow::Result<JobKind> {
    match raw {
        "exec" => Ok(JobKind::Exec),
        "analyze" => Ok(JobKind::Analyze),
        "draft" => Ok(JobKind::Draft),
        _ => Err(anyhow::anyhow!("unknown job kind: {raw}")),
    }
}

fn parse_job_state(raw: &str) -> anyhow::Result<JobState> {
    match raw {
        "queued" => Ok(JobState::Queued),
        "claimed" => Ok(JobState::Claimed),
        "cancel_requested" => Ok(JobState::CancelRequested),
        "cancelled" => Ok(JobState::Cancelled),
        "succeeded" => Ok(JobState::Succeeded),
        "failed" => Ok(JobState::Failed),
        _ => Err(anyhow::anyhow!("unknown job state: {raw}")),
    }
}

fn parse_ledger_state(raw: &str) -> anyhow::Result<LedgerEntryState> {
    match raw {
        "posting" => Ok(LedgerEntryState::Posting),
        "posted" => Ok(LedgerEntryState::Posted),
        "failed" => Ok(LedgerEntryState::Failed),
        _ => Err(anyhow::anyhow!("unknown ledger state: {raw}")),
    }
}

fn map_job(row: &Row) -> anyhow::Result<JobRecord> {
    Ok(JobRecord {
        id: row.get("id"),
        kind: parse_job_kind(row.get::<_, String>("kind").as_str())?,
        project: row.get("project"),
        action: row.get("preset"),
        cwd: row.get("cwd"),
        argv: parse_json_vec(Some(row.get("argv_json"))),
        args: parse_json_map(row.try_get("args_json").ok()),
        required_capabilities: parse_json_vec(row.try_get("required_capabilities_json").ok()),
        state: parse_job_state(row.get::<_, String>("state").as_str())?,
        requested_by_email: row.try_get("requested_by_email").ok(),
        requested_by_name: row.try_get("requested_by_name").ok(),
        zulip_message_id: row.try_get("zulip_message_id").ok(),
        zulip_stream_id: row.try_get("zulip_stream_id").ok(),
        zulip_topic: row.try_get("zulip_topic").ok(),
        zulip_sender_email: row.try_get("zulip_sender_email").ok(),
        created_at: row.get("created_at"),
        claimed_at: row.try_get("claimed_at").ok(),
        heartbeat_at: row.try_get("heartbeat_at").ok(),
        finished_at: row.try_get("finished_at").ok(),
        runner_id: row.try_get("runner_id").ok(),
        exit_code: row.try_get("exit_code").ok(),
        summary: row.try_get("summary").ok(),
        result: parse_json_map(row.try_get("result_json").ok()),
    })
}

fn map_runner(row: &Row) -> RunnerRecord {
    RunnerRecord {
        id: row.get("id"),
        display_name: row.get("display_name"),
        version: row.try_get("version").ok(),
        capabilities: parse_json_vec(row.try_get("capabilities_json").ok()),
        concurrency_limit: row.try_get("concurrency_limit").unwrap_or(1),
        status: row.get("status"),
        current_job_id: row.try_get("current_job_id").ok(),
        last_seen_at: row.get("last_seen_at"),
    }
}

fn map_ledger_entry(row: &Row) -> anyhow::Result<LedgerEntryRecord> {
    Ok(LedgerEntryRecord {
        id: row.get("id"),
        stream_name: row.get("stream_name"),
        topic: row.get("topic"),
        state: parse_ledger_state(row.get::<_, String>("state").as_str())?,
        created_at: row.get("created_at"),
        posted_at: row.try_get("posted_at").ok(),
        requested_by_email: row.try_get("requested_by_email").ok(),
        requested_by_name: row.try_get("requested_by_name").ok(),
        zulip_message_id: row.try_get("zulip_message_id").ok(),
        content_markdown: row.get("content_markdown"),
    })
}

fn supports_capabilities(available: &[String], required: &[String]) -> bool {
    let available = available
        .iter()
        .map(String::as_str)
        .collect::<std::collections::HashSet<_>>();
    required
        .iter()
        .all(|capability| available.contains(capability.as_str()))
}

#[async_trait]
impl DispatchStore for PgStore {
    async fn create_queued_job(
        &self,
        job_spec: JobSpec,
        zulip: ZulipContext,
    ) -> anyhow::Result<JobRecord> {
        let id = create_job_id();
        let created_at = now_iso();
        let argv_json = serde_json::to_string(&job_spec.argv)?;
        let args_json = serde_json::to_string(&job_spec.args)?;
        let caps_json = serde_json::to_string(&job_spec.required_capabilities)?;
        let result_json = serde_json::to_string(&JsonMap::default())?;
        self.exec(
            "INSERT INTO jobs (id, kind, project, preset, cwd, argv_json, args_json, required_capabilities_json, state, requested_by_email, requested_by_name, zulip_message_id, zulip_stream_id, zulip_topic, zulip_sender_email, created_at, result_json) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)",
            &[
                &id,
                &job_spec.kind.as_str(),
                &job_spec.project,
                &job_spec.action,
                &job_spec.cwd,
                &argv_json,
                &args_json,
                &caps_json,
                &JobState::Queued.as_str(),
                &zulip.sender_email,
                &zulip.sender_name,
                &zulip.message_id,
                &zulip.stream_id,
                &zulip.topic,
                &zulip.sender_email,
                &created_at,
                &result_json,
            ],
        )
        .await?;
        self.get_job(&id)
            .await?
            .ok_or_else(|| anyhow::anyhow!("job insert succeeded but fetch failed for {id}"))
    }

    async fn get_job(&self, job_id: &str) -> anyhow::Result<Option<JobRecord>> {
        self.one("SELECT * FROM jobs WHERE id = $1", &[&job_id])
            .await?
            .map(|row| map_job(&row))
            .transpose()
    }

    async fn clone_job(&self, original_id: &str) -> anyhow::Result<Option<JobRecord>> {
        let Some(original) = self.get_job(original_id).await? else {
            return Ok(None);
        };
        let id = create_job_id();
        let created_at = now_iso();
        let argv_json = serde_json::to_string(&original.argv)?;
        let args_json = serde_json::to_string(&original.args)?;
        let caps_json = serde_json::to_string(&original.required_capabilities)?;
        let result_json = serde_json::to_string(&JsonMap::default())?;
        self.exec(
            "INSERT INTO jobs (id, kind, project, preset, cwd, argv_json, args_json, required_capabilities_json, state, requested_by_email, requested_by_name, zulip_message_id, zulip_stream_id, zulip_topic, zulip_sender_email, created_at, result_json) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)",
            &[
                &id,
                &original.kind.as_str(),
                &original.project,
                &original.action,
                &original.cwd,
                &argv_json,
                &args_json,
                &caps_json,
                &JobState::Queued.as_str(),
                &original.requested_by_email,
                &original.requested_by_name,
                &original.zulip_message_id,
                &original.zulip_stream_id,
                &original.zulip_topic,
                &original.zulip_sender_email,
                &created_at,
                &result_json,
            ],
        )
        .await?;
        self.get_job(&id).await
    }

    async fn request_cancel(&self, job_id: &str) -> anyhow::Result<Option<JobRecord>> {
        let Some(job) = self.get_job(job_id).await? else {
            return Ok(None);
        };
        match job.state {
            JobState::Queued => {
                let finished_at = now_iso();
                self.exec(
                    "UPDATE jobs SET state = $1, finished_at = $2, summary = $3 WHERE id = $4",
                    &[
                        &JobState::Cancelled.as_str(),
                        &finished_at,
                        &"Cancelled before claim.",
                        &job_id,
                    ],
                )
                .await?;
                self.get_job(job_id).await
            }
            JobState::Claimed => {
                self.exec(
                    "UPDATE jobs SET state = $1 WHERE id = $2",
                    &[&JobState::CancelRequested.as_str(), &job_id],
                )
                .await?;
                self.get_job(job_id).await
            }
            _ => Ok(Some(job)),
        }
    }

    async fn register_runner(&self, runner: RunnerRegistration) -> anyhow::Result<RunnerRecord> {
        let seen_at = now_iso();
        let caps_json = serde_json::to_string(&runner.capabilities)?;
        self.exec(
            "INSERT INTO runners (id, display_name, version, capabilities_json, concurrency_limit, status, current_job_id, last_seen_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT(id) DO UPDATE SET display_name = excluded.display_name, version = excluded.version, capabilities_json = excluded.capabilities_json, concurrency_limit = excluded.concurrency_limit, status = excluded.status, last_seen_at = excluded.last_seen_at",
            &[&runner.runner_id, &runner.display_name, &runner.version, &caps_json, &runner.concurrency_limit, &"online", &Option::<String>::None, &seen_at],
        )
        .await?;
        let row = self
            .one("SELECT * FROM runners WHERE id = $1", &[&runner.runner_id])
            .await?
            .ok_or_else(|| anyhow::anyhow!("runner upsert failed for {}", runner.runner_id))?;
        Ok(map_runner(&row))
    }

    async fn claim_next_job(&self, runner_id: &str) -> anyhow::Result<Option<JobRecord>> {
        let runner_row = self
            .one("SELECT * FROM runners WHERE id = $1", &[&runner_id])
            .await?
            .ok_or_else(|| anyhow::anyhow!("unknown runner: {runner_id}"))?;
        let runner = map_runner(&runner_row);
        if let Some(current_job_id) = runner.current_job_id {
            return self.get_job(&current_job_id).await;
        }
        let candidates = self
            .many(
                "SELECT * FROM jobs WHERE state = $1 ORDER BY created_at ASC LIMIT 50",
                &[&JobState::Queued.as_str()],
            )
            .await?;
        for row in candidates {
            let job = map_job(&row)?;
            if !supports_capabilities(&runner.capabilities, &job.required_capabilities) {
                continue;
            }
            let stamp = now_iso();
            let updated = self
                .exec(
                    "UPDATE jobs SET state = $1, runner_id = $2, claimed_at = $3, heartbeat_at = $4 WHERE id = $5 AND state = $6",
                    &[&JobState::Claimed.as_str(), &runner.id, &stamp, &stamp, &job.id, &JobState::Queued.as_str()],
                )
                .await?;
            if updated != 1 {
                continue;
            }
            self.exec(
                "UPDATE runners SET status = $1, current_job_id = $2, last_seen_at = $3 WHERE id = $4",
                &[&"busy", &job.id, &stamp, &runner.id],
            )
            .await?;
            self.exec(
                "INSERT INTO job_attempts (id, job_id, runner_id, state, started_at, updated_at) VALUES ($1,$2,$3,$4,$5,$6)",
                &[&create_attempt_id(), &job.id, &runner.id, &JobState::Claimed.as_str(), &stamp, &stamp],
            )
            .await?;
            return self.get_job(&job.id).await;
        }
        self.exec(
            "UPDATE runners SET status = $1, last_seen_at = $2 WHERE id = $3",
            &[&"online", &now_iso(), &runner.id],
        )
        .await?;
        Ok(None)
    }

    async fn heartbeat_runner_job(
        &self,
        runner_id: &str,
        job_id: &str,
    ) -> anyhow::Result<Option<JobRecord>> {
        let stamp = now_iso();
        self.exec(
            "UPDATE jobs SET heartbeat_at = $1 WHERE id = $2 AND runner_id = $3 AND state IN ($4, $5)",
            &[&stamp, &job_id, &runner_id, &JobState::Claimed.as_str(), &JobState::CancelRequested.as_str()],
        )
        .await?;
        self.exec(
            "UPDATE runners SET last_seen_at = $1 WHERE id = $2",
            &[&stamp, &runner_id],
        )
        .await?;
        self.get_job(job_id).await
    }

    async fn complete_job(
        &self,
        runner_id: &str,
        job_id: &str,
        completion: JobCompletion,
    ) -> anyhow::Result<Option<JobRecord>> {
        finalize_job(self, runner_id, job_id, JobState::Succeeded, completion).await
    }

    async fn fail_job(
        &self,
        runner_id: &str,
        job_id: &str,
        completion: JobCompletion,
    ) -> anyhow::Result<Option<JobRecord>> {
        finalize_job(self, runner_id, job_id, JobState::Failed, completion).await
    }

    async fn cancel_job(
        &self,
        runner_id: &str,
        job_id: &str,
        completion: JobCompletion,
    ) -> anyhow::Result<Option<JobRecord>> {
        finalize_job(self, runner_id, job_id, JobState::Cancelled, completion).await
    }

    async fn list_recent_jobs(
        &self,
        limit: usize,
        states: &[JobState],
    ) -> anyhow::Result<Vec<JobRecord>> {
        let limit = i64::try_from(limit)?;
        let rows = if states.is_empty() {
            self.many(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1",
                &[&limit],
            )
            .await?
        } else {
            let state_values = states
                .iter()
                .map(|state| state.as_str().to_owned())
                .collect::<Vec<_>>();
            let placeholders = (1..=state_values.len())
                .map(|index| format!("${index}"))
                .collect::<Vec<_>>()
                .join(", ");
            let sql = format!(
                "SELECT * FROM jobs WHERE state IN ({placeholders}) ORDER BY created_at DESC LIMIT ${}",
                state_values.len() + 1
            );
            let mut params: Vec<&(dyn ToSql + Sync)> = Vec::new();
            for value in &state_values {
                params.push(value);
            }
            params.push(&limit);
            self.many(&sql, &params).await?
        };
        rows.iter().map(map_job).collect()
    }

    async fn list_runners(&self) -> anyhow::Result<Vec<RunnerRecord>> {
        Ok(self
            .many("SELECT * FROM runners ORDER BY last_seen_at DESC", &[])
            .await?
            .iter()
            .map(map_runner)
            .collect())
    }

    async fn health_snapshot(&self) -> anyhow::Result<HealthSnapshot> {
        let fresh_threshold = (Utc::now() - chrono::TimeDelta::milliseconds(120_000))
            .to_rfc3339_opts(SecondsFormat::Millis, true);
        let queued_row = self
            .one(
                "SELECT COUNT(*)::BIGINT AS count FROM jobs WHERE state = $1",
                &[&JobState::Queued.as_str()],
            )
            .await?
            .ok_or_else(|| anyhow::anyhow!("missing queued count"))?;
        let active_row = self
            .one(
                "SELECT COUNT(*)::BIGINT AS count FROM jobs WHERE state IN ($1, $2)",
                &[
                    &JobState::Claimed.as_str(),
                    &JobState::CancelRequested.as_str(),
                ],
            )
            .await?
            .ok_or_else(|| anyhow::anyhow!("missing active count"))?;
        let runner_row = self
            .one(
                "SELECT COUNT(*)::BIGINT AS count FROM runners WHERE status IN ($1, $2) AND last_seen_at >= $3",
                &[&"online", &"busy", &fresh_threshold],
            )
            .await?
            .ok_or_else(|| anyhow::anyhow!("missing runner count"))?;
        Ok(HealthSnapshot {
            queued_jobs: u64::try_from(queued_row.get::<_, i64>("count")).unwrap_or_default(),
            active_jobs: u64::try_from(active_row.get::<_, i64>("count")).unwrap_or_default(),
            online_runners: u64::try_from(runner_row.get::<_, i64>("count")).unwrap_or_default(),
        })
    }

    async fn reserve_github_delivery(
        &self,
        delivery_id: &str,
        event_name: &str,
    ) -> anyhow::Result<bool> {
        Ok(self
            .exec(
                "INSERT INTO github_event_dedupe (delivery_id, event_name, received_at) VALUES ($1,$2,$3) ON CONFLICT(delivery_id) DO NOTHING",
                &[&delivery_id, &event_name, &now_iso()],
            )
            .await?
            == 1)
    }

    async fn reserve_ledger_entry(
        &self,
        entry: LedgerEntryReservation,
    ) -> anyhow::Result<LedgerEntryRecord> {
        self.exec(
            "INSERT INTO ledger_entries (id, stream_name, topic, state, created_at, posted_at, requested_by_email, requested_by_name, zulip_message_id, content_markdown) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
            &[&entry.id, &entry.stream_name, &entry.topic, &LedgerEntryState::Posting.as_str(), &entry.created_at, &Option::<String>::None, &entry.requested_by_email, &entry.requested_by_name, &Option::<i64>::None, &entry.content_markdown],
        )
        .await?;
        let row = self
            .one("SELECT * FROM ledger_entries WHERE id = $1", &[&entry.id])
            .await?
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "ledger entry insert succeeded but fetch failed for {}",
                    entry.id
                )
            })?;
        map_ledger_entry(&row)
    }

    async fn mark_ledger_entry_posted(
        &self,
        entry_id: &str,
        zulip_message_id: Option<i64>,
    ) -> anyhow::Result<Option<LedgerEntryRecord>> {
        let posted_at = now_iso();
        self.exec(
            "UPDATE ledger_entries SET state = $1, posted_at = $2, zulip_message_id = $3 WHERE id = $4",
            &[&LedgerEntryState::Posted.as_str(), &posted_at, &zulip_message_id, &entry_id],
        )
        .await?;
        self.one("SELECT * FROM ledger_entries WHERE id = $1", &[&entry_id])
            .await?
            .map(|row| map_ledger_entry(&row))
            .transpose()
    }

    async fn mark_ledger_entry_failed(
        &self,
        entry_id: &str,
    ) -> anyhow::Result<Option<LedgerEntryRecord>> {
        self.exec(
            "UPDATE ledger_entries SET state = $1 WHERE id = $2",
            &[&LedgerEntryState::Failed.as_str(), &entry_id],
        )
        .await?;
        self.one("SELECT * FROM ledger_entries WHERE id = $1", &[&entry_id])
            .await?
            .map(|row| map_ledger_entry(&row))
            .transpose()
    }
}

async fn finalize_job(
    store: &PgStore,
    runner_id: &str,
    job_id: &str,
    state: JobState,
    completion: JobCompletion,
) -> anyhow::Result<Option<JobRecord>> {
    let finished_at = now_iso();
    let result_json = serde_json::to_string(&completion.result)?;
    store
        .exec(
            "UPDATE jobs SET state = $1, finished_at = $2, heartbeat_at = $3, summary = $4, exit_code = $5, result_json = $6 WHERE id = $7 AND runner_id = $8",
            &[&state.as_str(), &finished_at, &finished_at, &completion.summary, &completion.exit_code, &result_json, &job_id, &runner_id],
        )
        .await?;
    store
        .exec(
            "UPDATE runners SET status = $1, current_job_id = $2, last_seen_at = $3 WHERE id = $4",
            &[&"online", &Option::<String>::None, &finished_at, &runner_id],
        )
        .await?;
    store
        .exec(
            "UPDATE job_attempts SET state = $1, finished_at = $2, exit_code = $3, summary = $4, updated_at = $5 WHERE id IN (SELECT id FROM job_attempts WHERE job_id = $6 AND runner_id = $7 AND finished_at IS NULL ORDER BY started_at DESC LIMIT 1)",
            &[&state.as_str(), &finished_at, &completion.exit_code, &completion.summary, &finished_at, &job_id, &runner_id],
        )
        .await?;
    store.get_job(job_id).await
}
