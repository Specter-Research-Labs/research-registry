use anyhow::{Context, Result};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

pub(crate) const PORTAL_MANIFEST_DIR: &str = ".spctr";
pub(crate) const PORTAL_MANIFEST_FILE: &str = "portal-surfaces.json";
pub(crate) const PORTAL_MANIFEST_RELATIVE_PATH: &str = ".spctr/portal-surfaces.json";
pub(crate) const PORTAL_MANIFEST_SOURCE_PATH: &str = "ops/spctr/src/site/archive.rs";

const RELEASES_PUBLIC_BASE: &str = "https://releases.specterlab.org";

#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "camelCase")]
pub(crate) struct ArchiveSurfaceRecord {
    pub project: String,
    pub surface: String,
    pub title: String,
    pub summary: String,
    pub primary_label: String,
    pub current_label: String,
    pub current_url: String,
}

impl ArchiveSurfaceRecord {
    pub(crate) fn namespace_parts(&self) -> Vec<&str> {
        if matches!(self.surface.as_str(), "" | "." | "_" | "default" | "root") {
            vec![self.project.as_str()]
        } else {
            vec![self.project.as_str(), self.surface.as_str()]
        }
    }

    pub(crate) fn namespace_relative(&self) -> String {
        self.namespace_parts().join("/")
    }

    pub(crate) fn release_index_url(&self) -> String {
        format!("/{}/releases/", self.namespace_relative())
    }

    pub(crate) fn current_archive_url(&self) -> String {
        format!(
            "{}/{}/current/",
            RELEASES_PUBLIC_BASE,
            self.namespace_relative()
        )
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ArchiveSurfaceManifest {
    version: u32,
    generated_at: String,
    surfaces: Vec<ArchiveSurfaceRecord>,
}

fn surface(
    project: &str,
    surface: &str,
    title: &str,
    summary: &str,
    primary_label: &str,
    current_label: &str,
    current_url: &str,
) -> ArchiveSurfaceRecord {
    ArchiveSurfaceRecord {
        project: project.to_owned(),
        surface: surface.to_owned(),
        title: title.to_owned(),
        summary: summary.to_owned(),
        primary_label: primary_label.to_owned(),
        current_label: current_label.to_owned(),
        current_url: current_url.to_owned(),
    }
}

pub(crate) fn canonical_archive_surfaces() -> Vec<ArchiveSurfaceRecord> {
    vec![
        surface(
            "site",
            "root",
            "Canonical Site Snapshots",
            "Archived snapshots of the public site.",
            "Site snapshots",
            "Current site",
            "https://specterlab.org/",
        ),
        surface(
            "typst-field-manual",
            "root",
            "Typst Field Manual Releases",
            "Promoted public PDFs for the field manual.",
            "Field manual",
            "Current public PDF",
            "https://releases.specterlab.org/typst-field-manual/current/",
        ),
        surface(
            "lenia-swarm",
            "compendium",
            "Lenia Compendium Releases",
            "Archived public compendium bundles.",
            "Lenia compendium",
            "Current compendium",
            "https://specterlab.org/dossiers/lenia-swarm/compendium/",
        ),
        surface(
            "lenia-swarm",
            "causal-emergence",
            "Flow Lenia Causal Emergence Reports",
            "Immutable releases of the Flow Lenia causal-emergence synthesis and experiment reports.",
            "Causal-emergence reports",
            "Current synthesis",
            "https://releases.specterlab.org/lenia-swarm/causal-emergence/current/",
        ),
        surface(
            "wonton-soup",
            "site-dashboard",
            "Wonton Site Dashboard Releases",
            "Archived Wonton dashboard bundles.",
            "Wonton dashboard",
            "Current dashboard",
            "https://specterlab.org/dashboards/wonton-soup/",
        ),
    ]
}

fn canonical_archive_surface_manifest() -> ArchiveSurfaceManifest {
    ArchiveSurfaceManifest {
        version: 1,
        generated_at: Utc::now().to_rfc3339(),
        surfaces: canonical_archive_surfaces(),
    }
}

pub(crate) fn portal_manifest_path(release_root: &Path) -> PathBuf {
    release_root
        .join(PORTAL_MANIFEST_DIR)
        .join(PORTAL_MANIFEST_FILE)
}

pub(crate) fn load_portal_surfaces(release_root: &Path) -> Result<Vec<ArchiveSurfaceRecord>> {
    let manifest_path = portal_manifest_path(release_root);
    if !manifest_path.is_file() {
        return Ok(canonical_archive_surfaces());
    }
    let text = fs::read_to_string(&manifest_path)
        .with_context(|| format!("failed to read {}", manifest_path.display()))?;
    let manifest: ArchiveSurfaceManifest = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse {}", manifest_path.display()))?;
    Ok(manifest.surfaces)
}

pub(crate) fn write_portal_manifest_file(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create {}", parent.display()))?;
    }
    let rendered = serde_json::to_string_pretty(&canonical_archive_surface_manifest())
        .context("failed to serialize portal surface manifest")?
        + "\n";
    fs::write(path, rendered).with_context(|| format!("failed to write {}", path.display()))?;
    Ok(())
}
