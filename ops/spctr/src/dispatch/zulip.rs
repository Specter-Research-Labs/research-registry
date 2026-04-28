use async_trait::async_trait;
use base64::Engine;
use reqwest::Client;
use serde::Deserialize;
use serde_json::Value;

use crate::dispatch::env::DispatchConfig;
use crate::dispatch::results::{as_publish_result, duration_label};
use crate::dispatch::types::{JobRecord, ZulipSendContext};

#[async_trait]
pub trait MessagePoster: Send + Sync {
    fn can_send(&self) -> bool;
    async fn send_context_message(
        &self,
        context: ZulipSendContext,
        content: &str,
    ) -> anyhow::Result<Option<i64>>;

    async fn send_stream_message(
        &self,
        stream_name: &str,
        topic: &str,
        content: &str,
    ) -> anyhow::Result<Option<i64>> {
        self.send_context_message(
            ZulipSendContext {
                stream_id: None,
                stream_name: Some(stream_name.to_owned()),
                topic: Some(topic.to_owned()),
                sender_email: None,
            },
            content,
        )
        .await
    }
}

#[derive(Clone)]
pub struct ReqwestMessagePoster {
    site: Option<String>,
    email: Option<String>,
    api_key: Option<String>,
    client: Client,
}

#[derive(Deserialize)]
struct ZulipSendResponse {
    id: Option<i64>,
}

impl ReqwestMessagePoster {
    pub fn from_config(config: &DispatchConfig) -> Self {
        Self {
            site: config.zulip_site.clone(),
            email: config.zulip_bot_email.clone(),
            api_key: config.zulip_bot_api_key.clone(),
            client: Client::new(),
        }
    }

    fn auth_header(&self) -> Option<String> {
        let email = self.email.as_deref()?;
        let api_key = self.api_key.as_deref()?;
        Some(format!(
            "Basic {}",
            base64::engine::general_purpose::STANDARD.encode(format!("{email}:{api_key}"))
        ))
    }
}

#[async_trait]
impl MessagePoster for ReqwestMessagePoster {
    fn can_send(&self) -> bool {
        self.site.is_some() && self.auth_header().is_some()
    }

    async fn send_context_message(
        &self,
        context: ZulipSendContext,
        content: &str,
    ) -> anyhow::Result<Option<i64>> {
        let Some(site) = self.site.as_deref() else {
            return Ok(None);
        };
        let Some(auth) = self.auth_header() else {
            return Ok(None);
        };
        let mut body = Vec::<(String, String)>::new();
        if (context.stream_id.is_some() || context.stream_name.is_some()) && context.topic.is_some()
        {
            body.push(("type".to_owned(), "stream".to_owned()));
            body.push((
                "to".to_owned(),
                context
                    .stream_id
                    .map(|value| value.to_string())
                    .or(context.stream_name)
                    .unwrap_or_default(),
            ));
            body.push(("topic".to_owned(), context.topic.unwrap_or_default()));
        } else if let Some(sender_email) = context.sender_email {
            body.push(("type".to_owned(), "private".to_owned()));
            body.push(("to".to_owned(), serde_json::to_string(&vec![sender_email])?));
        } else {
            return Ok(None);
        }
        body.push(("content".to_owned(), content.to_owned()));
        let response = self
            .client
            .post(reqwest::Url::parse(site)?.join("/api/v1/messages")?)
            .header(reqwest::header::AUTHORIZATION, auth)
            .form(&body)
            .send()
            .await?;
        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().await.unwrap_or_default();
            anyhow::bail!("zulip send failed: {status} {text}");
        }
        let payload = response.json::<ZulipSendResponse>().await?;
        Ok(payload.id)
    }
}

pub fn format_job_update(job: &JobRecord) -> String {
    let command_label = job
        .args
        .get("commandLabel")
        .and_then(Value::as_str)
        .unwrap_or(&format!("{} {}", job.project, job.action))
        .to_owned();
    let state_label = match job.state {
        crate::dispatch::types::JobState::Succeeded => "Succeeded",
        crate::dispatch::types::JobState::Failed => "Failed",
        crate::dispatch::types::JobState::Cancelled => "Cancelled",
        crate::dispatch::types::JobState::CancelRequested => "Cancel Requested",
        crate::dispatch::types::JobState::Claimed => "Claimed",
        crate::dispatch::types::JobState::Queued => "Queued",
    };
    let mut lines = vec![
        format!("**{state_label}** `{command_label}`"),
        format!("- job: `{}`", job.id),
    ];
    if let Some(runner_id) = &job.runner_id {
        lines.push(format!("- runner: `{runner_id}`"));
    }
    if let Some(duration) = duration_label(job) {
        lines.push(format!("- duration: `{duration}`"));
    }
    if let Some(summary) = &job.summary {
        lines.push(format!("- summary: {summary}"));
    }
    if let Some(exit_code) = job.exit_code {
        lines.push(format!("- exit code: `{exit_code}`"));
    }
    if let Some(publish) = as_publish_result(&job.result) {
        if matches!(job.state, crate::dispatch::types::JobState::Succeeded) {
            lines.push(format!("- release: `{}`", publish.release_id));
            lines.push(format!(
                "- archive: [immutable release]({})",
                publish.public_url
            ));
            lines.push(format!(
                "- current: [current surface]({})",
                publish.current_url
            ));
            if let Some(manifest_path) = publish.manifest_path {
                lines.push(format!("- manifest: `{manifest_path}`"));
            }
            if let Some(site_path) = publish.site_path {
                lines.push(format!("- site path: `{site_path}`"));
            }
            if let Some(provenance) = publish.provenance {
                lines.push(format!("- provenance: `{provenance}`"));
            }
            for artifact in publish.artifacts.into_iter().take(4) {
                if let Some(url) = artifact.url {
                    lines.push(format!("- artifact: [{}]({url})", artifact.label));
                } else if let Some(path) = artifact.path {
                    lines.push(format!("- artifact: `{}: {path}`", artifact.label));
                }
            }
        } else {
            lines.push(format!("- cwd: `{}`", job.cwd));
        }
    } else {
        lines.push(format!("- cwd: `{}`", job.cwd));
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;
    use crate::dispatch::types::{JobRecord, JobState};

    fn base_job(overrides: impl FnOnce(&mut JobRecord)) -> JobRecord {
        let mut job = JobRecord {
            id: "job-123".to_owned(),
            kind: crate::dispatch::types::JobKind::Exec,
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
            required_capabilities: vec![
                "cargo".to_owned(),
                "python".to_owned(),
                "pandoc".to_owned(),
                "rsync".to_owned(),
                "ssh".to_owned(),
                "git".to_owned(),
            ],
            state: JobState::Succeeded,
            requested_by_email: Some("operator@example.invalid".to_owned()),
            requested_by_name: Some("Operator".to_owned()),
            zulip_message_id: Some(1),
            zulip_stream_id: Some(2),
            zulip_topic: Some("publish / site / site".to_owned()),
            zulip_sender_email: Some("operator@example.invalid".to_owned()),
            created_at: "2026-03-13T10:00:00.000Z".to_owned(),
            claimed_at: Some("2026-03-13T10:00:01.000Z".to_owned()),
            heartbeat_at: Some("2026-03-13T10:00:03.000Z".to_owned()),
            finished_at: Some("2026-03-13T10:00:04.000Z".to_owned()),
            runner_id: Some("runner-macos-1".to_owned()),
            exit_code: Some(0),
            summary: Some("Succeeded in 3.0s.".to_owned()),
            result: serde_json::from_value(json!({
                "durationSeconds": 3,
                "releaseId": "abc123",
                "surface": "site",
                "publicUrl": "https://releases.specterlab.org/site/releases/abc123/",
                "currentUrl": "https://specterlab.org/",
                "sitePath": "site",
                "artifacts": []
            }))
            .unwrap(),
        };
        overrides(&mut job);
        job
    }

    #[test]
    fn renders_publish_jobs_as_structured_cards() {
        let message = format_job_update(&base_job(|_| {}));
        assert!(message.contains("**Succeeded** `publish site`"));
        assert!(message.contains("- runner: `runner-macos-1`"));
        assert!(message.contains("- duration: `3.0s`"));
        assert!(message.contains("- release: `abc123`"));
        assert!(message.contains(
            "- archive: [immutable release](https://releases.specterlab.org/site/releases/abc123/)"
        ));
        assert!(message.contains("- current: [current surface](https://specterlab.org/)"));
    }

    #[test]
    fn keeps_failed_non_publish_jobs_compact() {
        let message = format_job_update(&base_job(|job| {
            job.project = "wonton-soup".to_owned();
            job.action = "lean-run".to_owned();
            job.args = serde_json::from_value(
                json!({ "commandLabel": "run wonton-soup lean-run --sample 20" }),
            )
            .unwrap();
            job.state = JobState::Failed;
            job.result = serde_json::from_value(
                json!({ "durationSeconds": 12.5, "stderrTail": "traceback..." }),
            )
            .unwrap();
            job.exit_code = Some(1);
            job.summary = Some("Failed with exit code 1 after 12.5s.".to_owned());
        }));

        assert!(message.contains("**Failed** `run wonton-soup lean-run --sample 20`"));
        assert!(message.contains("- exit code: `1`"));
        assert!(message.contains("- cwd: `.`"));
        assert!(!message.contains("- release:"));
    }
}
