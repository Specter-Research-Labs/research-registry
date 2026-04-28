use hmac::{Hmac, Mac};
use serde::Deserialize;
use sha2::Sha256;

use crate::dispatch::env::DispatchConfig;
use crate::dispatch::types::GithubWebhookOutcome;
use crate::dispatch::zulip::MessagePoster;

type HmacSha256 = Hmac<Sha256>;

#[derive(Deserialize)]
struct GithubRepository {
    full_name: Option<String>,
}

#[derive(Deserialize)]
struct GithubSender {
    login: Option<String>,
}

#[derive(Deserialize)]
struct GithubIssueLike {
    number: Option<u64>,
    title: Option<String>,
    html_url: Option<String>,
    user: Option<GithubSender>,
    draft: Option<bool>,
    merged: Option<bool>,
}

#[derive(Deserialize)]
struct GithubRelease {
    tag_name: Option<String>,
    name: Option<String>,
    html_url: Option<String>,
    author: Option<GithubSender>,
    prerelease: Option<bool>,
}

#[derive(Deserialize)]
struct GithubWorkflowRun {
    name: Option<String>,
    html_url: Option<String>,
    conclusion: Option<String>,
    status: Option<String>,
    event: Option<String>,
    head_branch: Option<String>,
    head_sha: Option<String>,
    run_number: Option<u64>,
}

#[derive(Deserialize)]
struct GithubWebhookEnvelope {
    action: Option<String>,
    repository: Option<GithubRepository>,
    sender: Option<GithubSender>,
    pull_request: Option<GithubIssueLike>,
    issue: Option<GithubIssueLike>,
    release: Option<GithubRelease>,
    workflow_run: Option<GithubWorkflowRun>,
}

struct GithubMessage {
    stream_name: String,
    topic: String,
    content: String,
}

fn short_sha(sha: Option<&str>) -> Option<String> {
    sha.map(|value| value.chars().take(8).collect())
}

fn repo_label(payload: &GithubWebhookEnvelope) -> String {
    payload
        .repository
        .as_ref()
        .and_then(|repository| repository.full_name.clone())
        .unwrap_or_else(|| "unknown-repo".to_owned())
}

fn repo_topic_label(payload: &GithubWebhookEnvelope) -> String {
    let Some(full_name) = payload
        .repository
        .as_ref()
        .and_then(|repository| repository.full_name.as_deref())
    else {
        return "unknown-repo".to_owned();
    };
    full_name.rsplit('/').next().unwrap_or(full_name).to_owned()
}

fn require_dispatch_stream(config: &DispatchConfig) -> anyhow::Result<String> {
    config
        .zulip_dispatch_stream
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| anyhow::anyhow!("ZULIP_DISPATCH_STREAM is not configured"))
}

fn format_pull_request_message(payload: &GithubWebhookEnvelope) -> Option<GithubMessage> {
    let pull_request = payload.pull_request.as_ref()?;
    let action = payload.action.as_deref()?;
    if ![
        "opened",
        "reopened",
        "synchronize",
        "ready_for_review",
        "closed",
    ]
    .contains(&action)
    {
        return None;
    }
    let number = pull_request.number?;
    let url = pull_request.html_url.as_deref()?;
    let title = pull_request.title.as_deref().unwrap_or("(untitled)");
    let closer = if action == "closed" && pull_request.merged == Some(true) {
        "merged"
    } else {
        action
    };
    Some(GithubMessage {
        stream_name: String::new(),
        topic: format!("github / pr / {} / #{number}", repo_topic_label(payload)),
        content: [
            format!("GitHub PR [#{number}]({url}) {closer}: {title}"),
            format!("- repo: `{}`", repo_label(payload)),
            format!(
                "- author: `{}`",
                pull_request
                    .user
                    .as_ref()
                    .and_then(|sender| sender.login.as_deref())
                    .or(payload
                        .sender
                        .as_ref()
                        .and_then(|sender| sender.login.as_deref()))
                    .unwrap_or("unknown")
            ),
            format!(
                "- draft: `{}`",
                if pull_request.draft == Some(true) {
                    "yes"
                } else {
                    "no"
                }
            ),
        ]
        .join("\n"),
    })
}

fn format_issue_message(payload: &GithubWebhookEnvelope) -> Option<GithubMessage> {
    let issue = payload.issue.as_ref()?;
    let action = payload.action.as_deref()?;
    if !["opened", "reopened", "closed"].contains(&action) {
        return None;
    }
    let number = issue.number?;
    let url = issue.html_url.as_deref()?;
    let title = issue.title.as_deref().unwrap_or("(untitled)");
    Some(GithubMessage {
        stream_name: String::new(),
        topic: format!("github / issue / {} / #{number}", repo_topic_label(payload)),
        content: [
            format!("GitHub issue [#{number}]({url}) {action}: {title}"),
            format!("- repo: `{}`", repo_label(payload)),
            format!(
                "- author: `{}`",
                issue
                    .user
                    .as_ref()
                    .and_then(|sender| sender.login.as_deref())
                    .or(payload
                        .sender
                        .as_ref()
                        .and_then(|sender| sender.login.as_deref()))
                    .unwrap_or("unknown")
            ),
        ]
        .join("\n"),
    })
}

fn format_release_message(payload: &GithubWebhookEnvelope) -> Option<GithubMessage> {
    let release = payload.release.as_ref()?;
    let action = payload.action.as_deref()?;
    if !["published", "released", "prereleased"].contains(&action) {
        return None;
    }
    let tag = release.tag_name.as_deref().unwrap_or("unknown-tag");
    let name = release.name.as_deref().unwrap_or(tag);
    let url = release.html_url.as_deref()?;
    Some(GithubMessage {
        stream_name: String::new(),
        topic: format!("github / release / {} / {tag}", repo_topic_label(payload)),
        content: [
            format!("GitHub release [{name}]({url}) {action}"),
            format!("- repo: `{}`", repo_label(payload)),
            format!("- tag: `{tag}`"),
            format!(
                "- author: `{}`",
                release
                    .author
                    .as_ref()
                    .and_then(|sender| sender.login.as_deref())
                    .or(payload
                        .sender
                        .as_ref()
                        .and_then(|sender| sender.login.as_deref()))
                    .unwrap_or("unknown")
            ),
            format!(
                "- prerelease: `{}`",
                if release.prerelease == Some(true) {
                    "yes"
                } else {
                    "no"
                }
            ),
        ]
        .join("\n"),
    })
}

fn format_workflow_run_message(payload: &GithubWebhookEnvelope) -> Option<GithubMessage> {
    let workflow_run = payload.workflow_run.as_ref()?;
    let action = payload.action.as_deref()?;
    if action != "completed" {
        return None;
    }
    let name = workflow_run.name.as_deref().unwrap_or("workflow");
    let url = workflow_run.html_url.as_deref()?;
    Some(GithubMessage {
        stream_name: String::new(),
        topic: format!("github / ci / {} / {name}", repo_topic_label(payload)),
        content: [
            format!(
                "GitHub workflow [{name}]({url}) completed with `{}`",
                workflow_run
                    .conclusion
                    .as_deref()
                    .or(workflow_run.status.as_deref())
                    .unwrap_or("unknown")
            ),
            format!("- repo: `{}`", repo_label(payload)),
            format!(
                "- branch: `{}`",
                workflow_run.head_branch.as_deref().unwrap_or("unknown")
            ),
            format!(
                "- sha: `{}`",
                short_sha(workflow_run.head_sha.as_deref()).unwrap_or_else(|| "unknown".to_owned())
            ),
            format!(
                "- trigger: `{}`",
                workflow_run.event.as_deref().unwrap_or("unknown")
            ),
            format!(
                "- run number: `{}`",
                workflow_run
                    .run_number
                    .map_or_else(|| "unknown".to_owned(), |value| value.to_string())
            ),
        ]
        .join("\n"),
    })
}

fn normalize_message(
    config: &DispatchConfig,
    event_name: &str,
    payload: &GithubWebhookEnvelope,
) -> anyhow::Result<Option<GithubMessage>> {
    let message = match event_name {
        "pull_request" => format_pull_request_message(payload),
        "issues" => format_issue_message(payload),
        "release" => format_release_message(payload),
        "workflow_run" => format_workflow_run_message(payload),
        _ => None,
    };
    let Some(message) = message else {
        return Ok(None);
    };
    Ok(Some(GithubMessage {
        stream_name: require_dispatch_stream(config)?,
        ..message
    }))
}

pub fn verify_github_signature(secret: &str, body: &str, signature_header: Option<&str>) -> bool {
    let Some(signature_header) = signature_header else {
        return false;
    };
    let Some(expected) = signature_header.strip_prefix("sha256=") else {
        return false;
    };
    let Ok(mut mac) = HmacSha256::new_from_slice(secret.as_bytes()) else {
        return false;
    };
    mac.update(body.as_bytes());
    let actual = mac.finalize().into_bytes();
    let actual = actual
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    if actual.len() != expected.len() {
        return false;
    }
    actual
        .bytes()
        .zip(expected.bytes())
        .fold(0u8, |acc, (left, right)| acc | (left ^ right))
        == 0
}

pub async fn handle_github_webhook(
    config: &DispatchConfig,
    poster: &dyn MessagePoster,
    event_name: &str,
    body: &str,
) -> anyhow::Result<GithubWebhookOutcome> {
    let payload: GithubWebhookEnvelope = serde_json::from_str(body)?;
    if let (Some(expected), Some(full_name)) = (
        config.github_repository.as_deref(),
        payload
            .repository
            .as_ref()
            .and_then(|repository| repository.full_name.as_deref()),
    ) {
        if expected != full_name {
            return Ok(GithubWebhookOutcome {
                accepted: false,
                reason: "repo filtered".to_owned(),
            });
        }
    }
    let Some(message) = normalize_message(config, event_name, &payload)? else {
        return Ok(GithubWebhookOutcome {
            accepted: false,
            reason: "event ignored".to_owned(),
        });
    };
    poster
        .send_stream_message(&message.stream_name, &message.topic, &message.content)
        .await?;
    Ok(GithubWebhookOutcome {
        accepted: true,
        reason: "posted".to_owned(),
    })
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use async_trait::async_trait;

    use super::*;
    use crate::dispatch::types::ZulipSendContext;

    #[derive(Default)]
    struct RecordingPoster {
        calls: Arc<Mutex<Vec<(String, String, String)>>>,
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
            self.calls.lock().unwrap().push((
                context.stream_name.unwrap_or_default(),
                context.topic.unwrap_or_default(),
                content.to_owned(),
            ));
            Ok(Some(1))
        }
    }

    #[tokio::test]
    async fn routes_completed_workflow_runs_to_dispatch_stream() {
        let config = DispatchConfig {
            github_repository: Some("Specter-Research-Labs/research-registry".to_owned()),
            zulip_dispatch_stream: Some("dispatch".to_owned()),
            ..DispatchConfig::default()
        };
        let poster = RecordingPoster::default();

        let result = handle_github_webhook(
            &config,
            &poster,
            "workflow_run",
            r#"{
              "action": "completed",
              "repository": { "full_name": "Specter-Research-Labs/research-registry" },
              "workflow_run": {
                "name": "site-projects",
                "html_url": "https://github.com/Specter-Research-Labs/research-registry/actions/runs/1",
                "conclusion": "success",
                "event": "push",
                "head_branch": "main",
                "head_sha": "1234567890abcdef",
                "run_number": 42
              }
            }"#,
        )
        .await
        .unwrap();

        assert_eq!(
            result,
            GithubWebhookOutcome {
                accepted: true,
                reason: "posted".to_owned(),
            }
        );
        let calls = poster.calls.lock().unwrap();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, "dispatch");
        assert_eq!(
            calls[0].1,
            "github / ci / research-registry / site-projects"
        );
        assert!(calls[0].2.contains("completed with `success`"));
    }

    #[tokio::test]
    async fn rejects_filtered_repositories() {
        let config = DispatchConfig {
            github_repository: Some("Specter-Research-Labs/research-registry".to_owned()),
            zulip_dispatch_stream: Some("dispatch".to_owned()),
            ..DispatchConfig::default()
        };
        let poster = RecordingPoster::default();

        let result = handle_github_webhook(
            &config,
            &poster,
            "pull_request",
            r#"{
              "action": "opened",
              "repository": { "full_name": "someone-else/other-repo" },
              "pull_request": {
                "number": 12,
                "title": "Test",
                "html_url": "https://github.com/someone-else/other-repo/pull/12"
              }
            }"#,
        )
        .await
        .unwrap();

        assert_eq!(
            result,
            GithubWebhookOutcome {
                accepted: false,
                reason: "repo filtered".to_owned(),
            }
        );
        assert!(poster.calls.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn fails_when_dispatch_stream_is_missing() {
        let config = DispatchConfig {
            github_repository: Some("Specter-Research-Labs/research-registry".to_owned()),
            ..DispatchConfig::default()
        };
        let poster = RecordingPoster::default();

        let error = handle_github_webhook(
            &config,
            &poster,
            "pull_request",
            r#"{
              "action": "opened",
              "repository": { "full_name": "Specter-Research-Labs/research-registry" },
              "pull_request": {
                "number": 12,
                "title": "Test",
                "html_url": "https://github.com/Specter-Research-Labs/research-registry/pull/12"
              }
            }"#,
        )
        .await
        .unwrap_err();

        assert!(error
            .to_string()
            .contains("ZULIP_DISPATCH_STREAM is not configured"));
        assert!(poster.calls.lock().unwrap().is_empty());
    }
}
