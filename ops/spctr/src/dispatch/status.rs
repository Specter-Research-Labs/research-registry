use crate::dispatch::results::as_publish_result;
use crate::dispatch::store::DispatchStore;
use crate::dispatch::surfaces::list_surfaces;
use crate::dispatch::types::{
    DispatchHealthResponse, DispatchHealthSnapshot, HealthRecentJobView, HealthRunnerView,
    JobRecord, JobState,
};

const RUNNER_FRESHNESS_MS: i64 = 120_000;

fn is_runner_fresh(last_seen_at: &str) -> bool {
    chrono::DateTime::parse_from_rfc3339(last_seen_at)
        .map(|stamp| {
            chrono::Utc::now()
                .signed_duration_since(stamp.with_timezone(&chrono::Utc))
                .num_milliseconds()
                <= RUNNER_FRESHNESS_MS
        })
        .unwrap_or(false)
}

pub fn job_status_message(job: &JobRecord) -> String {
    let publish = as_publish_result(&job.result);
    let command_label = job
        .args
        .get("commandLabel")
        .and_then(serde_json::Value::as_str)
        .map(str::to_owned)
        .unwrap_or_else(|| format!("{} {}", job.project, job.action));
    let mut lines = vec![
        format!("Job `{}`", job.id),
        format!("- state: `{}`", job.state.as_str()),
        format!("- command: `{command_label}`"),
        format!("- created: `{}`", job.created_at),
    ];
    if let Some(runner_id) = &job.runner_id {
        lines.push(format!("- runner: `{runner_id}`"));
    }
    if let Some(claimed_at) = &job.claimed_at {
        lines.push(format!("- claimed: `{claimed_at}`"));
    }
    if let Some(finished_at) = &job.finished_at {
        lines.push(format!("- finished: `{finished_at}`"));
    }
    if let Some(summary) = &job.summary {
        lines.push(format!("- summary: {summary}"));
    }
    if let Some(exit_code) = job.exit_code {
        lines.push(format!("- exit code: `{exit_code}`"));
    }
    if let Some(publish) = publish {
        lines.push(format!("- release: `{}`", publish.release_id));
        lines.push(format!("- archive: {}", publish.public_url));
        lines.push(format!("- current: {}", publish.current_url));
        if let Some(manifest_path) = publish.manifest_path {
            lines.push(format!("- manifest: `{manifest_path}`"));
        }
        if let Some(site_path) = publish.site_path {
            lines.push(format!("- site path: `{site_path}`"));
        }
    }
    lines.join("\n")
}

pub fn commands_status_message() -> String {
    let mut lines = vec!["Enabled command surfaces:".to_owned()];
    for surface in list_surfaces() {
        lines.push(format!(
            "- `{}` caps=`{}`",
            surface.synopsis,
            surface.required_capabilities.join(", ")
        ));
        lines.push(format!("  {}", surface.description));
    }
    lines.join("\n")
}

pub async fn status_job_message(store: &dyn DispatchStore, job_id: &str) -> anyhow::Result<String> {
    let Some(job) = store.get_job(job_id).await? else {
        return Ok(format!("No job found for `{job_id}`."));
    };
    Ok(job_status_message(&job))
}

pub async fn status_health_message(store: &dyn DispatchStore) -> anyhow::Result<String> {
    let snapshot = store.health_snapshot().await?;
    let runners = store.list_runners().await?;
    let fresh_runners = runners
        .into_iter()
        .filter(|runner| is_runner_fresh(&runner.last_seen_at))
        .collect::<Vec<_>>();
    let runner_summary = if fresh_runners.is_empty() {
        "none".to_owned()
    } else {
        fresh_runners
            .into_iter()
            .map(|runner| match runner.current_job_id {
                Some(job_id) => format!("{} ({job_id})", runner.display_name),
                None => runner.display_name,
            })
            .collect::<Vec<_>>()
            .join(", ")
    };
    Ok([
        "Specter dispatch is reachable.".to_owned(),
        format!("- queued jobs: `{}`", snapshot.queued_jobs),
        format!("- active jobs: `{}`", snapshot.active_jobs),
        format!("- online runners: `{}`", snapshot.online_runners),
        format!("- runner names: `{runner_summary}`"),
    ]
    .join("\n"))
}

pub async fn status_queue_message(store: &dyn DispatchStore) -> anyhow::Result<String> {
    let snapshot = store.health_snapshot().await?;
    let jobs = store
        .list_recent_jobs(
            10,
            &[
                JobState::Queued,
                JobState::Claimed,
                JobState::CancelRequested,
            ],
        )
        .await?;
    let mut lines = vec![
        "Queue status".to_owned(),
        format!("- queued jobs: `{}`", snapshot.queued_jobs),
        format!("- active jobs: `{}`", snapshot.active_jobs),
        format!("- online runners: `{}`", snapshot.online_runners),
    ];
    if jobs.is_empty() {
        lines.push("- recent jobs: none".to_owned());
        return Ok(lines.join("\n"));
    }
    lines.push(String::new());
    lines.push("Recent queued/active jobs:".to_owned());
    lines.extend(jobs.into_iter().map(|job| {
        format!(
            "- `{}` `{}` `{} {}`",
            job.id,
            job.state.as_str(),
            job.project,
            job.action
        )
    }));
    Ok(lines.join("\n"))
}

pub async fn status_runners_message(store: &dyn DispatchStore) -> anyhow::Result<String> {
    let runners = store.list_runners().await?;
    if runners.is_empty() {
        return Ok("No runners are registered.".to_owned());
    }
    let mut lines = vec!["Registered runners:".to_owned()];
    for runner in runners {
        let freshness = if is_runner_fresh(&runner.last_seen_at) {
            "fresh"
        } else {
            "stale"
        };
        lines.push(format!(
            "- `{}` id=`{}` status=`{}/{freshness}` last_seen=`{}`",
            runner.display_name, runner.id, runner.status, runner.last_seen_at
        ));
        if let Some(current_job_id) = runner.current_job_id {
            lines.push(format!("  current job: `{current_job_id}`"));
        }
        lines.push(format!(
            "  capabilities: `{}`",
            runner.capabilities.join(", ")
        ));
    }
    Ok(lines.join("\n"))
}

pub async fn health_response(store: &dyn DispatchStore) -> anyhow::Result<DispatchHealthResponse> {
    let snapshot = store.health_snapshot().await?;
    let runners = store.list_runners().await?;
    let recent_jobs = store.list_recent_jobs(10, &[]).await?;
    Ok(DispatchHealthResponse {
        ok: true,
        snapshot: DispatchHealthSnapshot {
            queued_jobs: snapshot.queued_jobs,
            active_jobs: snapshot.active_jobs,
            online_runners: snapshot.online_runners,
            runners: runners
                .into_iter()
                .filter(|runner| is_runner_fresh(&runner.last_seen_at))
                .map(|runner| HealthRunnerView {
                    display_name: runner.display_name,
                    last_seen_at: runner.last_seen_at,
                    current_job_id: runner.current_job_id,
                    capabilities: runner.capabilities,
                })
                .collect(),
            recent_jobs: recent_jobs
                .into_iter()
                .map(|job| HealthRecentJobView {
                    id: job.id,
                    command: job
                        .args
                        .get("commandLabel")
                        .and_then(serde_json::Value::as_str)
                        .map(str::to_owned)
                        .unwrap_or_else(|| format!("{} {}", job.project, job.action)),
                    state: job.state.as_str().to_owned(),
                    created_at: job.created_at,
                })
                .collect(),
        },
    })
}
