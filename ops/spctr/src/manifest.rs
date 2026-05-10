use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::Path;
use toml::{Table, Value};

pub const MANIFEST_NAME: &str = "spctr.toml";

pub const REPO_TREE_URL: &str =
    "https://github.com/Specter-Research-Labs/research-registry/tree/main";

const DOSSIER_LABEL_SCOPE: &[&str] = &["expansion"];
const DOSSIER_LABEL_PUBLICATION: &[&str] = &["preprint-pending", "public"];

#[derive(Clone, Debug)]
pub struct Vocabularies {
    pub dossier_statuses: Vec<String>,
    pub addenda_statuses: Vec<String>,
    pub addenda_types: Vec<String>,
}

impl Vocabularies {
    pub fn from_spec(tokens: &crate::design_tokens::DesignTokens) -> Result<Self> {
        let dossier_statuses = crate::design_tokens::badge_statuses_for_kind(tokens, "dossier")?;
        let addenda_statuses = crate::design_tokens::badge_statuses_for_kind(tokens, "addendum")?;
        let addenda_types = crate::design_tokens::badge_type_values(tokens, "addenda-type")?;
        Ok(Self {
            dossier_statuses,
            addenda_statuses,
            addenda_types,
        })
    }

    fn statuses_for(&self, kind: &str) -> &[String] {
        match kind {
            "dossier" => &self.dossier_statuses,
            "addendum" => &self.addenda_statuses,
            _ => &[],
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SiteMetadata {
    pub visible: bool,
    pub featured: bool,
    pub featured_order: Option<u32>,
    pub hub_path: Option<String>,
    pub publish_docs: bool,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RawRootConfig {
    pub path: String,
    pub remote_base: Option<String>,
    pub excludes: Vec<String>,
    pub sync_mode: String,
    pub resolve: Option<String>,
    pub runtime_slug: Option<String>,
    pub project_fallback: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SurfaceConfig {
    pub name: String,
    pub kind: String,
    pub raw_roots: Vec<RawRootConfig>,
    pub local_db_path: Option<String>,
    pub db_raw_root: Option<usize>,
    pub refresh_command: Option<Vec<String>>,
    pub refresh_commands: Option<Vec<Vec<String>>>,
    pub remote_raw_namespace: Option<String>,
    pub remote_snapshot_namespace: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SiteDataConfig {
    pub name: String,
    pub site_path: String,
    pub local_source: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NetworkPolicy {
    Off,
    Bootstrap,
    On,
}

impl NetworkPolicy {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Off => "off",
            Self::Bootstrap => "bootstrap",
            Self::On => "on",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ExecActionConfig {
    pub description: Option<String>,
    pub workdir: Option<String>,
    pub command: Option<Vec<String>>,
    pub commands: Option<Vec<Vec<String>>>,
    pub env: BTreeMap<String, String>,
    pub timeout_sec: Option<u64>,
    pub network: Option<NetworkPolicy>,
    pub requires: Vec<String>,
    pub expected_outputs: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RuntimeConfig {
    pub platforms: Vec<String>,
    pub requires: Vec<String>,
    pub network: Option<NetworkPolicy>,
    pub cache_paths: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CiConfig {
    pub runner: Option<String>,
    pub pull_request: Vec<String>,
    pub push_main: Vec<String>,
    pub nightly: Vec<String>,
    pub nightly_cron: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EvidenceOutputConfig {
    pub name: String,
    pub path: String,
    pub kind: String,
    pub required: bool,
    pub surface: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EvidenceConfig {
    pub card_path: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DocsConfig {
    pub root: String,
    pub landing: Option<String>,
    pub require_frontmatter: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ReleaseStage {
    Wip,
    Candidate,
    Promoted,
}

impl ReleaseStage {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Wip => "wip",
            Self::Candidate => "candidate",
            Self::Promoted => "promoted",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ReleaseSurfaceKind {
    SourceBundle,
    Package,
    ArtifactRelease,
}

impl ReleaseSurfaceKind {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::SourceBundle => "source_bundle",
            Self::Package => "package",
            Self::ArtifactRelease => "artifact_release",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PackageLanguage {
    Python,
    Rust,
    Swift,
    Julia,
    Lean,
}

impl PackageLanguage {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Python => "python",
            Self::Rust => "rust",
            Self::Swift => "swift",
            Self::Julia => "julia",
            Self::Lean => "lean",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PublishMode {
    Subdir,
    MirrorRepo,
}

impl PublishMode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Subdir => "subdir",
            Self::MirrorRepo => "mirror_repo",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ReleaseSurfaceConfig {
    pub name: String,
    pub kind: ReleaseSurfaceKind,
    pub publish: bool,
    pub path: String,
    pub include_docs: bool,
    pub support_paths: Vec<String>,
    pub language: Option<PackageLanguage>,
    pub registry: Option<String>,
    pub distribution_channel: Option<String>,
    pub publish_mode: Option<PublishMode>,
    pub mirror_repo: Option<String>,
    pub source_path: Option<String>,
    pub public_namespace: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ReleaseConfig {
    pub stage: ReleaseStage,
    pub surfaces: Vec<ReleaseSurfaceConfig>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SpctrConfig {
    pub project: String,
    pub default_surface: Option<String>,
    pub surfaces: BTreeMap<String, SurfaceConfig>,
    pub site_data: Vec<SiteDataConfig>,
    pub exec: BTreeMap<String, ExecActionConfig>,
    pub expected_outputs: Vec<EvidenceOutputConfig>,
    pub runtime: Option<RuntimeConfig>,
    pub ci: Option<CiConfig>,
    pub evidence: Option<EvidenceConfig>,
    pub docs: Option<DocsConfig>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProjectManifest {
    pub path: Utf8PathBuf,
    pub root: Utf8PathBuf,
    pub kind: String,
    pub slug: String,
    pub license: String,
    pub title: String,
    pub summary: String,
    pub status: String,
    pub site: SiteMetadata,
    pub labels: BTreeMap<String, String>,
    pub related_dossier: Option<String>,
    pub release: ReleaseConfig,
    pub spctr: Option<SpctrConfig>,
    pub series: Option<String>,
}

fn require_string(value: Option<&Value>, field_name: &str, path: &Utf8Path) -> Result<String> {
    let text = value
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be a non-empty string", path))?
        .trim()
        .to_owned();
    if text.is_empty() {
        bail!("{}: {field_name} must be a non-empty string", path);
    }
    Ok(text)
}

fn require_bool(value: Option<&Value>, field_name: &str, path: &Utf8Path) -> Result<bool> {
    value
        .and_then(Value::as_bool)
        .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be a boolean", path))
}

fn require_relative_path(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<String> {
    let text = require_string(value, field_name, path)?;
    if Path::new(&text).is_absolute() || text.starts_with('~') {
        bail!("{}: {field_name} must be relative, got: {text}", path);
    }
    Ok(text)
}

fn require_project_relative_path(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<String> {
    let text = require_relative_path(value, field_name, path)?;
    if Utf8Path::new(&text)
        .components()
        .any(|component| component == camino::Utf8Component::ParentDir)
    {
        bail!(
            "{}: {field_name} must stay within the project root, got: {text}",
            path
        );
    }
    Ok(text)
}

fn require_repo_relative_path(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<String> {
    let text = require_string(value, field_name, path)?;
    if Path::new(&text).is_absolute() || text.starts_with('~') || text.contains("..") {
        bail!("{}: {field_name} must be repo-relative, got: {text}", path);
    }
    Ok(text)
}

fn ensure_allowed_keys(
    table: &Table,
    allowed: &[&str],
    context: &str,
    path: &Utf8Path,
) -> Result<()> {
    let unknown: Vec<String> = table
        .keys()
        .filter(|key| !allowed.contains(&key.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        bail!(
            "{}: unsupported {context} keys: {}",
            path,
            unknown.join(", ")
        );
    }
    Ok(())
}

fn require_u64(value: Option<&Value>, field_name: &str, path: &Utf8Path) -> Result<u64> {
    let raw = value
        .and_then(Value::as_integer)
        .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be an integer", path))?;
    if raw < 0 {
        bail!("{}: {field_name} must be non-negative", path);
    }
    u64::try_from(raw).map_err(|_| anyhow::anyhow!("{}: {field_name} is out of range", path))
}

fn validate_string_array(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<Vec<String>> {
    match value {
        None => Ok(Vec::new()),
        Some(value) => value
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be an array of strings", path))?
            .iter()
            .enumerate()
            .map(|(idx, item)| require_string(Some(item), &format!("{field_name}[{idx}]"), path))
            .collect(),
    }
}

fn validate_project_relative_path_array(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<Vec<String>> {
    match value {
        None => Ok(Vec::new()),
        Some(value) => value
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be an array of paths", path))?
            .iter()
            .enumerate()
            .map(|(idx, item)| {
                require_project_relative_path(Some(item), &format!("{field_name}[{idx}]"), path)
            })
            .collect(),
    }
}

fn validate_string_map(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<BTreeMap<String, String>> {
    let Some(value) = value else {
        return Ok(BTreeMap::new());
    };
    let table = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be a table of strings", path))?;
    table
        .iter()
        .map(|(key, value)| {
            Ok((
                key.clone(),
                require_string(Some(value), &format!("{field_name}.{key}"), path)?,
            ))
        })
        .collect()
}

fn validate_network_policy(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<Option<NetworkPolicy>> {
    let Some(value) = value else {
        return Ok(None);
    };
    let raw = require_string(Some(value), field_name, path)?;
    let parsed = match raw.as_str() {
        "off" => NetworkPolicy::Off,
        "bootstrap" => NetworkPolicy::Bootstrap,
        "on" => NetworkPolicy::On,
        _ => {
            bail!(
                "{}: {field_name} must be one of [\"off\", \"bootstrap\", \"on\"]",
                path
            )
        }
    };
    Ok(Some(parsed))
}

fn validate_command(value: &Value, field_name: &str, path: &Utf8Path) -> Result<Vec<String>> {
    let array = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("{}: {field_name} must be a non-empty array", path))?;
    if array.is_empty() {
        bail!("{}: {field_name} must be a non-empty array", path);
    }
    array
        .iter()
        .enumerate()
        .map(|(idx, item)| require_string(Some(item), &format!("{field_name}[{idx}]"), path))
        .collect()
}

fn validate_command_list(
    value: &Value,
    field_name: &str,
    path: &Utf8Path,
) -> Result<Vec<Vec<String>>> {
    let outer = value.as_array().ok_or_else(|| {
        anyhow::anyhow!("{}: {field_name} must be a non-empty array of arrays", path)
    })?;
    if outer.is_empty() {
        bail!("{}: {field_name} must be a non-empty array of arrays", path);
    }
    outer
        .iter()
        .enumerate()
        .map(|(idx, item)| validate_command(item, &format!("{field_name}[{idx}]"), path))
        .collect()
}

fn validate_exec_action(name: &str, raw: &Value, path: &Utf8Path) -> Result<ExecActionConfig> {
    let field = format!("spctr.exec.{name}");
    let table = raw
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a table", path))?;
    ensure_allowed_keys(
        table,
        &[
            "description",
            "workdir",
            "command",
            "commands",
            "env",
            "timeout_sec",
            "network",
            "requires",
            "expected_outputs",
            "outputs",
        ],
        &field,
        path,
    )?;
    let description = table
        .get("description")
        .map(|value| require_string(Some(value), &format!("{field}.description"), path))
        .transpose()?;
    let workdir = table
        .get("workdir")
        .map(|value| require_project_relative_path(Some(value), &format!("{field}.workdir"), path))
        .transpose()?;
    let command = table
        .get("command")
        .map(|value| validate_command(value, &format!("{field}.command"), path))
        .transpose()?;
    let commands = table
        .get("commands")
        .map(|value| validate_command_list(value, &format!("{field}.commands"), path))
        .transpose()?;
    if command.is_some() == commands.is_some() {
        bail!(
            "{}: {field} must define exactly one of command or commands",
            path
        );
    }
    Ok(ExecActionConfig {
        description,
        workdir,
        command,
        commands,
        env: validate_string_map(table.get("env"), &format!("{field}.env"), path)?,
        timeout_sec: table
            .get("timeout_sec")
            .map(|value| require_u64(Some(value), &format!("{field}.timeout_sec"), path))
            .transpose()?,
        network: validate_network_policy(table.get("network"), &format!("{field}.network"), path)?,
        requires: validate_string_array(table.get("requires"), &format!("{field}.requires"), path)?,
        expected_outputs: validate_exec_output_names(table, &field, path)?,
    })
}

fn validate_runtime(value: &Value, path: &Utf8Path) -> Result<RuntimeConfig> {
    let field = "spctr.runtime";
    let table = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a table", path))?;
    ensure_allowed_keys(
        table,
        &["platforms", "requires", "network", "cache_paths"],
        field,
        path,
    )?;
    let platforms = validate_string_array(table.get("platforms"), "spctr.runtime.platforms", path)?;
    for platform in &platforms {
        if platform != "macos" && platform != "linux" {
            bail!(
                "{}: spctr.runtime.platforms entries must be one of [\"macos\", \"linux\"]",
                path
            );
        }
    }
    Ok(RuntimeConfig {
        platforms,
        requires: validate_string_array(table.get("requires"), "spctr.runtime.requires", path)?,
        network: validate_network_policy(table.get("network"), "spctr.runtime.network", path)?,
        cache_paths: validate_project_relative_path_array(
            table.get("cache_paths"),
            "spctr.runtime.cache_paths",
            path,
        )?,
    })
}

fn validate_ci(value: &Value, path: &Utf8Path) -> Result<CiConfig> {
    let field = "spctr.ci";
    let table = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a table", path))?;
    ensure_allowed_keys(
        table,
        &[
            "runner",
            "pull_request",
            "push_main",
            "nightly",
            "nightly_cron",
        ],
        field,
        path,
    )?;
    Ok(CiConfig {
        runner: table
            .get("runner")
            .map(|value| require_string(Some(value), "spctr.ci.runner", path))
            .transpose()?,
        pull_request: validate_string_array(
            table.get("pull_request"),
            "spctr.ci.pull_request",
            path,
        )?,
        push_main: validate_string_array(table.get("push_main"), "spctr.ci.push_main", path)?,
        nightly: validate_string_array(table.get("nightly"), "spctr.ci.nightly", path)?,
        nightly_cron: table
            .get("nightly_cron")
            .map(|value| validate_github_cron(Some(value), "spctr.ci.nightly_cron", path))
            .transpose()?,
    })
}

fn validate_exec_output_names(table: &Table, field: &str, path: &Utf8Path) -> Result<Vec<String>> {
    if table.get("outputs").is_some() {
        bail!(
            "{}: {field}.outputs was removed; use {field}.expected_outputs",
            path
        );
    }
    validate_string_array(
        table.get("expected_outputs"),
        &format!("{field}.expected_outputs"),
        path,
    )
}

fn validate_expected_output_list(
    value: Option<&Value>,
    field: &str,
    path: &Utf8Path,
) -> Result<Vec<EvidenceOutputConfig>> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let array = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be an array of tables", path))?;
    let mut seen = BTreeSet::new();
    let mut outputs = Vec::with_capacity(array.len());
    for (idx, item) in array.iter().enumerate() {
        let entry = item
            .as_table()
            .ok_or_else(|| anyhow::anyhow!("{}: {field}[{idx}] must be a table", path))?;
        let entry_field = format!("{field}[{idx}]");
        ensure_allowed_keys(
            entry,
            &["name", "path", "kind", "required", "surface"],
            &entry_field,
            path,
        )?;
        let name = require_string(entry.get("name"), &format!("{entry_field}.name"), path)?;
        if !seen.insert(name.clone()) {
            bail!("{}: duplicate {field} name '{name}'", path);
        }
        outputs.push(EvidenceOutputConfig {
            name,
            path: require_project_relative_path(
                entry.get("path"),
                &format!("{entry_field}.path"),
                path,
            )?,
            kind: require_string(entry.get("kind"), &format!("{entry_field}.kind"), path)?,
            required: require_bool(
                entry.get("required"),
                &format!("{entry_field}.required"),
                path,
            )?,
            surface: entry
                .get("surface")
                .map(|value| require_string(Some(value), &format!("{entry_field}.surface"), path))
                .transpose()?,
        });
    }
    Ok(outputs)
}

fn validate_expected_outputs(
    canonical: Option<&Value>,
    path: &Utf8Path,
) -> Result<Vec<EvidenceOutputConfig>> {
    validate_expected_output_list(canonical, "spctr.expected_outputs", path)
}

fn validate_evidence(value: &Value, path: &Utf8Path) -> Result<EvidenceConfig> {
    let field = "spctr.evidence";
    let table = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a table", path))?;
    if table.get("outputs").is_some() {
        bail!(
            "{}: spctr.evidence.outputs was removed; use [[spctr.expected_outputs]]",
            path
        );
    }
    ensure_allowed_keys(table, &["card_path"], field, path)?;
    let card_path = table
        .get("card_path")
        .map(|value| require_project_relative_path(Some(value), "spctr.evidence.card_path", path))
        .transpose()?;
    Ok(EvidenceConfig { card_path })
}

fn validate_docs(value: &Value, path: &Utf8Path) -> Result<DocsConfig> {
    let field = "spctr.docs";
    let table = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a table", path))?;
    ensure_allowed_keys(
        table,
        &["root", "landing", "require_frontmatter"],
        field,
        path,
    )?;
    Ok(DocsConfig {
        root: require_project_relative_path(table.get("root"), "spctr.docs.root", path)?,
        landing: table
            .get("landing")
            .map(|value| require_project_relative_path(Some(value), "spctr.docs.landing", path))
            .transpose()?,
        require_frontmatter: match table.get("require_frontmatter") {
            Some(value) => require_bool(Some(value), "spctr.docs.require_frontmatter", path)?,
            None => false,
        },
    })
}

fn validate_spctr_internal_consistency(spctr: &SpctrConfig, path: &Utf8Path) -> Result<()> {
    let evidence_outputs: BTreeSet<&str> = spctr
        .expected_outputs
        .iter()
        .map(|output| output.name.as_str())
        .collect();
    for (action_name, action) in &spctr.exec {
        for output_name in &action.expected_outputs {
            if !evidence_outputs.contains(output_name.as_str()) {
                bail!(
                    "{}: spctr.exec.{action_name}.expected_outputs references unknown output '{output_name}'",
                    path
                );
            }
        }
    }
    if let Some(ci) = &spctr.ci {
        for (lane, actions) in [
            ("pull_request", &ci.pull_request),
            ("push_main", &ci.push_main),
            ("nightly", &ci.nightly),
        ] {
            for action_name in actions {
                if !spctr.exec.contains_key(action_name) {
                    bail!(
                        "{}: spctr.ci.{lane} references unknown exec action '{action_name}'",
                        path
                    );
                }
            }
        }
        if ci.nightly_cron.is_some() && ci.nightly.is_empty() {
            bail!(
                "{}: spctr.ci.nightly_cron requires at least one spctr.ci.nightly action",
                path
            );
        }
    }
    Ok(())
}

fn validate_github_cron(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<String> {
    let cron = require_string(value, field_name, path)?;
    if cron.split_whitespace().count() != 5 {
        bail!(
            "{}: {field_name} must be a five-field GitHub Actions cron expression",
            path
        );
    }
    Ok(cron)
}

fn validate_spctr_release_references(
    spctr: &SpctrConfig,
    release: &ReleaseConfig,
    path: &Utf8Path,
) -> Result<()> {
    let release_surface_names: BTreeSet<&str> = release
        .surfaces
        .iter()
        .map(|surface| surface.name.as_str())
        .collect();
    for output in &spctr.expected_outputs {
        if let Some(surface) = &output.surface {
            if !release_surface_names.contains(surface.as_str()) {
                bail!(
                    "{}: spctr.expected_outputs entry '{}' references unknown release surface '{}'",
                    path,
                    output.name,
                    surface
                );
            }
        }
    }
    Ok(())
}

fn validate_site(kind: &str, value: Option<&Value>, path: &Utf8Path) -> Result<SiteMetadata> {
    let site = value
        .and_then(Value::as_table)
        .ok_or_else(|| anyhow::anyhow!("{}: site must be a table", path))?;
    ensure_allowed_keys(
        site,
        &[
            "visible",
            "featured",
            "featured_order",
            "hub_path",
            "publish_docs",
        ],
        "site",
        path,
    )?;
    let visible = require_bool(site.get("visible"), "site.visible", path)?;
    let featured = site
        .get("featured")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let raw_order = site.get("featured_order").and_then(Value::as_integer);
    let featured_order;
    if featured {
        if !visible {
            bail!("{}: site.featured requires site.visible = true", path);
        }
        let order = raw_order.unwrap_or(0);
        if order < 1 {
            bail!("{}: site.featured_order must be an integer >= 1", path);
        }
        featured_order =
            Some(u32::try_from(order).map_err(|_| {
                anyhow::anyhow!("{}: site.featured_order out of range: {order}", path)
            })?);
    } else {
        if raw_order.is_some() {
            bail!(
                "{}: site.featured_order requires site.featured = true",
                path
            );
        }
        featured_order = None;
    }
    let hub_path = if site.get("hub_path").is_some() {
        if kind != "dossier" {
            bail!("{}: site.hub_path is only valid for dossiers", path);
        }
        Some(require_relative_path(
            site.get("hub_path"),
            "site.hub_path",
            path,
        )?)
    } else {
        None
    };
    let publish_docs = site
        .get("publish_docs")
        .and_then(Value::as_bool)
        .unwrap_or(true);
    Ok(SiteMetadata {
        visible,
        featured,
        featured_order,
        hub_path,
        publish_docs,
    })
}

fn validate_labels(
    kind: &str,
    value: Option<&Value>,
    path: &Utf8Path,
    vocabs: Option<&Vocabularies>,
) -> Result<BTreeMap<String, String>> {
    let Some(labels) = value else {
        return Ok(BTreeMap::new());
    };
    let table = labels
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: labels must be a table", path))?;
    match kind {
        "dossier" => {
            ensure_allowed_keys(table, &["scope", "publication"], "labels for dossier", path)?;
        }
        "addendum" => ensure_allowed_keys(table, &["type"], "labels for addendum", path)?,
        _ => bail!("{}: unsupported project kind: {kind}", path),
    }
    let mut parsed = BTreeMap::new();
    for (key, raw) in table {
        let text = raw
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("{}: labels.{key} must be a string", path))?;
        match (kind, key.as_str()) {
            ("dossier", "scope") => {
                if !DOSSIER_LABEL_SCOPE.contains(&text) {
                    bail!(
                        "{}: labels.{key} must be one of {:?}",
                        path,
                        DOSSIER_LABEL_SCOPE
                    );
                }
            }
            ("dossier", "publication") => {
                if !DOSSIER_LABEL_PUBLICATION.contains(&text) {
                    bail!(
                        "{}: labels.{key} must be one of {:?}",
                        path,
                        DOSSIER_LABEL_PUBLICATION
                    );
                }
            }
            ("addendum", "type") => {
                if let Some(v) = vocabs {
                    if !v.addenda_types.iter().any(|t| t == text) {
                        bail!(
                            "{}: labels.{key} must be one of {:?}",
                            path,
                            v.addenda_types
                        );
                    }
                }
            }
            _ => {}
        }
        parsed.insert(key.clone(), text.to_owned());
    }
    Ok(parsed)
}

fn validate_relations(
    kind: &str,
    value: Option<&Value>,
    path: &Utf8Path,
) -> Result<Option<String>> {
    let Some(relations) = value else {
        return Ok(None);
    };
    if kind != "addendum" {
        bail!("{}: relations are only supported for addenda", path);
    }
    let table = relations
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: relations must be a table", path))?;
    ensure_allowed_keys(table, &["dossier"], "relation", path)?;
    if table.get("dossier").is_some() {
        let dossier = require_string(table.get("dossier"), "relations.dossier", path)?;
        return Ok(Some(dossier));
    }
    Ok(None)
}

fn validate_raw_root_item(
    name: &str,
    idx: usize,
    item: &Value,
    path: &Utf8Path,
) -> Result<RawRootConfig> {
    let field = format!("spctr.surfaces.{name}.raw_roots[{idx}]");
    if let Some(s) = item.as_str() {
        let text = s.trim();
        if text.is_empty() {
            bail!("{}: {field} must be a non-empty string", path);
        }
        if Path::new(text).is_absolute() || text.starts_with('~') {
            bail!("{}: {field} must be relative, got: {text}", path);
        }
        return Ok(RawRootConfig {
            path: text.to_owned(),
            remote_base: None,
            excludes: Vec::new(),
            sync_mode: "mirror".to_owned(),
            resolve: None,
            runtime_slug: None,
            project_fallback: None,
        });
    }
    let table = item
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a string or table", path))?;
    let allowed = [
        "path",
        "remote_base",
        "excludes",
        "sync_mode",
        "resolve",
        "runtime_slug",
        "project_fallback",
    ];
    ensure_allowed_keys(table, &allowed, &field, path)?;
    let root_path = require_relative_path(table.get("path"), &format!("{field}.path"), path)?;
    let remote_base = table
        .get("remote_base")
        .map(|v| require_string(Some(v), &format!("{field}.remote_base"), path))
        .transpose()?;
    if let Some(ref base) = remote_base {
        if base != "logs" && base != "artifacts" {
            bail!(
                "{}: {field}.remote_base must be 'logs' or 'artifacts'",
                path
            );
        }
    }
    let excludes = match table.get("excludes") {
        None => Vec::new(),
        Some(v) => v
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("{}: {field}.excludes must be an array", path))?
            .iter()
            .enumerate()
            .map(|(i, item)| require_string(Some(item), &format!("{field}.excludes[{i}]"), path))
            .collect::<Result<Vec<_>>>()?,
    };
    let sync_mode = table
        .get("sync_mode")
        .map(|v| require_string(Some(v), &format!("{field}.sync_mode"), path))
        .transpose()?
        .unwrap_or_else(|| "mirror".to_owned());
    if sync_mode != "mirror" && sync_mode != "upsert" {
        bail!("{}: {field}.sync_mode must be 'mirror' or 'upsert'", path);
    }
    let resolve = table
        .get("resolve")
        .map(|v| require_string(Some(v), &format!("{field}.resolve"), path))
        .transpose()?;
    if let Some(ref r) = resolve {
        if r != "runtime" {
            bail!("{}: {field}.resolve must be 'runtime'", path);
        }
    }
    let runtime_slug = table
        .get("runtime_slug")
        .map(|v| require_string(Some(v), &format!("{field}.runtime_slug"), path))
        .transpose()?;
    let project_fallback = table
        .get("project_fallback")
        .map(|v| require_relative_path(Some(v), &format!("{field}.project_fallback"), path))
        .transpose()?;
    if resolve.as_deref() == Some("runtime") && runtime_slug.is_none() {
        bail!(
            "{}: {field}.runtime_slug is required when resolve = \"runtime\"",
            path
        );
    }
    if resolve.as_deref() == Some("runtime") && project_fallback.is_none() {
        bail!(
            "{}: {field}.project_fallback is required when resolve = \"runtime\"",
            path
        );
    }
    if resolve.is_none() && runtime_slug.is_some() {
        bail!(
            "{}: {field}.runtime_slug requires resolve = \"runtime\"",
            path
        );
    }
    if resolve.is_none() && project_fallback.is_some() {
        bail!(
            "{}: {field}.project_fallback requires resolve = \"runtime\"",
            path
        );
    }
    Ok(RawRootConfig {
        path: root_path,
        remote_base,
        excludes,
        sync_mode,
        resolve,
        runtime_slug,
        project_fallback,
    })
}

fn validate_refresh_commands(
    name: &str,
    value: &Value,
    path: &Utf8Path,
) -> Result<Vec<Vec<String>>> {
    let field = format!("spctr.surfaces.{name}.refresh_commands");
    let outer = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a non-empty array of arrays", path))?;
    if outer.is_empty() {
        bail!("{}: {field} must be a non-empty array of arrays", path);
    }
    outer
        .iter()
        .enumerate()
        .map(|(i, inner_val)| {
            let inner = inner_val.as_array().ok_or_else(|| {
                anyhow::anyhow!(
                    "{}: {field}[{i}] must be a non-empty array of strings",
                    path
                )
            })?;
            if inner.is_empty() {
                bail!(
                    "{}: {field}[{i}] must be a non-empty array of strings",
                    path
                );
            }
            inner
                .iter()
                .enumerate()
                .map(|(j, item)| require_string(Some(item), &format!("{field}[{i}][{j}]"), path))
                .collect::<Result<Vec<_>>>()
        })
        .collect::<Result<Vec<_>>>()
}

fn validate_surface(name: &str, raw: &Value, path: &Utf8Path) -> Result<SurfaceConfig> {
    let table = raw
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: spctr.surfaces.{name} must be a table", path))?;
    let allowed = [
        "kind",
        "raw_roots",
        "local_db_path",
        "db_raw_root",
        "refresh_command",
        "refresh_commands",
        "remote_raw_namespace",
        "remote_snapshot_namespace",
    ];
    let unknown: Vec<String> = table
        .keys()
        .filter(|key| !allowed.contains(&key.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        bail!(
            "{}: unsupported spctr.surfaces.{name} keys: {}",
            path,
            unknown.join(", ")
        );
    }
    let kind = require_string(
        table.get("kind"),
        &format!("spctr.surfaces.{name}.kind"),
        path,
    )?;
    if kind != "raw" && kind != "raw_plus_db" {
        bail!(
            "{}: spctr.surfaces.{name}.kind must be 'raw' or 'raw_plus_db'",
            path
        );
    }
    let raw_roots = match table.get("raw_roots") {
        None => Vec::new(),
        Some(value) => {
            let array = value.as_array().ok_or_else(|| {
                anyhow::anyhow!("{}: spctr.surfaces.{name}.raw_roots must be an array", path)
            })?;
            array
                .iter()
                .enumerate()
                .map(|(idx, item)| validate_raw_root_item(name, idx, item, path))
                .collect::<Result<Vec<_>>>()?
        }
    };
    let local_db_path = table
        .get("local_db_path")
        .map(|value| {
            require_relative_path(
                Some(value),
                &format!("spctr.surfaces.{name}.local_db_path"),
                path,
            )
        })
        .transpose()?;
    let db_raw_root = table
        .get("db_raw_root")
        .map(|value| {
            value.as_integer().ok_or_else(|| {
                anyhow::anyhow!(
                    "{}: spctr.surfaces.{name}.db_raw_root must be an integer",
                    path
                )
            })
        })
        .transpose()?
        .map(|v| {
            usize::try_from(v).map_err(|_| {
                anyhow::anyhow!(
                    "{}: spctr.surfaces.{name}.db_raw_root must be non-negative",
                    path
                )
            })
        })
        .transpose()?;
    if let Some(idx) = db_raw_root {
        if idx >= raw_roots.len() {
            bail!(
                "{}: spctr.surfaces.{name}.db_raw_root ({idx}) is out of range (have {} raw roots)",
                path,
                raw_roots.len()
            );
        }
    }
    let refresh_command = match table.get("refresh_command") {
        None => None,
        Some(value) => {
            let array = value.as_array().ok_or_else(|| {
                anyhow::anyhow!(
                    "{}: spctr.surfaces.{name}.refresh_command must be a non-empty array",
                    path
                )
            })?;
            if array.is_empty() {
                bail!(
                    "{}: spctr.surfaces.{name}.refresh_command must be a non-empty array",
                    path
                );
            }
            Some(
                array
                    .iter()
                    .enumerate()
                    .map(|(idx, item)| {
                        require_string(
                            Some(item),
                            &format!("spctr.surfaces.{name}.refresh_command[{idx}]"),
                            path,
                        )
                    })
                    .collect::<Result<Vec<_>>>()?,
            )
        }
    };
    let refresh_commands = table
        .get("refresh_commands")
        .map(|value| validate_refresh_commands(name, value, path))
        .transpose()?;
    if refresh_command.is_some() && refresh_commands.is_some() {
        bail!(
            "{}: spctr.surfaces.{name} must not define both refresh_command and refresh_commands",
            path
        );
    }
    let remote_raw_namespace = table
        .get("remote_raw_namespace")
        .map(|value| {
            require_string(
                Some(value),
                &format!("spctr.surfaces.{name}.remote_raw_namespace"),
                path,
            )
        })
        .transpose()?;
    let remote_snapshot_namespace = table
        .get("remote_snapshot_namespace")
        .map(|value| {
            require_string(
                Some(value),
                &format!("spctr.surfaces.{name}.remote_snapshot_namespace"),
                path,
            )
        })
        .transpose()?;
    if raw_roots.is_empty() {
        bail!("{}: spctr.surfaces.{name} must define raw_roots", path);
    }
    if kind == "raw_plus_db" && local_db_path.is_none() {
        bail!(
            "{}: spctr.surfaces.{name} must define local_db_path for raw_plus_db",
            path
        );
    }
    Ok(SurfaceConfig {
        name: name.to_owned(),
        kind,
        raw_roots,
        local_db_path,
        db_raw_root,
        refresh_command,
        refresh_commands,
        remote_raw_namespace,
        remote_snapshot_namespace,
    })
}

fn validate_spctr(
    slug: &str,
    value: Option<&Value>,
    path: &Utf8Path,
) -> Result<Option<SpctrConfig>> {
    let Some(spctr) = value else {
        return Ok(None);
    };
    let table = spctr
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: spctr must be a table", path))?;
    ensure_allowed_keys(
        table,
        &[
            "project",
            "default_surface",
            "surfaces",
            "site_data",
            "exec",
            "expected_outputs",
            "runtime",
            "ci",
            "evidence",
            "docs",
        ],
        "spctr",
        path,
    )?;
    let project = match table.get("project") {
        Some(value) => require_string(Some(value), "spctr.project", path)?,
        None => slug.to_owned(),
    };
    let default_surface = table
        .get("default_surface")
        .map(|value| require_string(Some(value), "spctr.default_surface", path))
        .transpose()?;
    let surfaces_table = match table.get("surfaces") {
        None => Table::new(),
        Some(value) => value
            .as_table()
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("{}: spctr.surfaces must be a table", path))?,
    };
    let mut surfaces = BTreeMap::new();
    for (name, raw_surface) in surfaces_table {
        surfaces.insert(name.clone(), validate_surface(&name, &raw_surface, path)?);
    }
    if let Some(default_name) = &default_surface {
        if !surfaces.contains_key(default_name) {
            bail!("{}: spctr.default_surface references unknown surface", path);
        }
    }
    let site_data = match table.get("site_data") {
        None => Vec::new(),
        Some(value) => {
            let array = value.as_array().ok_or_else(|| {
                anyhow::anyhow!("{}: spctr.site_data must be an array of tables", path)
            })?;
            array
                .iter()
                .enumerate()
                .map(|(idx, item)| {
                    let entry = item.as_table().ok_or_else(|| {
                        anyhow::anyhow!("{}: spctr.site_data[{idx}] must be a table", path)
                    })?;
                    let field = format!("spctr.site_data[{idx}]");
                    ensure_allowed_keys(
                        entry,
                        &["name", "site_path", "local_source"],
                        &field,
                        path,
                    )?;
                    Ok(SiteDataConfig {
                        name: require_string(entry.get("name"), &format!("{field}.name"), path)?,
                        site_path: require_relative_path(
                            entry.get("site_path"),
                            &format!("{field}.site_path"),
                            path,
                        )?,
                        local_source: require_relative_path(
                            entry.get("local_source"),
                            &format!("{field}.local_source"),
                            path,
                        )?,
                    })
                })
                .collect::<Result<Vec<_>>>()?
        }
    };
    let exec = match table.get("exec") {
        None => BTreeMap::new(),
        Some(value) => {
            let actions = value
                .as_table()
                .cloned()
                .ok_or_else(|| anyhow::anyhow!("{}: spctr.exec must be a table", path))?;
            let mut exec = BTreeMap::new();
            for (name, raw_action) in actions {
                exec.insert(
                    name.clone(),
                    validate_exec_action(&name, &raw_action, path)?,
                );
            }
            exec
        }
    };
    let expected_outputs = validate_expected_outputs(table.get("expected_outputs"), path)?;
    let runtime = table
        .get("runtime")
        .map(|value| validate_runtime(value, path))
        .transpose()?;
    let ci = table
        .get("ci")
        .map(|value| validate_ci(value, path))
        .transpose()?;
    let evidence = table
        .get("evidence")
        .map(|value| validate_evidence(value, path))
        .transpose()?;
    let docs = table
        .get("docs")
        .map(|value| validate_docs(value, path))
        .transpose()?;
    let spctr = SpctrConfig {
        project,
        default_surface,
        surfaces,
        site_data,
        exec,
        expected_outputs,
        runtime,
        ci,
        evidence,
        docs,
    };
    validate_spctr_internal_consistency(&spctr, path)?;
    Ok(Some(spctr))
}

fn validate_series(kind: &str, value: Option<&Value>, path: &Utf8Path) -> Result<Option<String>> {
    let Some(raw) = value else {
        return Ok(None);
    };
    let text = raw
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("{}: series must be a string", path))?
        .trim();
    if text.is_empty() {
        bail!("{}: series must be a non-empty string", path);
    }
    let expected_prefix = match kind {
        "dossier" => "D-",
        "addendum" => "A-",
        _ => bail!("{}: unsupported kind for series: {kind}", path),
    };
    if !text.starts_with(expected_prefix) {
        bail!(
            "{}: series for {kind} must start with '{expected_prefix}', got '{text}'",
            path
        );
    }
    let num_part = &text[2..];
    if num_part.is_empty() || !num_part.chars().all(|c| c.is_ascii_digit()) {
        bail!("{}: series must match [DA]-<number>, got '{text}'", path);
    }
    Ok(Some(text.to_owned()))
}

fn validate_release_stage(value: Option<&Value>, path: &Utf8Path) -> Result<ReleaseStage> {
    let text = require_string(value, "release.stage", path)?;
    match text.as_str() {
        "wip" => Ok(ReleaseStage::Wip),
        "candidate" => Ok(ReleaseStage::Candidate),
        "promoted" => Ok(ReleaseStage::Promoted),
        _ => bail!(
            "{}: release.stage must be one of [\"wip\", \"candidate\", \"promoted\"]",
            path
        ),
    }
}

fn validate_release_surface_kind(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<ReleaseSurfaceKind> {
    let text = require_string(value, field_name, path)?;
    match text.as_str() {
        "source_bundle" => Ok(ReleaseSurfaceKind::SourceBundle),
        "package" => Ok(ReleaseSurfaceKind::Package),
        "artifact_release" => Ok(ReleaseSurfaceKind::ArtifactRelease),
        _ => bail!(
            "{}: {field_name} must be one of [\"source_bundle\", \"package\", \"artifact_release\"]",
            path
        ),
    }
}

fn validate_package_language(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<PackageLanguage> {
    let text = require_string(value, field_name, path)?;
    match text.as_str() {
        "python" => Ok(PackageLanguage::Python),
        "rust" => Ok(PackageLanguage::Rust),
        "swift" => Ok(PackageLanguage::Swift),
        "julia" => Ok(PackageLanguage::Julia),
        "lean" => Ok(PackageLanguage::Lean),
        _ => bail!(
            "{}: {field_name} must be one of [\"python\", \"rust\", \"swift\", \"julia\", \"lean\"]",
            path
        ),
    }
}

fn validate_publish_mode(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> Result<PublishMode> {
    let text = require_string(value, field_name, path)?;
    match text.as_str() {
        "subdir" => Ok(PublishMode::Subdir),
        "mirror_repo" => Ok(PublishMode::MirrorRepo),
        _ => bail!(
            "{}: {field_name} must be one of [\"subdir\", \"mirror_repo\"]",
            path
        ),
    }
}

fn validate_release_surface(
    raw: &Value,
    idx: usize,
    path: &Utf8Path,
) -> Result<ReleaseSurfaceConfig> {
    let field = format!("release.surfaces[{idx}]");
    let table = raw
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{}: {field} must be a table", path))?;
    ensure_allowed_keys(
        table,
        &[
            "name",
            "kind",
            "publish",
            "path",
            "include_docs",
            "support_paths",
            "language",
            "registry",
            "distribution_channel",
            "publish_mode",
            "mirror_repo",
            "source_path",
            "public_namespace",
        ],
        &field,
        path,
    )?;
    let name = require_string(table.get("name"), &format!("{field}.name"), path)?;
    let kind = validate_release_surface_kind(table.get("kind"), &format!("{field}.kind"), path)?;
    let publish = require_bool(table.get("publish"), &format!("{field}.publish"), path)?;
    let rel_path = table
        .get("path")
        .map(|value| require_project_relative_path(Some(value), &format!("{field}.path"), path))
        .transpose()?
        .unwrap_or_else(|| ".".to_owned());
    let include_docs = table
        .get("include_docs")
        .map(|value| require_bool(Some(value), &format!("{field}.include_docs"), path))
        .transpose()?
        .unwrap_or(kind == ReleaseSurfaceKind::SourceBundle);
    let support_paths = match table.get("support_paths") {
        None => Vec::new(),
        Some(value) => value
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("{}: {field}.support_paths must be an array", path))?
            .iter()
            .enumerate()
            .map(|(i, item)| {
                require_repo_relative_path(Some(item), &format!("{field}.support_paths[{i}]"), path)
            })
            .collect::<Result<Vec<_>>>()?,
    };
    let language = table
        .get("language")
        .map(|value| validate_package_language(Some(value), &format!("{field}.language"), path))
        .transpose()?;
    let registry = table
        .get("registry")
        .map(|value| require_string(Some(value), &format!("{field}.registry"), path))
        .transpose()?;
    let distribution_channel = table
        .get("distribution_channel")
        .map(|value| require_string(Some(value), &format!("{field}.distribution_channel"), path))
        .transpose()?;
    let publish_mode = table
        .get("publish_mode")
        .map(|value| validate_publish_mode(Some(value), &format!("{field}.publish_mode"), path))
        .transpose()?;
    let mirror_repo = table
        .get("mirror_repo")
        .map(|value| require_string(Some(value), &format!("{field}.mirror_repo"), path))
        .transpose()?;
    let source_path = table
        .get("source_path")
        .map(|value| {
            require_project_relative_path(Some(value), &format!("{field}.source_path"), path)
        })
        .transpose()?;
    let public_namespace = table
        .get("public_namespace")
        .map(|value| {
            require_repo_relative_path(Some(value), &format!("{field}.public_namespace"), path)
        })
        .transpose()?;

    match kind {
        ReleaseSurfaceKind::SourceBundle => {
            if language.is_some()
                || registry.is_some()
                || distribution_channel.is_some()
                || publish_mode.is_some()
                || mirror_repo.is_some()
                || source_path.is_some()
                || public_namespace.is_some()
            {
                bail!(
                    "{}: {field} source_bundle surfaces may only define name, kind, publish, path, include_docs, and support_paths",
                    path
                );
            }
        }
        ReleaseSurfaceKind::Package => {
            if source_path.is_some() || public_namespace.is_some() {
                bail!(
                    "{}: {field} package surfaces must not define source_path or public_namespace",
                    path
                );
            }
            let Some(mode) = publish_mode else {
                bail!(
                    "{}: {field}.publish_mode is required for package surfaces",
                    path
                );
            };
            if language.is_none() {
                bail!(
                    "{}: {field}.language is required for package surfaces",
                    path
                );
            }
            if registry.is_none() && distribution_channel.is_none() {
                bail!(
                    "{}: {field} package surfaces require registry or distribution_channel",
                    path
                );
            }
            if mode == PublishMode::MirrorRepo && mirror_repo.is_none() {
                bail!(
                    "{}: {field}.mirror_repo is required when publish_mode = \"mirror_repo\"",
                    path
                );
            }
            if mode == PublishMode::Subdir && mirror_repo.is_some() {
                bail!(
                    "{}: {field}.mirror_repo requires publish_mode = \"mirror_repo\"",
                    path
                );
            }
        }
        ReleaseSurfaceKind::ArtifactRelease => {
            if include_docs
                || !support_paths.is_empty()
                || language.is_some()
                || registry.is_some()
                || distribution_channel.is_some()
                || publish_mode.is_some()
                || mirror_repo.is_some()
            {
                bail!(
                    "{}: {field} artifact_release surfaces may only define name, kind, publish, path, source_path, and public_namespace",
                    path
                );
            }
            if source_path.is_none() || public_namespace.is_none() {
                bail!(
                    "{}: {field} artifact_release surfaces require source_path and public_namespace",
                    path
                );
            }
        }
    }

    Ok(ReleaseSurfaceConfig {
        name,
        kind,
        publish,
        path: rel_path,
        include_docs,
        support_paths,
        language,
        registry,
        distribution_channel,
        publish_mode,
        mirror_repo,
        source_path,
        public_namespace,
    })
}

fn validate_release(value: Option<&Value>, path: &Utf8Path) -> Result<ReleaseConfig> {
    let release = value
        .and_then(Value::as_table)
        .ok_or_else(|| anyhow::anyhow!("{}: release must be a table", path))?;
    ensure_allowed_keys(release, &["stage", "surfaces"], "release", path)?;
    let stage = validate_release_stage(release.get("stage"), path)?;
    let surfaces = match release.get("surfaces") {
        None => Vec::new(),
        Some(value) => value
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("{}: release.surfaces must be an array", path))?
            .iter()
            .enumerate()
            .map(|(idx, item)| validate_release_surface(item, idx, path))
            .collect::<Result<Vec<_>>>()?,
    };
    Ok(ReleaseConfig { stage, surfaces })
}

pub fn load_project_manifest(
    path: &Utf8Path,
    vocabs: Option<&Vocabularies>,
) -> Result<ProjectManifest> {
    if !path.exists() {
        bail!("missing manifest: {path}");
    }
    let text = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let value = text
        .parse::<Value>()
        .with_context(|| format!("invalid TOML in {path}"))?;
    let raw = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("{path}: manifest root must be a table"))?;
    let allowed_top = [
        "version",
        "license",
        "title",
        "summary",
        "status",
        "site",
        "labels",
        "relations",
        "release",
        "spctr",
        "series",
    ];
    let unknown: Vec<String> = raw
        .keys()
        .filter(|key| !allowed_top.contains(&key.as_str()))
        .cloned()
        .collect();
    if !unknown.is_empty() {
        bail!("{}: unsupported keys: {}", path, unknown.join(", "));
    }
    let root = path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("{path}: manifest must have a parent directory"))?
        .to_owned();
    let parent_name = root
        .parent()
        .and_then(Utf8Path::file_name)
        .ok_or_else(|| anyhow::anyhow!("{path}: unsupported manifest location"))?;
    let kind: &str = match parent_name {
        "dossiers" => "dossier",
        "addenda" => "addendum",
        _ => bail!("{}: unsupported manifest location", path),
    };
    if raw.get("version").and_then(Value::as_integer) != Some(1) {
        bail!("{}: version must be 1", path);
    }
    let license = require_string(raw.get("license"), "license", path)?;
    let title = require_string(raw.get("title"), "title", path)?;
    let summary = require_string(raw.get("summary"), "summary", path)?;
    let status = require_string(raw.get("status"), "status", path)?;
    if let Some(v) = vocabs {
        let allowed = v.statuses_for(kind);
        if !allowed.iter().any(|s| s == &status) {
            bail!("{}: status must be one of {:?}", path, allowed);
        }
    }
    let site = validate_site(kind, raw.get("site"), path)?;
    let labels = validate_labels(kind, raw.get("labels"), path, vocabs)?;
    let related_dossier = validate_relations(kind, raw.get("relations"), path)?;
    let release = validate_release(raw.get("release"), path)?;
    let slug = root
        .file_name()
        .ok_or_else(|| anyhow::anyhow!("{path}: manifest root must be a directory"))?
        .to_owned();
    let spctr = validate_spctr(&slug, raw.get("spctr"), path)?;
    if let Some(ref spctr_config) = spctr {
        validate_spctr_release_references(spctr_config, &release, path)?;
    }
    let series = validate_series(kind, raw.get("series"), path)?;
    Ok(ProjectManifest {
        path: path.to_owned(),
        root,
        kind: kind.to_owned(),
        slug,
        license,
        title,
        summary,
        status,
        site,
        labels,
        related_dossier,
        release,
        spctr,
        series,
    })
}

pub fn discover_manifest(start: Option<&Utf8Path>) -> Result<ProjectManifest> {
    let current: Utf8PathBuf = match start {
        Some(path) => path.to_owned(),
        None => env::current_dir()
            .context("failed to read current directory")?
            .try_into()
            .context("current directory is not valid UTF-8")?,
    };
    for candidate in current.ancestors() {
        let manifest_path = candidate.join(MANIFEST_NAME);
        if manifest_path.is_file() {
            return load_project_manifest(&manifest_path, None);
        }
    }
    bail!("could not find {MANIFEST_NAME} from {current}");
}

pub fn discover_all_manifests(
    repo_root: &Utf8Path,
    vocabs: &Vocabularies,
) -> Result<Vec<ProjectManifest>> {
    let mut manifests = Vec::new();
    for parent in &["dossiers", "addenda"] {
        let root = repo_root.join(parent);
        if !root.is_dir() {
            continue;
        }
        let mut entries = Vec::new();
        for entry in fs::read_dir(&root).with_context(|| format!("failed to read {root}"))? {
            let entry = entry.with_context(|| format!("failed to read entry in {root}"))?;
            let manifest_path: Utf8PathBuf = entry
                .path()
                .join(MANIFEST_NAME)
                .try_into()
                .context("non-UTF-8 path in manifest discovery")?;
            if manifest_path.is_file() {
                entries.push(manifest_path);
            }
        }
        entries.sort();
        for manifest_path in entries {
            manifests.push(load_project_manifest(&manifest_path, Some(vocabs))?);
        }
    }
    Ok(manifests)
}

pub fn discover_surfaced_manifests(repo_root: &Utf8Path) -> Result<Vec<ProjectManifest>> {
    let mut manifests = Vec::new();
    for parent in &["dossiers", "addenda"] {
        let root = repo_root.join(parent);
        if !root.is_dir() {
            continue;
        }
        let mut entries = Vec::new();
        for entry in fs::read_dir(&root).with_context(|| format!("failed to read {root}"))? {
            let entry = entry.with_context(|| format!("failed to read entry in {root}"))?;
            let manifest_path: Utf8PathBuf = entry
                .path()
                .join(MANIFEST_NAME)
                .try_into()
                .context("non-UTF-8 path in manifest discovery")?;
            if manifest_path.is_file() {
                entries.push(manifest_path);
            }
        }
        entries.sort();
        for manifest_path in entries {
            let manifest = load_project_manifest(&manifest_path, None)?;
            let has_surfaces = manifest
                .spctr
                .as_ref()
                .is_some_and(|spctr| !spctr.surfaces.is_empty());
            if has_surfaces {
                manifests.push(manifest);
            }
        }
    }
    Ok(manifests)
}

pub fn discover_site_data_mounts(
    repo_root: &Utf8Path,
) -> Result<Vec<(ProjectManifest, SiteDataConfig)>> {
    let mut results = Vec::new();
    for parent in &["dossiers", "addenda"] {
        let root = repo_root.join(parent);
        if !root.is_dir() {
            continue;
        }
        let mut entries = Vec::new();
        for entry in fs::read_dir(&root).with_context(|| format!("failed to read {root}"))? {
            let entry = entry.with_context(|| format!("failed to read entry in {root}"))?;
            let manifest_path: Utf8PathBuf = entry
                .path()
                .join(MANIFEST_NAME)
                .try_into()
                .context("non-UTF-8 path in manifest discovery")?;
            if manifest_path.is_file() {
                entries.push(manifest_path);
            }
        }
        entries.sort();
        for manifest_path in entries {
            let manifest = load_project_manifest(&manifest_path, None)?;
            if let Some(ref spctr) = manifest.spctr {
                for data in &spctr.site_data {
                    results.push((manifest.clone(), data.clone()));
                }
            }
        }
    }
    Ok(results)
}

pub fn repo_root() -> Result<Utf8PathBuf> {
    let git_output = std::process::Command::new("git")
        .args(["rev-parse", "--show-toplevel"])
        .output()
        .context("failed to run git rev-parse")?;
    if git_output.status.success() {
        let path = String::from_utf8(git_output.stdout)
            .context("invalid UTF-8 from git")?
            .trim()
            .to_owned();
        return Ok(Utf8PathBuf::from(path));
    }
    let jj_output = std::process::Command::new("jj")
        .args(["root"])
        .output()
        .context("failed to run jj root")?;
    if !jj_output.status.success() {
        bail!(
            "repo root discovery failed via git and jj:\ngit: {}\njj: {}",
            String::from_utf8_lossy(&git_output.stderr).trim(),
            String::from_utf8_lossy(&jj_output.stderr).trim()
        );
    }
    let path = String::from_utf8(jj_output.stdout)
        .context("invalid UTF-8 from jj")?
        .trim()
        .to_owned();
    Ok(Utf8PathBuf::from(path))
}
