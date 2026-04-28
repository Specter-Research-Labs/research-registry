use crate::dispatch::types::{JobRecord, JsonMap, PublishArtifact, PublishResult};
use serde_json::Value;

fn as_string(value: Option<&Value>) -> Option<String> {
    value
        .and_then(Value::as_str)
        .map(str::trim)
        .and_then(|value| {
            if value.is_empty() {
                None
            } else {
                Some(value.to_owned())
            }
        })
}

fn as_artifact(value: &Value) -> Option<PublishArtifact> {
    let record = value.as_object()?;
    let label = as_string(record.get("label"))?;
    Some(PublishArtifact {
        label,
        url: as_string(record.get("url")),
        path: as_string(record.get("path")),
    })
}

pub fn as_publish_result(result: &JsonMap) -> Option<PublishResult> {
    let release_id = as_string(result.get("releaseId"))?;
    let surface = as_string(result.get("surface"))?;
    let public_url = as_string(result.get("publicUrl"))?;
    let current_url = as_string(result.get("currentUrl"))?;
    let artifacts = result
        .get("artifacts")
        .and_then(Value::as_array)
        .map(|items| items.iter().filter_map(as_artifact).collect())
        .unwrap_or_default();
    Some(PublishResult {
        release_id,
        surface,
        public_url,
        current_url,
        artifacts,
        manifest_path: as_string(result.get("manifestPath")),
        site_path: as_string(result.get("sitePath")),
        provenance: as_string(result.get("provenance")),
    })
}

pub fn duration_seconds(job: &JobRecord) -> Option<f64> {
    if let Some(seconds) = job.result.get("durationSeconds").and_then(Value::as_f64) {
        return Some(seconds);
    }
    let claimed = job.claimed_at.as_deref()?;
    let finished = job.finished_at.as_deref()?;
    let claimed = chrono::DateTime::parse_from_rfc3339(claimed).ok()?;
    let finished = chrono::DateTime::parse_from_rfc3339(finished).ok()?;
    let millis = finished.signed_duration_since(claimed).num_milliseconds();
    Some((millis.max(0) as f64) / 1000.0)
}

pub fn duration_label(job: &JobRecord) -> Option<String> {
    duration_seconds(job).map(|seconds| format!("{seconds:.1}s"))
}
