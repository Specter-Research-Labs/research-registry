use anyhow::{bail, Result};
use camino::Utf8Path;
use serde::Serialize;

use crate::{graph, registry, series};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SeriesAssignment {
    pub kind: String,
    pub slug: String,
    pub series_id: String,
    pub path: String,
    pub patch_source: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DocAssignment {
    pub series_id: String,
    pub project_kind: String,
    pub project_slug: String,
    pub doc_slug: String,
    pub doc_id: String,
    pub path: String,
}

#[derive(Debug, Clone, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RegistrySyncReport {
    pub series_assignments: Vec<SeriesAssignment>,
    pub doc_assignments: Vec<DocAssignment>,
}

impl RegistrySyncReport {
    pub fn is_clean(&self) -> bool {
        self.series_assignments.is_empty() && self.doc_assignments.is_empty()
    }

    pub fn drift_message(&self) -> String {
        let mut lines = vec!["registry drift detected:".to_owned()];
        for assignment in &self.series_assignments {
            lines.push(format!(
                "- missing series assignment: {} {} -> {} ({})",
                assignment.kind, assignment.slug, assignment.series_id, assignment.path
            ));
        }
        for assignment in &self.doc_assignments {
            lines.push(format!(
                "- missing cabinet doc id: {}/{} -> {} ({})",
                assignment.project_slug, assignment.doc_slug, assignment.doc_id, assignment.path
            ));
        }
        lines.push("run `spctr registry sync` and commit the results".to_owned());
        lines.join("\n")
    }
}

struct PlannedSync {
    report: RegistrySyncReport,
    registry: registry::Registry,
}

pub fn plan(repo_root: &Utf8Path) -> Result<RegistrySyncReport> {
    Ok(build_plan(repo_root)?.report)
}

pub fn ensure_clean(repo_root: &Utf8Path) -> Result<()> {
    let report = plan(repo_root)?;
    if report.is_clean() {
        Ok(())
    } else {
        bail!(report.drift_message())
    }
}

pub fn sync(repo_root: &Utf8Path) -> Result<RegistrySyncReport> {
    let planned = build_plan(repo_root)?;
    if planned.report.is_clean() {
        return Ok(planned.report);
    }

    for assignment in &planned.report.series_assignments {
        if !assignment.patch_source {
            continue;
        }
        let path = repo_root.join(&assignment.path);
        let text = std::fs::read_to_string(&path)?;
        let patched = match assignment.kind.as_str() {
            "dossier" | "addendum" => series::patch_toml_series(&text, &assignment.series_id)?,
            "article" => series::patch_frontmatter_field(&text, "series", &assignment.series_id)?,
            other => bail!("unknown registry sync assignment kind '{other}'"),
        };
        std::fs::write(&path, patched)?;
    }

    registry::save_registry(repo_root, &planned.registry)?;
    Ok(planned.report)
}

fn build_plan(repo_root: &Utf8Path) -> Result<PlannedSync> {
    let mut report = RegistrySyncReport::default();
    let mut planned_registry = registry::load_registry(repo_root)?;
    let graph = graph::build_with_options(
        repo_root,
        None,
        graph::GraphBuildOptions {
            include_docs: true,
            include_evidence: false,
            include_updates: false,
        },
    )?;

    assign_missing_series(repo_root, &graph, &mut planned_registry, &mut report)?;
    assign_missing_doc_ids(&graph, &mut planned_registry, &mut report)?;

    Ok(PlannedSync {
        report,
        registry: planned_registry,
    })
}

fn assign_missing_series(
    repo_root: &Utf8Path,
    graph: &graph::RegistryGraph,
    planned_registry: &mut registry::Registry,
    report: &mut RegistrySyncReport,
) -> Result<()> {
    for node in graph.nodes_of_kind("project") {
        let kind = required_attr(node, "kind")?;
        if !matches!(kind, "dossier" | "addendum") {
            continue;
        }
        if graph::attr_str(node, "series_id").is_some() {
            continue;
        }
        let slug = required_attr(node, "slug")?;
        let title = required_attr(node, "title")?;
        let path = required_attr(node, "manifest_path")?;
        let series_id = registry::allocate_series(planned_registry, kind, slug, title)?;
        report.series_assignments.push(SeriesAssignment {
            kind: kind.to_owned(),
            slug: slug.to_owned(),
            series_id,
            path: path.to_owned(),
            patch_source: true,
        });
    }

    for post in series::missing_article_series_records(repo_root)? {
        let series_id =
            registry::allocate_series(planned_registry, "article", &post.slug, &post.title)?;
        report.series_assignments.push(SeriesAssignment {
            kind: "article".to_owned(),
            slug: post.slug,
            series_id,
            path: post.path.to_string(),
            patch_source: post.patch_source,
        });
    }

    for note in series::missing_research_note_series_records(repo_root, planned_registry)? {
        let series_id =
            registry::allocate_series(planned_registry, "research-note", &note.slug, &note.title)?;
        report.series_assignments.push(SeriesAssignment {
            kind: "research-note".to_owned(),
            slug: note.slug,
            series_id,
            path: note.path.to_string(),
            patch_source: note.patch_source,
        });
    }

    Ok(())
}

fn assign_missing_doc_ids(
    graph: &graph::RegistryGraph,
    planned_registry: &mut registry::Registry,
    report: &mut RegistrySyncReport,
) -> Result<()> {
    for node in graph.nodes_of_kind("doc") {
        if graph::attr_bool(node, "published") != Some(true) {
            continue;
        }
        if graph::attr_str(node, "doc_id").is_some() {
            continue;
        }
        let project_kind = required_attr(node, "project_kind")?;
        let project_slug = required_attr(node, "project_slug")?;
        let doc_slug = required_attr(node, "slug")?;
        let path = required_attr(node, "path")?;
        let project_id = format!("project:{project_kind}:{project_slug}");
        let project = graph
            .node(&project_id)
            .ok_or_else(|| anyhow::anyhow!("{path}: missing graph project node {project_id}"))?;
        let series_id = graph::attr_str(project, "series_id")
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "{path}: published cabinet doc requires a registry series assignment"
                )
            })?
            .to_owned();
        let existing =
            registry::doc_id_for_slug(planned_registry, &series_id, doc_slug).map(str::to_owned);
        let doc_id = registry::allocate_doc_id(planned_registry, &series_id, doc_slug)?;
        if existing.is_none() {
            report.doc_assignments.push(DocAssignment {
                series_id,
                project_kind: project_kind.to_owned(),
                project_slug: project_slug.to_owned(),
                doc_slug: doc_slug.to_owned(),
                doc_id,
                path: path.to_owned(),
            });
        }
    }
    Ok(())
}

fn required_attr<'a>(node: &'a graph::GraphNode, key: &str) -> Result<&'a str> {
    match graph::attr_str(node, key) {
        Some(value) => Ok(value),
        None => bail!("{}: missing graph attr '{key}'", node.id),
    }
}
