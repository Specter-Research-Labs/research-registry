use anyhow::Result;
use maud::{html, Markup, PreEscaped, DOCTYPE};
use std::path::{Path, PathBuf};

use crate::site::archive::{self, ArchiveSurfaceRecord};
use crate::site::artifacts::{ProjectArtifactEntry, ProjectArtifactReport};

const INLINE_CSS: &str = r#"
@font-face {
  font-family: "Berkeley Mono";
  src: url("https://specterlab.org/fonts/BerkeleyMono-Regular.woff2") format("woff2");
  font-weight: 400; font-style: normal; font-display: swap;
}
@font-face {
  font-family: "Berkeley Mono";
  src: url("https://specterlab.org/fonts/BerkeleyMono-Light.woff2") format("woff2");
  font-weight: 300; font-style: normal; font-display: swap;
}
@font-face {
  font-family: "Berkeley Mono";
  src: url("https://specterlab.org/fonts/BerkeleyMono-Medium.woff2") format("woff2");
  font-weight: 500; font-style: normal; font-display: swap;
}
@font-face {
  font-family: "Berkeley Mono";
  src: url("https://specterlab.org/fonts/BerkeleyMono-Bold.woff2") format("woff2");
  font-weight: 700; font-style: normal; font-display: swap;
}
:root {
  --sl-font-mono: "Berkeley Mono", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  --sl-color-paper: #fff;
  --sl-color-bg: #edeef0;
  --sl-color-ink: #0b0e14;
  --sl-color-muted: rgba(11, 14, 20, 0.68);
  --sl-color-rule: rgba(11, 14, 20, 0.18);
  --sl-color-rule-strong: rgba(11, 14, 20, 0.42);
  --sl-color-cab-tab: #e6e3db;
  --sl-color-cab-folder: #f5f3ed;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html {
  font-size: 14px;
  background: var(--sl-color-bg);
  scrollbar-gutter: stable;
}

body {
  font-family: var(--sl-font-mono);
  background: var(--sl-color-bg);
  color: var(--sl-color-ink);
  line-height: 1.65;
}

a {
  color: inherit;
  text-decoration: underline;
  text-decoration-thickness: 0.08em;
  text-underline-offset: 0.18em;
}
p { margin-bottom: 1em; }
p:last-child { margin-bottom: 0; }

.registry-shell { max-width: 1120px; margin: 0 auto; padding: 32px 24px 64px; }

.registry-masthead {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; margin-bottom: 4px;
}

.registry-brand {
  display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
}

.logo { height: 20px; width: auto; }

.registry-brand-name {
  font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
}

.registry-markings { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }

.registry-marking {
  display: inline-flex; align-items: center; padding: 2px 10px;
  border: 1px solid var(--sl-color-rule);
  font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; white-space: nowrap;
}

.registry-rules { margin-bottom: 24px; }
.registry-rule { height: 1px; background: var(--sl-color-rule); }
.registry-rule.strong { height: 2px; background: var(--sl-color-ink); margin-bottom: 1px; }

.registry-intro { max-width: 74ch; margin-bottom: 24px; }

.registry-title {
  font-size: 2rem; line-height: 1.06; letter-spacing: -0.03em; margin-bottom: 0.4em;
}

.registry-panel { background: var(--sl-color-paper); border: 1px solid var(--sl-color-rule); }

.registry-panel-header {
  display: flex; align-items: center; gap: 8px; padding-right: 14px;
}

.registry-panel-tab {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 14px 5px;
  background: var(--sl-color-cab-tab);
  border: 1px solid var(--sl-color-rule); border-bottom: 0;
  font-size: 12px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase;
  transform: translateX(-1px);
}

.registry-panel-body { border-top: 1px solid var(--sl-color-rule); padding: 0; }

.registry-card a { overflow-wrap: anywhere; word-break: break-word; }

.registry-log { background: var(--sl-color-paper); border: 1px solid var(--sl-color-rule); }

.registry-log-head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; padding: 14px 16px 12px; border-bottom: 1px solid var(--sl-color-rule);
}

.registry-log-title { font-size: 15px; font-weight: 700; }

.registry-log-body { padding: 0; }
.registry-card-list { display: grid; gap: 10px; }

.registry-card {
  background: var(--sl-color-paper); border: 1px solid var(--sl-color-rule); padding: 12px;
}

.registry-card-title {
  font-size: 12px; font-weight: 500; margin-bottom: 0.35em; overflow-wrap: anywhere;
}

.registry-link-row { display: flex; flex-wrap: wrap; gap: 10px 14px; }
.registry-link-row a { font-size: 12px; font-weight: 500; }

.registry-inventory-list { display: grid; }

.registry-inventory-item {
  display: grid; grid-template-columns: minmax(180px, 0.34fr) minmax(0, 1fr);
  border-top: 1px solid var(--sl-color-rule);
}

.registry-inventory-item:first-child { border-top: 0; }

.registry-inventory-head {
  padding: 14px 16px;
  background: var(--sl-color-cab-folder);
  border-right: 1px solid var(--sl-color-rule-strong);
}

.registry-inventory-title { font-size: 14px; font-weight: 700; line-height: 1.25; }

.registry-inventory-body { padding: 14px 16px; display: grid; gap: 10px; min-width: 0; }

.registry-surface-row {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 12px; padding-bottom: 6px;
  border-bottom: 1px solid var(--sl-color-rule);
}

.registry-surface-row:last-child { padding-bottom: 0; border-bottom: 0; }

.registry-surface-name { font-size: 13px; overflow-wrap: anywhere; }

@media (max-width: 900px) {
  .registry-masthead { align-items: flex-start; flex-direction: column; }
}

@media (max-width: 640px) {
  .registry-shell { padding: 20px 14px 40px; }
  .registry-inventory-item { grid-template-columns: 1fr; }
  .registry-inventory-head { border-right: 0; border-bottom: 1px solid var(--sl-color-rule); }
  .registry-surface-row { align-items: flex-start; flex-direction: column; gap: 6px; }
}
"#;

fn page_shell(title: &str, body: &Markup) -> String {
    let doc = html! {
        (DOCTYPE)
        html lang="en" {
            head {
                meta charset="UTF-8";
                meta name="viewport" content="width=device-width, initial-scale=1.0";
                meta name="color-scheme" content="light";
                title { (title) " | SPECTER Labs" }
                link rel="icon" href="https://specterlab.org/assets/logo-black.svg" type="image/svg+xml";
                style { (PreEscaped(INLINE_CSS)) }
            }
            body {
                div class="registry-shell" {
                    header class="registry-masthead" {
                        a class="registry-brand" href="https://specterlab.org/" {
                            img src="https://specterlab.org/assets/logo-black.svg" alt="SPECTER Labs logo" class="logo";
                            span class="registry-brand-name" { "SPECTER Labs" }
                        }
                        div class="registry-markings" {
                            span class="registry-marking" { "Immutable Release Registry" }
                        }
                    }
                    div class="registry-rules" aria-hidden="true" {
                        div class="registry-rule strong" {}
                        div class="registry-rule" {}
                    }
                    (body)
                }
            }
        }
    };
    doc.into_string()
}

fn release_dirs(path: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(path) else {
        return Vec::new();
    };
    let mut dirs: Vec<String> = entries
        .filter_map(std::result::Result::ok)
        .filter(|e| e.file_type().is_ok_and(|ft| ft.is_dir()))
        .filter_map(|e| e.file_name().into_string().ok())
        .collect();
    dirs.sort();
    dirs.reverse();
    dirs
}

fn render_release_cards(surface: &ArchiveSurfaceRecord, releases: &[String]) -> Markup {
    let ns = surface.namespace_relative();
    if releases.is_empty() {
        return html! {
            article class="registry-card" {
                div class="registry-card-title" { "No archived releases yet" }
            }
        };
    }
    html! {
        @for name in releases {
            @let release_url = format!("/{ns}/releases/{name}/");
            article class="registry-card" {
                div class="registry-card-title" {
                    a href=(release_url) { (name) }
                }
                div class="registry-link-row" {
                    a href=(release_url) { "Open" }
                }
            }
        }
    }
}

fn render_surface_link_rows(root: &Path, surfaces: &[ArchiveSurfaceRecord]) -> Markup {
    html! {
        @for surface in surfaces {
            @let ns = surface.namespace_relative();
            @let ns_path = surface
                .namespace_parts()
                .iter()
                .fold(root.to_path_buf(), |p, part| p.join(part));
            @let release_count = release_dirs(&ns_path.join("releases")).len();
            div class="registry-inventory-item" {
                div class="registry-inventory-head" {
                    a class="registry-inventory-title" href=(format!("/{ns}/")) { (surface.primary_label) }
                }
                div class="registry-inventory-body" {
                    div class="registry-surface-row" {
                        a class="registry-surface-name" href=(surface.current_url) { (surface.current_label) }
                    }
                    div class="registry-link-row" {
                        a href=(format!("/{ns}/")) { "Archive" }
                        a href=(surface.release_index_url()) { "Releases (" (release_count) ")" }
                    }
                }
            }
        }
    }
}

fn render_root(
    root: &Path,
    surfaces: &[ArchiveSurfaceRecord],
    inventory_available: bool,
) -> Result<()> {
    let body = html! {
        section class="registry-intro" {
            h1 class="registry-title" { "Release Registry" }
        }
        section class="registry-panel" {
            div class="registry-panel-header" {
                div class="registry-panel-tab" { "Current" }
            }
            div class="registry-panel-body" {
                div class="registry-inventory-list" {
                    @if inventory_available {
                        div class="registry-inventory-item" {
                            div class="registry-inventory-head" {
                                a class="registry-inventory-title" href="/inventory/" { "Artifact Inventory" }
                            }
                            div class="registry-inventory-body" {
                                div class="registry-link-row" {
                                    a href="/inventory/" { "Open" }
                                }
                            }
                        }
                    }
                    (render_surface_link_rows(root, surfaces))
                }
            }
        }
    };

    let content = page_shell("Release Registry", &body);
    write_page(&root.join("index.html"), &content)
}

fn inventory_report_path(root: &Path) -> PathBuf {
    root.join("site/current/projects/artifacts.json")
}

fn current_site_href(site_href: &str) -> String {
    format!("/site/current/{}", site_href.trim_start_matches('/'))
}

fn render_inventory_rows(entries: &[ProjectArtifactEntry]) -> Markup {
    html! {
        @for entry in entries {
            @if !entry.durable_surfaces.is_empty() || !entry.site_data_mounts.is_empty() {
                div class="registry-inventory-item" {
                    div class="registry-inventory-head" {
                        @if let Some(ref hub_href) = entry.hub_href {
                            a class="registry-inventory-title" href=(current_site_href(hub_href)) { (&entry.title) }
                        } @else {
                            div class="registry-inventory-title" { (&entry.title) }
                        }
                    }
                    div class="registry-inventory-body" {
                        @if !entry.durable_surfaces.is_empty() {
                            div {
                                @for surface in &entry.durable_surfaces {
                                    div class="registry-surface-row" {
                                        div class="registry-surface-name" { (&surface.name) }
                                    }
                                }
                            }
                        }
                        @if !entry.site_data_mounts.is_empty() {
                            div class="registry-link-row" {
                                @for mount in &entry.site_data_mounts {
                                    a href=(current_site_href(&mount.site_path)) { (&mount.name) " data" }
                                }
                            }
                        }
                        div class="registry-link-row" {
                            a href=(&entry.repo_url) { "Repository" }
                        }
                    }
                }
            }
        }
    }
}

fn render_inventory(root: &Path) -> Result<bool> {
    let path = inventory_report_path(root);
    if !path.is_file() {
        return Ok(false);
    }

    let report: ProjectArtifactReport = serde_json::from_str(&std::fs::read_to_string(&path)?)?;
    let body = html! {
        section class="registry-intro" {
            h1 class="registry-title" { "Artifact Inventory" }
        }
        section class="registry-panel" {
            div class="registry-panel-header" {
                div class="registry-panel-tab" { "Dossiers" }
            }
            div class="registry-panel-body" {
                div class="registry-inventory-list" {
                    (render_inventory_rows(&report.dossiers))
                    (render_inventory_rows(&report.addenda))
                }
            }
        }
    };

    write_page(
        &root.join("inventory/index.html"),
        &page_shell("Artifact Inventory", &body),
    )?;
    Ok(true)
}

fn render_surface(root: &Path, surface: &ArchiveSurfaceRecord) -> Result<()> {
    let ns_path = surface
        .namespace_parts()
        .iter()
        .fold(root.to_path_buf(), |p, part| p.join(part));
    let releases_root = ns_path.join("releases");
    std::fs::create_dir_all(&releases_root)?;
    let releases = release_dirs(&releases_root);
    let release_count = releases.len();

    let body = html! {
        section class="registry-intro" {
            h1 class="registry-title" { (surface.title) }
        }
        section class="registry-panel" {
            div class="registry-panel-header" {
                div class="registry-panel-tab" { "Surface" }
            }
            div class="registry-panel-body" {
                div class="registry-inventory-list" {
                    div class="registry-inventory-item" {
                        div class="registry-inventory-head" {
                            div class="registry-inventory-title" { (surface.primary_label) }
                        }
                        div class="registry-inventory-body" {
                            div class="registry-surface-row" {
                                a class="registry-surface-name" href=(surface.current_url) { (surface.current_label) }
                            }
                            div class="registry-link-row" {
                                a href="/" { "Registry" }
                                a href=(surface.current_archive_url()) { "Current archive" }
                                a href=(surface.release_index_url()) { "Releases" }
                            }
                        }
                    }
                }
            }
        }
        section class="registry-log" {
            div class="registry-log-head" {
                div class="registry-log-title" { "Archived Releases (" (release_count) ")" }
            }
            div class="registry-log-body" style="padding: 14px 16px;" {
                div class="registry-card-list" {
                    (render_release_cards(surface, &releases))
                }
            }
        }
    };

    write_page(
        &ns_path.join("index.html"),
        &page_shell(&surface.title, &body),
    )?;

    let releases_body = html! {
        section class="registry-intro" {
            h1 class="registry-title" { (surface.title) }
        }
        section class="registry-log" {
            div class="registry-log-head" {
                div class="registry-log-title" { "Release Entries (" (release_count) ")" }
            }
            div class="registry-log-body" style="padding: 14px 16px;" {
                div class="registry-card-list" {
                    (render_release_cards(surface, &releases))
                }
            }
        }
    };

    let releases_title = format!("{} Releases", surface.title);
    write_page(
        &releases_root.join("index.html"),
        &page_shell(&releases_title, &releases_body),
    )
}

fn write_page(path: &Path, content: &str) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, content)?;
    eprintln!("wrote {}", path.display());
    Ok(())
}

#[allow(clippy::missing_errors_doc)]
pub fn render_portal(release_root: &Path) -> Result<()> {
    std::fs::create_dir_all(release_root)?;
    let surfaces = archive::load_portal_surfaces(release_root)?;
    let inventory_available = render_inventory(release_root)?;
    render_root(release_root, &surfaces, inventory_available)?;
    for surface in &surfaces {
        render_surface(release_root, surface)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::render_portal;
    use crate::site::archive::portal_manifest_path;
    use std::fs;
    use tempfile::tempdir;

    #[test]
    fn render_portal_uses_manifest_surface_metadata() {
        let root = tempdir().unwrap();
        let manifest_path = portal_manifest_path(root.path());
        if let Some(parent) = manifest_path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(
            &manifest_path,
            serde_json::to_string_pretty(&serde_json::json!({
                "version": 1,
                "generatedAt": "2026-04-07T12:00:00Z",
                "surfaces": [{
                    "project": "alpha",
                    "surface": "root",
                    "title": "Alpha Release Shelf",
                    "summary": "Custom archived bundles.",
                    "primaryLabel": "Alpha archive",
                    "currentLabel": "Current alpha",
                    "currentUrl": "https://example.test/alpha/"
                }]
            }))
            .unwrap(),
        )
        .unwrap();
        fs::create_dir_all(root.path().join("alpha/releases/release-001")).unwrap();

        render_portal(root.path()).unwrap();

        let root_page = fs::read_to_string(root.path().join("index.html")).unwrap();
        assert!(root_page.contains("Alpha archive"));
        assert!(root_page.contains("Current alpha"));

        let surface_page = fs::read_to_string(root.path().join("alpha/index.html")).unwrap();
        assert!(surface_page.contains("Alpha Release Shelf"));
        assert!(surface_page.contains("release-001"));
    }

    #[test]
    fn render_portal_falls_back_to_canonical_manifest() {
        let root = tempdir().unwrap();
        render_portal(root.path()).unwrap();

        let root_page = fs::read_to_string(root.path().join("index.html")).unwrap();
        assert!(root_page.contains("Site snapshots"));
        assert!(root_page.contains("Current dashboard"));
    }

    #[test]
    fn render_portal_publishes_dossier_inventory_from_site_feed() {
        let root = tempdir().unwrap();
        let feed_path = root.path().join("site/current/projects/artifacts.json");
        fs::create_dir_all(feed_path.parent().unwrap()).unwrap();
        fs::write(
            &feed_path,
            serde_json::to_string_pretty(&serde_json::json!({
                "version": 1,
                "generated_at": "2026-04-26T00:00:00Z",
                "summary": {
                    "visible_projects": 1,
                    "durable_surfaces": 1,
                    "site_data_mounts": 1
                },
                "dossiers": [{
                    "kind": "dossier",
                    "slug": "alpha",
                    "title": "Alpha Dossier",
                    "summary": "Alpha summary.",
                    "series": "D-001",
                    "repo_path": "dossiers/alpha",
                    "repo_url": "https://example.test/repo",
                    "hub_href": "dossiers/alpha/",
                    "cabinet_href": null,
                    "durable_surfaces": [{
                        "name": "alpha-lake",
                        "kind": "duckdb",
                        "local_db_path": "lake/lake.duckdb",
                        "remote_raw_namespace": null,
                        "remote_snapshot_namespace": "alpha-lake",
                        "raw_root_count": 0,
                        "refresh_command_count": 1
                    }],
                    "site_data_mounts": [{
                        "name": "dashboard",
                        "site_path": "dossiers/alpha/dashboard/data",
                        "local_source": "artifacts/dashboard"
                    }]
                }],
                "addenda": []
            }))
            .unwrap(),
        )
        .unwrap();

        render_portal(root.path()).unwrap();

        let root_page = fs::read_to_string(root.path().join("index.html")).unwrap();
        let inventory_page = fs::read_to_string(root.path().join("inventory/index.html")).unwrap();
        assert!(root_page.contains("Artifact Inventory"));
        assert!(inventory_page.contains("Artifact Inventory"));
        assert!(inventory_page.contains("Alpha Dossier"));
        assert!(inventory_page.contains("dashboard data"));
        assert!(!inventory_page.contains("lake/lake.duckdb"));
        assert!(!inventory_page.contains("Evidence"));
    }
}
