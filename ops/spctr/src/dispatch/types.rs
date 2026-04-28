use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

pub type JsonMap = Map<String, Value>;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum JobKind {
    Exec,
    Analyze,
    Draft,
}

impl JobKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Exec => "exec",
            Self::Analyze => "analyze",
            Self::Draft => "draft",
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum JobState {
    Queued,
    Claimed,
    CancelRequested,
    Cancelled,
    Succeeded,
    Failed,
}

impl JobState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Queued => "queued",
            Self::Claimed => "claimed",
            Self::CancelRequested => "cancel_requested",
            Self::Cancelled => "cancelled",
            Self::Succeeded => "succeeded",
            Self::Failed => "failed",
        }
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LedgerEntryState {
    Posting,
    Posted,
    Failed,
}

impl LedgerEntryState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Posting => "posting",
            Self::Posted => "posted",
            Self::Failed => "failed",
        }
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct JobRecord {
    pub id: String,
    pub kind: JobKind,
    pub project: String,
    pub action: String,
    pub cwd: String,
    pub argv: Vec<String>,
    pub args: JsonMap,
    pub required_capabilities: Vec<String>,
    pub state: JobState,
    pub requested_by_email: Option<String>,
    pub requested_by_name: Option<String>,
    pub zulip_message_id: Option<i64>,
    pub zulip_stream_id: Option<i64>,
    pub zulip_topic: Option<String>,
    pub zulip_sender_email: Option<String>,
    pub created_at: String,
    pub claimed_at: Option<String>,
    pub heartbeat_at: Option<String>,
    pub finished_at: Option<String>,
    pub runner_id: Option<String>,
    pub exit_code: Option<i32>,
    pub summary: Option<String>,
    pub result: JsonMap,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct RunnerRecord {
    pub id: String,
    pub display_name: String,
    pub version: Option<String>,
    pub capabilities: Vec<String>,
    pub concurrency_limit: i32,
    pub status: String,
    pub current_job_id: Option<String>,
    pub last_seen_at: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ZulipContext {
    pub message_id: Option<i64>,
    pub stream_id: Option<i64>,
    pub topic: Option<String>,
    pub sender_email: Option<String>,
    pub sender_name: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunnerRegistration {
    pub runner_id: String,
    pub display_name: String,
    pub version: Option<String>,
    pub capabilities: Vec<String>,
    #[serde(default = "default_runner_concurrency_limit")]
    pub concurrency_limit: i32,
}

fn default_runner_concurrency_limit() -> i32 {
    1
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct LedgerEntryRecord {
    pub id: String,
    pub stream_name: String,
    pub topic: String,
    pub state: LedgerEntryState,
    pub created_at: String,
    pub posted_at: Option<String>,
    pub requested_by_email: Option<String>,
    pub requested_by_name: Option<String>,
    pub zulip_message_id: Option<i64>,
    pub content_markdown: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct LedgerEntryReservation {
    pub id: String,
    pub stream_name: String,
    pub topic: String,
    pub created_at: String,
    pub requested_by_email: Option<String>,
    pub requested_by_name: Option<String>,
    pub content_markdown: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct JobCompletion {
    pub summary: String,
    pub exit_code: Option<i32>,
    pub result: JsonMap,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct JobSpec {
    pub kind: JobKind,
    pub project: String,
    pub action: String,
    pub description: String,
    pub cwd: String,
    pub argv: Vec<String>,
    pub required_capabilities: Vec<String>,
    pub args: JsonMap,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SurfaceDefinition {
    pub command: String,
    pub project: String,
    pub action: String,
    pub synopsis: String,
    pub description: String,
    pub required_capabilities: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PublishArtifact {
    pub label: String,
    pub url: Option<String>,
    pub path: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct PublishResult {
    pub release_id: String,
    pub surface: String,
    pub public_url: String,
    pub current_url: String,
    pub artifacts: Vec<PublishArtifact>,
    pub manifest_path: Option<String>,
    pub site_path: Option<String>,
    pub provenance: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct HealthSnapshot {
    pub queued_jobs: u64,
    pub active_jobs: u64,
    pub online_runners: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HealthRunnerView {
    pub display_name: String,
    pub last_seen_at: String,
    pub current_job_id: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HealthRecentJobView {
    pub id: String,
    pub command: String,
    pub state: String,
    pub created_at: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DispatchHealthSnapshot {
    pub queued_jobs: u64,
    pub active_jobs: u64,
    pub online_runners: u64,
    #[serde(default)]
    pub runners: Vec<HealthRunnerView>,
    #[serde(default)]
    pub recent_jobs: Vec<HealthRecentJobView>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct DispatchHealthResponse {
    pub ok: bool,
    pub snapshot: DispatchHealthSnapshot,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ZulipOutgoingMessage {
    pub id: Option<i64>,
    pub content: Option<String>,
    pub stream_id: Option<i64>,
    pub subject: Option<String>,
    pub topic: Option<String>,
    pub sender_email: Option<String>,
    pub sender_full_name: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ZulipOutgoingPayload {
    pub token: Option<String>,
    pub message: Option<ZulipOutgoingMessage>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdminLedgerPostRequest {
    pub topic: String,
    pub body: String,
    pub requested_by_email: Option<String>,
    pub requested_by_name: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdminLedgerPostResponse {
    pub entry_id: String,
    pub created_at: String,
    pub message_id: Option<i64>,
    pub stream_name: String,
    pub topic: String,
    pub content: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct GithubWebhookOutcome {
    pub accepted: bool,
    pub reason: String,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunnerClaimRequest {
    pub runner_id: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunnerHeartbeatRequest {
    pub runner_id: Option<String>,
    pub job_id: Option<String>,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RunnerCompleteRequest {
    pub runner_id: Option<String>,
    pub job_id: Option<String>,
    pub summary: Option<String>,
    pub exit_code: Option<i32>,
    pub result: Option<JsonMap>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct RunnerEnvelope<T> {
    pub runner: T,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct JobEnvelope {
    pub job: Option<JobRecord>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HeartbeatEnvelope {
    pub job: Option<JobRecord>,
    pub cancel_requested: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
pub struct ZulipSendContext {
    pub stream_id: Option<i64>,
    pub stream_name: Option<String>,
    pub topic: Option<String>,
    pub sender_email: Option<String>,
}
