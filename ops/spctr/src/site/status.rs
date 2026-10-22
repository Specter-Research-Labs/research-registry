use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use std::collections::BTreeSet;
use std::fs;

use crate::panel::{centered, divider_bot, divider_mid, divider_top, header_top, row};
use crate::site::{blog, cabinet, discover, records};

const OUTPUT_PATH: &str = "site/status/index.html";
const SHORT_SHA_LEN: usize = 7;

struct Published {
    series: String,
    title: String,
}

struct LabStatus {
    dossiers: Vec<(String, String, String)>,
    addenda: usize,
    posts: Vec<Published>,
    notes: Vec<Published>,
    cabinet_docs: usize,
    cabinet_projects: usize,
    latest_update: (String, String),
    release: String,
    generated_at: String,
}

pub(crate) fn write_status_page(repo_root: &Utf8Path, release_id: &str) -> Result<()> {
    let status = collect(repo_root, release_id)?;
    let path = repo_root.join(OUTPUT_PATH);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    fs::write(&path, render_html(&format_panel(&status)))
        .with_context(|| format!("failed to write {path}"))
}

fn collect(repo_root: &Utf8Path, release_id: &str) -> Result<LabStatus> {
    let graph = crate::graph::build_with_options(
        repo_root,
        None,
        crate::graph::GraphBuildOptions::site_projection(),
    )?;
    let site_records = records::load_site_records_from_graph(repo_root, &graph)?;
    let slices = records::slice_records(&site_records);

    let dossiers = slices
        .visible_dossiers
        .iter()
        .map(|record| {
            let Some(series) = record.series.clone() else {
                bail!("visible dossier {} has no series id", record.slug);
            };
            Ok((series, record.slug.clone(), record.status.clone()))
        })
        .collect::<Result<Vec<_>>>()?;

    let posts = blog::load_published_posts_from_graph(&graph)?
        .into_iter()
        .filter(|post| post.release == discover::RELEASE_PUBLISHED)
        .map(|post| {
            let Some(series) = post.series else {
                bail!("published post {} has no series id", post.href);
            };
            Ok(Published {
                series,
                title: post.title,
            })
        })
        .collect::<Result<Vec<_>>>()?;

    let notes = blog::published_research_notes(repo_root)?
        .into_iter()
        .map(|note| {
            let Some(series) = note.spctr_id else {
                bail!("published note {} has no series id", note.slug);
            };
            Ok(Published {
                series,
                title: note.title,
            })
        })
        .collect::<Result<Vec<_>>>()?;

    let docs = cabinet::docs::find_published_docs_from_graph(repo_root, &graph)?;
    let cabinet_projects = docs
        .iter()
        .map(|doc| doc.project_slug.as_str())
        .collect::<BTreeSet<_>>()
        .len();

    Ok(LabStatus {
        dossiers,
        addenda: slices.visible_addenda.len(),
        posts,
        notes,
        cabinet_docs: docs.len(),
        cabinet_projects,
        latest_update: crate::updates_archive::latest_update(repo_root)?,
        release: short_release(release_id),
        generated_at: chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
    })
}

// Series ids are zero-padded (B-001), so the lexical maximum is the most recent publication.
fn latest(items: &[Published]) -> String {
    items
        .iter()
        .max_by(|left, right| left.series.cmp(&right.series))
        .map_or_else(
            || "none".to_owned(),
            |item| format!("{}  {}", item.series, item.title),
        )
}

fn short_release(release_id: &str) -> String {
    let is_full_sha = release_id.len() == 40 && release_id.bytes().all(|b| b.is_ascii_hexdigit());
    if is_full_sha {
        release_id[..SHORT_SHA_LEN].to_owned()
    } else {
        release_id.to_owned()
    }
}

fn format_panel(status: &LabStatus) -> String {
    let mut buf = String::with_capacity(4096);
    header_top(&mut buf);
    centered(&mut buf, "SPECTER LABS");
    centered(&mut buf, "LAB STATUS");

    divider_top(&mut buf);
    row(&mut buf, "DOSSIERS", &status.dossiers.len().to_string());
    for (series, slug, state) in &status.dossiers {
        row(&mut buf, series, &format!("{slug:<24}{state}"));
    }

    divider_mid(&mut buf);
    row(&mut buf, "ADDENDA", &status.addenda.to_string());
    row(&mut buf, "POSTS", &status.posts.len().to_string());
    row(&mut buf, "LATEST POST", &latest(&status.posts));
    row(&mut buf, "RESEARCH NOTES", &status.notes.len().to_string());
    row(&mut buf, "LATEST NOTE", &latest(&status.notes));
    row(
        &mut buf,
        "CABINET DOCS",
        &format!(
            "{} across {} projects",
            status.cabinet_docs, status.cabinet_projects
        ),
    );
    let (update_label, update_date) = &status.latest_update;
    row(
        &mut buf,
        "LATEST UPDATE",
        &format!("{update_label}  {update_date}"),
    );

    divider_mid(&mut buf);
    row(&mut buf, "RELEASE", &status.release);
    row(&mut buf, "GENERATED", &status.generated_at);
    divider_bot(&mut buf);
    buf
}

fn render_html(panel: &str) -> String {
    let escaped = panel
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;");
    format!(
        r#"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lab Status | Specter Labs</title>
<meta name="spctr:card" content="none">
<meta name="description" content="Build-time counts of Specter Labs dossiers, writing and cabinet docs.">
<link rel="icon" href="/assets/logo-black.svg" type="image/svg+xml">
<style>
body {{ margin: 0; min-height: 100vh; padding: 2rem; background: #0a0a0a; color: #d4d4d4; font-family: "IBM Plex Mono", "Menlo", monospace; display: flex; justify-content: center; }}
pre {{ width: fit-content; max-width: 100%; margin: 0; font-size: 13px; line-height: 1.5; white-space: pre; overflow-x: auto; }}
</style>
</head>
<body>
<pre>{escaped}</pre>
</body>
</html>"#
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn published(series: &str, title: &str) -> Published {
        Published {
            series: series.to_owned(),
            title: title.to_owned(),
        }
    }

    #[test]
    fn panel_lists_counts_latest_entries_and_release() {
        let status = LabStatus {
            dossiers: vec![("D-001".into(), "alpha".into(), "active".into())],
            addenda: 2,
            posts: vec![published("B-001", "First post")],
            notes: vec![
                published("N-002", "Later note"),
                published("N-010", "Latest note"),
            ],
            cabinet_docs: 12,
            cabinet_projects: 3,
            latest_update: ("SPCTR-UPDATE-002".into(), "2026-03-28".into()),
            release: short_release("0123456789abcdef0123456789abcdef01234567"),
            generated_at: "2026-10-17T00:00:00Z".into(),
        };
        let panel = format_panel(&status);
        assert!(panel.contains("D-001"));
        assert!(panel.contains("alpha"));
        assert!(panel.contains("N-010  Latest note"));
        assert!(panel.contains("12 across 3 projects"));
        assert!(panel.contains("SPCTR-UPDATE-002  2026-03-28"));
        assert!(panel.contains("0123456 "));
        assert!(!panel.contains("01234567"));
    }
}
