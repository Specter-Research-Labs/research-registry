use crate::manifest::{
    self, PackageLanguage, ProjectManifest, PublishMode, ReleaseStage, ReleaseSurfaceConfig,
    ReleaseSurfaceKind, REPO_TREE_URL,
};
use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use chrono::Utc;
use regex_lite::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::fs;
use std::process::{Command, Output};

const RELEASES_PUBLIC_URL: &str = "https://releases.specterlab.org";
const RECORDS_ARCHIVE_PUBLIC_URL: &str = "https://releases.specterlab.org/records";

#[derive(Clone, Debug, Serialize)]
pub struct PublicSurfaceLink {
    pub name: String,
    pub kind: String,
    pub label: String,
    pub publish: bool,
    pub href: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReleasePlan {
    pub project: String,
    pub kind: String,
    pub slug: String,
    pub license: String,
    pub stage: String,
    pub surfaces: Vec<PublicSurfaceLink>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReleaseAuditReport {
    pub plans: Vec<ReleasePlan>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReleaseGateCheck {
    pub name: String,
    pub ok: bool,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ReleaseGateReport {
    pub project: String,
    pub slug: String,
    pub stage: String,
    pub ok: bool,
    pub checks: Vec<ReleaseGateCheck>,
}

#[derive(Clone, Debug, Serialize)]
struct ReleaseArtifactEvidence {
    version: u32,
    action: String,
    generated_at: String,
    project: String,
    title: String,
    series: Option<String>,
    stage: String,
    surface: String,
    surface_kind: String,
    language: Option<String>,
    release_id: Option<String>,
    manifest_path: String,
    git: ReleaseEvidenceGitContext,
    inputs: Vec<ReleaseEvidencePathRecord>,
    outputs: Vec<ReleaseEvidencePathRecord>,
}

#[derive(Clone, Debug, Serialize)]
struct ReleaseEvidenceGitContext {
    commit: Option<String>,
    branch: Option<String>,
    dirty: Option<bool>,
}

#[derive(Clone, Debug, Serialize)]
struct ReleaseEvidencePathRecord {
    path: String,
    kind: String,
    sha256: String,
    size_bytes: u64,
    file_count: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum GateMode {
    StaticValidation,
    RuntimeEvidence,
}

pub fn discover_release_manifests(repo_root: &Utf8Path) -> Result<Vec<ProjectManifest>> {
    let vocabs = release_vocabularies(repo_root)?;
    manifest::discover_all_manifests(repo_root, &vocabs)
}

pub fn lookup_project(repo_root: &Utf8Path, slug: &str) -> Result<ProjectManifest> {
    let vocabs = release_vocabularies(repo_root)?;
    for kind in ["dossiers", "addenda"] {
        let manifest_path = repo_root
            .join(kind)
            .join(slug)
            .join(manifest::MANIFEST_NAME);
        if manifest_path.is_file() {
            return manifest::load_project_manifest(&manifest_path, Some(&vocabs));
        }
    }
    bail!("unknown project slug: {slug}")
}

fn release_vocabularies(repo_root: &Utf8Path) -> Result<manifest::Vocabularies> {
    let spec_dir = crate::design_tokens::spec_dir(repo_root);
    let tokens = crate::design_tokens::load_spec(&spec_dir, "web")?;
    manifest::Vocabularies::from_spec(&tokens)
}

pub fn public_surface_links(manifest: &ProjectManifest) -> Vec<PublicSurfaceLink> {
    manifest
        .release
        .surfaces
        .iter()
        .map(|surface| PublicSurfaceLink {
            name: surface.name.clone(),
            kind: surface.kind.as_str().to_owned(),
            label: surface_label(surface),
            publish: surface.publish,
            href: surface
                .publish
                .then(|| public_surface_href(manifest, surface))
                .flatten(),
        })
        .collect()
}

pub fn build_plan(manifest: &ProjectManifest) -> ReleasePlan {
    ReleasePlan {
        project: manifest.title.clone(),
        kind: manifest.kind.clone(),
        slug: manifest.slug.clone(),
        license: manifest.license.clone(),
        stage: manifest.release.stage.as_str().to_owned(),
        surfaces: public_surface_links(manifest),
    }
}

pub(crate) fn required_exec_gate_actions(manifest: &ProjectManifest) -> Vec<&'static str> {
    match manifest.release.stage {
        ReleaseStage::Wip => Vec::new(),
        ReleaseStage::Candidate => vec!["check"],
        ReleaseStage::Promoted => {
            let mut actions = vec!["check", "smoke", "build"];
            if manifest
                .release
                .surfaces
                .iter()
                .any(|surface| surface.publish)
            {
                actions.push("publish");
            }
            actions
        }
    }
}

fn surface_label(surface: &ReleaseSurfaceConfig) -> String {
    match surface.kind {
        ReleaseSurfaceKind::SourceBundle => "Source Bundle".to_owned(),
        ReleaseSurfaceKind::ArtifactRelease => "Artifact Release".to_owned(),
        ReleaseSurfaceKind::Package => {
            let language = surface
                .language
                .expect("validated package language")
                .as_str()
                .to_owned();
            format!("{} Package", capitalize(&language))
        }
    }
}

fn public_surface_href(
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
) -> Option<String> {
    match surface.kind {
        ReleaseSurfaceKind::SourceBundle => None,
        ReleaseSurfaceKind::ArtifactRelease => Some(format!(
            "{}/{}/releases/",
            RELEASES_PUBLIC_URL,
            surface
                .public_namespace
                .as_deref()
                .expect("validated artifact namespace")
        )),
        ReleaseSurfaceKind::Package => {
            if let Some(mode) = surface.publish_mode {
                if mode == PublishMode::MirrorRepo {
                    return surface.mirror_repo.clone();
                }
            }
            let registry = surface.registry.as_deref()?;
            match (surface.language?, registry) {
                (PackageLanguage::Rust, "crates.io") => Some(format!(
                    "https://crates.io/crates/{}",
                    package_name(manifest, surface)
                )),
                (PackageLanguage::Python, "pypi") => Some(format!(
                    "https://pypi.org/project/{}/",
                    package_name(manifest, surface)
                )),
                _ => None,
            }
        }
    }
}

pub fn validate(repo_root: &Utf8Path, slug: Option<&str>) -> Result<Vec<ReleasePlan>> {
    let forbidden_paths = forbidden_tracked_paths(repo_root)?;
    if !forbidden_paths.is_empty() {
        bail!(
            "tracked files violate public release policy:\n{}",
            forbidden_paths.join("\n")
        );
    }
    let manifests = if let Some(project_slug) = slug {
        vec![lookup_project(repo_root, project_slug)?]
    } else {
        discover_release_manifests(repo_root)?
    };
    manifests
        .into_iter()
        .map(|manifest| validate_manifest(repo_root, &manifest).map(|_| build_plan(&manifest)))
        .collect()
}

pub fn audit(repo_root: &Utf8Path) -> Result<ReleaseAuditReport> {
    audit_public_copy(repo_root)?;
    let plans = validate(repo_root, None)?;
    crate::site::build(repo_root, false)?;
    Ok(ReleaseAuditReport { plans })
}

pub fn gate(repo_root: &Utf8Path, slug: Option<&str>) -> Result<Vec<ReleaseGateReport>> {
    let manifests = if let Some(project_slug) = slug {
        vec![lookup_project(repo_root, project_slug)?]
    } else {
        discover_release_manifests(repo_root)?
    };
    Ok(manifests
        .into_iter()
        .map(|manifest| gate_manifest(&manifest))
        .collect())
}

fn gate_manifest(manifest: &ProjectManifest) -> ReleaseGateReport {
    gate_manifest_with_mode(manifest, GateMode::RuntimeEvidence)
}

fn gate_manifest_with_mode(manifest: &ProjectManifest, mode: GateMode) -> ReleaseGateReport {
    let mut checks = Vec::new();
    let spctr = manifest.spctr.as_ref();
    let publishable_surface_count = manifest
        .release
        .surfaces
        .iter()
        .filter(|surface| surface.publish)
        .count();

    match manifest.release.stage {
        ReleaseStage::Wip => push_gate_check(
            &mut checks,
            "stage-policy",
            true,
            "wip projects do not require exec gates",
        ),
        ReleaseStage::Candidate => push_gate_check(
            &mut checks,
            "exec.check",
            spctr.is_some_and(|spctr| spctr.exec.contains_key("check")),
            "candidate projects must declare spctr.exec.check",
        ),
        ReleaseStage::Promoted => {
            push_gate_check(
                &mut checks,
                "publishable-surface",
                publishable_surface_count > 0,
                "promoted projects must declare at least one publishable release surface",
            );
            push_gate_check(
                &mut checks,
                "readme",
                manifest.root.join("README.md").is_file(),
                "promoted projects require a README.md in the project root",
            );
            for action in required_exec_gate_actions(manifest) {
                let has_action = spctr.is_some_and(|spctr| spctr.exec.contains_key(action));
                push_gate_check(
                    &mut checks,
                    &format!("exec.{action}"),
                    has_action,
                    format!("promoted projects must declare spctr.exec.{action}"),
                );
                if has_action && mode == GateMode::RuntimeEvidence {
                    let (ok, detail) = action_evidence_gate_check(manifest, action);
                    push_gate_check(&mut checks, &format!("exec.{action}.evidence"), ok, detail);
                }
            }
        }
    }

    if publishable_surface_count > 0 {
        push_gate_check(
            &mut checks,
            "evidence.card_path",
            spctr
                .and_then(|spctr| spctr.evidence.as_ref())
                .and_then(|evidence| evidence.card_path.as_ref())
                .is_some(),
            "publishable release surfaces require spctr.evidence.card_path",
        );
    }

    if manifest.site.visible && manifest.site.publish_docs {
        match spctr.and_then(|spctr| spctr.docs.as_ref()) {
            Some(docs) => {
                push_gate_check(
                    &mut checks,
                    "docs.root",
                    true,
                    format!("publish_docs is enabled via {}", docs.root),
                );
                push_gate_check(
                    &mut checks,
                    "docs.root.exists",
                    manifest.root.join(&docs.root).exists(),
                    format!("docs root must exist at {}", manifest.root.join(&docs.root)),
                );
                if manifest.release.stage == ReleaseStage::Promoted {
                    match docs.landing.as_deref() {
                        Some(landing) => push_gate_check(
                            &mut checks,
                            "docs.landing",
                            manifest.root.join(landing).is_file(),
                            format!(
                                "promoted visible docs require a landing page at {}",
                                manifest.root.join(landing)
                            ),
                        ),
                        None => push_gate_check(
                            &mut checks,
                            "docs.landing",
                            false,
                            "promoted visible docs require spctr.docs.landing",
                        ),
                    }
                }
            }
            None => push_gate_check(
                &mut checks,
                "docs.root",
                false,
                "site.publish_docs requires a spctr.docs section",
            ),
        }
    }

    let ok = checks.iter().all(|check| check.ok);
    ReleaseGateReport {
        project: manifest.title.clone(),
        slug: manifest.slug.clone(),
        stage: manifest.release.stage.as_str().to_owned(),
        ok,
        checks,
    }
}

fn push_gate_check(
    checks: &mut Vec<ReleaseGateCheck>,
    name: &str,
    ok: bool,
    detail: impl Into<String>,
) {
    checks.push(ReleaseGateCheck {
        name: name.to_owned(),
        ok,
        detail: detail.into(),
    });
}

fn validate_manifest(repo_root: &Utf8Path, manifest: &ProjectManifest) -> Result<()> {
    if manifest.license.trim().is_empty() {
        bail!("{}: license must be non-empty", manifest.path);
    }
    if !project_license_path(manifest).is_file() {
        bail!(
            "{}: public projects require a local LICENSE file at {}",
            manifest.path,
            project_license_path(manifest)
        );
    }
    let mut names = BTreeSet::new();
    for surface in &manifest.release.surfaces {
        if !names.insert(surface.name.clone()) {
            bail!(
                "{}: duplicate release surface '{}'",
                manifest.path,
                surface.name
            );
        }
        match surface.kind {
            ReleaseSurfaceKind::SourceBundle => {
                validate_source_bundle(repo_root, manifest, surface)?
            }
            ReleaseSurfaceKind::Package => validate_package_surface(repo_root, manifest, surface)?,
            ReleaseSurfaceKind::ArtifactRelease => {
                validate_artifact_surface(repo_root, manifest, surface)?
            }
        }
    }
    validate_manifest_gate_requirements(manifest)?;
    Ok(())
}

fn validate_manifest_gate_requirements(manifest: &ProjectManifest) -> Result<()> {
    let report = gate_manifest_with_mode(manifest, GateMode::StaticValidation);
    let failures = report
        .checks
        .iter()
        .filter(|check| !check.ok)
        .map(|check| format!("{}: {}", check.name, check.detail))
        .collect::<Vec<_>>();
    if failures.is_empty() {
        return Ok(());
    }
    bail!(
        "{}: manifest-declared release gates failed:\n{}",
        manifest.path,
        failures.join("\n")
    )
}

#[derive(Deserialize)]
struct GateEvidenceCard {
    action: String,
    status: String,
}

fn action_evidence_gate_check(manifest: &ProjectManifest, action: &str) -> (bool, String) {
    let Some(action_card_path) = crate::exec::action_evidence_card_path(manifest, action) else {
        return (
            false,
            format!(
                "run `spctr exec run --project {} {action}` to emit evidence",
                manifest.slug
            ),
        );
    };

    let mut candidates = vec![action_card_path.clone()];
    if let Some(configured) = crate::exec::configured_evidence_card_path(manifest)
        .filter(|path| path != &action_card_path)
    {
        candidates.push(configured);
    }

    let mut first_missing = None;
    for path in candidates {
        match load_gate_evidence_card(&path) {
            Ok(Some(card)) => {
                if card.action != action {
                    continue;
                }
                if card.status == "ok" {
                    return (
                        true,
                        format!(
                            "successful evidence card recorded at {}",
                            path.strip_prefix(&manifest.root).unwrap_or(&path)
                        ),
                    );
                }
                return (
                    false,
                    format!(
                        "evidence card at {} has status {}; rerun `spctr exec run --project {} {action}`",
                        path.strip_prefix(&manifest.root).unwrap_or(&path),
                        card.status,
                        manifest.slug
                    ),
                );
            }
            Ok(None) => {
                first_missing.get_or_insert(path);
            }
            Err(error) => {
                return (
                    false,
                    format!(
                        "failed to read evidence card at {}: {error}",
                        path.strip_prefix(&manifest.root).unwrap_or(&path)
                    ),
                );
            }
        }
    }

    let missing_path = first_missing.unwrap_or(action_card_path);
    (
        false,
        format!(
            "missing successful evidence card at {}; run `spctr exec run --project {} {action}`",
            missing_path
                .strip_prefix(&manifest.root)
                .unwrap_or(&missing_path),
            manifest.slug
        ),
    )
}

fn load_gate_evidence_card(path: &Utf8Path) -> Result<Option<GateEvidenceCard>> {
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let card = serde_json::from_str(&text).with_context(|| format!("failed to parse {}", path))?;
    Ok(Some(card))
}

fn project_license_path(manifest: &ProjectManifest) -> Utf8PathBuf {
    manifest.root.join("LICENSE")
}

fn audit_public_copy(repo_root: &Utf8Path) -> Result<()> {
    let tracked = tracked_files(repo_root)?;

    let stale_private_refs = find_text_pattern_hits(
        repo_root,
        &tracked,
        &[
            "README.md",
            "AGENTS.md",
            "ops",
            "dossiers",
            "addenda",
            "site",
            ".github",
        ],
        &["ops/spctr/src/release.rs"],
        &[
            "records.specterlab.org",
            "SPECTER_GENERATED_ROOT",
            "../generated",
        ],
    )?;
    if !stale_private_refs.is_empty() {
        bail!(
            "stale private-root or records host references remain:\n{}",
            stale_private_refs.join("\n")
        );
    }

    let stale_mit_refs = find_text_pattern_hits(
        repo_root,
        &tracked,
        &[
            "README.md",
            "LICENSE",
            "LICENSING.md",
            "ops",
            "dossiers",
            "addenda",
            "site",
            ".github",
        ],
        &[
            "dossiers/lenia-swarm/tt_backend/metal/reintegration",
            "dossiers/jolt-material-memory/engine/src/recording_viewer.mm",
            "ops/spctr/src/release.rs",
        ],
        &["license = \"MIT\"", "MIT License"],
    )?;
    if !stale_mit_refs.is_empty() {
        bail!(
            "stale MIT licensing references remain outside approved carve-outs:\n{}",
            stale_mit_refs.join("\n")
        );
    }

    let open_source_refs = find_text_pattern_hits(
        repo_root,
        &tracked,
        &["README.md", "ops", "dossiers", "addenda", "site", ".github"],
        &["ops/spctr/src/release.rs"],
        &["open source"],
    )?;
    if !open_source_refs.is_empty() {
        bail!(
            "public copy still says open source:\n{}",
            open_source_refs.join("\n")
        );
    }

    Ok(())
}

pub(crate) fn validate_release_id(release_id: &str) -> Result<String> {
    let trimmed = release_id.trim();
    if trimmed.is_empty() {
        bail!("release_id must be non-empty");
    }
    if trimmed.starts_with('.') || trimmed.ends_with('.') || trimmed.contains("..") {
        bail!("release_id must not contain dot segments: {trimmed}");
    }
    if trimmed.contains('/') || trimmed.contains('\\') {
        bail!("release_id must not contain path separators: {trimmed}");
    }
    if !trimmed
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    {
        bail!("release_id must contain only ASCII letters, digits, '.', '_' or '-': {trimmed}");
    }
    Ok(trimmed.to_owned())
}

fn validate_project_subpath(manifest: &ProjectManifest, rel_path: &str) -> Result<Utf8PathBuf> {
    let joined = manifest.root.join(rel_path);
    if !joined.exists() {
        bail!(
            "{}: release surface path does not exist: {}",
            manifest.path,
            joined
        );
    }
    let project_root = manifest
        .root
        .canonicalize_utf8()
        .with_context(|| format!("failed to canonicalize project root {}", manifest.root))?;
    let resolved = joined
        .canonicalize_utf8()
        .with_context(|| format!("failed to canonicalize release surface path {joined}"))?;
    if !resolved.starts_with(&project_root) {
        bail!(
            "{}: release surface path must stay within project root: {}",
            manifest.path,
            rel_path
        );
    }
    Ok(resolved)
}

fn validate_source_bundle(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
) -> Result<()> {
    validate_project_subpath(manifest, &surface.path)?;
    if surface.include_docs && !manifest.root.join("docs").exists() {
        bail!(
            "{}: release surface '{}' enables include_docs but project has no docs/ directory",
            manifest.path,
            surface.name
        );
    }
    for support_path in &surface.support_paths {
        let abs = repo_root.join(support_path);
        if !abs.exists() {
            bail!(
                "{}: release surface '{}' support path missing: {}",
                manifest.path,
                surface.name,
                support_path
            );
        }
    }
    Ok(())
}

fn validate_package_surface(
    _repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
) -> Result<()> {
    let package_root = validate_project_subpath(manifest, &surface.path)?;
    match surface.language.expect("validated package language") {
        PackageLanguage::Python => ensure_file(
            &package_root.join("pyproject.toml"),
            manifest,
            surface,
            "pyproject.toml",
        )?,
        PackageLanguage::Rust => ensure_file(
            &package_root.join("Cargo.toml"),
            manifest,
            surface,
            "Cargo.toml",
        )?,
        PackageLanguage::Swift => ensure_file(
            &package_root.join("Package.swift"),
            manifest,
            surface,
            "Package.swift",
        )?,
        PackageLanguage::Julia => ensure_file(
            &package_root.join("Project.toml"),
            manifest,
            surface,
            "Project.toml",
        )?,
        PackageLanguage::Lean => ensure_file(
            &package_root.join("lakefile.lean"),
            manifest,
            surface,
            "lakefile.lean",
        )?,
    }
    Ok(())
}

fn validate_artifact_surface(
    _repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
) -> Result<()> {
    validate_project_subpath(manifest, &surface.path)?;
    let source_path = surface
        .source_path
        .as_deref()
        .expect("validated source_path");
    validate_project_subpath(manifest, source_path)?;
    Ok(())
}

fn ensure_file(
    path: &Utf8Path,
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
    name: &str,
) -> Result<()> {
    if !path.is_file() {
        bail!(
            "{}: release surface '{}' expected {} under {}",
            manifest.path,
            surface.name,
            name,
            path.parent().unwrap_or(path)
        );
    }
    Ok(())
}

pub fn bundle_source_surface(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface_name: &str,
    release_id: &str,
    output_dir: Option<&Utf8Path>,
) -> Result<Utf8PathBuf> {
    let release_id = validate_release_id(release_id)?;
    let surface = manifest
        .release
        .surfaces
        .iter()
        .find(|surface| surface.name == surface_name)
        .with_context(|| {
            format!(
                "unknown release surface '{}' for {}",
                surface_name, manifest.slug
            )
        })?;
    if surface.kind != ReleaseSurfaceKind::SourceBundle {
        bail!(
            "{}: release surface '{}' is not a source_bundle",
            manifest.path,
            surface.name
        );
    }
    validate_source_bundle(repo_root, manifest, surface)?;
    let bundle_root = tempfile::tempdir().context("failed to create bundle tempdir")?;
    let stage_dir = Utf8PathBuf::from_path_buf(bundle_root.path().to_path_buf())
        .expect("tempdir path is valid UTF-8")
        .join(format!("{}-{}", manifest.slug, release_id));
    fs::create_dir_all(&stage_dir)
        .with_context(|| format!("failed to create bundle staging dir {stage_dir}"))?;

    let mut include_paths: BTreeSet<String> = BTreeSet::new();
    let surface_rel = normalize_repo_relative(
        repo_root,
        &validate_project_subpath(manifest, &surface.path)?,
        "surface path",
    )?;
    include_paths.insert(surface_rel);
    if surface.include_docs && manifest.root.join("docs").exists() {
        include_paths.insert(format!(
            "{}/docs",
            manifest.root.strip_prefix(repo_root)?.as_str()
        ));
    }
    include_paths.extend(surface.support_paths.iter().cloned());

    let copied_paths = copy_tracked_include_paths(repo_root, &include_paths, &stage_dir)?;
    rewrite_bundle_markdown_links(&stage_dir, &include_paths)?;

    let release_manifest = serde_json::to_string_pretty(&serde_json::json!({
        "version": 1,
        "project": manifest.slug,
        "title": manifest.title,
        "release_id": release_id,
        "surface": surface.name,
        "license": manifest.license,
        "stage": manifest.release.stage.as_str(),
        "included_paths": include_paths,
    }))?;
    fs::write(stage_dir.join("spctr-release.json"), release_manifest)
        .with_context(|| format!("failed to write release manifest into {stage_dir}"))?;

    let target_dir = output_dir
        .map(ToOwned::to_owned)
        .unwrap_or_else(|| repo_root.join("tmp/releases"));
    fs::create_dir_all(&target_dir)
        .with_context(|| format!("failed to create output dir {target_dir}"))?;
    let archive_path = target_dir.join(format!(
        "{}-{}-{}.tar.gz",
        manifest.slug, surface.name, release_id
    ));
    let args = vec![
        "-czf".to_owned(),
        archive_path.to_string(),
        "-C".to_owned(),
        bundle_root.path().display().to_string(),
        stage_dir
            .file_name()
            .expect("bundle stage dir should have basename")
            .to_owned(),
    ];
    let mut command = Command::new("tar");
    command.args(&args).current_dir(repo_root);
    run_command(&mut command, "failed to create source bundle archive")?;
    let evidence_inputs = include_paths
        .iter()
        .map(|rel| fingerprint_tracked_include_path(repo_root, rel, &copied_paths))
        .collect::<Result<Vec<_>>>()?;
    write_release_artifact_evidence_with_inputs(
        repo_root,
        manifest,
        surface,
        "source_bundle",
        Some(&release_id),
        evidence_inputs,
        &[archive_path.clone()],
        &bundle_evidence_path(&archive_path),
    )?;
    Ok(archive_path)
}

pub fn materialize_package_surface(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface_name: &str,
    output_dir: &Utf8Path,
) -> Result<Utf8PathBuf> {
    let surface = manifest
        .release
        .surfaces
        .iter()
        .find(|surface| surface.name == surface_name)
        .with_context(|| {
            format!(
                "unknown release surface '{}' for {}",
                surface_name, manifest.slug
            )
        })?;
    if surface.kind != ReleaseSurfaceKind::Package {
        bail!(
            "{}: release surface '{}' is not a package surface",
            manifest.path,
            surface.name
        );
    }
    validate_package_surface(repo_root, manifest, surface)?;
    fs::create_dir_all(output_dir)
        .with_context(|| format!("failed to create package output dir {output_dir}"))?;
    let package_root = validate_project_subpath(manifest, &surface.path)?;
    let package_name = package_name(manifest, surface);
    let materialized_root = output_dir.join(&package_name);
    if materialized_root.exists() {
        fs::remove_dir_all(&materialized_root)
            .with_context(|| format!("failed to clear existing package dir {materialized_root}"))?;
    }
    fs::create_dir_all(&materialized_root)
        .with_context(|| format!("failed to create package dir {materialized_root}"))?;
    let mirror_mode = surface.publish_mode == Some(PublishMode::MirrorRepo);
    if mirror_mode {
        copy_dir_contents(&package_root, &materialized_root)?;
    } else {
        let repo_rel = normalize_repo_relative(repo_root, &package_root, "package root")?;
        copy_rel_path(repo_root, &repo_rel, &materialized_root)?;
    }
    let payload = serde_json::to_string_pretty(&serde_json::json!({
        "version": 1,
        "project": manifest.slug,
        "surface": surface.name,
        "language": surface.language.expect("validated package language").as_str(),
        "registry": surface.registry,
        "distribution_channel": surface.distribution_channel,
        "publish_mode": surface.publish_mode.expect("validated publish mode").as_str(),
        "mirror_repo": surface.mirror_repo,
        "source_path": package_root.as_str(),
    }))?;
    fs::write(
        materialized_root.join("spctr-package-surface.json"),
        payload,
    )
    .with_context(|| format!("failed to write package metadata into {materialized_root}"))?;
    let package_root_rel = normalize_repo_relative(repo_root, &package_root, "package root")?;
    write_release_artifact_evidence(
        repo_root,
        manifest,
        surface,
        "package_surface",
        None,
        &[package_root_rel.as_str()],
        &[materialized_root.clone()],
        &materialized_root.join("spctr-release-evidence.json"),
    )?;
    Ok(materialized_root)
}

fn bundle_evidence_path(archive_path: &Utf8Path) -> Utf8PathBuf {
    let file_name = archive_path
        .file_name()
        .unwrap_or("release-artifact.tar.gz")
        .to_owned();
    archive_path
        .parent()
        .unwrap_or_else(|| Utf8Path::new("."))
        .join(format!("{file_name}.evidence.json"))
}

fn write_release_artifact_evidence(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
    action: &str,
    release_id: Option<&str>,
    input_paths: &[&str],
    output_paths: &[Utf8PathBuf],
    card_path: &Utf8Path,
) -> Result<()> {
    let inputs = input_paths
        .iter()
        .map(|rel| fingerprint_repo_rel_path(repo_root, rel))
        .collect::<Result<Vec<_>>>()?;
    write_release_artifact_evidence_with_inputs(
        repo_root,
        manifest,
        surface,
        action,
        release_id,
        inputs,
        output_paths,
        card_path,
    )
}

fn write_release_artifact_evidence_with_inputs(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    surface: &ReleaseSurfaceConfig,
    action: &str,
    release_id: Option<&str>,
    inputs: Vec<ReleaseEvidencePathRecord>,
    output_paths: &[Utf8PathBuf],
    card_path: &Utf8Path,
) -> Result<()> {
    if let Some(parent) = card_path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create release evidence dir {parent}"))?;
    }
    let outputs = output_paths
        .iter()
        .map(|path| fingerprint_path(repo_root, path))
        .collect::<Result<Vec<_>>>()?;
    let payload = ReleaseArtifactEvidence {
        version: 1,
        action: action.to_owned(),
        generated_at: Utc::now().to_rfc3339(),
        project: manifest.slug.clone(),
        title: manifest.title.clone(),
        series: manifest.series.clone(),
        stage: manifest.release.stage.as_str().to_owned(),
        surface: surface.name.clone(),
        surface_kind: surface.kind.as_str().to_owned(),
        language: surface
            .language
            .map(|language| language.as_str().to_owned()),
        release_id: release_id.map(str::to_owned),
        manifest_path: normalize_repo_relative(repo_root, &manifest.path, "manifest path")?,
        git: release_git_context(repo_root),
        inputs,
        outputs,
    };
    let rendered = serde_json::to_string_pretty(&payload)? + "\n";
    fs::write(card_path, rendered)
        .with_context(|| format!("failed to write release evidence card {card_path}"))?;
    Ok(())
}

fn fingerprint_repo_rel_path(
    repo_root: &Utf8Path,
    rel_path: &str,
) -> Result<ReleaseEvidencePathRecord> {
    fingerprint_path(repo_root, &repo_root.join(rel_path))
}

fn fingerprint_tracked_include_path(
    repo_root: &Utf8Path,
    include_path: &str,
    copied_paths: &[String],
) -> Result<ReleaseEvidencePathRecord> {
    let root = repo_root.join(include_path);
    if root.is_file() {
        return fingerprint_file(repo_root, &root);
    }
    if !root.is_dir() {
        bail!("missing path while fingerprinting source bundle input: {include_path}");
    }

    let mut files = copied_paths
        .iter()
        .filter_map(|path| path_relative_to_include(path, include_path).map(|rel| (path, rel)))
        .collect::<Vec<_>>();
    files.sort_by(|(_, left), (_, right)| left.cmp(right));
    if files.is_empty() {
        bail!("source bundle include path has no tracked files: {include_path}");
    }

    let mut hasher = Sha256::new();
    let mut size_bytes = 0_u64;
    for (repo_rel, include_rel) in &files {
        let absolute = repo_root.join(repo_rel);
        let bytes = fs::read(&absolute)
            .with_context(|| format!("failed to read source bundle input file {absolute}"))?;
        let file_size = u64::try_from(bytes.len())
            .map_err(|_| anyhow::anyhow!("artifact file too large: {absolute}"))?;
        size_bytes = size_bytes
            .checked_add(file_size)
            .ok_or_else(|| anyhow::anyhow!("source bundle input too large: {include_path}"))?;
        let mut file_hasher = Sha256::new();
        file_hasher.update(&bytes);
        hasher.update(include_rel.as_bytes());
        hasher.update([0]);
        hasher.update(format!("{:x}", file_hasher.finalize()).as_bytes());
        hasher.update([0]);
    }

    Ok(ReleaseEvidencePathRecord {
        path: include_path.to_owned(),
        kind: "directory".to_owned(),
        sha256: format!("{:x}", hasher.finalize()),
        size_bytes,
        file_count: u64::try_from(files.len()).map_err(|_| {
            anyhow::anyhow!(
                "too many files while fingerprinting source bundle input {include_path}"
            )
        })?,
    })
}

fn fingerprint_path(repo_root: &Utf8Path, path: &Utf8Path) -> Result<ReleaseEvidencePathRecord> {
    if path.is_dir() {
        return fingerprint_dir(repo_root, path);
    }
    fingerprint_file(repo_root, path)
}

fn fingerprint_file(repo_root: &Utf8Path, path: &Utf8Path) -> Result<ReleaseEvidencePathRecord> {
    let bytes = fs::read(path).with_context(|| format!("failed to read artifact file {path}"))?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok(ReleaseEvidencePathRecord {
        path: display_path(repo_root, path),
        kind: "file".to_owned(),
        sha256: format!("{:x}", hasher.finalize()),
        size_bytes: u64::try_from(bytes.len())
            .map_err(|_| anyhow::anyhow!("artifact file too large: {path}"))?,
        file_count: 1,
    })
}

fn fingerprint_dir(repo_root: &Utf8Path, root: &Utf8Path) -> Result<ReleaseEvidencePathRecord> {
    let mut files = Vec::new();
    collect_dir_files(root, root, &mut files)?;
    files.sort();
    let mut hasher = Sha256::new();
    let mut size_bytes = 0_u64;
    for rel in &files {
        let absolute = root.join(rel);
        let bytes = fs::read(&absolute)
            .with_context(|| format!("failed to read artifact file {absolute}"))?;
        let file_size = u64::try_from(bytes.len())
            .map_err(|_| anyhow::anyhow!("artifact file too large: {absolute}"))?;
        size_bytes = size_bytes
            .checked_add(file_size)
            .ok_or_else(|| anyhow::anyhow!("directory too large to fingerprint: {root}"))?;
        let mut file_hasher = Sha256::new();
        file_hasher.update(&bytes);
        hasher.update(rel.as_bytes());
        hasher.update([0]);
        hasher.update(format!("{:x}", file_hasher.finalize()).as_bytes());
        hasher.update([0]);
    }
    Ok(ReleaseEvidencePathRecord {
        path: display_path(repo_root, root),
        kind: "directory".to_owned(),
        sha256: format!("{:x}", hasher.finalize()),
        size_bytes,
        file_count: u64::try_from(files.len())
            .map_err(|_| anyhow::anyhow!("too many files while fingerprinting {root}"))?,
    })
}

fn collect_dir_files(root: &Utf8Path, current: &Utf8Path, files: &mut Vec<String>) -> Result<()> {
    for entry in fs::read_dir(current).with_context(|| format!("failed to read {current}"))? {
        let entry = entry.with_context(|| format!("failed to read entry in {current}"))?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow::anyhow!("artifact path was not UTF-8"))?;
        if path.is_dir() {
            collect_dir_files(root, &path, files)?;
        } else if path.is_file() {
            files.push(
                path.strip_prefix(root)
                    .context("fingerprinted file must stay inside root")?
                    .as_str()
                    .to_owned(),
            );
        }
    }
    Ok(())
}

fn display_path(repo_root: &Utf8Path, path: &Utf8Path) -> String {
    normalize_repo_relative(repo_root, path, "artifact path")
        .unwrap_or_else(|_| path.as_str().to_owned())
}

fn release_git_context(repo_root: &Utf8Path) -> ReleaseEvidenceGitContext {
    ReleaseEvidenceGitContext {
        commit: command_text(repo_root, &["git", "rev-parse", "HEAD"]),
        branch: command_text(repo_root, &["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        dirty: command_stdout(
            repo_root,
            &["git", "status", "--short", "--untracked-files=no"],
        )
        .map(|output| !output.is_empty()),
    }
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

fn run_command(command: &mut Command, context: &str) -> Result<()> {
    let output = command.output().with_context(|| context.to_owned())?;
    if output.status.success() {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
    if stderr.is_empty() {
        bail!("{context}");
    }
    bail!("{context}: {stderr}");
}

fn package_name(manifest: &ProjectManifest, surface: &ReleaseSurfaceConfig) -> String {
    match surface.language.expect("validated package language") {
        PackageLanguage::Python => {
            let pyproject = manifest.root.join(&surface.path).join("pyproject.toml");
            let text = fs::read_to_string(pyproject).unwrap_or_default();
            let value = text.parse::<toml::Value>().ok();
            value
                .as_ref()
                .and_then(|value| value.get("project"))
                .and_then(|project| project.get("name"))
                .and_then(toml::Value::as_str)
                .unwrap_or(&surface.name)
                .to_owned()
        }
        PackageLanguage::Rust => {
            let cargo = manifest.root.join(&surface.path).join("Cargo.toml");
            let text = fs::read_to_string(cargo).unwrap_or_default();
            let value = text.parse::<toml::Value>().ok();
            value
                .as_ref()
                .and_then(|value| value.get("package"))
                .and_then(|package| package.get("name"))
                .and_then(toml::Value::as_str)
                .unwrap_or(&surface.name)
                .to_owned()
        }
        PackageLanguage::Julia => {
            let project_toml = manifest.root.join(&surface.path).join("Project.toml");
            let text = fs::read_to_string(project_toml).unwrap_or_default();
            let value = text.parse::<toml::Value>().ok();
            value
                .as_ref()
                .and_then(|value| value.get("name"))
                .and_then(toml::Value::as_str)
                .unwrap_or(&surface.name)
                .to_owned()
        }
        PackageLanguage::Swift | PackageLanguage::Lean => surface.name.clone(),
    }
}

fn normalize_repo_relative(repo_root: &Utf8Path, abs: &Utf8Path, field: &str) -> Result<String> {
    if let Ok(path) = abs.strip_prefix(repo_root) {
        return Ok(path.as_str().to_owned());
    }
    let canonical_root = repo_root
        .canonicalize_utf8()
        .with_context(|| format!("failed to canonicalize repo root {repo_root}"))?;
    let canonical_abs = abs
        .canonicalize_utf8()
        .with_context(|| format!("failed to canonicalize {field} {abs}"))?;
    canonical_abs
        .strip_prefix(&canonical_root)
        .map(|path| path.as_str().to_owned())
        .with_context(|| format!("{field} must stay inside repo root"))
}

fn copy_rel_path(repo_root: &Utf8Path, rel_path: &str, dest_root: &Utf8Path) -> Result<()> {
    let source = repo_root.join(rel_path);
    if source.is_dir() {
        copy_dir_recursive(&source, &dest_root.join(rel_path))
    } else if source.is_file() {
        copy_file(&source, &dest_root.join(rel_path))
    } else {
        bail!("missing path while bundling: {rel_path}");
    }
}

fn copy_tracked_include_paths(
    repo_root: &Utf8Path,
    include_paths: &BTreeSet<String>,
    dest_root: &Utf8Path,
) -> Result<Vec<String>> {
    let copied_paths = tracked_files(repo_root)?
        .into_iter()
        .filter(|path| is_included_path(path, include_paths))
        .collect::<BTreeSet<_>>();

    let missing_includes = include_paths
        .iter()
        .filter(|include| {
            !copied_paths
                .iter()
                .any(|path| path_is_within_include(path, include))
        })
        .cloned()
        .collect::<Vec<_>>();
    if !missing_includes.is_empty() {
        bail!(
            "source bundle include paths contain no tracked files:\n{}",
            missing_includes.join("\n")
        );
    }

    for rel in &copied_paths {
        copy_file(&repo_root.join(rel), &dest_root.join(rel))?;
    }
    Ok(copied_paths.into_iter().collect())
}

fn copy_dir_contents(source: &Utf8Path, dest: &Utf8Path) -> Result<()> {
    for entry in fs::read_dir(source).with_context(|| format!("failed to read {source}"))? {
        let entry = entry.with_context(|| format!("failed to read entry in {source}"))?;
        let file_name = entry.file_name();
        let child_source = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow::anyhow!("non-UTF-8 path"))?;
        let child_dest = dest.join(
            file_name
                .to_str()
                .ok_or_else(|| anyhow::anyhow!("non-UTF-8 path component"))?,
        );
        if child_source.is_dir() {
            copy_dir_recursive(&child_source, &child_dest)?;
        } else if child_source.is_file() {
            copy_file(&child_source, &child_dest)?;
        }
    }
    Ok(())
}

fn copy_dir_recursive(source: &Utf8Path, dest: &Utf8Path) -> Result<()> {
    fs::create_dir_all(dest).with_context(|| format!("failed to create {dest}"))?;
    copy_dir_contents(source, dest)
}

fn copy_file(source: &Utf8Path, dest: &Utf8Path) -> Result<()> {
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    fs::copy(source, dest).with_context(|| format!("failed to copy {source} to {dest}"))?;
    Ok(())
}

fn capitalize(value: &str) -> String {
    let mut chars = value.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => value.to_owned(),
    }
}

fn forbidden_tracked_paths(repo_root: &Utf8Path) -> Result<Vec<String>> {
    let mut violations = Vec::new();
    for tracked in tracked_files(repo_root)? {
        if is_forbidden_tracked_path(&tracked) || !is_safe_tracked_envrc(repo_root, &tracked)? {
            violations.push(tracked);
        }
    }
    violations.sort();
    Ok(violations)
}

fn tracked_files(repo_root: &Utf8Path) -> Result<Vec<String>> {
    let jj = Command::new("jj")
        .args(["file", "list"])
        .current_dir(repo_root)
        .output();
    let git = Command::new("git")
        .args(["ls-files", "-z"])
        .current_dir(repo_root)
        .output();

    if repo_root.join(".jj").is_dir() {
        if let Ok(output) = &jj {
            if output.status.success() {
                return parse_jj_tracked_files(output);
            }
        }
    }

    if let Ok(output) = &git {
        if output.status.success() {
            return parse_git_tracked_files(output);
        }
    }

    if let Ok(output) = &jj {
        if output.status.success() {
            return parse_jj_tracked_files(output);
        }
    }

    bail!(
        "tracked-file audit failed via git and jj:\ngit: {}\njj: {}",
        command_error(&git),
        command_error(&jj)
    );
}

fn parse_git_tracked_files(output: &Output) -> Result<Vec<String>> {
    output
        .stdout
        .split(|byte| *byte == 0)
        .filter(|path| !path.is_empty())
        .map(|path| String::from_utf8(path.to_vec()).context("tracked path was not UTF-8"))
        .collect()
}

fn parse_jj_tracked_files(output: &Output) -> Result<Vec<String>> {
    let tracked = String::from_utf8(output.stdout.clone())
        .context("jj file list output was not UTF-8")?
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToOwned::to_owned)
        .collect();
    Ok(tracked)
}

fn command_error(output: &std::io::Result<Output>) -> String {
    match output {
        Ok(output) => String::from_utf8_lossy(&output.stderr).trim().to_owned(),
        Err(error) => error.to_string(),
    }
}

fn find_text_pattern_hits(
    repo_root: &Utf8Path,
    tracked: &[String],
    roots: &[&str],
    excludes: &[&str],
    patterns: &[&str],
) -> Result<Vec<String>> {
    let mut hits = Vec::new();
    for path in tracked {
        if !matches_any_root(path, roots) || matches_any_root(path, excludes) {
            continue;
        }
        let abs = repo_root.join(path);
        if !abs.is_file() {
            continue;
        }
        let Ok(bytes) = fs::read(&abs) else {
            continue;
        };
        let Ok(text) = String::from_utf8(bytes) else {
            continue;
        };
        for pattern in patterns {
            if text.contains(pattern) {
                hits.push(format!("{path}: {pattern}"));
            }
        }
    }
    hits.sort();
    hits.dedup();
    Ok(hits)
}

fn matches_any_root(path: &str, roots: &[&str]) -> bool {
    roots.iter().any(|root| matches_root(path, root))
}

fn matches_root(path: &str, root: &str) -> bool {
    let trimmed = root.trim_end_matches('/');
    path == trimmed || path.starts_with(&format!("{trimmed}/"))
}

fn is_forbidden_tracked_path(path: &str) -> bool {
    let utf8 = Utf8Path::new(path);
    let basename = utf8.file_name().unwrap_or(path);
    path == "generated"
        || path.starts_with("generated/")
        || path == "synthetic-bureau"
        || path.starts_with("synthetic-bureau/")
        || path == "records-bureau"
        || path.starts_with("records-bureau/")
        || (basename.starts_with(".env") && basename != ".envrc")
        || basename.starts_with(".zuliprc")
        || matches!(
            basename,
            "id_rsa" | "id_ed25519" | "id_ecdsa" | "id_dsa" | "known_hosts" | "authorized_keys"
        )
        || utf8
            .components()
            .any(|component| component.as_str() == ".ssh")
}

fn is_safe_tracked_envrc(repo_root: &Utf8Path, path: &str) -> Result<bool> {
    if Utf8Path::new(path).file_name() != Some(".envrc") {
        return Ok(true);
    }
    let text = fs::read_to_string(repo_root.join(path))
        .with_context(|| format!("failed to read tracked direnv file {path}"))?;
    Ok(text
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .all(|line| line == "use flake" || line == "source_env_if_exists .envrc.local"))
}

fn rewrite_bundle_markdown_links(
    stage_dir: &Utf8Path,
    include_paths: &BTreeSet<String>,
) -> Result<()> {
    let mut files = Vec::new();
    collect_markdown_files(stage_dir, stage_dir, &mut files)?;
    let link_regex = Regex::new(r"(?P<prefix>!?\[[^\]]*\]\()(?P<target>[^)\s]+)(?P<suffix>\))")
        .expect("link regex should compile");
    for file in files {
        let repo_rel = file
            .strip_prefix(stage_dir)
            .context("bundle markdown path must stay inside stage dir")?
            .as_str()
            .to_owned();
        let original = fs::read_to_string(&file)
            .with_context(|| format!("failed to read bundle file {file}"))?;
        let rewritten = link_regex.replace_all(&original, |captures: &regex_lite::Captures<'_>| {
            let prefix = captures.name("prefix").map_or("", |m| m.as_str());
            let suffix = captures.name("suffix").map_or("", |m| m.as_str());
            let target = captures.name("target").map_or("", |m| m.as_str());
            let new_target = rewrite_bundle_target(target, &repo_rel, include_paths)
                .unwrap_or_else(|| target.to_owned());
            format!("{prefix}{new_target}{suffix}")
        });
        if rewritten != original {
            fs::write(&file, rewritten.as_ref())
                .with_context(|| format!("failed to rewrite bundle file {file}"))?;
        }
    }
    Ok(())
}

fn collect_markdown_files(
    root: &Utf8Path,
    current: &Utf8Path,
    files: &mut Vec<Utf8PathBuf>,
) -> Result<()> {
    for entry in fs::read_dir(current).with_context(|| format!("failed to read {current}"))? {
        let entry = entry.with_context(|| format!("failed to read entry in {current}"))?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow::anyhow!("bundle path was not UTF-8"))?;
        if path.is_dir() {
            collect_markdown_files(root, &path, files)?;
        } else if path.is_file() && path.extension() == Some("md") && path.starts_with(root) {
            files.push(path);
        }
    }
    Ok(())
}

fn rewrite_bundle_target(
    target: &str,
    source_repo_rel: &str,
    include_paths: &BTreeSet<String>,
) -> Option<String> {
    if target.is_empty()
        || target.starts_with('#')
        || target.starts_with("http://")
        || target.starts_with("https://")
        || target.starts_with("mailto:")
    {
        return None;
    }
    let (path_part, fragment) = match target.split_once('#') {
        Some((path, anchor)) => (path, Some(anchor)),
        None => (target, None),
    };
    let source_dir = Utf8Path::new(source_repo_rel)
        .parent()
        .map_or_else(String::new, |parent| parent.as_str().to_owned());
    let resolved = resolve_repo_relative_target(&source_dir, path_part)?;
    if is_included_path(&resolved, include_paths) {
        return None;
    }
    let suffix = fragment.map_or(String::new(), |anchor| format!("#{anchor}"));
    if resolved == "records-bureau" || resolved.starts_with("records-bureau/") {
        let public_path = resolved
            .strip_prefix("records-bureau/")
            .unwrap_or(resolved.as_str());
        return Some(format!(
            "{RECORDS_ARCHIVE_PUBLIC_URL}/{public_path}{suffix}"
        ));
    }
    Some(format!("{REPO_TREE_URL}/{resolved}{suffix}"))
}

fn resolve_repo_relative_target(source_dir: &str, target: &str) -> Option<String> {
    let mut components: Vec<&str> = Vec::new();
    if !target.starts_with('/') {
        components.extend(source_dir.split('/').filter(|part| !part.is_empty()));
    }
    for part in target.split('/') {
        match part {
            "" | "." => {}
            ".." => {
                components.pop()?;
            }
            value => components.push(value),
        }
    }
    Some(components.join("/"))
}

fn is_included_path(path: &str, include_paths: &BTreeSet<String>) -> bool {
    include_paths
        .iter()
        .any(|include| path_is_within_include(path, include))
}

fn path_is_within_include(path: &str, include: &str) -> bool {
    path == include
        || path
            .strip_prefix(include)
            .is_some_and(|suffix| suffix.starts_with('/'))
}

fn path_relative_to_include(path: &str, include: &str) -> Option<String> {
    if path == include {
        return Some(String::new());
    }
    path.strip_prefix(include)
        .and_then(|suffix| suffix.strip_prefix('/'))
        .map(ToOwned::to_owned)
}

#[cfg(test)]
mod tests {
    use super::{
        bundle_source_surface, find_text_pattern_hits, gate_manifest, is_forbidden_tracked_path,
        is_safe_tracked_envrc, lookup_project, matches_root, materialize_package_surface,
        validate_manifest, validate_release_id,
    };
    use camino::Utf8Path;
    use serde_json::Value;
    use std::fs;
    use std::process::Command;
    use tempfile::TempDir;

    fn write(path: &Utf8Path, content: &str) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(path, content).unwrap();
    }

    fn write_action_evidence(project_root: &Utf8Path, action: &str, status: &str) {
        write(
            &project_root.join(format!("artifacts/evidence/{action}.json")),
            &format!("{{\n  \"action\": \"{action}\",\n  \"status\": \"{status}\"\n}}\n"),
        );
    }

    fn run_git(repo_root: &Utf8Path, args: &[&str]) {
        let output = Command::new("git")
            .args(args)
            .current_dir(repo_root)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "git {:?} failed: {}",
            args,
            String::from_utf8_lossy(&output.stderr)
        );
    }

    fn track_all(repo_root: &Utf8Path) {
        run_git(repo_root, &["init"]);
        run_git(repo_root, &["add", "."]);
    }

    fn archive_entries(archive: &Utf8Path) -> Vec<String> {
        let output = Command::new("tar")
            .args(["-tzf", archive.as_str()])
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "tar list failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        let mut entries = String::from_utf8(output.stdout)
            .unwrap()
            .lines()
            .map(ToOwned::to_owned)
            .collect::<Vec<_>>();
        entries.sort();
        entries
    }

    fn minimal_design_tokens(root: &Utf8Path) {
        write(
            &root.join("addenda/design-tokens/base.toml"),
            r##"
[colors]
ink = "#0b0e14"

[badges.project-status]
dossier = ["concept", "active", "active-writing", "hold"]
addenda = ["concept", "active", "operational", "hold", "archived"]

[badges.project-status.concept]
color = "ink"

[badges.project-status.active]
color = "ink"

[badges.project-status.active-writing]
color = "ink"

[badges.project-status.hold]
color = "ink"

[badges.project-status.operational]
color = "ink"

[badges.project-status.archived]
color = "ink"

[badges.addenda-type]
values = ["tooling", "research", "dataset", "benchmark"]

[badges.addenda-type.tooling]
color = "ink"

[badges.addenda-type.research]
color = "ink"

[badges.addenda-type.dataset]
color = "ink"

[badges.addenda-type.benchmark]
color = "ink"
"##,
        );
        write(&root.join("addenda/design-tokens/web.toml"), "");
    }

    #[test]
    fn bundle_source_surface_writes_evidence_sidecar() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("src/lib.rs"), "pub fn alpha() {}\n");
        write(
            &manifest_path,
            r#"version = 1
license = "MIT"
title = "Alpha"
series = "D-001"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "src"
include_docs = false
"#,
        );
        track_all(repo_root);

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let output_dir = repo_root.join("tmp/releases-check");
        let archive =
            bundle_source_surface(repo_root, &manifest, "source", "r1", Some(&output_dir)).unwrap();
        let evidence_path = output_dir.join("alpha-source-r1.tar.gz.evidence.json");
        assert!(archive.is_file());
        assert!(evidence_path.is_file());
        let card: Value =
            serde_json::from_str(&fs::read_to_string(evidence_path).unwrap()).unwrap();
        assert_eq!(card["action"], "source_bundle");
        assert_eq!(card["series"], "D-001");
        assert_eq!(card["release_id"], "r1");
        assert_eq!(
            card["outputs"][0]["path"],
            "tmp/releases-check/alpha-source-r1.tar.gz"
        );
        assert!(card["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["path"] == "dossiers/alpha/src" && entry["kind"] == "directory"));
    }

    #[test]
    fn bundle_source_surface_omits_untracked_runtime_files() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("src/lib.rs"), "pub fn alpha() {}\n");
        write(
            &manifest_path,
            r#"version = 1
license = "MIT"
title = "Alpha"
series = "D-001"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "."
include_docs = false
"#,
        );
        track_all(repo_root);
        write(
            &project_root.join(".venv/cache.py"),
            "print('runtime cache')\n",
        );
        write(
            &project_root.join("artifacts/evidence/generated.json"),
            "{\"status\":\"ok\"}\n",
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let output_dir = repo_root.join("tmp/releases-check");
        let archive =
            bundle_source_surface(repo_root, &manifest, "source", "r1", Some(&output_dir)).unwrap();
        let entries = archive_entries(&archive);

        assert!(entries
            .iter()
            .any(|entry| entry.ends_with("/dossiers/alpha/src/lib.rs")));
        assert!(entries
            .iter()
            .any(|entry| entry.ends_with("/dossiers/alpha/spctr.toml")));
        assert!(!entries.iter().any(|entry| entry.contains("/.venv/")));
        assert!(!entries
            .iter()
            .any(|entry| entry.contains("/artifacts/evidence/generated.json")));

        let evidence_path = output_dir.join("alpha-source-r1.tar.gz.evidence.json");
        let card: Value =
            serde_json::from_str(&fs::read_to_string(evidence_path).unwrap()).unwrap();
        let source_input = card["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .find(|entry| entry["path"] == "dossiers/alpha")
            .unwrap();
        assert_eq!(source_input["file_count"], 2);
    }

    #[test]
    fn materialize_package_surface_writes_release_evidence() {
        let temp = TempDir::new().unwrap();
        let repo_root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = repo_root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(
            &project_root.join("pkg/pyproject.toml"),
            r#"[project]
name = "alpha-pkg"
version = "0.1.0"
"#,
        );
        write(&project_root.join("pkg/alpha_pkg.py"), "VALUE = 1\n");
        write(
            &manifest_path,
            r#"version = 1
license = "MIT"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[[release.surfaces]]
name = "python"
kind = "package"
publish = false
language = "python"
registry = "pypi"
publish_mode = "subdir"
path = "pkg"
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let output_dir = repo_root.join("tmp/package-check");
        let materialized =
            materialize_package_surface(repo_root, &manifest, "python", &output_dir).unwrap();
        let evidence_path = materialized.join("spctr-release-evidence.json");
        assert!(materialized.is_dir());
        assert!(evidence_path.is_file());
        let card: Value =
            serde_json::from_str(&fs::read_to_string(evidence_path).unwrap()).unwrap();
        assert_eq!(card["action"], "package_surface");
        assert_eq!(card["surface"], "python");
        assert_eq!(card["language"], "python");
        assert_eq!(card["outputs"][0]["path"], "tmp/package-check/alpha-pkg");
        assert!(card["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .any(|entry| entry["path"] == "dossiers/alpha/pkg" && entry["kind"] == "directory"));
    }

    #[test]
    fn release_id_rejects_path_traversal_inputs() {
        assert!(validate_release_id("../oops").is_err());
        assert!(validate_release_id("..").is_err());
        assert!(validate_release_id("nested/id").is_err());
        assert!(validate_release_id(".hidden").is_err());
    }

    #[test]
    fn release_id_accepts_safe_identifiers() {
        assert_eq!(
            validate_release_id("smoke-2026-04-01").unwrap(),
            "smoke-2026-04-01"
        );
        assert_eq!(validate_release_id("v1.0.0").unwrap(), "v1.0.0");
    }

    #[test]
    fn matches_root_handles_files_and_directories() {
        assert!(matches_root("README.md", "README.md"));
        assert!(matches_root("ops/spctr/src/cli.rs", "ops"));
        assert!(matches_root(
            ".github/workflows/site-projects.yml",
            ".github"
        ));
        assert!(!matches_root("site/README.md", "README.md"));
    }

    #[test]
    fn pattern_hits_skip_excluded_paths_and_binary_content() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        fs::create_dir_all(root.join("ops")).unwrap();
        fs::create_dir_all(root.join("dossiers/keep")).unwrap();
        fs::create_dir_all(root.join("dossiers/skip")).unwrap();
        fs::write(root.join("README.md"), "open source").unwrap();
        fs::write(root.join("ops/notes.md"), "records.specterlab.org").unwrap();
        fs::write(root.join("dossiers/keep/file.txt"), "MIT License").unwrap();
        fs::write(root.join("dossiers/skip/file.txt"), "MIT License").unwrap();
        fs::write(root.join("ops/binary.bin"), [0_u8, 159, 146, 150]).unwrap();

        let tracked = vec![
            "README.md".to_owned(),
            "ops/notes.md".to_owned(),
            "dossiers/keep/file.txt".to_owned(),
            "dossiers/skip/file.txt".to_owned(),
            "ops/binary.bin".to_owned(),
        ];
        let hits = find_text_pattern_hits(
            root,
            &tracked,
            &["README.md", "ops", "dossiers"],
            &["dossiers/skip"],
            &["open source", "records.specterlab.org", "MIT License"],
        )
        .unwrap();

        assert_eq!(
            hits,
            vec![
                "README.md: open source".to_owned(),
                "dossiers/keep/file.txt: MIT License".to_owned(),
                "ops/notes.md: records.specterlab.org".to_owned(),
            ]
        );
    }

    #[test]
    fn public_safe_envrc_defaults_are_allowed() {
        assert!(!is_forbidden_tracked_path(".envrc"));
        assert!(!is_forbidden_tracked_path("dossiers/wonton-soup/.envrc"));
        assert!(is_forbidden_tracked_path(".env"));
        assert!(is_forbidden_tracked_path(".env.local"));
        assert!(is_forbidden_tracked_path(".envrc.local"));
        assert!(is_forbidden_tracked_path(
            "dossiers/wonton-soup/.envrc.local"
        ));
    }

    #[test]
    fn envrc_audit_allows_only_flake_bootstrap_lines() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            &root.join(".envrc"),
            "use flake\nsource_env_if_exists .envrc.local\n",
        );
        write(&root.join("dossiers/wonton-soup/.envrc"), "use flake\n");
        write(
            &root.join("dossiers/private/.envrc"),
            "use flake\nexport SPECTER_REMOTE_SSH=host\n",
        );

        assert!(is_safe_tracked_envrc(root, ".envrc").unwrap());
        assert!(is_safe_tracked_envrc(root, "dossiers/wonton-soup/.envrc").unwrap());
        assert!(!is_safe_tracked_envrc(root, "dossiers/private/.envrc").unwrap());
    }

    #[test]
    fn lookup_project_ignores_unrelated_invalid_manifests() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        minimal_design_tokens(root);
        write(
            &root.join("addenda/design-tokens/spctr.toml"),
            r#"version = 1
license = "MIT"
title = "Design Tokens"
summary = "Tokens."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "wip"
"#,
        );
        write(
            &root.join("addenda/poly-morphogenesis/spctr.toml"),
            r#"version = 1
license = ""
title = "Broken"
summary = "Broken."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "wip"
"#,
        );
        write(
            &root.join("dossiers/alpha/spctr.toml"),
            r#"version = 1
license = "MIT"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"
"#,
        );

        let manifest = lookup_project(root, "alpha").unwrap();
        assert_eq!(manifest.slug, "alpha");
    }

    #[test]
    fn candidate_gate_requires_exec_check() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        let manifest_path = root.join("dossiers/alpha/spctr.toml");
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
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = gate_manifest(&manifest);
        assert!(!report.ok);
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "exec.check" && !check.ok));
    }

    #[test]
    fn promoted_gate_requires_smoke_and_build() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("README.md"), "# Alpha\n");
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
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "."
include_docs = false

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["uv", "run", "pytest"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = gate_manifest(&manifest);
        assert!(!report.ok);
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "exec.smoke" && !check.ok));
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "exec.build" && !check.ok));
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "exec.publish" && !check.ok));
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "exec.check.evidence" && !check.ok));
    }

    #[test]
    fn visible_docs_gate_requires_docs_section() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        let manifest_path = root.join("dossiers/alpha/spctr.toml");
        write(
            &manifest_path,
            r#"version = 1
license = "Apache-2.0"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = true
featured = false
publish_docs = true

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["uv", "run", "pytest"]
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = gate_manifest(&manifest);
        assert!(!report.ok);
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "docs.root" && !check.ok));
    }

    #[test]
    fn validate_manifest_static_exec_gates_do_not_require_runtime_evidence() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("README.md"), "# Alpha\n");
        write(&project_root.join("LICENSE"), "license text\n");
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
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "."
include_docs = false

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.exec.smoke]
command = ["python3", "-c", "print('smoke')"]

[spctr.exec.build]
command = ["python3", "-c", "print('build')"]

[spctr.exec.publish]
command = ["python3", "-c", "print('publish')"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        validate_manifest(root, &manifest).unwrap();

        let report = gate_manifest(&manifest);
        assert!(!report.ok);
        assert!(report
            .checks
            .iter()
            .any(|check| check.name == "exec.check.evidence" && !check.ok));
    }

    #[test]
    fn validate_manifest_fails_manifest_gated_project_missing_exec_smoke() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("README.md"), "# Alpha\n");
        write(&project_root.join("LICENSE"), "license text\n");
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
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "."
include_docs = false

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.exec.build]
command = ["python3", "-c", "print('build')"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        );

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let error = validate_manifest(root, &manifest).unwrap_err().to_string();
        assert!(error.contains("exec.smoke"));
    }

    #[test]
    fn promoted_gate_requires_successful_exec_evidence() {
        let temp = TempDir::new().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        let project_root = root.join("dossiers/alpha");
        let manifest_path = project_root.join("spctr.toml");
        write(&project_root.join("README.md"), "# Alpha\n");
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
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "."
include_docs = false

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.exec.smoke]
command = ["python3", "-c", "print('smoke')"]

[spctr.exec.build]
command = ["python3", "-c", "print('build')"]

[spctr.exec.publish]
command = ["python3", "-c", "print('publish')"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        );
        write_action_evidence(&project_root, "check", "ok");
        write_action_evidence(&project_root, "smoke", "failed");
        write_action_evidence(&project_root, "build", "ok");
        write_action_evidence(&project_root, "publish", "ok");

        let manifest = crate::manifest::load_project_manifest(&manifest_path, None).unwrap();
        let report = gate_manifest(&manifest);
        assert!(!report.ok);
        assert!(report.checks.iter().any(|check| {
            check.name == "exec.smoke.evidence"
                && !check.ok
                && check.detail.contains("status failed")
        }));
    }
}
