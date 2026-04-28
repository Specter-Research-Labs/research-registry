use crate::graph::{self, GraphNode, RegistryGraph};
use crate::site::records::{self, SiteRecord};
use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ProjectArtifactSummary {
    pub visible_projects: usize,
    pub durable_surfaces: usize,
    pub site_data_mounts: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct DurableSurfaceArtifact {
    pub name: String,
    pub kind: String,
    pub local_db_path: Option<String>,
    pub remote_raw_namespace: Option<String>,
    pub remote_snapshot_namespace: Option<String>,
    pub raw_root_count: usize,
    pub refresh_command_count: usize,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SiteDataArtifact {
    pub name: String,
    pub site_path: String,
    pub local_source: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ProjectArtifactEntry {
    pub kind: String,
    pub slug: String,
    pub title: String,
    pub summary: String,
    pub series: Option<String>,
    pub repo_path: String,
    pub repo_url: String,
    pub hub_href: Option<String>,
    pub cabinet_href: Option<String>,
    pub durable_surfaces: Vec<DurableSurfaceArtifact>,
    pub site_data_mounts: Vec<SiteDataArtifact>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ProjectArtifactReport {
    pub version: u32,
    pub generated_at: String,
    pub summary: ProjectArtifactSummary,
    pub dossiers: Vec<ProjectArtifactEntry>,
    pub addenda: Vec<ProjectArtifactEntry>,
}

pub fn build_report_from_graph(
    graph: &RegistryGraph,
    records: &[SiteRecord],
) -> Result<ProjectArtifactReport> {
    let slices = records::slice_records(records);
    let dossiers = slices
        .visible_dossiers
        .iter()
        .map(|record| build_entry(graph, record))
        .collect::<Result<Vec<_>>>()?;
    let addenda = slices
        .visible_addenda
        .iter()
        .map(|record| build_entry(graph, record))
        .collect::<Result<Vec<_>>>()?;
    let all = dossiers.iter().chain(addenda.iter());
    let summary = ProjectArtifactSummary {
        visible_projects: dossiers.len() + addenda.len(),
        durable_surfaces: all.clone().map(|entry| entry.durable_surfaces.len()).sum(),
        site_data_mounts: all.clone().map(|entry| entry.site_data_mounts.len()).sum(),
    };
    Ok(ProjectArtifactReport {
        version: 1,
        generated_at: graph.generated_at.clone(),
        summary,
        dossiers,
        addenda,
    })
}

pub fn render_json(report: &ProjectArtifactReport) -> Result<String> {
    Ok(serde_json::to_string_pretty(report)? + "\n")
}

fn build_entry(graph: &RegistryGraph, record: &SiteRecord) -> Result<ProjectArtifactEntry> {
    let project_id = format!("project:{}:{}", record.kind, record.slug);
    let durable_surfaces = durable_surfaces(graph, &project_id)?;
    let site_data_mounts = site_data_mounts(graph, &project_id)?;
    Ok(ProjectArtifactEntry {
        kind: record.kind.clone(),
        slug: record.slug.clone(),
        title: record.title.clone(),
        summary: record.summary.clone(),
        series: record.series.clone(),
        repo_path: record.repo_path.clone(),
        repo_url: record.repo_url.clone(),
        hub_href: record.hub_href(),
        cabinet_href: record.cabinet_href(),
        durable_surfaces,
        site_data_mounts,
    })
}

fn durable_surfaces(
    graph: &RegistryGraph,
    project_id: &str,
) -> Result<Vec<DurableSurfaceArtifact>> {
    let mut surfaces = graph
        .outgoing_edges(project_id, "project_declares_durable_surface")
        .filter_map(|edge| graph.node(&edge.dst))
        .map(durable_surface_from_node)
        .collect::<Result<Vec<_>>>()?;
    surfaces.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(surfaces)
}

fn durable_surface_from_node(node: &GraphNode) -> Result<DurableSurfaceArtifact> {
    Ok(DurableSurfaceArtifact {
        name: required_attr(node, "name")?,
        kind: required_attr(node, "kind")?,
        local_db_path: graph::attr_str(node, "local_db_path").map(str::to_owned),
        remote_raw_namespace: graph::attr_str(node, "remote_raw_namespace").map(str::to_owned),
        remote_snapshot_namespace: graph::attr_str(node, "remote_snapshot_namespace")
            .map(str::to_owned),
        raw_root_count: array_len(node, "raw_roots"),
        refresh_command_count: array_len(node, "refresh_commands"),
    })
}

fn site_data_mounts(graph: &RegistryGraph, project_id: &str) -> Result<Vec<SiteDataArtifact>> {
    let mut mounts = graph
        .outgoing_edges(project_id, "project_mounts_site_data")
        .filter_map(|edge| graph.node(&edge.dst))
        .map(|node| {
            Ok(SiteDataArtifact {
                name: required_attr(node, "name")?,
                site_path: required_attr(node, "site_path")?,
                local_source: required_attr(node, "local_source")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    mounts.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(mounts)
}

fn required_attr(node: &GraphNode, key: &str) -> Result<String> {
    graph::attr_str(node, key)
        .map(str::to_owned)
        .ok_or_else(|| anyhow!("{}: missing {key}", node.id))
}

fn array_len(node: &GraphNode, key: &str) -> usize {
    graph::attr_value(node, key)
        .and_then(Value::as_array)
        .map_or(0, Vec::len)
}
