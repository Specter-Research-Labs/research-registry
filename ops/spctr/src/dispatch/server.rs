use std::sync::Arc;

use axum::body::Bytes;
use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::Serialize;
use serde_json::{json, Value};

use crate::dispatch::commands::{build_help_message, parse_command, ParsedCommand};
use crate::dispatch::env::{load_env_file_from_var, trim_non_empty, DispatchConfig};
use crate::dispatch::github::{handle_github_webhook, verify_github_signature};
use crate::dispatch::ledger::{
    build_ledger_post_usage, create_ledger_entry_id, format_ledger_entry, parse_ledger_sections,
    LedgerEntryDraft,
};
use crate::dispatch::pg::PgStore;
use crate::dispatch::status::{
    commands_status_message, health_response, status_health_message, status_job_message,
    status_queue_message, status_runners_message,
};
use crate::dispatch::store::DispatchStore;
use crate::dispatch::surfaces::resolve_surface;
use crate::dispatch::types::{
    AdminLedgerPostRequest, AdminLedgerPostResponse, HeartbeatEnvelope, JobCompletion, JobEnvelope,
    JsonMap, RunnerClaimRequest, RunnerCompleteRequest, RunnerEnvelope, RunnerHeartbeatRequest,
    RunnerRegistration, ZulipContext, ZulipOutgoingMessage, ZulipOutgoingPayload, ZulipSendContext,
};
use crate::dispatch::zulip::{format_job_update, MessagePoster, ReqwestMessagePoster};

#[derive(Clone)]
struct AppState {
    config: DispatchConfig,
    store: Arc<dyn DispatchStore>,
    poster: Arc<dyn MessagePoster>,
}

pub async fn serve() -> anyhow::Result<()> {
    load_env_file_from_var()?;
    let config = DispatchConfig::from_process();
    let database_url = config.require_database_url()?.to_owned();
    let host = config.host().to_owned();
    let port = config.port()?;
    let store: Arc<dyn DispatchStore> = Arc::new(PgStore::connect(&database_url).await?);
    let poster: Arc<dyn MessagePoster> = Arc::new(ReqwestMessagePoster::from_config(&config));
    let app = app(AppState {
        config,
        store,
        poster,
    });
    let listener = tokio::net::TcpListener::bind((host.as_str(), port)).await?;
    println!("specter-dispatch listening on http://{host}:{port}");
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

fn app(state: AppState) -> Router {
    Router::new()
        .route("/health", get(handle_health))
        .route("/zulip/outgoing", post(handle_zulip_outgoing))
        .route("/admin/ledger/post", post(handle_admin_ledger_post))
        .route("/webhooks/github", post(handle_github_webhook_request))
        .route("/runner/register", post(handle_runner_register))
        .route("/runner/claim", post(handle_runner_claim))
        .route("/runner/heartbeat", post(handle_runner_heartbeat))
        .route("/runner/complete", post(handle_runner_complete))
        .route("/runner/fail", post(handle_runner_fail))
        .route("/runner/cancelled", post(handle_runner_cancelled))
        .fallback(not_found_handler)
        .with_state(state)
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut terminate =
            signal(SignalKind::terminate()).expect("sigterm handler should install");
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {},
            _ = terminate.recv() => {},
        }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}

fn json_response<T: Serialize>(data: T, status: StatusCode) -> Response {
    (status, Json(data)).into_response()
}

fn markdown_response(content: String, status: StatusCode) -> Response {
    json_response(json!({ "content": content }), status)
}

fn bad_request(message: impl Into<String>) -> Response {
    json_response(json!({ "error": message.into() }), StatusCode::BAD_REQUEST)
}

fn unauthorized(message: impl Into<String>) -> Response {
    json_response(json!({ "error": message.into() }), StatusCode::UNAUTHORIZED)
}

fn not_found() -> Response {
    json_response(json!({ "error": "not found" }), StatusCode::NOT_FOUND)
}

async fn not_found_handler() -> Response {
    not_found()
}

fn parse_json_body(content_type: Option<&str>, body: &[u8]) -> anyhow::Result<Value> {
    if content_type.is_some_and(|value| value.contains("application/json")) {
        return Ok(serde_json::from_slice(body)?);
    }
    if body.is_empty() {
        return Ok(json!({}));
    }
    if content_type.is_some_and(|value| value.contains("application/x-www-form-urlencoded")) {
        let params = url::form_urlencoded::parse(body)
            .into_owned()
            .collect::<Vec<_>>();
        if let Some((_, data)) = params.iter().find(|(key, _)| key == "data") {
            return Ok(serde_json::from_str(data)?);
        }
        let object = params
            .into_iter()
            .map(|(key, value)| (key, Value::String(value)))
            .collect();
        return Ok(Value::Object(object));
    }
    Ok(serde_json::from_slice(body)?)
}

fn normalize_zulip_payload(raw: Value) -> ZulipOutgoingPayload {
    let Some(record) = raw.as_object() else {
        return ZulipOutgoingPayload::default();
    };
    if let Some(nested_raw) = record.get("data").and_then(Value::as_str) {
        let nested = serde_json::from_str::<Value>(nested_raw).ok();
        let nested_record = nested.as_ref().and_then(Value::as_object);
        return ZulipOutgoingPayload {
            token: record
                .get("token")
                .and_then(Value::as_str)
                .map(str::to_owned)
                .or_else(|| {
                    nested_record
                        .and_then(|value| value.get("token"))
                        .and_then(Value::as_str)
                        .map(str::to_owned)
                }),
            message: nested_record
                .and_then(|value| value.get("message"))
                .and_then(|value| {
                    serde_json::from_value::<ZulipOutgoingMessage>(value.clone()).ok()
                }),
        };
    }
    ZulipOutgoingPayload {
        token: record
            .get("token")
            .and_then(Value::as_str)
            .map(str::to_owned),
        message: record
            .get("message")
            .and_then(|value| serde_json::from_value::<ZulipOutgoingMessage>(value.clone()).ok()),
    }
}

fn message_to_context(message: Option<&ZulipOutgoingMessage>) -> ZulipContext {
    ZulipContext {
        message_id: message.and_then(|value| value.id),
        stream_id: message.and_then(|value| value.stream_id),
        topic: message.and_then(|value| value.topic.clone().or_else(|| value.subject.clone())),
        sender_email: message.and_then(|value| value.sender_email.clone()),
        sender_name: message.and_then(|value| value.sender_full_name.clone()),
    }
}

fn is_mutating_command(command: &ParsedCommand) -> bool {
    matches!(
        command,
        ParsedCommand::Publish { .. }
            | ParsedCommand::LedgerPost { .. }
            | ParsedCommand::Cancel { .. }
            | ParsedCommand::Rerun { .. }
    )
}

fn require_runner_secret(headers: &HeaderMap, config: &DispatchConfig) -> bool {
    let Some(secret) = config.runner_shared_secret.as_deref() else {
        return false;
    };
    headers
        .get("authorization")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .map_or_else(
            || {
                headers
                    .get("x-specter-runner-secret")
                    .and_then(|value| value.to_str().ok())
                    .is_some_and(|value| value == secret)
            },
            |value| value == secret,
        )
}

async fn execute_zulip_command_content(
    state: &AppState,
    message: Option<&ZulipOutgoingMessage>,
) -> anyhow::Result<String> {
    let command = parse_command(
        message
            .and_then(|value| value.content.as_deref())
            .unwrap_or(""),
    );
    let zulip = message_to_context(message);
    let admin_emails = state.config.admin_email_set();
    if is_mutating_command(&command) {
        if admin_emails.is_empty() {
            return Ok(
                "Mutating commands are disabled until `ADMIN_EMAILS` is configured.".to_owned(),
            );
        }
        if zulip
            .sender_email
            .as_deref()
            .map(str::to_ascii_lowercase)
            .is_none_or(|email| !admin_emails.contains(&email))
        {
            return Ok("This command is restricted to configured admin emails.".to_owned());
        }
    }
    match command {
        ParsedCommand::Help => Ok(build_help_message()),
        ParsedCommand::StatusHealth => status_health_message(state.store.as_ref()).await,
        ParsedCommand::StatusQueue => status_queue_message(state.store.as_ref()).await,
        ParsedCommand::StatusRunners => status_runners_message(state.store.as_ref()).await,
        ParsedCommand::StatusCommands => Ok(commands_status_message()),
        ParsedCommand::StatusJob { job_id } => {
            status_job_message(state.store.as_ref(), &job_id).await
        }
        ParsedCommand::Publish {
            project,
            action,
            args,
        } => {
            let job_spec = match resolve_surface("publish", &project, action.as_deref(), &args) {
                Ok(job_spec) => job_spec,
                Err(error) => return Ok(format!("{error}.\n\n{}", build_help_message())),
            };
            let job = state
                .store
                .create_queued_job(job_spec.clone(), zulip)
                .await?;
            Ok([
                format!(
                    "Queued job `{}` for `{}`.",
                    job.id,
                    job_spec
                        .args
                        .get("commandLabel")
                        .and_then(Value::as_str)
                        .unwrap_or("publish site")
                ),
                format!(
                    "Required capabilities: `{}`",
                    job_spec.required_capabilities.join(", ")
                ),
            ]
            .join("\n"))
        }
        ParsedCommand::LedgerPostInvalid { message } => {
            Ok(format!("{message}\n\n{}", build_ledger_post_usage()))
        }
        ParsedCommand::LedgerPost { topic, body } => match post_ledger_entry(
            state,
            AdminLedgerPostRequest {
                topic,
                body,
                requested_by_email: zulip.sender_email,
                requested_by_name: zulip.sender_name,
            },
        )
        .await
        {
            Ok(outcome) => Ok(format_ledger_post_success(&outcome)),
            Err(error) => {
                let message = error.to_string();
                if message.contains("Ledger body must")
                    || message.contains("added/changed/removed entry")
                {
                    Ok(format!("{message}\n\n{}", build_ledger_post_usage()))
                } else {
                    Ok(message)
                }
            }
        },
        ParsedCommand::Cancel { job_id } => {
            let Some(job) = state.store.request_cancel(&job_id).await? else {
                return Ok(format!("No job found for `{job_id}`."));
            };
            Ok(format!("Job `{}` is now `{}`.", job.id, job.state.as_str()))
        }
        ParsedCommand::Rerun { job_id } => {
            let Some(job) = state.store.clone_job(&job_id).await? else {
                return Ok(format!("No job found for `{job_id}`."));
            };
            Ok(format!("Queued replay as `{}`.", job.id))
        }
        ParsedCommand::NotEnabled { feature } => Ok(format!(
            "`{feature}` is not enabled in this dispatch build."
        )),
    }
}

async fn post_ledger_entry(
    state: &AppState,
    request: AdminLedgerPostRequest,
) -> anyhow::Result<AdminLedgerPostResponse> {
    let stream_name = state.config.zulip_ledger_stream.clone().ok_or_else(|| {
        anyhow::anyhow!("Ledger posting is disabled until `ZULIP_LEDGER_STREAM` is configured.")
    })?;
    if !state.poster.can_send() {
        anyhow::bail!("Ledger posting is unavailable until Zulip bot credentials are configured.");
    }
    let sections = parse_ledger_sections(&request.body)?;
    let created_at = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
    let entry_id = create_ledger_entry_id(&created_at);
    let content = format_ledger_entry(&LedgerEntryDraft {
        id: entry_id.clone(),
        topic: request.topic.clone(),
        created_at: created_at.clone(),
        requested_by_email: request.requested_by_email.clone(),
        requested_by_name: request.requested_by_name.clone(),
        sections,
    });
    state
        .store
        .reserve_ledger_entry(crate::dispatch::types::LedgerEntryReservation {
            id: entry_id.clone(),
            stream_name: stream_name.clone(),
            topic: request.topic.clone(),
            created_at: created_at.clone(),
            requested_by_email: request.requested_by_email.clone(),
            requested_by_name: request.requested_by_name.clone(),
            content_markdown: content.clone(),
        })
        .await?;
    let message_id = match state
        .poster
        .send_stream_message(&stream_name, &request.topic, &content)
        .await
    {
        Ok(message_id) => message_id,
        Err(error) => {
            let _ = state.store.mark_ledger_entry_failed(&entry_id).await;
            anyhow::bail!(
                "Reserved ledger entry `{entry_id}` but failed to post it to `{stream_name} > {}`.\n- timestamp: `{created_at}`\n- error: {error}",
                request.topic
            );
        }
    };
    if let Err(error) = state
        .store
        .mark_ledger_entry_posted(&entry_id, message_id)
        .await
    {
        let mut lines = vec![
            format!(
                "Posted ledger entry `{entry_id}` to `{stream_name} > {}`, but failed to update dispatch storage.",
                request.topic
            ),
            format!("- timestamp: `{created_at}`"),
            format!("- error: {error}"),
        ];
        if let Some(message_id) = message_id {
            lines.push(format!("- zulip message id: `{message_id}`"));
        }
        anyhow::bail!(lines.join("\n"));
    }
    Ok(AdminLedgerPostResponse {
        entry_id,
        created_at,
        message_id,
        stream_name,
        topic: request.topic,
        content,
    })
}

fn format_ledger_post_success(outcome: &AdminLedgerPostResponse) -> String {
    let mut lines = vec![
        format!(
            "Posted ledger entry `{}` to `{}`.",
            outcome.entry_id,
            format!("{} > {}", outcome.stream_name, outcome.topic)
        ),
        format!("- timestamp: `{}`", outcome.created_at),
    ];
    if let Some(message_id) = outcome.message_id {
        lines.push(format!("- zulip message id: `{message_id}`"));
    }
    lines.join("\n")
}

async fn handle_health(State(state): State<AppState>) -> Response {
    match health_response(state.store.as_ref()).await {
        Ok(payload) => json_response(payload, StatusCode::OK),
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn handle_zulip_outgoing(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let payload = match parse_json_body(
        headers
            .get("content-type")
            .and_then(|value| value.to_str().ok()),
        &body,
    ) {
        Ok(raw) => normalize_zulip_payload(raw),
        Err(error) => return bad_request(error.to_string()),
    };
    let Some(expected_token) = state.config.zulip_webhook_token.as_deref() else {
        return json_response(
            json!({ "error": "ZULIP_WEBHOOK_TOKEN is not configured" }),
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    };
    if payload.token.as_deref() != Some(expected_token) {
        return unauthorized("invalid webhook token");
    }
    match execute_zulip_command_content(&state, payload.message.as_ref()).await {
        Ok(content) => markdown_response(content, StatusCode::OK),
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn handle_admin_ledger_post(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !require_runner_secret(&headers, &state.config) {
        return unauthorized("unauthorized");
    }
    let raw = match parse_json_body(
        headers
            .get("content-type")
            .and_then(|value| value.to_str().ok()),
        &body,
    ) {
        Ok(raw) => raw,
        Err(error) => return bad_request(error.to_string()),
    };
    let Ok(mut payload) = serde_json::from_value::<AdminLedgerPostRequest>(raw) else {
        return bad_request("topic is required");
    };
    payload.topic = payload.topic.trim().to_owned();
    if payload.topic.is_empty() {
        return bad_request("topic is required");
    }
    if payload.body.trim().is_empty() {
        return bad_request("body is required");
    }
    match trim_non_empty(payload.requested_by_email.as_deref(), "requestedByEmail") {
        Ok(value) => payload.requested_by_email = value,
        Err(error) => return bad_request(error.to_string()),
    }
    match trim_non_empty(payload.requested_by_name.as_deref(), "requestedByName") {
        Ok(value) => payload.requested_by_name = value,
        Err(error) => return bad_request(error.to_string()),
    }
    match post_ledger_entry(&state, payload).await {
        Ok(response) => json_response(response, StatusCode::OK),
        Err(error) => bad_request(error.to_string()),
    }
}

async fn handle_github_webhook_request(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    let Some(secret) = state.config.github_webhook_secret.as_deref() else {
        return json_response(
            json!({ "error": "GITHUB_WEBHOOK_SECRET is not configured" }),
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    };
    let Some(event_name) = headers
        .get("x-github-event")
        .and_then(|value| value.to_str().ok())
    else {
        return bad_request("missing x-github-event header");
    };
    let Some(delivery_id) = headers
        .get("x-github-delivery")
        .and_then(|value| value.to_str().ok())
    else {
        return bad_request("missing x-github-delivery header");
    };
    let body_text = match String::from_utf8(body.to_vec()) {
        Ok(body) => body,
        Err(error) => return bad_request(error.to_string()),
    };
    if !verify_github_signature(
        secret,
        &body_text,
        headers
            .get("x-hub-signature-256")
            .and_then(|value| value.to_str().ok()),
    ) {
        return unauthorized("invalid github signature");
    }
    match state
        .store
        .reserve_github_delivery(delivery_id, event_name)
        .await
    {
        Ok(false) => json_response(
            json!({ "accepted": false, "reason": "duplicate delivery" }),
            StatusCode::OK,
        ),
        Ok(true) => match handle_github_webhook(
            &state.config,
            state.poster.as_ref(),
            event_name,
            &body_text,
        )
        .await
        {
            Ok(payload) => json_response(payload, StatusCode::OK),
            Err(error) => json_response(
                json!({ "error": error.to_string() }),
                StatusCode::INTERNAL_SERVER_ERROR,
            ),
        },
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn handle_runner_register(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !require_runner_secret(&headers, &state.config) {
        return unauthorized("unauthorized");
    }
    let raw = match parse_json_body(
        headers
            .get("content-type")
            .and_then(|value| value.to_str().ok()),
        &body,
    ) {
        Ok(raw) => raw,
        Err(error) => return bad_request(error.to_string()),
    };
    let payload = match serde_json::from_value::<RunnerRegistration>(raw) {
        Ok(payload) => payload,
        Err(_) => return bad_request("runnerId, displayName, and capabilities are required"),
    };
    match state.store.register_runner(payload).await {
        Ok(runner) => json_response(RunnerEnvelope { runner }, StatusCode::OK),
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn handle_runner_claim(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !require_runner_secret(&headers, &state.config) {
        return unauthorized("unauthorized");
    }
    let raw = match parse_json_body(
        headers
            .get("content-type")
            .and_then(|value| value.to_str().ok()),
        &body,
    ) {
        Ok(raw) => raw,
        Err(error) => return bad_request(error.to_string()),
    };
    let payload = serde_json::from_value::<RunnerClaimRequest>(raw).unwrap_or_default();
    let Some(runner_id) = payload.runner_id else {
        return bad_request("runnerId is required");
    };
    match state.store.claim_next_job(&runner_id).await {
        Ok(job) => json_response(JobEnvelope { job }, StatusCode::OK),
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn handle_runner_heartbeat(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !require_runner_secret(&headers, &state.config) {
        return unauthorized("unauthorized");
    }
    let raw = match parse_json_body(
        headers
            .get("content-type")
            .and_then(|value| value.to_str().ok()),
        &body,
    ) {
        Ok(raw) => raw,
        Err(error) => return bad_request(error.to_string()),
    };
    let payload = serde_json::from_value::<RunnerHeartbeatRequest>(raw).unwrap_or_default();
    let (Some(runner_id), Some(job_id)) = (payload.runner_id, payload.job_id) else {
        return bad_request("runnerId and jobId are required");
    };
    match state.store.heartbeat_runner_job(&runner_id, &job_id).await {
        Ok(job) => json_response(
            HeartbeatEnvelope {
                cancel_requested: job.as_ref().is_some_and(|job| {
                    matches!(job.state, crate::dispatch::types::JobState::CancelRequested)
                }),
                job,
            },
            StatusCode::OK,
        ),
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn handle_runner_complete(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    handle_runner_completion(
        state,
        headers,
        body,
        crate::dispatch::types::JobState::Succeeded,
    )
    .await
}

async fn handle_runner_fail(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    handle_runner_completion(
        state,
        headers,
        body,
        crate::dispatch::types::JobState::Failed,
    )
    .await
}

async fn handle_runner_cancelled(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    handle_runner_completion(
        state,
        headers,
        body,
        crate::dispatch::types::JobState::Cancelled,
    )
    .await
}

async fn handle_runner_completion(
    state: AppState,
    headers: HeaderMap,
    body: Bytes,
    outcome: crate::dispatch::types::JobState,
) -> Response {
    if !require_runner_secret(&headers, &state.config) {
        return unauthorized("unauthorized");
    }
    let raw = match parse_json_body(
        headers
            .get("content-type")
            .and_then(|value| value.to_str().ok()),
        &body,
    ) {
        Ok(raw) => raw,
        Err(error) => return bad_request(error.to_string()),
    };
    let payload = serde_json::from_value::<RunnerCompleteRequest>(raw).unwrap_or_default();
    let (Some(runner_id), Some(job_id), Some(summary)) =
        (payload.runner_id, payload.job_id, payload.summary)
    else {
        return bad_request("runnerId, jobId, and summary are required");
    };
    let completion = JobCompletion {
        summary,
        exit_code: payload.exit_code,
        result: payload.result.unwrap_or_else(JsonMap::default),
    };
    let result = match outcome {
        crate::dispatch::types::JobState::Succeeded => {
            state
                .store
                .complete_job(&runner_id, &job_id, completion)
                .await
        }
        crate::dispatch::types::JobState::Failed => {
            state.store.fail_job(&runner_id, &job_id, completion).await
        }
        crate::dispatch::types::JobState::Cancelled => {
            state
                .store
                .cancel_job(&runner_id, &job_id, completion)
                .await
        }
        _ => unreachable!(),
    };
    match result {
        Ok(job) => {
            maybe_post_job_update(&state, job.as_ref()).await;
            json_response(JobEnvelope { job }, StatusCode::OK)
        }
        Err(error) => json_response(
            json!({ "error": error.to_string() }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn maybe_post_job_update(state: &AppState, job: Option<&crate::dispatch::types::JobRecord>) {
    let Some(job) = job else {
        return;
    };
    if let Err(error) = state
        .poster
        .send_context_message(
            ZulipSendContext {
                stream_id: job.zulip_stream_id,
                stream_name: None,
                topic: job.zulip_topic.clone(),
                sender_email: job.zulip_sender_email.clone(),
            },
            &format_job_update(job),
        )
        .await
    {
        eprintln!("zulip follow-up failed: {error}");
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use async_trait::async_trait;
    use axum::body::{to_bytes, Body};
    use axum::http::{Request, StatusCode};
    use serde_json::json;
    use tower::ServiceExt;

    use super::*;
    use crate::dispatch::store::DispatchStore;
    use crate::dispatch::types::{
        HealthSnapshot, JobKind, JobRecord, JobState, LedgerEntryRecord, LedgerEntryReservation,
        LedgerEntryState, RunnerRecord,
    };

    #[derive(Default)]
    struct RecordingPoster {
        stream_messages: Mutex<Vec<(String, String, String)>>,
        context_messages: Mutex<Vec<(ZulipSendContext, String)>>,
    }

    #[async_trait]
    impl MessagePoster for RecordingPoster {
        fn can_send(&self) -> bool {
            true
        }

        async fn send_context_message(
            &self,
            context: ZulipSendContext,
            content: &str,
        ) -> anyhow::Result<Option<i64>> {
            if let Some(stream_name) = context.stream_name.clone() {
                self.stream_messages.lock().unwrap().push((
                    stream_name,
                    context.topic.clone().unwrap_or_default(),
                    content.to_owned(),
                ));
            }
            self.context_messages
                .lock()
                .unwrap()
                .push((context, content.to_owned()));
            Ok(Some(4321))
        }
    }

    struct MockStore {
        health: HealthSnapshot,
        runners: Vec<RunnerRecord>,
        recent_jobs: Vec<JobRecord>,
        claim_job: Mutex<Option<JobRecord>>,
        heartbeat_job: Mutex<Option<JobRecord>>,
        complete_job: Mutex<Option<JobRecord>>,
        reserved_entries: Mutex<Vec<LedgerEntryReservation>>,
        posted_entries: Mutex<Vec<(String, Option<i64>)>>,
        registered_runners: Mutex<Vec<RunnerRegistration>>,
    }

    impl Default for MockStore {
        fn default() -> Self {
            Self {
                health: HealthSnapshot::default(),
                runners: Vec::new(),
                recent_jobs: Vec::new(),
                claim_job: Mutex::new(None),
                heartbeat_job: Mutex::new(None),
                complete_job: Mutex::new(None),
                reserved_entries: Mutex::new(Vec::new()),
                posted_entries: Mutex::new(Vec::new()),
                registered_runners: Mutex::new(Vec::new()),
            }
        }
    }

    #[async_trait]
    impl DispatchStore for MockStore {
        async fn create_queued_job(
            &self,
            _job_spec: crate::dispatch::types::JobSpec,
            _zulip: ZulipContext,
        ) -> anyhow::Result<JobRecord> {
            Ok(sample_job(JobState::Queued))
        }

        async fn get_job(&self, _job_id: &str) -> anyhow::Result<Option<JobRecord>> {
            Ok(None)
        }

        async fn clone_job(&self, _original_id: &str) -> anyhow::Result<Option<JobRecord>> {
            Ok(None)
        }

        async fn request_cancel(&self, _job_id: &str) -> anyhow::Result<Option<JobRecord>> {
            Ok(None)
        }

        async fn register_runner(
            &self,
            runner: RunnerRegistration,
        ) -> anyhow::Result<RunnerRecord> {
            self.registered_runners.lock().unwrap().push(runner.clone());
            Ok(RunnerRecord {
                id: runner.runner_id,
                display_name: runner.display_name,
                version: runner.version,
                capabilities: runner.capabilities,
                concurrency_limit: runner.concurrency_limit,
                status: "online".to_owned(),
                current_job_id: None,
                last_seen_at: "2026-03-14T10:00:00.000Z".to_owned(),
            })
        }

        async fn claim_next_job(&self, _runner_id: &str) -> anyhow::Result<Option<JobRecord>> {
            Ok(self.claim_job.lock().unwrap().clone())
        }

        async fn heartbeat_runner_job(
            &self,
            _runner_id: &str,
            _job_id: &str,
        ) -> anyhow::Result<Option<JobRecord>> {
            Ok(self.heartbeat_job.lock().unwrap().clone())
        }

        async fn complete_job(
            &self,
            _runner_id: &str,
            _job_id: &str,
            _completion: JobCompletion,
        ) -> anyhow::Result<Option<JobRecord>> {
            Ok(self.complete_job.lock().unwrap().clone())
        }

        async fn fail_job(
            &self,
            _runner_id: &str,
            _job_id: &str,
            _completion: JobCompletion,
        ) -> anyhow::Result<Option<JobRecord>> {
            Ok(None)
        }

        async fn cancel_job(
            &self,
            _runner_id: &str,
            _job_id: &str,
            _completion: JobCompletion,
        ) -> anyhow::Result<Option<JobRecord>> {
            Ok(None)
        }

        async fn list_recent_jobs(
            &self,
            _limit: usize,
            _states: &[JobState],
        ) -> anyhow::Result<Vec<JobRecord>> {
            Ok(self.recent_jobs.clone())
        }

        async fn list_runners(&self) -> anyhow::Result<Vec<RunnerRecord>> {
            Ok(self.runners.clone())
        }

        async fn health_snapshot(&self) -> anyhow::Result<HealthSnapshot> {
            Ok(self.health.clone())
        }

        async fn reserve_github_delivery(
            &self,
            _delivery_id: &str,
            _event_name: &str,
        ) -> anyhow::Result<bool> {
            Ok(true)
        }

        async fn reserve_ledger_entry(
            &self,
            entry: LedgerEntryReservation,
        ) -> anyhow::Result<LedgerEntryRecord> {
            self.reserved_entries.lock().unwrap().push(entry.clone());
            Ok(LedgerEntryRecord {
                id: entry.id,
                stream_name: entry.stream_name,
                topic: entry.topic,
                state: LedgerEntryState::Posting,
                created_at: entry.created_at,
                posted_at: None,
                requested_by_email: entry.requested_by_email,
                requested_by_name: entry.requested_by_name,
                zulip_message_id: None,
                content_markdown: entry.content_markdown,
            })
        }

        async fn mark_ledger_entry_posted(
            &self,
            entry_id: &str,
            zulip_message_id: Option<i64>,
        ) -> anyhow::Result<Option<LedgerEntryRecord>> {
            self.posted_entries
                .lock()
                .unwrap()
                .push((entry_id.to_owned(), zulip_message_id));
            let reserved = self
                .reserved_entries
                .lock()
                .unwrap()
                .iter()
                .find(|entry| entry.id == entry_id)
                .cloned();
            Ok(reserved.map(|entry| LedgerEntryRecord {
                id: entry.id,
                stream_name: entry.stream_name,
                topic: entry.topic,
                state: LedgerEntryState::Posted,
                created_at: entry.created_at,
                posted_at: Some("2026-03-14T10:00:00.000Z".to_owned()),
                requested_by_email: entry.requested_by_email,
                requested_by_name: entry.requested_by_name,
                zulip_message_id,
                content_markdown: entry.content_markdown,
            }))
        }

        async fn mark_ledger_entry_failed(
            &self,
            _entry_id: &str,
        ) -> anyhow::Result<Option<LedgerEntryRecord>> {
            Ok(None)
        }
    }

    fn sample_job(state: JobState) -> JobRecord {
        JobRecord {
            id: "job-1".to_owned(),
            kind: JobKind::Exec,
            project: "site".to_owned(),
            action: "publish".to_owned(),
            cwd: ".".to_owned(),
            argv: vec![
                "cargo".to_owned(),
                "run".to_owned(),
                "--release".to_owned(),
                "--manifest-path".to_owned(),
                "ops/spctr/Cargo.toml".to_owned(),
                "--".to_owned(),
                "site".to_owned(),
                "publish".to_owned(),
            ],
            args: serde_json::from_value(json!({ "commandLabel": "publish site" })).unwrap(),
            required_capabilities: vec!["cargo".to_owned()],
            state,
            requested_by_email: Some("operator@example.invalid".to_owned()),
            requested_by_name: Some("Operator".to_owned()),
            zulip_message_id: Some(1),
            zulip_stream_id: Some(5),
            zulip_topic: Some("dispatch".to_owned()),
            zulip_sender_email: Some("operator@example.invalid".to_owned()),
            created_at: "2026-03-14T10:00:00.000Z".to_owned(),
            claimed_at: Some("2026-03-14T10:00:01.000Z".to_owned()),
            heartbeat_at: Some("2026-03-14T10:00:02.000Z".to_owned()),
            finished_at: Some("2026-03-14T10:00:03.000Z".to_owned()),
            runner_id: Some("runner-1".to_owned()),
            exit_code: Some(0),
            summary: Some("done".to_owned()),
            result: serde_json::Map::new(),
        }
    }

    fn test_state(store: Arc<dyn DispatchStore>, poster: Arc<dyn MessagePoster>) -> AppState {
        AppState {
            config: DispatchConfig {
                runner_shared_secret: Some("secret-123".to_owned()),
                zulip_ledger_stream: Some("ledger".to_owned()),
                ..DispatchConfig::default()
            },
            store,
            poster,
        }
    }

    #[tokio::test]
    async fn health_endpoint_returns_snapshot_payload() {
        let store = Arc::new(MockStore {
            health: HealthSnapshot {
                queued_jobs: 1,
                active_jobs: 2,
                online_runners: 3,
            },
            runners: vec![RunnerRecord {
                id: "runner-1".to_owned(),
                display_name: "runner-macos-1".to_owned(),
                version: None,
                capabilities: vec!["python".to_owned(), "nix".to_owned()],
                concurrency_limit: 1,
                status: "online".to_owned(),
                current_job_id: None,
                last_seen_at: chrono::Utc::now()
                    .to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
            }],
            recent_jobs: vec![sample_job(JobState::Succeeded)],
            ..MockStore::default()
        });
        let app = app(test_state(store, Arc::new(RecordingPoster::default())));

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body: serde_json::Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(body["ok"], json!(true));
        assert_eq!(body["snapshot"]["queuedJobs"], json!(1));
        assert_eq!(body["snapshot"]["activeJobs"], json!(2));
        assert_eq!(body["snapshot"]["onlineRunners"], json!(3));
        assert_eq!(
            body["snapshot"]["runners"][0]["displayName"],
            json!("runner-macos-1")
        );
        assert_eq!(
            body["snapshot"]["recentJobs"][0]["command"],
            json!("publish site")
        );
    }

    #[tokio::test]
    async fn admin_ledger_post_accepts_shared_secret_requests() {
        let store = Arc::new(MockStore::default());
        let poster = Arc::new(RecordingPoster::default());
        let app = app(test_state(store.clone(), poster.clone()));
        let body_text = ["Dossiers:", "- lenia-swarm: added Lenia Lab."].join("\n");

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/admin/ledger/post")
                    .header("authorization", "Bearer secret-123")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "topic": "weekly / 2026-03-14",
                            "body": body_text,
                            "requestedByEmail": "operator@example.invalid",
                            "requestedByName": "Operator"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body: serde_json::Value =
            serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(body["streamName"], json!("ledger"));
        assert_eq!(body["topic"], json!("weekly / 2026-03-14"));
        assert_eq!(body["messageId"], json!(4321));
        assert!(body["entryId"].as_str().unwrap().starts_with("ledger-"));
        let stream_messages = &poster.stream_messages.lock().unwrap()[0];
        assert_eq!(stream_messages.0, "ledger");
        assert_eq!(stream_messages.1, "weekly / 2026-03-14");
        assert!(stream_messages.2.contains("**Dossiers**"));
    }

    #[tokio::test]
    async fn runner_endpoints_preserve_json_contracts() {
        let store = Arc::new(MockStore {
            claim_job: Mutex::new(Some(sample_job(JobState::Claimed))),
            heartbeat_job: Mutex::new(Some(sample_job(JobState::CancelRequested))),
            complete_job: Mutex::new(Some(sample_job(JobState::Succeeded))),
            ..MockStore::default()
        });
        let poster = Arc::new(RecordingPoster::default());
        let app = app(test_state(store.clone(), poster.clone()));

        let register = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/runner/register")
                    .header("authorization", "Bearer secret-123")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "runnerId": "runner-1",
                            "displayName": "runner-macos-1",
                            "capabilities": ["cargo", "git"]
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(register.status(), StatusCode::OK);

        let claim = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/runner/claim")
                    .header("authorization", "Bearer secret-123")
                    .header("content-type", "application/json")
                    .body(Body::from(json!({ "runnerId": "runner-1" }).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        let claim_body: serde_json::Value =
            serde_json::from_slice(&to_bytes(claim.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(claim_body["job"]["id"], json!("job-1"));

        let heartbeat = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/runner/heartbeat")
                    .header("authorization", "Bearer secret-123")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({ "runnerId": "runner-1", "jobId": "job-1" }).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let heartbeat_body: serde_json::Value =
            serde_json::from_slice(&to_bytes(heartbeat.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(heartbeat_body["cancelRequested"], json!(true));
        assert_eq!(heartbeat_body["job"]["state"], json!("cancel_requested"));

        let complete = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/runner/complete")
                    .header("authorization", "Bearer secret-123")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({
                            "runnerId": "runner-1",
                            "jobId": "job-1",
                            "summary": "done",
                            "exitCode": 0,
                            "result": {}
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let complete_body: serde_json::Value =
            serde_json::from_slice(&to_bytes(complete.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(complete_body["job"]["id"], json!("job-1"));
        assert_eq!(poster.context_messages.lock().unwrap().len(), 1);
    }
}
