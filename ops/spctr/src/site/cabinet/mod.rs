pub mod docs;
pub mod links;
pub mod render;

use anyhow::{bail, Context, Result};
use camino::Utf8Path;

use crate::graph::{self, GraphBuildOptions};

pub fn build_cabinet(repo_root: &Utf8Path, write: bool) -> Result<()> {
    if !which_pandoc() {
        bail!("pandoc not found; install pandoc >= 3.x");
    }

    let site_root = repo_root.join("site");
    let template = site_root.join("cabinet/cabinet-template.html");
    if !template.is_file() {
        bail!("missing template: {}", template);
    }

    let graph = graph::build_with_options(
        repo_root,
        None,
        GraphBuildOptions {
            include_docs: true,
            include_evidence: false,
            include_updates: false,
        },
    )?;
    let mut entries = docs::find_published_docs_from_graph(repo_root, &graph)?;

    if entries.is_empty() {
        bail!("no docs found in dossiers/*/docs/ or addenda/*/docs/");
    }

    let lookup = links::build_doc_lookup(&entries);
    let backlinks = links::build_backlink_graph(&mut entries, &lookup)?;

    let total: usize = entries.len();
    let projects: std::collections::HashSet<&str> =
        entries.iter().map(|e| e.project_slug.as_str()).collect();
    eprintln!("cabinet: {total} docs across {} projects", projects.len());

    if !write {
        eprintln!("cabinet: validated (use --write to emit HTML)");
        return Ok(());
    }

    let built_at = {
        let now = chrono::Utc::now();
        now.format("%Y-%m-%dT%H:%M:%SZ").to_string()
    };

    clean_generated(&site_root)?;

    let mut current_project = String::new();
    for entry in &entries {
        if entry.project_slug != current_project {
            current_project.clone_from(&entry.project_slug);
            eprintln!("[{current_project}]");
        }
        render::render_doc(
            entry, &template, &site_root, repo_root, &built_at, &backlinks, &entries,
        )?;
    }

    render::build_index(&entries, &site_root)?;

    eprintln!("cabinet: done");
    Ok(())
}

fn clean_generated(site_root: &Utf8Path) -> Result<()> {
    let cabinet_dir = site_root.join("cabinet");
    if !cabinet_dir.is_dir() {
        return Ok(());
    }
    for entry in std::fs::read_dir(&cabinet_dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            std::fs::remove_dir_all(&path)
                .with_context(|| format!("failed to remove {}", path.display()))?;
        }
    }
    Ok(())
}

fn which_pandoc() -> bool {
    std::process::Command::new("pandoc")
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .is_ok_and(|s| s.success())
}
