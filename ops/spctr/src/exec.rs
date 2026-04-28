use crate::manifest::{self, ExecActionConfig, ProjectManifest};
use crate::release;
use anyhow::{Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use chrono::Utc;
use globset::{Glob, GlobSetBuilder};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::process::{Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};

const MAX_EXEC_ERROR_BYTES: usize = 16 * 1024;

#[derive(Clone, Debug, Serialize)]
pub struct ExecOutputPlan {
    pub name: String,
    pub path: String,
    pub kind: String,
    pub required: bool,
    pub surface: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecRuntimePlan {
    pub platforms: Vec<String>,
    pub requires: Vec<String>,
    pub network: Option<String>,
    pub cache_paths: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecPlan {
    pub project: String,
    pub kind: String,
    pub action: String,
    pub description: Option<String>,
    pub project_root: String,
    pub workdir: String,
    pub commands: Vec<Vec<String>>,
    pub env: BTreeMap<String, String>,
    pub timeout_sec: Option<u64>,
    pub network: Option<String>,
    pub requires: Vec<String>,
    pub expected_outputs: Vec<ExecOutputPlan>,
    pub runtime: Option<ExecRuntimePlan>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecValidatedOutput {
    pub name: String,
    pub path: String,
    pub kind: String,
    pub required: bool,
    pub surface: Option<String>,
    pub matches: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecValidationReport {
    pub project: String,
    pub kind: String,
    pub action: String,
    pub ok: bool,
    pub outputs: Vec<ExecValidatedOutput>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ExecRunReport {
    pub project: String,
    pub kind: String,
    pub action: String,
    pub ok: bool,
    pub exit_code: Option<i32>,
    pub timed_out: bool,
    pub error: Option<String>,
    pub card_path: Option<String>,
    pub outputs: Vec<ExecValidatedOutput>,
}

#[derive(Clone, Debug, Serialize)]
struct ExecEvidenceCard {
    version: u32,
    project: String,
    kind: String,
    action: String,
    description: Option<String>,
    status: String,
    started_at: String,
    finished_at: String,
    manifest: ExecManifestRecord,
    git: ExecGitContext,
    runtime: ExecRuntimeRecord,
    requires: Vec<String>,
    commands: Vec<Vec<String>>,
    inputs: Vec<ExecEvidenceInput>,
    outputs: Vec<ExecEvidenceOutput>,
    error: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
struct ExecManifestRecord {
    path: String,
    project_root: String,
    title: String,
    series: Option<String>,
    release_stage: String,
    docs_root: Option<String>,
    docs_landing: Option<String>,
    release_surfaces: Vec<String>,
    publishable_surfaces: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
struct ExecGitContext {
    commit: Option<String>,
    branch: Option<String>,
    dirty: Option<bool>,
}

#[derive(Clone, Debug, Serialize)]
struct ExecRuntimeRecord {
    workdir: String,
    platform: String,
    arch: String,
    hostname: Option<String>,
    network: Option<String>,
    exit_code: Option<i32>,
    timed_out: bool,
}

#[derive(Clone, Debug, Serialize)]
struct ExecEvidenceInput {
    kind: String,
    path: String,
    sha256: String,
    size_bytes: u64,
}

#[derive(Clone, Debug, Serialize)]
struct ExecEvidenceOutput {
    name: String,
    path: String,
    kind: String,
    required: bool,
    surface: Option<String>,
    matches: Vec<ExecEvidenceMatch>,
}

#[derive(Clone, Debug, Serialize)]
struct ExecEvidenceMatch {
    path: String,
    sha256: String,
    size_bytes: u64,
}

#[derive(Clone, Debug)]
struct ExecCommandOutcome {
    exit_code: Option<i32>,
    timed_out: bool,
    error: Option<String>,
}

pub fn plan(repo_root: &Utf8Path, project: Option<&str>, action: &str) -> Result<ExecPlan> {
    let manifest = lookup_project(repo_root, project)?;
    build_plan(repo_root, &manifest, action)
}

pub fn validate(
    repo_root: &Utf8Path,
    project: Option<&str>,
    action: &str,
) -> Result<ExecValidationReport> {
    let manifest = lookup_project(repo_root, project)?;
    validate_action(repo_root, &manifest, action)
}

pub fn run(repo_root: &Utf8Path, project: Option<&str>, action: &str) -> Result<ExecRunReport> {
    let manifest = lookup_project(repo_root, project)?;
    run_action(repo_root, &manifest, action)
}

pub fn lookup_project(repo_root: &Utf8Path, project: Option<&str>) -> Result<ProjectManifest> {
    match project {
        Some(slug) => release::lookup_project(repo_root, slug),
        None => manifest::discover_manifest(None),
    }
}

pub fn build_plan(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    action_name: &str,
) -> Result<ExecPlan> {
    let spctr = manifest
        .spctr
        .as_ref()
        .with_context(|| format!("{}: missing [spctr] configuration", manifest.path))?;
    let action = spctr.exec.get(action_name).with_context(|| {
        format!(
            "{}: unknown spctr exec action '{}'",
            manifest.path, action_name
        )
    })?;
    let project_root = repo_relative(repo_root, &manifest.root, "project root")?;
    let workdir_path = action
        .workdir
        .as_deref()
        .map(|workdir| manifest.root.join(workdir))
        .unwrap_or_else(|| manifest.root.clone());
    let workdir = repo_relative(repo_root, &workdir_path, "exec workdir")?;
    let requires = resolved_requires(spctr, action);
    let expected_outputs = resolve_outputs(spctr, action, manifest)?;
    let runtime = spctr.runtime.as_ref().map(|runtime| ExecRuntimePlan {
        platforms: runtime.platforms.clone(),
        requires: runtime.requires.clone(),
        network: runtime.network.map(|policy| policy.as_str().to_owned()),
        cache_paths: runtime.cache_paths.clone(),
    });
    let mut env = action.env.clone();
    if let Ok(bin) = env::current_exe() {
        env.entry("SPCTR_BIN".to_owned())
            .or_insert_with(|| bin.to_string_lossy().into_owned());
    }

    Ok(ExecPlan {
        project: manifest.slug.clone(),
        kind: manifest.kind.clone(),
        action: action_name.to_owned(),
        description: action.description.clone(),
        project_root,
        workdir,
        commands: action_commands(action),
        env,
        timeout_sec: action.timeout_sec,
        network: action
            .network
            .or_else(|| spctr.runtime.as_ref().and_then(|runtime| runtime.network))
            .map(|policy| policy.as_str().to_owned()),
        requires,
        expected_outputs,
        runtime,
    })
}

pub(crate) fn validate_action(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    action_name: &str,
) -> Result<ExecValidationReport> {
    let plan = build_plan(repo_root, manifest, action_name)?;
    let outputs = validated_outputs_from_plan(manifest, &plan)?;
    let ok = outputs
        .iter()
        .all(|output| !output.required || !output.matches.is_empty());
    Ok(ExecValidationReport {
        project: plan.project,
        kind: plan.kind,
        action: plan.action,
        ok,
        outputs,
    })
}

pub(crate) fn run_action(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    action_name: &str,
) -> Result<ExecRunReport> {
    let plan = build_plan(repo_root, manifest, action_name)?;
    let started_at = Utc::now();
    let outcome = execute_plan(repo_root, &plan)?;
    let outputs = validated_outputs_from_plan(manifest, &plan)?;
    let outputs_ok = outputs
        .iter()
        .all(|output| !output.required || !output.matches.is_empty());
    let ok = outcome.error.is_none() && !outcome.timed_out && outputs_ok;
    let finished_at = Utc::now();
    let card_path = write_evidence_card(
        repo_root,
        manifest,
        &plan,
        &outputs,
        &outcome,
        started_at.to_rfc3339(),
        finished_at.to_rfc3339(),
    )?;
    Ok(ExecRunReport {
        project: plan.project,
        kind: plan.kind,
        action: plan.action,
        ok,
        exit_code: outcome.exit_code,
        timed_out: outcome.timed_out,
        error: outcome.error,
        card_path,
        outputs,
    })
}

fn action_commands(action: &ExecActionConfig) -> Vec<Vec<String>> {
    if let Some(command) = &action.command {
        vec![command.clone()]
    } else {
        action.commands.clone().unwrap_or_default()
    }
}

fn resolved_requires(spctr: &manifest::SpctrConfig, action: &ExecActionConfig) -> Vec<String> {
    let mut requires = Vec::new();
    for requirement in spctr
        .runtime
        .as_ref()
        .into_iter()
        .flat_map(|runtime| runtime.requires.iter())
        .chain(action.requires.iter())
    {
        if !requires.iter().any(|existing| existing == requirement) {
            requires.push(requirement.clone());
        }
    }
    requires
}

fn resolve_outputs(
    spctr: &manifest::SpctrConfig,
    action: &ExecActionConfig,
    manifest: &ProjectManifest,
) -> Result<Vec<ExecOutputPlan>> {
    if action.expected_outputs.is_empty() {
        return Ok(Vec::new());
    }
    if spctr.expected_outputs.is_empty() {
        return Err(anyhow::anyhow!(
            "{}: spctr exec action requires [[spctr.expected_outputs]] declarations",
            manifest.path
        ));
    }
    let evidence = spctr.evidence.as_ref().with_context(|| {
        format!(
            "{}: spctr exec action requires [spctr.evidence] declarations",
            manifest.path
        )
    })?;
    let _ = evidence;
    action
        .expected_outputs
        .iter()
        .map(|name| {
            let output = spctr
                .expected_outputs
                .iter()
                .find(|output| output.name == *name)
                .with_context(|| {
                    format!(
                        "{}: spctr exec action references unknown expected output '{}'",
                        manifest.path, name
                    )
                })?;
            Ok(ExecOutputPlan {
                name: output.name.clone(),
                path: output.path.clone(),
                kind: output.kind.clone(),
                required: output.required,
                surface: output.surface.clone(),
            })
        })
        .collect()
}

fn validated_outputs_from_plan(
    manifest: &ProjectManifest,
    plan: &ExecPlan,
) -> Result<Vec<ExecValidatedOutput>> {
    plan.expected_outputs
        .iter()
        .map(|output| {
            let matches = resolve_output_matches(&manifest.root, &output.path)?;
            Ok(ExecValidatedOutput {
                name: output.name.clone(),
                path: output.path.clone(),
                kind: output.kind.clone(),
                required: output.required,
                surface: output.surface.clone(),
                matches,
            })
        })
        .collect()
}

fn execute_plan(repo_root: &Utf8Path, plan: &ExecPlan) -> Result<ExecCommandOutcome> {
    let workdir = repo_root.join(&plan.workdir);
    let mut last_outcome = ExecCommandOutcome {
        exit_code: Some(0),
        timed_out: false,
        error: None,
    };
    for command in &plan.commands {
        let outcome = run_command(command, &workdir, &plan.env, plan.timeout_sec)?;
        let is_failure = outcome.error.is_some() || outcome.timed_out;
        last_outcome = outcome;
        if is_failure {
            break;
        }
    }
    Ok(last_outcome)
}

fn run_command(
    argv: &[String],
    workdir: &Utf8Path,
    envs: &BTreeMap<String, String>,
    timeout_sec: Option<u64>,
) -> Result<ExecCommandOutcome> {
    let mut command = Command::new(
        argv.first()
            .ok_or_else(|| anyhow::anyhow!("exec command must contain a program name"))?,
    );
    let mut stdout_file = tempfile::tempfile().context("failed to create exec stdout capture")?;
    let mut stderr_file = tempfile::tempfile().context("failed to create exec stderr capture")?;
    command
        .args(&argv[1..])
        .current_dir(workdir)
        .envs(envs)
        .stdin(Stdio::null())
        .stdout(Stdio::from(
            stdout_file
                .try_clone()
                .context("failed to prepare exec stdout capture")?,
        ))
        .stderr(Stdio::from(
            stderr_file
                .try_clone()
                .context("failed to prepare exec stderr capture")?,
        ));
    let child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            return Ok(ExecCommandOutcome {
                exit_code: None,
                timed_out: false,
                error: Some(format!("failed to spawn '{}': {error}", argv[0])),
            });
        }
    };
    let (status, timed_out) = wait_for_status(child, timeout_sec)?;
    let stdout = read_capture(&mut stdout_file).context("failed to read exec stdout capture")?;
    let stderr = read_capture(&mut stderr_file).context("failed to read exec stderr capture")?;
    let exit_code = status.code();
    let error = if timed_out {
        Some(format!(
            "command timed out after {}s: {}",
            timeout_sec.unwrap_or_default(),
            argv.join(" ")
        ))
    } else if status.success() {
        None
    } else {
        let diagnostics = command_diagnostics(&stdout, &stderr);
        Some(if diagnostics.is_empty() {
            match exit_code {
                Some(code) => format!("command exited with status {code}: {}", argv.join(" ")),
                None => format!("command terminated without exit code: {}", argv.join(" ")),
            }
        } else {
            diagnostics
        })
    };
    Ok(ExecCommandOutcome {
        exit_code,
        timed_out,
        error,
    })
}

fn wait_for_status(
    mut child: std::process::Child,
    timeout_sec: Option<u64>,
) -> Result<(ExitStatus, bool)> {
    let Some(timeout_sec) = timeout_sec else {
        let status = child.wait().context("failed to wait for exec command")?;
        return Ok((status, false));
    };
    let timeout = Duration::from_secs(timeout_sec);
    let start = Instant::now();
    loop {
        if child
            .try_wait()
            .context("failed to poll exec command status")?
            .is_some()
        {
            let status = child
                .wait()
                .context("failed to collect exec command status")?;
            return Ok((status, false));
        }
        if start.elapsed() >= timeout {
            child
                .kill()
                .context("failed to kill timed out exec command")?;
            let status = child
                .wait()
                .context("failed to collect timed out exec command status")?;
            return Ok((status, true));
        }
        thread::sleep(Duration::from_millis(50));
    }
}

fn read_capture(file: &mut File) -> Result<Vec<u8>> {
    file.seek(SeekFrom::Start(0))?;
    let mut bytes = Vec::new();
    file.read_to_end(&mut bytes)?;
    Ok(bytes)
}

fn command_diagnostics(stdout: &[u8], stderr: &[u8]) -> String {
    let stdout = String::from_utf8_lossy(stdout).trim().to_owned();
    let stderr = String::from_utf8_lossy(stderr).trim().to_owned();
    match (stderr.is_empty(), stdout.is_empty()) {
        (true, true) => String::new(),
        (true, false) => truncate_diagnostics(&stdout),
        (false, true) => truncate_diagnostics(&stderr),
        (false, false) => {
            format!(
                "{}\n{}",
                truncate_diagnostics(&stderr),
                truncate_diagnostics(&stdout)
            )
        }
    }
}

fn truncate_diagnostics(text: &str) -> String {
    if text.len() <= MAX_EXEC_ERROR_BYTES {
        return text.to_owned();
    }
    let mut start = text.len() - MAX_EXEC_ERROR_BYTES;
    while !text.is_char_boundary(start) {
        start += 1;
    }
    format!(
        "[truncated {} bytes of exec diagnostics]\n{}",
        start,
        &text[start..]
    )
}

fn write_evidence_card(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    plan: &ExecPlan,
    outputs: &[ExecValidatedOutput],
    outcome: &ExecCommandOutcome,
    started_at: String,
    finished_at: String,
) -> Result<Option<String>> {
    if manifest
        .spctr
        .as_ref()
        .and_then(|spctr| spctr.evidence.as_ref())
        .is_none()
    {
        return Ok(None);
    }
    let Some(absolute_card_path) = configured_evidence_card_path(manifest) else {
        return Ok(None);
    };
    if let Some(parent) = absolute_card_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create evidence dir {parent}"))?;
    }
    let status = if outcome.timed_out {
        "timed_out"
    } else if outcome.error.is_none()
        && outputs
            .iter()
            .all(|output| !output.required || !output.matches.is_empty())
    {
        "ok"
    } else {
        "failed"
    };
    let payload = ExecEvidenceCard {
        version: 2,
        project: plan.project.clone(),
        kind: plan.kind.clone(),
        action: plan.action.clone(),
        description: plan.description.clone(),
        status: status.to_owned(),
        started_at,
        finished_at,
        manifest: manifest_record(repo_root, manifest)?,
        git: resolve_git_context(repo_root),
        runtime: ExecRuntimeRecord {
            workdir: plan.workdir.clone(),
            platform: env::consts::OS.to_owned(),
            arch: env::consts::ARCH.to_owned(),
            hostname: resolve_hostname(),
            network: plan.network.clone(),
            exit_code: outcome.exit_code,
            timed_out: outcome.timed_out,
        },
        requires: plan.requires.clone(),
        commands: plan.commands.clone(),
        inputs: evidence_inputs(repo_root, manifest)?,
        outputs: evidence_outputs(manifest, outputs)?,
        error: outcome.error.clone(),
    };
    let rendered = serde_json::to_string_pretty(&payload)? + "\n";
    fs::write(&absolute_card_path, &rendered)
        .with_context(|| format!("failed to write evidence card {}", absolute_card_path))?;
    if let Some(action_card_path) =
        action_evidence_card_path(manifest, &plan.action).filter(|path| path != &absolute_card_path)
    {
        fs::write(&action_card_path, &rendered).with_context(|| {
            format!("failed to write action evidence card {}", action_card_path)
        })?;
    }
    Ok(Some(repo_relative(
        repo_root,
        &absolute_card_path,
        "evidence card path",
    )?))
}

pub(crate) fn configured_evidence_card_path(manifest: &ProjectManifest) -> Option<Utf8PathBuf> {
    manifest
        .spctr
        .as_ref()
        .and_then(|spctr| spctr.evidence.as_ref())
        .and_then(|evidence| evidence.card_path.as_ref())
        .map(|card_path| manifest.root.join(card_path))
}

pub(crate) fn action_evidence_card_path(
    manifest: &ProjectManifest,
    action: &str,
) -> Option<Utf8PathBuf> {
    let configured = configured_evidence_card_path(manifest)?;
    let parent = configured.parent()?;
    Some(parent.join(action_evidence_file_name(&configured, action)))
}

fn action_evidence_file_name(configured: &Utf8Path, action: &str) -> String {
    let sanitized_action = sanitize_action_name(action);
    let stem = configured.file_stem().unwrap_or("evidence");
    match configured.extension() {
        Some(extension) if stem == "latest" => format!("{sanitized_action}.{extension}"),
        Some(extension) => format!("{stem}-{sanitized_action}.{extension}"),
        None if stem == "latest" => sanitized_action,
        None => format!("{stem}-{sanitized_action}"),
    }
}

fn sanitize_action_name(action: &str) -> String {
    let sanitized = action
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>();
    if sanitized.is_empty() {
        "action".to_owned()
    } else {
        sanitized
    }
}

fn manifest_record(repo_root: &Utf8Path, manifest: &ProjectManifest) -> Result<ExecManifestRecord> {
    let docs_root = manifest
        .spctr
        .as_ref()
        .and_then(|spctr| spctr.docs.as_ref())
        .map(|docs| docs.root.clone());
    let docs_landing = manifest
        .spctr
        .as_ref()
        .and_then(|spctr| spctr.docs.as_ref())
        .and_then(|docs| docs.landing.clone());
    let release_surfaces = manifest
        .release
        .surfaces
        .iter()
        .map(|surface| surface.name.clone())
        .collect::<Vec<_>>();
    let publishable_surfaces = manifest
        .release
        .surfaces
        .iter()
        .filter(|surface| surface.publish)
        .map(|surface| surface.name.clone())
        .collect::<Vec<_>>();
    Ok(ExecManifestRecord {
        path: repo_relative(repo_root, &manifest.path, "manifest path")?,
        project_root: repo_relative(repo_root, &manifest.root, "project root")?,
        title: manifest.title.clone(),
        series: manifest.series.clone(),
        release_stage: manifest.release.stage.as_str().to_owned(),
        docs_root,
        docs_landing,
        release_surfaces,
        publishable_surfaces,
    })
}

fn evidence_inputs(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
) -> Result<Vec<ExecEvidenceInput>> {
    let mut inputs = vec![build_evidence_input(
        repo_root,
        &manifest.path,
        "manifest",
        "manifest path",
    )?];
    for lockfile in discover_lockfiles(&manifest.root)? {
        let absolute = manifest.root.join(&lockfile);
        inputs.push(build_evidence_input(
            repo_root,
            &absolute,
            "lockfile",
            "lockfile path",
        )?);
    }
    Ok(inputs)
}

fn build_evidence_input(
    repo_root: &Utf8Path,
    absolute: &Utf8Path,
    kind: &str,
    label: &str,
) -> Result<ExecEvidenceInput> {
    let (sha256, size_bytes) = hash_file_info(absolute)?;
    Ok(ExecEvidenceInput {
        kind: kind.to_owned(),
        path: repo_relative(repo_root, absolute, label)?,
        sha256,
        size_bytes,
    })
}

fn discover_lockfiles(project_root: &Utf8Path) -> Result<Vec<String>> {
    let mut files = Vec::new();
    collect_lockfiles(project_root, project_root, &mut files)?;
    files.sort();
    Ok(files)
}

fn collect_lockfiles(
    project_root: &Utf8Path,
    current: &Utf8Path,
    files: &mut Vec<String>,
) -> Result<()> {
    for entry in fs::read_dir(current).with_context(|| format!("failed to read {current}"))? {
        let entry = entry.with_context(|| format!("failed to read entry in {current}"))?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow::anyhow!("lockfile path was not UTF-8"))?;
        let file_name = path.file_name().unwrap_or_default();
        if path.is_dir() {
            if should_skip_lockfile_dir(file_name) {
                continue;
            }
            collect_lockfiles(project_root, &path, files)?;
        } else if path.is_file() && is_lockfile_name(file_name) {
            files.push(
                path.strip_prefix(project_root)
                    .context("lockfile path must stay inside project root")?
                    .as_str()
                    .to_owned(),
            );
        }
    }
    Ok(())
}

fn is_lockfile_name(name: &str) -> bool {
    matches!(
        name,
        "uv.lock"
            | "Cargo.lock"
            | "flake.lock"
            | "poetry.lock"
            | "Pipfile.lock"
            | "pixi.lock"
            | "package-lock.json"
            | "pnpm-lock.yaml"
            | "yarn.lock"
            | "bun.lock"
            | "bun.lockb"
            | "Package.resolved"
    )
}

fn should_skip_lockfile_dir(name: &str) -> bool {
    matches!(
        name,
        ".git"
            | ".jj"
            | ".venv"
            | "venv"
            | "node_modules"
            | "target"
            | "dist"
            | "build"
            | "artifacts"
            | "DerivedData"
            | ".pytest_cache"
            | ".ruff_cache"
    )
}

fn evidence_outputs(
    manifest: &ProjectManifest,
    outputs: &[ExecValidatedOutput],
) -> Result<Vec<ExecEvidenceOutput>> {
    outputs
        .iter()
        .map(|output| {
            let matches = output
                .matches
                .iter()
                .map(|matched| {
                    let absolute = manifest.root.join(matched);
                    let (sha256, size_bytes) = hash_file_info(&absolute)?;
                    Ok(ExecEvidenceMatch {
                        path: matched.clone(),
                        sha256,
                        size_bytes,
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            Ok(ExecEvidenceOutput {
                name: output.name.clone(),
                path: output.path.clone(),
                kind: output.kind.clone(),
                required: output.required,
                surface: output.surface.clone(),
                matches,
            })
        })
        .collect()
}

fn hash_file_info(path: &Utf8Path) -> Result<(String, u64)> {
    let bytes = fs::read(path).with_context(|| format!("failed to read evidence file {}", path))?;
    let size_bytes = u64::try_from(bytes.len())
        .map_err(|_| anyhow::anyhow!("evidence file too large: {}", path))?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok((format!("{:x}", hasher.finalize()), size_bytes))
}

fn resolve_git_context(repo_root: &Utf8Path) -> ExecGitContext {
    ExecGitContext {
        commit: command_text(repo_root, &["git", "rev-parse", "HEAD"]),
        branch: command_text(repo_root, &["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        dirty: command_stdout(
            repo_root,
            &["git", "status", "--short", "--untracked-files=no"],
        )
        .map(|output| !output.is_empty()),
    }
}

fn resolve_hostname() -> Option<String> {
    env::var("HOSTNAME")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .or_else(|| command_text(Utf8Path::new("."), &["hostname"]))
}

fn command_text(cwd: &Utf8Path, argv: &[&str]) -> Option<String> {
    command_stdout(cwd, argv).filter(|text| !text.is_empty())
}

fn command_stdout(cwd: &Utf8Path, argv: &[&str]) -> Option<String> {
    let (program, args) = argv.split_first()?;
    let output = Command::new(program)
        .args(args)
        .current_dir(cwd)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn resolve_output_matches(project_root: &Utf8Path, pattern: &str) -> Result<Vec<String>> {
    if !contains_glob(pattern) {
        return Ok(project_root
            .join(pattern)
            .exists()
            .then(|| vec![pattern.to_owned()])
            .unwrap_or_default());
    }
    let matcher = build_globset(pattern)?;
    let mut candidates = Vec::new();
    collect_files(project_root, project_root, &mut candidates)?;
    let mut matches = candidates
        .into_iter()
        .filter(|candidate| matcher.is_match(candidate.as_str()))
        .collect::<Vec<_>>();
    matches.sort();
    Ok(matches)
}

fn contains_glob(pattern: &str) -> bool {
    pattern
        .bytes()
        .any(|byte| matches!(byte, b'*' | b'?' | b'[' | b']' | b'{'))
}

fn build_globset(pattern: &str) -> Result<globset::GlobSet> {
    let glob = Glob::new(pattern).with_context(|| format!("invalid glob pattern: {pattern}"))?;
    let mut builder = GlobSetBuilder::new();
    builder.add(glob);
    builder
        .build()
        .context("failed to build output glob matcher")
}

fn collect_files(root: &Utf8Path, current: &Utf8Path, files: &mut Vec<String>) -> Result<()> {
    for entry in fs::read_dir(current).with_context(|| format!("failed to read {current}"))? {
        let entry = entry.with_context(|| format!("failed to read entry in {current}"))?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow::anyhow!("output path was not UTF-8"))?;
        if path.is_dir() {
            collect_files(root, &path, files)?;
        } else if path.is_file() {
            let relative = path
                .strip_prefix(root)
                .context("collected file must stay inside project root")?
                .as_str()
                .to_owned();
            files.push(relative);
        }
    }
    Ok(())
}

fn repo_relative(repo_root: &Utf8Path, path: &Utf8Path, label: &str) -> Result<String> {
    Ok(path
        .strip_prefix(repo_root)
        .with_context(|| format!("{label} must stay under repo root"))?
        .as_str()
        .to_owned())
}

#[cfg(test)]
mod tests {
    use super::{action_evidence_card_path, run_action, validate_action};
    use camino::Utf8Path;
    use serde_json::Value;
    use std::fs;
    use tempfile::TempDir;

    fn write(path: &Utf8Path, content: &str) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, content).unwrap();
    }

    #[test]
    fn validate_reports_missing_required_output() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let manifest_path = repo_root.join("dossiers/alpha/spctr.toml");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["uv", "run", "pytest"]
expected_outputs = ["report"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "report"
path = "artifacts/report.json"
kind = "status_json"
required = true
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = validate_action(repo_root, &manifest, "check").unwrap();
        assert!(!report.ok);
        assert!(report.outputs[0].matches.is_empty());
    }

    #[test]
    fn validate_accepts_present_required_output() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("artifacts/report.json"), "{}\n");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["uv", "run", "pytest"]
expected_outputs = ["report"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "report"
path = "artifacts/report.json"
kind = "status_json"
required = true
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = validate_action(repo_root, &manifest, "check").unwrap();
        assert!(report.ok);
        assert_eq!(report.outputs[0].matches, vec!["artifacts/report.json"]);
    }

    #[test]
    fn validate_matches_globbed_output() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("dist/alpha-0.1.0.whl"), "wheel\n");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["uv", "run", "pytest"]
expected_outputs = ["wheel"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "wheel"
path = "dist/*.whl"
kind = "python_wheel"
required = true
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = validate_action(repo_root, &manifest, "check").unwrap();
        assert!(report.ok);
        assert_eq!(report.outputs[0].matches, vec!["dist/alpha-0.1.0.whl"]);
    }

    #[test]
    fn run_writes_evidence_card_for_successful_action() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("uv.lock"), "version = 1\n");
        write(&project_root.join("docs/README.md"), "# Alpha docs\n");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
series = "D-001"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "from pathlib import Path; Path('artifacts').mkdir(exist_ok=True); Path('artifacts/report.json').write_text('{}\\n')"]
expected_outputs = ["report"]
requires = ["python"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "report"
path = "artifacts/report.json"
kind = "status_json"
required = true

[spctr.docs]
root = "docs"
landing = "docs/README.md"
require_frontmatter = false
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = run_action(repo_root, &manifest, "check").unwrap();
        assert!(report.ok);
        assert_eq!(
            report.card_path.as_deref(),
            Some("dossiers/alpha/artifacts/evidence/latest.json")
        );
        let card: Value = serde_json::from_str(
            &fs::read_to_string(project_root.join("artifacts/evidence/latest.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(card["version"], 2);
        assert_eq!(card["status"], "ok");
        assert_eq!(card["manifest"]["path"], "dossiers/alpha/spctr.toml");
        assert_eq!(card["manifest"]["series"], "D-001");
        assert_eq!(card["manifest"]["docs_landing"], "docs/README.md");
        assert_eq!(card["requires"], serde_json::json!(["python"]));
        assert_eq!(card["inputs"][0]["kind"], "manifest");
        assert_eq!(card["inputs"][0]["path"], "dossiers/alpha/spctr.toml");
        assert!(card["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["kind"] == "lockfile" && entry["path"] == "dossiers/alpha/uv.lock"));
        assert_eq!(card["runtime"]["arch"], std::env::consts::ARCH);
        assert_eq!(
            card["outputs"][0]["matches"][0]["path"],
            "artifacts/report.json"
        );
        let action_card_path = action_evidence_card_path(&manifest, "check").unwrap();
        let action_card: Value =
            serde_json::from_str(&fs::read_to_string(action_card_path).unwrap()).unwrap();
        assert_eq!(action_card["action"], "check");
        assert_eq!(action_card["status"], "ok");
    }

    #[test]
    fn run_marks_timeout_and_records_failed_card() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "import time; time.sleep(2)"]
timeout_sec = 1

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = run_action(repo_root, &manifest, "check").unwrap();
        assert!(!report.ok);
        assert!(report.timed_out);
        let card: Value = serde_json::from_str(
            &fs::read_to_string(project_root.join("artifacts/evidence/latest.json")).unwrap(),
        )
        .unwrap();
        assert_eq!(card["version"], 2);
        assert_eq!(card["status"], "timed_out");
        assert_eq!(card["inputs"][0]["kind"], "manifest");
        let action_card_path = action_evidence_card_path(&manifest, "check").unwrap();
        let action_card: Value =
            serde_json::from_str(&fs::read_to_string(action_card_path).unwrap()).unwrap();
        assert_eq!(action_card["action"], "check");
        assert_eq!(action_card["status"], "timed_out");
    }

    #[test]
    fn run_handles_noisy_failed_commands_without_timing_out() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "import sys; print('x' * 200000); print('boom', file=sys.stderr); sys.exit(7)"]
timeout_sec = 5

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = run_action(repo_root, &manifest, "check").unwrap();

        assert!(!report.ok);
        assert_eq!(report.exit_code, Some(7));
        assert!(!report.timed_out);
        assert!(report
            .error
            .as_deref()
            .is_some_and(|error| error.contains("boom")));
    }
}
