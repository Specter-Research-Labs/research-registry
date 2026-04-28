use crate::graph::{self, GraphNode, RegistryGraph};
use crate::manifest::{MANIFEST_NAME, REPO_TREE_URL};
use crate::release;
use crate::site::discover;
use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap};
use std::process::Command;

#[derive(Clone, Debug)]
pub struct SiteRecord {
    pub kind: String,
    pub slug: String,
    pub title: String,
    pub summary: String,
    pub license: String,
    pub status: String,
    pub release_stage: String,
    pub release_surfaces: Vec<release::PublicSurfaceLink>,
    pub visible: bool,
    pub featured: bool,
    pub featured_order: Option<u32>,
    pub hub_path: Option<String>,
    pub hub_generated: bool,
    pub labels: BTreeMap<String, String>,
    pub related_dossier: Option<String>,
    pub repo_path: String,
    pub repo_url: String,
    pub last_activity: String,
    pub has_docs_dir: bool,
    pub has_docs_readme: bool,
    pub series: Option<String>,
}

pub struct SiteRecordSlices<'a> {
    pub visible_dossiers: Vec<&'a SiteRecord>,
    pub visible_addenda: Vec<&'a SiteRecord>,
    pub featured_dossiers: Vec<&'a SiteRecord>,
    pub featured_addenda: Vec<&'a SiteRecord>,
    pub dossier_by_slug: HashMap<&'a str, &'a SiteRecord>,
}

impl SiteRecord {
    pub fn hub_mode(&self) -> &'static str {
        if self.kind != "dossier" {
            "n/a"
        } else if self.hub_path.is_none() {
            "missing"
        } else if self.hub_generated {
            "generated"
        } else {
            "manual"
        }
    }

    pub fn hub_href(&self) -> Option<String> {
        self.hub_path
            .as_ref()
            .map(|hub_path| discover::site_href_from_path(hub_path))
    }

    pub fn relative_hub_href(&self, page_path: &str) -> Option<String> {
        self.hub_href()
            .map(|href| discover::relative_href(page_path, &href))
    }

    pub fn cabinet_href(&self) -> Option<String> {
        self.has_docs_readme
            .then(|| format!("cabinet/{}/README/", self.slug))
    }

    pub fn relative_cabinet_href(&self, page_path: &str) -> Option<String> {
        self.cabinet_href()
            .map(|href| discover::relative_href(page_path, &href))
    }

    pub fn published_release_surfaces(
        &self,
    ) -> impl Iterator<Item = &release::PublicSurfaceLink> + '_ {
        let promoted = self.release_stage == "promoted";
        self.publishable_release_surfaces()
            .filter(move |surface| promoted && surface.href.is_some())
    }

    pub fn publishable_release_surfaces(
        &self,
    ) -> impl Iterator<Item = &release::PublicSurfaceLink> + '_ {
        self.release_surfaces
            .iter()
            .filter(|surface| surface.publish)
    }

    pub fn has_published_release_surfaces(&self) -> bool {
        self.published_release_surfaces().next().is_some()
    }

    pub fn published_surface_links(&self) -> Vec<(&str, &str)> {
        self.published_release_surfaces()
            .filter_map(|surface| {
                surface
                    .href
                    .as_deref()
                    .map(|href| (surface.label.as_str(), href))
            })
            .collect()
    }
}

pub fn load_site_records(repo_root: &Utf8Path) -> Result<Vec<SiteRecord>> {
    let registry_graph =
        graph::build_with_options(repo_root, None, graph::GraphBuildOptions::site_records())?;
    load_site_records_from_graph(repo_root, &registry_graph)
}

pub fn load_site_records_from_graph(
    repo_root: &Utf8Path,
    registry_graph: &RegistryGraph,
) -> Result<Vec<SiteRecord>> {
    let records = registry_graph
        .nodes_of_kind("project")
        .map(|node| graph_to_record(repo_root, &registry_graph, node))
        .collect::<Result<Vec<_>>>()?;
    validate_cross_references(&records)?;
    Ok(records)
}

fn graph_to_record(
    repo_root: &Utf8Path,
    registry_graph: &RegistryGraph,
    node: &GraphNode,
) -> Result<SiteRecord> {
    let kind = require_string_attr(node, "kind")?;
    let slug = require_string_attr(node, "slug")?;
    let title = require_string_attr(node, "title")?;
    let summary = require_string_attr(node, "summary")?;
    let license = require_string_attr(node, "license")?;
    let status = require_string_attr(node, "status")?;
    let release_stage = require_string_attr(node, "release_stage")?;
    let repo_path = require_string_attr(node, "repo_path")?;
    let repo_url = format!("{REPO_TREE_URL}/{repo_path}");
    let last_activity = git_last_activity(repo_root, &repo_path);
    let source_path = graph::attr_str(node, "source_path").unwrap_or(&slug);
    let declared_hub_path = graph::attr_str(node, "site_hub_path");
    let hub_path = graph::attr_str(node, "site_effective_hub_path").map(str::to_owned);
    let hub_generated = require_bool_attr(node, "site_hub_generated")?;
    validate_hub_output_path(source_path, hub_path.as_deref().or(declared_hub_path))?;
    validate_declared_hub_template(repo_root, source_path, declared_hub_path)?;
    let (has_docs_dir, has_docs_readme) = docs_flags(registry_graph, node);

    Ok(SiteRecord {
        kind,
        slug,
        title,
        summary,
        license,
        status,
        release_stage,
        release_surfaces: release_surfaces_for_project(registry_graph, node)?,
        visible: require_bool_attr(node, "site_visible")?,
        featured: require_bool_attr(node, "site_featured")?,
        featured_order: optional_u32_attr(node, "site_featured_order")?,
        hub_path,
        hub_generated,
        labels: labels_attr(node)?,
        related_dossier: graph::attr_str(node, "related_dossier").map(str::to_owned),
        repo_path,
        repo_url,
        last_activity,
        has_docs_dir,
        has_docs_readme,
        series: graph::attr_str(node, "series_id").map(str::to_owned),
    })
}

fn release_surfaces_for_project(
    registry_graph: &RegistryGraph,
    node: &GraphNode,
) -> Result<Vec<release::PublicSurfaceLink>> {
    let mut surfaces = registry_graph
        .outgoing_edges(&node.id, "project_declares_surface")
        .filter_map(|edge| registry_graph.node(&edge.dst))
        .map(|surface| {
            Ok((
                graph::attr_u64(surface, "ordinal").unwrap_or(u64::MAX),
                release::PublicSurfaceLink {
                    name: require_string_attr(surface, "name")?,
                    kind: require_string_attr(surface, "kind")?,
                    label: require_string_attr(surface, "label")?,
                    publish: require_bool_attr(surface, "publish")?,
                    href: graph::attr_str(surface, "href").map(str::to_owned),
                },
            ))
        })
        .collect::<Result<Vec<_>>>()?;
    surfaces.sort_by_key(|(ordinal, _)| *ordinal);
    Ok(surfaces.into_iter().map(|(_, surface)| surface).collect())
}

fn docs_flags(registry_graph: &RegistryGraph, node: &GraphNode) -> (bool, bool) {
    if let (Some(has_docs_dir), Some(has_docs_readme)) = (
        graph::attr_bool(node, "has_docs_dir"),
        graph::attr_bool(node, "has_docs_readme"),
    ) {
        return (has_docs_dir, has_docs_readme);
    }
    let mut has_docs_dir = false;
    let mut has_docs_readme = false;
    for edge in registry_graph.outgoing_edges(&node.id, "project_has_doc") {
        has_docs_dir = true;
        if registry_graph
            .node(&edge.dst)
            .and_then(|doc| graph::attr_str(doc, "slug"))
            == Some("README")
        {
            has_docs_readme = true;
        }
    }
    (has_docs_dir, has_docs_readme)
}

fn labels_attr(node: &GraphNode) -> Result<BTreeMap<String, String>> {
    match graph::attr_value(node, "labels") {
        Some(Value::Object(_)) => serde_json::from_value(
            graph::attr_value(node, "labels")
                .expect("labels checked above")
                .clone(),
        )
        .with_context(|| format!("{}: labels must be a string map", node.id)),
        Some(Value::Null) | None => Ok(BTreeMap::new()),
        Some(_) => bail!("{}: labels must be a string map", node.id),
    }
}

fn validate_hub_output_path(source_path: &str, hub_path: Option<&str>) -> Result<()> {
    let Some(hub_path) = hub_path else {
        return Ok(());
    };
    if !hub_path.starts_with("site/") || !hub_path.ends_with(".html") {
        bail!("{source_path}: site.hub_path must point to a file under site/");
    }
    if hub_path.contains("..") {
        bail!("{source_path}: site.hub_path must not contain '..': {hub_path}");
    }
    Ok(())
}

fn validate_declared_hub_template(
    repo_root: &Utf8Path,
    source_path: &str,
    hub_path: Option<&str>,
) -> Result<()> {
    let Some(hub_path) = hub_path else {
        return Ok(());
    };
    validate_hub_output_path(source_path, Some(hub_path))?;
    let template_path = format!(
        "site/templates/{}",
        hub_path
            .strip_prefix("site/")
            .expect("validated to start with site/")
    );
    let template_file = repo_root.join(&template_path);
    if !template_file.is_file() {
        bail!("{source_path}: hub template does not exist: {template_path}");
    }
    Ok(())
}

fn require_string_attr(node: &GraphNode, key: &str) -> Result<String> {
    graph::attr_str(node, key)
        .map(str::to_owned)
        .ok_or_else(|| anyhow::anyhow!("{}: missing or invalid '{key}'", node.id))
}

fn require_bool_attr(node: &GraphNode, key: &str) -> Result<bool> {
    graph::attr_bool(node, key)
        .ok_or_else(|| anyhow::anyhow!("{}: missing or invalid '{key}'", node.id))
}

fn optional_u32_attr(node: &GraphNode, key: &str) -> Result<Option<u32>> {
    graph::attr_u64(node, key)
        .map(|value| {
            u32::try_from(value)
                .map_err(|_| anyhow::anyhow!("{}: '{key}' must fit in u32", node.id))
        })
        .transpose()
}

fn validate_cross_references(records: &[SiteRecord]) -> Result<()> {
    let visible_dossiers: HashMap<&str, &SiteRecord> = records
        .iter()
        .filter(|r| r.kind == "dossier" && r.visible)
        .map(|r| (r.slug.as_str(), r))
        .collect();

    let mut featured_orders: HashMap<&str, HashMap<u32, &str>> = HashMap::new();
    for record in records {
        if record.visible && record.featured {
            let order = record.featured_order.expect("featured requires order");
            let used = featured_orders.entry(record.kind.as_str()).or_default();
            if let Some(&existing) = used.get(&order) {
                bail!(
                    "duplicate featured order for {}s: {} and {} both use {}",
                    record.kind,
                    existing,
                    record.slug,
                    order
                );
            }
            used.insert(order, &record.slug);
        }

        if record.kind == "addendum" && record.visible {
            if let Some(ref dossier_slug) = record.related_dossier {
                let linked = visible_dossiers.get(dossier_slug.as_str());
                match linked {
                    None => bail!(
                        "addenda/{}/{}: relations.dossier points to unknown or hidden dossier '{}'",
                        record.slug,
                        MANIFEST_NAME,
                        dossier_slug
                    ),
                    Some(d) if d.hub_path.is_none() => bail!(
                        "addenda/{}/{}: relations.dossier '{}' does not expose a public hub",
                        record.slug,
                        MANIFEST_NAME,
                        dossier_slug
                    ),
                    _ => {}
                }
            }
        }
    }
    Ok(())
}

fn git_last_activity(repo_root: &Utf8Path, repo_path: &str) -> String {
    let target = repo_root.join(repo_path);
    if !target.exists() {
        return "unknown".to_owned();
    }
    let output = Command::new("git")
        .args(["log", "--all", "-1", "--format=%cs", "--", repo_path])
        .current_dir(repo_root)
        .output();
    match output {
        Ok(o) if o.status.success() => {
            let stamp = String::from_utf8_lossy(&o.stdout).trim().to_owned();
            if stamp.is_empty() {
                "unknown".to_owned()
            } else {
                stamp
            }
        }
        _ => "unknown".to_owned(),
    }
}

pub fn slice_records<'a>(records: &'a [SiteRecord]) -> SiteRecordSlices<'a> {
    let mut visible_dossiers = Vec::new();
    let mut visible_addenda = Vec::new();
    let mut featured_dossiers = Vec::new();
    let mut featured_addenda = Vec::new();

    for record in records {
        if !record.visible {
            continue;
        }
        match record.kind.as_str() {
            "dossier" => {
                visible_dossiers.push(record);
                if record.featured {
                    featured_dossiers.push(record);
                }
            }
            "addendum" => {
                visible_addenda.push(record);
                if record.featured {
                    featured_addenda.push(record);
                }
            }
            _ => {}
        }
    }

    visible_dossiers.sort_by(|a, b| dossier_index_sort_key(a).cmp(&dossier_index_sort_key(b)));
    visible_addenda.sort_by(|a, b| addenda_index_sort_key(a).cmp(&addenda_index_sort_key(b)));
    featured_dossiers.sort_by(featured_record_cmp);
    featured_addenda.sort_by(featured_record_cmp);

    let dossier_by_slug = visible_dossiers
        .iter()
        .map(|record| (record.slug.as_str(), *record))
        .collect();

    SiteRecordSlices {
        visible_dossiers,
        visible_addenda,
        featured_dossiers,
        featured_addenda,
        dossier_by_slug,
    }
}

pub fn related_visible_dossier<'a>(
    record: &SiteRecord,
    dossier_by_slug: &HashMap<&'a str, &'a SiteRecord>,
) -> Option<&'a SiteRecord> {
    record
        .related_dossier
        .as_deref()
        .and_then(|slug| dossier_by_slug.get(slug).copied())
}

fn dossier_index_sort_key(r: &SiteRecord) -> (bool, u32, String, String) {
    (
        r.featured_order.is_none(),
        r.featured_order.unwrap_or(u32::MAX),
        r.title.to_lowercase(),
        r.slug.clone(),
    )
}

fn addenda_index_sort_key(r: &SiteRecord) -> (bool, std::cmp::Reverse<String>, String, String) {
    (
        r.series.is_none(),
        std::cmp::Reverse(r.series.clone().unwrap_or_default()),
        r.title.to_lowercase(),
        r.slug.clone(),
    )
}

fn featured_release_rank(stage: &str) -> u8 {
    match stage {
        "promoted" => 0,
        "candidate" => 1,
        _ => 2,
    }
}

fn featured_record_cmp(left: &&SiteRecord, right: &&SiteRecord) -> std::cmp::Ordering {
    featured_release_rank(&left.release_stage)
        .cmp(&featured_release_rank(&right.release_stage))
        .then_with(|| {
            let left_order = left.featured_order.unwrap_or(u32::MAX);
            let right_order = right.featured_order.unwrap_or(u32::MAX);
            left_order.cmp(&right_order)
        })
        .then_with(|| left.title.to_lowercase().cmp(&right.title.to_lowercase()))
        .then_with(|| left.slug.cmp(&right.slug))
}

#[cfg(test)]
mod tests {
    use super::SiteRecord;
    use crate::release::PublicSurfaceLink;
    use std::collections::BTreeMap;

    fn make_record(stage: &str, surfaces: Vec<PublicSurfaceLink>) -> SiteRecord {
        SiteRecord {
            kind: "dossier".to_owned(),
            slug: "alpha".to_owned(),
            title: "Alpha".to_owned(),
            summary: "Alpha summary".to_owned(),
            license: "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)".to_owned(),
            status: "active".to_owned(),
            release_stage: stage.to_owned(),
            release_surfaces: surfaces,
            visible: true,
            featured: false,
            featured_order: None,
            hub_path: Some("site/dossiers/alpha/index.html".to_owned()),
            hub_generated: true,
            labels: BTreeMap::new(),
            related_dossier: None,
            repo_path: "dossiers/alpha".to_owned(),
            repo_url: "https://example.test/dossiers/alpha".to_owned(),
            last_activity: "today".to_owned(),
            has_docs_dir: true,
            has_docs_readme: true,
            series: Some("D-001".to_owned()),
        }
    }

    #[test]
    fn published_release_surfaces_require_promoted_publish_and_href() {
        let record = make_record(
            "promoted",
            vec![
                PublicSurfaceLink {
                    name: "python".to_owned(),
                    kind: "package".to_owned(),
                    label: "PyPI".to_owned(),
                    publish: true,
                    href: Some("https://example.test/pypi".to_owned()),
                },
                PublicSurfaceLink {
                    name: "docs".to_owned(),
                    kind: "docs".to_owned(),
                    label: "Docs".to_owned(),
                    publish: true,
                    href: None,
                },
                PublicSurfaceLink {
                    name: "source".to_owned(),
                    kind: "source_bundle".to_owned(),
                    label: "Source".to_owned(),
                    publish: false,
                    href: Some("https://example.test/source".to_owned()),
                },
            ],
        );

        assert!(record.has_published_release_surfaces());
        assert_eq!(
            record.published_surface_links(),
            vec![("PyPI", "https://example.test/pypi")]
        );

        let candidate = make_record("candidate", record.release_surfaces.clone());
        assert!(!candidate.has_published_release_surfaces());
        assert!(candidate.published_surface_links().is_empty());
    }
}
