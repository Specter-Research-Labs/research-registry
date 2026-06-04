use crate::graph::{self, GraphNode, RegistryGraph};
use crate::release;
use crate::site::discover::relative_href;
use crate::site::markup;
use crate::site::records::{self, SiteRecord};
use anyhow::{anyhow, Result};
use maud::{html, Markup};
use serde::Serialize;
use std::collections::HashMap;

#[derive(Clone, Debug, Serialize)]
pub struct ProjectHealthSummary {
    pub visible_projects: usize,
    pub proof_ready_projects: usize,
    pub docs_ready_projects: usize,
    pub release_tracked_projects: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct ActionHealth {
    pub name: String,
    pub declared: bool,
    pub status: Option<String>,
    pub finished_at: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SurfaceHealth {
    pub name: String,
    pub label: String,
    pub kind: String,
    pub href: Option<String>,
    pub generated_at: Option<String>,
    pub evidence_present: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct ProjectHealthEntry {
    pub kind: String,
    pub slug: String,
    pub title: String,
    pub summary: String,
    pub series: Option<String>,
    pub repo_path: String,
    pub repo_url: String,
    pub last_activity: String,
    pub status: String,
    pub release_stage: String,
    pub gate_state: String,
    pub site_visible: bool,
    pub featured: bool,
    pub hub_mode: String,
    pub hub_href: Option<String>,
    pub cabinet_href: Option<String>,
    pub related_dossier: Option<String>,
    pub related_dossier_title: Option<String>,
    pub related_dossier_href: Option<String>,
    pub has_docs_dir: bool,
    pub has_docs_readme: bool,
    pub published_doc_count: usize,
    pub total_doc_count: usize,
    pub last_exec_at: Option<String>,
    pub latest_release_at: Option<String>,
    pub release_coverage_state: String,
    pub check: ActionHealth,
    pub smoke: ActionHealth,
    pub build: ActionHealth,
    pub publish: ActionHealth,
    pub additional_actions: Vec<ActionHealth>,
    pub published_surfaces: Vec<SurfaceHealth>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ProjectHealthReport {
    pub version: u32,
    pub generated_at: String,
    pub summary: ProjectHealthSummary,
    pub dossiers: Vec<ProjectHealthEntry>,
    pub addenda: Vec<ProjectHealthEntry>,
}

pub fn build_report_from_graph(
    graph: &RegistryGraph,
    records: &[SiteRecord],
) -> Result<ProjectHealthReport> {
    let slices = records::slice_records(records);
    let visible_count = slices.visible_dossiers.len() + slices.visible_addenda.len();

    let dossiers = slices
        .visible_dossiers
        .iter()
        .map(|record| build_entry(&graph, record, &slices.dossier_by_slug))
        .collect::<Result<Vec<_>>>()?;
    let addenda = slices
        .visible_addenda
        .iter()
        .map(|record| build_entry(&graph, record, &slices.dossier_by_slug))
        .collect::<Result<Vec<_>>>()?;

    let summary = ProjectHealthSummary {
        visible_projects: visible_count,
        proof_ready_projects: dossiers
            .iter()
            .chain(addenda.iter())
            .filter(|entry| entry.gate_state == "ready")
            .count(),
        docs_ready_projects: dossiers
            .iter()
            .chain(addenda.iter())
            .filter(|entry| entry.has_docs_readme)
            .count(),
        release_tracked_projects: dossiers
            .iter()
            .chain(addenda.iter())
            .filter(|entry| entry.release_coverage_state == "tracked")
            .count(),
    };

    Ok(ProjectHealthReport {
        version: 1,
        generated_at: graph.generated_at.clone(),
        summary,
        dossiers,
        addenda,
    })
}

pub fn render_json(report: &ProjectHealthReport) -> Result<String> {
    Ok(serde_json::to_string_pretty(report)? + "\n")
}

pub fn render_html(report: &ProjectHealthReport) -> String {
    let page_path = "projects/health/index.html";
    let markup = html! {
        section class="section-block" id="overview" {
            div class="site-page-title" { "Project Health" }
            ul class="update-meta-list" {
                li class="update-meta-item" {
                    span class="update-meta-label" { "Generated" }
                    span { (compact_timestamp(&report.generated_at)) }
                }
                li class="update-meta-item" {
                    span class="update-meta-label" { "Visible Projects" }
                    span { (report.summary.visible_projects) }
                }
                li class="update-meta-item" {
                    span class="update-meta-label" { "Docs Maps Ready" }
                    span { (report.summary.docs_ready_projects) }
                }
                li class="update-meta-item" {
                    span class="update-meta-label" { "Release Tracked" }
                    span { (report.summary.release_tracked_projects) }
                }
            }
        }

        @if !report.dossiers.is_empty() {
            section class="section-block" id="dossiers" {
                div class="site-section-title" { "Dossiers" }
                div class="card-stack" {
                    @for entry in &report.dossiers {
                        (render_project_card(entry, page_path))
                    }
                }
            }
        }

        @if !report.addenda.is_empty() {
            section class="section-block" id="addenda" {
                div class="site-section-title" { "Addenda" }
                div class="card-stack" {
                    @for entry in &report.addenda {
                        (render_project_card(entry, page_path))
                    }
                }
            }
        }
    };
    markup.into_string()
}

fn build_entry(
    graph: &RegistryGraph,
    record: &SiteRecord,
    dossier_by_slug: &HashMap<&str, &SiteRecord>,
) -> Result<ProjectHealthEntry> {
    let project_id = format!("project:{}:{}", record.kind, record.slug);
    let docs = graph
        .outgoing_edges(&project_id, "project_has_doc")
        .filter_map(|edge| graph.node(&edge.dst))
        .collect::<Vec<_>>();
    let published_doc_count = docs
        .iter()
        .filter(|node| graph::attr_bool(node, "published") == Some(true))
        .count();

    let actions = declared_actions(graph, &project_id)?;
    let check = canonical_action("check", &actions);
    let smoke = canonical_action("smoke", &actions);
    let build = canonical_action("build", &actions);
    let publish = canonical_action("publish", &actions);
    let additional_actions = actions
        .into_iter()
        .filter(|action| {
            !matches!(
                action.name.as_str(),
                "check" | "smoke" | "build" | "publish"
            )
        })
        .collect::<Vec<_>>();
    let last_exec_at = [
        check.finished_at.as_ref(),
        smoke.finished_at.as_ref(),
        build.finished_at.as_ref(),
        publish.finished_at.as_ref(),
    ]
    .into_iter()
    .flatten()
    .max()
    .cloned()
    .or_else(|| {
        additional_actions
            .iter()
            .filter_map(|action| action.finished_at.clone())
            .max()
    });

    let published_surfaces = declared_surfaces(record, graph, &project_id)?;
    let requires_publish = record.publishable_release_surfaces().next().is_some();
    let latest_release_at = published_surfaces
        .iter()
        .filter_map(|surface| surface.generated_at.clone())
        .max();
    let release_coverage_state = release_coverage_state(&published_surfaces).to_owned();
    let gate_state =
        gate_state(record, &check, &smoke, &build, &publish, requires_publish).to_owned();

    let related_dossier = records::related_visible_dossier(record, dossier_by_slug);
    let (related_dossier_title, related_dossier_href) = related_dossier
        .map(|dossier| (Some(dossier.title.clone()), dossier.hub_href()))
        .unwrap_or((None, None));

    Ok(ProjectHealthEntry {
        kind: record.kind.clone(),
        slug: record.slug.clone(),
        title: record.title.clone(),
        summary: record.summary.clone(),
        series: record.series.clone(),
        repo_path: record.repo_path.clone(),
        repo_url: record.repo_url.clone(),
        last_activity: record.last_activity.clone(),
        status: record.status.clone(),
        release_stage: record.release_stage.clone(),
        gate_state,
        site_visible: record.visible,
        featured: record.featured,
        hub_mode: record.hub_mode().to_owned(),
        hub_href: record.hub_href(),
        cabinet_href: record.cabinet_href(),
        related_dossier: record.related_dossier.clone(),
        related_dossier_title,
        related_dossier_href,
        has_docs_dir: record.has_docs_dir,
        has_docs_readme: record.has_docs_readme,
        published_doc_count,
        total_doc_count: docs.len(),
        last_exec_at,
        latest_release_at,
        release_coverage_state,
        check,
        smoke,
        build,
        publish,
        additional_actions,
        published_surfaces,
    })
}

fn declared_actions(graph: &RegistryGraph, project_id: &str) -> Result<Vec<ActionHealth>> {
    let mut actions = graph
        .outgoing_edges(project_id, "project_declares_exec")
        .filter_map(|edge| graph.node(&edge.dst))
        .map(|node| action_from_node(graph, node))
        .collect::<Result<Vec<_>>>()?;
    actions.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(actions)
}

fn action_from_node(graph: &RegistryGraph, node: &GraphNode) -> Result<ActionHealth> {
    let name = graph::attr_str(node, "name")
        .ok_or_else(|| anyhow!("{}: missing exec action name", node.id))?
        .to_owned();
    let evidence = graph
        .incoming_edges(&node.id, "evidence_for_exec")
        .filter_map(|edge| graph.node(&edge.src))
        .max_by_key(|candidate| graph::attr_str(candidate, "finished_at").unwrap_or(""));

    Ok(ActionHealth {
        name,
        declared: true,
        status: evidence
            .and_then(|candidate| graph::attr_str(candidate, "status").map(str::to_owned)),
        finished_at: evidence
            .and_then(|candidate| graph::attr_str(candidate, "finished_at").map(str::to_owned)),
    })
}

fn canonical_action(name: &str, actions: &[ActionHealth]) -> ActionHealth {
    actions
        .iter()
        .find(|action| action.name == name)
        .cloned()
        .unwrap_or(ActionHealth {
            name: name.to_owned(),
            declared: false,
            status: None,
            finished_at: None,
        })
}

fn declared_surfaces(
    record: &SiteRecord,
    graph: &RegistryGraph,
    project_id: &str,
) -> Result<Vec<SurfaceHealth>> {
    let surface_nodes = graph
        .outgoing_edges(project_id, "project_declares_surface")
        .filter_map(|edge| graph.node(&edge.dst))
        .filter_map(|node| graph::attr_str(node, "name").map(|name| (name.to_owned(), node)))
        .collect::<HashMap<_, _>>();
    let mut surfaces = record
        .publishable_release_surfaces()
        .map(|surface| {
            let node = surface_nodes
                .get(surface.name.as_str())
                .copied()
                .ok_or_else(|| {
                    anyhow!(
                        "{project_id}: missing graph node for published surface {}",
                        surface.name
                    )
                })?;
            surface_from_record(graph, node, surface)
        })
        .collect::<Result<Vec<_>>>()?;
    surfaces.sort_by(|left, right| left.label.cmp(&right.label));
    Ok(surfaces)
}

fn surface_from_record(
    graph: &RegistryGraph,
    node: &GraphNode,
    surface: &release::PublicSurfaceLink,
) -> Result<SurfaceHealth> {
    let evidence = graph
        .incoming_edges(&node.id, "evidence_for_surface")
        .filter_map(|edge| graph.node(&edge.src))
        .max_by_key(|candidate| graph::attr_str(candidate, "generated_at").unwrap_or(""));

    Ok(SurfaceHealth {
        name: surface.name.clone(),
        label: surface.label.clone(),
        kind: surface.kind.clone(),
        href: surface.href.clone(),
        generated_at: evidence
            .and_then(|candidate| graph::attr_str(candidate, "generated_at").map(str::to_owned)),
        evidence_present: evidence.is_some(),
    })
}

fn gate_state(
    record: &SiteRecord,
    check: &ActionHealth,
    smoke: &ActionHealth,
    build: &ActionHealth,
    publish: &ActionHealth,
    requires_publish: bool,
) -> &'static str {
    match record.release_stage.as_str() {
        "promoted" => {
            if !check.declared
                || !smoke.declared
                || !build.declared
                || (requires_publish && !publish.declared)
            {
                "blocked"
            } else if action_ok(check)
                && action_ok(smoke)
                && action_ok(build)
                && (!requires_publish || action_ok(publish))
            {
                "ready"
            } else {
                "waiting"
            }
        }
        "candidate" => {
            if !check.declared {
                "blocked"
            } else if action_ok(check) {
                "ready"
            } else {
                "waiting"
            }
        }
        _ => {
            if action_ok(check) || action_ok(smoke) || action_ok(build) {
                "observed"
            } else {
                "informational"
            }
        }
    }
}

fn action_ok(action: &ActionHealth) -> bool {
    action.status.as_deref() == Some("ok")
}

fn release_coverage_state(surfaces: &[SurfaceHealth]) -> &'static str {
    if surfaces.is_empty() {
        "n/a"
    } else if surfaces.iter().all(|surface| surface.evidence_present) {
        "tracked"
    } else {
        "partial"
    }
}

fn render_project_card(project: &ProjectHealthEntry, page_path: &str) -> Markup {
    let hub_href = project
        .hub_href
        .as_ref()
        .map(|href| relative_href(page_path, href));
    let cabinet_href = project
        .cabinet_href
        .as_ref()
        .map(|href| relative_href(page_path, href));
    let related_dossier_href = project
        .related_dossier_href
        .as_ref()
        .map(|href| relative_href(page_path, href));

    html! {
        article class="dossier-card" id=(project.slug) {
            div class="dossier-card-header" {
                div class="dossier-card-tab" {
                    @if let Some(ref series) = project.series {
                        span class="series-badge" { (series) }
                    }
                    (project.title)
                }
            }
            div class="dossier-card-body" {
                div class="card-meta" {
                    div class="card-meta-row" {
                        span class="card-meta-label" { "Status" }
                        span class="card-meta-value" {
                            (render_status_value(project))
                        }
                    }
                    div class="card-meta-row" {
                        span class="card-meta-label" { "Docs" }
                        span class="card-meta-value" {
                            @if project.has_docs_readme {
                                span class="project-chip" { "map ready" }
                                " "
                            }
                            (project.published_doc_count) " published / " (project.total_doc_count) " total"
                        }
                    }
                    div class="card-meta-row" {
                        span class="card-meta-label" { "Hub" }
                        span class="card-meta-value" {
                            @if let Some(ref href) = hub_href {
                                span class="project-chip" { (project.hub_mode) }
                                " "
                                a href=(href) { "Open Hub" }
                            } @else if let Some(ref title) = project.related_dossier_title {
                                @if let Some(ref href) = related_dossier_href {
                                    a href=(href) { (title) }
                                } @else {
                                    (title)
                                }
                            } @else {
                                span class="project-chip" { (project.hub_mode) }
                            }
                        }
                    }
                    div class="card-meta-row" {
                        span class="card-meta-label" { "Last Release" }
                        span class="card-meta-value" {
                            span class="project-chip" { (project.release_coverage_state) }
                            @if let Some(ref ts) = project.latest_release_at {
                                " " (compact_timestamp(ts))
                            }
                        }
                    }
                    div class="card-meta-row" {
                        span class="card-meta-label" { "Activity" }
                        span class="card-meta-value" { (project.last_activity) }
                    }
                }
                p { (project.summary) }
                div class="link-row" {
                    @if let Some(ref href) = hub_href {
                        a href=(href) { "Hub" }
                    }
                    (markup::link(&project.repo_url, "Repository"))
                    @if let Some(ref href) = cabinet_href {
                        a href=(href) { "Cabinet Docs" }
                    }
                    @for surface in &project.published_surfaces {
                        @if let Some(ref href) = surface.href {
                            (markup::link(href, surface.label.as_str()))
                        }
                    }
                }
            }
        }
    }
}

fn render_status_value(project: &ProjectHealthEntry) -> Markup {
    if project.kind == "dossier" {
        html! {
            span class=(format!("project-status {}", project.status)) { (project.status) }
            " "
            span class="project-chip" { "release:" (project.release_stage) }
        }
    } else {
        html! {
            span class=(format!("addenda-chip status-{}", project.status)) { (project.status) }
            " "
            span class="project-chip" { "release:" (project.release_stage) }
        }
    }
}

fn compact_timestamp(value: &str) -> String {
    if let Some((date, time)) = value.split_once('T') {
        let time = time.trim_end_matches('Z');
        let hm = time.get(..5).unwrap_or(time);
        return format!("{date} {hm}Z");
    }
    value.to_owned()
}
