use anyhow::{bail, Result};
use serde_json::json;

use crate::dispatch::types::{JobKind, JobSpec, SurfaceDefinition};

const SITE_PUBLISH_CAPABILITIES: &[&str] = &["cargo", "pandoc", "typst", "rsync", "ssh", "git"];

pub fn list_surfaces() -> Vec<SurfaceDefinition> {
    vec![SurfaceDefinition {
        command: "publish".to_owned(),
        project: "site".to_owned(),
        action: "publish".to_owned(),
        synopsis: "publish site [--release-id <id>]".to_owned(),
        description: "Build the canonical site, publish the current surface, and archive the immutable release bundle.".to_owned(),
        required_capabilities: SITE_PUBLISH_CAPABILITIES.iter().map(|value| (*value).to_owned()).collect(),
    }]
}

pub fn resolve_surface(
    command: &str,
    project: &str,
    action: Option<&str>,
    raw_args: &[String],
) -> Result<JobSpec> {
    if command != "publish" || project != "site" {
        bail!("Only `publish site` is enabled in this dispatch build.");
    }
    if let Some(action) = action {
        if action != "publish" {
            bail!("`publish site` does not accept a secondary action.");
        }
    }
    let (argv, normalized) = parse_site_publish_args(raw_args)?;
    let mut args = serde_json::Map::new();
    args.insert("commandLabel".to_owned(), json!(command_label(raw_args)));
    args.insert("normalized".to_owned(), normalized);
    Ok(JobSpec {
        kind: JobKind::Exec,
        project: "site".to_owned(),
        action: "publish".to_owned(),
        description: "Publish the Specter Labs site.".to_owned(),
        cwd: ".".to_owned(),
        argv: [
            vec![
                "cargo".to_owned(),
                "run".to_owned(),
                "--release".to_owned(),
                "--manifest-path".to_owned(),
                "ops/spctr/Cargo.toml".to_owned(),
                "--".to_owned(),
                "site".to_owned(),
                "publish".to_owned(),
            ],
            argv,
        ]
        .concat(),
        required_capabilities: SITE_PUBLISH_CAPABILITIES
            .iter()
            .map(|value| (*value).to_owned())
            .collect(),
        args,
    })
}

fn command_label(raw_args: &[String]) -> String {
    let mut parts = vec!["publish".to_owned(), "site".to_owned()];
    parts.extend(raw_args.iter().cloned());
    parts.join(" ")
}

fn parse_site_publish_args(raw_args: &[String]) -> Result<(Vec<String>, serde_json::Value)> {
    let mut release_id: Option<String> = None;
    let mut index = 0;
    while index < raw_args.len() {
        let token = &raw_args[index];
        if token == "--release-id" {
            let value = raw_args
                .get(index + 1)
                .cloned()
                .ok_or_else(|| anyhow::anyhow!("option `--release-id` requires a value"))?;
            release_id = Some(assign_release_id(release_id.take(), value)?);
            index += 2;
            continue;
        }
        if let Some(value) = token.strip_prefix("--release-id=") {
            release_id = Some(assign_release_id(release_id.take(), value.to_owned())?);
            index += 1;
            continue;
        }
        bail!("unsupported option `{token}`; only `--release-id <id>` is supported for `publish site`");
    }
    let argv = match release_id.as_deref() {
        None | Some("auto") => Vec::new(),
        Some(value) => vec!["--release-id".to_owned(), value.to_owned()],
    };
    let normalized = release_id.map_or_else(|| json!({}), |value| json!({ "releaseId": value }));
    Ok((argv, normalized))
}

fn assign_release_id(current: Option<String>, value: String) -> Result<String> {
    if current.is_some() {
        bail!("option `--release-id` may only be provided once");
    }
    let trimmed = value.trim();
    if trimmed.is_empty() {
        bail!("option `--release-id` requires a value");
    }
    Ok(trimmed.to_owned())
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn resolves_publish_site_without_explicit_action() {
        let job = resolve_surface("publish", "site", None, &[]).unwrap();
        assert_eq!(job.project, "site");
        assert_eq!(job.action, "publish");
        assert_eq!(
            job.required_capabilities,
            vec![
                "cargo".to_owned(),
                "pandoc".to_owned(),
                "typst".to_owned(),
                "rsync".to_owned(),
                "ssh".to_owned(),
                "git".to_owned(),
            ]
        );
        assert_eq!(
            job.argv,
            vec![
                "cargo".to_owned(),
                "run".to_owned(),
                "--release".to_owned(),
                "--manifest-path".to_owned(),
                "ops/spctr/Cargo.toml".to_owned(),
                "--".to_owned(),
                "site".to_owned(),
                "publish".to_owned(),
            ]
        );
    }

    #[test]
    fn passes_through_explicit_release_ids() {
        let explicit = resolve_surface(
            "publish",
            "site",
            Some("publish"),
            &["--release-id".to_owned(), "2026-04-02-demo".to_owned()],
        )
        .unwrap();
        assert_eq!(
            explicit.argv,
            vec![
                "cargo".to_owned(),
                "run".to_owned(),
                "--release".to_owned(),
                "--manifest-path".to_owned(),
                "ops/spctr/Cargo.toml".to_owned(),
                "--".to_owned(),
                "site".to_owned(),
                "publish".to_owned(),
                "--release-id".to_owned(),
                "2026-04-02-demo".to_owned(),
            ]
        );
        assert_eq!(
            explicit.args.get("normalized").unwrap(),
            &json!({ "releaseId": "2026-04-02-demo" })
        );

        let auto = resolve_surface(
            "publish",
            "site",
            None,
            &["--release-id".to_owned(), "auto".to_owned()],
        )
        .unwrap();
        assert_eq!(
            auto.argv,
            vec![
                "cargo".to_owned(),
                "run".to_owned(),
                "--release".to_owned(),
                "--manifest-path".to_owned(),
                "ops/spctr/Cargo.toml".to_owned(),
                "--".to_owned(),
                "site".to_owned(),
                "publish".to_owned(),
            ]
        );
        assert_eq!(
            auto.args.get("normalized").unwrap(),
            &json!({ "releaseId": "auto" })
        );
    }

    #[test]
    fn rejects_unsupported_surfaces() {
        let error = resolve_surface("publish", "lenia-swarm", Some("compendium"), &[]).unwrap_err();
        assert!(error.to_string().contains("Only `publish site` is enabled"));
        let error = resolve_surface("run", "site", Some("build"), &[]).unwrap_err();
        assert!(error.to_string().contains("Only `publish site` is enabled"));
    }
}
