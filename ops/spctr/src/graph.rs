use crate::manifest::{self, ProjectManifest};
use crate::site::{archive, blog, cabinet::docs, discover};
use crate::{exec, registry, release};
use anyhow::{Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RegistryGraph {
    pub version: u32,
    pub generated_at: String,
    pub repo_root: String,
    pub scope_project: Option<String>,
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GraphNode {
    pub id: String,
    pub kind: String,
    pub attrs: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct GraphEdge {
    pub src: String,
    pub kind: String,
    pub dst: String,
    pub attrs: BTreeMap<String, Value>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct GraphBuildOptions {
    pub include_docs: bool,
    pub include_evidence: bool,
    pub include_updates: bool,
}

impl Default for GraphBuildOptions {
    fn default() -> Self {
        Self::full()
    }
}

impl GraphBuildOptions {
    pub const fn full() -> Self {
        Self {
            include_docs: true,
            include_evidence: true,
            include_updates: true,
        }
    }

    pub const fn site_projection() -> Self {
        Self {
            include_docs: true,
            include_evidence: true,
            include_updates: false,
        }
    }

    pub const fn site_records() -> Self {
        Self {
            include_docs: false,
            include_evidence: false,
            include_updates: false,
        }
    }
}

impl RegistryGraph {
    pub fn node(&self, id: &str) -> Option<&GraphNode> {
        self.nodes.iter().find(|node| node.id == id)
    }

    pub fn nodes_of_kind<'a>(&'a self, kind: &'a str) -> impl Iterator<Item = &'a GraphNode> + 'a {
        self.nodes.iter().filter(move |node| node.kind == kind)
    }

    pub fn outgoing_edges<'a>(
        &'a self,
        src: &'a str,
        kind: &'a str,
    ) -> impl Iterator<Item = &'a GraphEdge> + 'a {
        self.edges
            .iter()
            .filter(move |edge| edge.src == src && edge.kind == kind)
    }

    pub fn incoming_edges<'a>(
        &'a self,
        dst: &'a str,
        kind: &'a str,
    ) -> impl Iterator<Item = &'a GraphEdge> + 'a {
        self.edges
            .iter()
            .filter(move |edge| edge.dst == dst && edge.kind == kind)
    }
}

pub fn default_dossier_hub_path(slug: &str) -> String {
    format!("site/dossiers/{slug}/index.html")
}

pub fn attr_value<'a>(node: &'a GraphNode, key: &str) -> Option<&'a Value> {
    node.attrs.get(key)
}

pub fn attr_str<'a>(node: &'a GraphNode, key: &str) -> Option<&'a str> {
    attr_value(node, key).and_then(Value::as_str)
}

fn required_attr<'a>(node: &'a GraphNode, key: &str) -> Result<&'a str> {
    attr_str(node, key).ok_or_else(|| anyhow::anyhow!("{}: missing graph attr '{key}'", node.id))
}

pub fn attr_bool(node: &GraphNode, key: &str) -> Option<bool> {
    attr_value(node, key).and_then(Value::as_bool)
}

pub fn attr_u64(node: &GraphNode, key: &str) -> Option<u64> {
    attr_value(node, key).and_then(Value::as_u64)
}

#[derive(Clone, Debug)]
struct GraphDocRecord {
    entry: docs::DocEntry,
    published: bool,
}

#[derive(Clone, Debug)]
struct UpdateRecord {
    id: String,
    attrs: BTreeMap<String, Value>,
}

#[derive(Clone, Debug)]
struct ExecEvidenceRecord {
    action: String,
    attrs: BTreeMap<String, Value>,
}

#[derive(Clone, Debug)]
struct ReleaseEvidenceRecord {
    surface: Option<String>,
    path: Utf8PathBuf,
    attrs: BTreeMap<String, Value>,
}

#[derive(Default)]
struct GraphBuilder {
    nodes: BTreeMap<String, GraphNode>,
    edges: Vec<GraphEdge>,
}

impl GraphBuilder {
    fn upsert_node(&mut self, id: String, kind: &str, attrs: BTreeMap<String, Value>) {
        match self.nodes.get_mut(&id) {
            Some(existing) => {
                debug_assert_eq!(existing.kind, kind);
                existing.attrs.extend(attrs);
            }
            None => {
                self.nodes.insert(
                    id.clone(),
                    GraphNode {
                        id,
                        kind: kind.to_owned(),
                        attrs,
                    },
                );
            }
        }
    }

    fn add_edge(&mut self, src: String, kind: &str, dst: String, attrs: BTreeMap<String, Value>) {
        let duplicate = self.edges.iter().any(|edge| {
            edge.src == src && edge.kind == kind && edge.dst == dst && edge.attrs == attrs
        });
        if !duplicate {
            self.edges.push(GraphEdge {
                src,
                kind: kind.to_owned(),
                dst,
                attrs,
            });
        }
    }

    fn finish(self, repo_root: &Utf8Path, scope_project: Option<String>) -> RegistryGraph {
        let mut nodes = self.nodes.into_values().collect::<Vec<_>>();
        nodes.sort_by(|left, right| left.id.cmp(&right.id));

        let mut edges = self.edges;
        edges.sort_by(|left, right| {
            left.src
                .cmp(&right.src)
                .then_with(|| left.kind.cmp(&right.kind))
                .then_with(|| left.dst.cmp(&right.dst))
        });

        RegistryGraph {
            version: 1,
            generated_at: Utc::now().to_rfc3339(),
            repo_root: repo_root.as_str().to_owned(),
            scope_project,
            nodes,
            edges,
        }
    }
}

pub fn build(repo_root: &Utf8Path, project: Option<&str>) -> Result<RegistryGraph> {
    build_with_options(repo_root, project, GraphBuildOptions::full())
}

pub fn build_with_options(
    repo_root: &Utf8Path,
    project: Option<&str>,
    options: GraphBuildOptions,
) -> Result<RegistryGraph> {
    let manifests = discover_manifests(repo_root, project)?;
    let docs = if options.include_docs {
        load_docs(&manifests)?
    } else {
        Vec::new()
    };
    let updates = if project.is_some() || !options.include_updates {
        Vec::new()
    } else {
        load_updates(repo_root)?
    };
    let registry = if registry::registry_path(repo_root).is_file() {
        Some(registry::load_registry(repo_root)?)
    } else {
        None
    };
    if let Some(registry) = registry.as_ref() {
        registry::validate_manifest_consistency(registry, &manifests)?;
    }
    let docs_by_project = group_docs_by_project(docs);
    let mut builder = GraphBuilder::default();

    for manifest in &manifests {
        add_project_subgraph(
            repo_root,
            &mut builder,
            manifest,
            registry.as_ref(),
            docs_by_project.get(&(manifest.kind.clone(), manifest.slug.clone())),
            options,
        )?;
    }

    for update in updates {
        builder.upsert_node(update_node_id(&update.id), "update", update.attrs);
    }

    if project.is_none() {
        let article_ids = add_article_subgraph(repo_root, &mut builder, registry.as_ref())?;
        add_site_output_subgraph(repo_root, &mut builder, options, &article_ids)?;
        add_archive_surface_subgraph(&mut builder);
    }

    let scope_project = match project {
        Some(_) => manifests.first().map(project_node_id),
        None => None,
    };
    Ok(builder.finish(repo_root, scope_project))
}

pub fn write(graph: &RegistryGraph, output: &Utf8Path) -> Result<()> {
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create graph output dir {parent}"))?;
    }
    let rendered = serde_json::to_string_pretty(graph)? + "\n";
    fs::write(output, rendered).with_context(|| format!("failed to write graph to {output}"))?;
    Ok(())
}

fn discover_manifests(repo_root: &Utf8Path, project: Option<&str>) -> Result<Vec<ProjectManifest>> {
    match project {
        Some(slug) => Ok(vec![release::lookup_project(repo_root, slug)?]),
        None => release::discover_release_manifests(repo_root),
    }
}

fn load_docs(manifests: &[ProjectManifest]) -> Result<Vec<GraphDocRecord>> {
    let mut records = docs::find_docs_for_manifests(manifests)?
        .into_iter()
        .map(|entry| GraphDocRecord {
            published: entry.publish_docs && entry.published,
            entry,
        })
        .collect::<Vec<_>>();
    records.sort_by(|left, right| left.entry.path.cmp(&right.entry.path));
    Ok(records)
}

fn load_updates(repo_root: &Utf8Path) -> Result<Vec<UpdateRecord>> {
    let updates_root = repo_root.join("site/updates/entries");
    if !updates_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut paths = Vec::new();
    for entry in
        fs::read_dir(&updates_root).with_context(|| format!("failed to read {updates_root}"))?
    {
        let entry = entry.with_context(|| format!("failed to read entry in {updates_root}"))?;
        let path: Utf8PathBuf = entry
            .path()
            .try_into()
            .context("non-UTF-8 update entry path")?;
        if path.extension().is_some_and(|ext| ext == "json") {
            paths.push(path);
        }
    }
    paths.sort();

    let mut updates = Vec::new();
    for path in paths {
        let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
        let raw: Value =
            serde_json::from_str(&text).with_context(|| format!("invalid JSON in {path}"))?;
        let Some(object) = raw.as_object() else {
            anyhow::bail!("{path}: update entry must be a JSON object");
        };
        let id = require_string(object.get("id"), "id", &path)?;
        let mut attrs = base_attrs("update_entry", repo_rel(repo_root, &path)?);
        attrs.insert("id".to_owned(), json!(id));
        attrs.insert(
            "kind".to_owned(),
            json!(require_string(object.get("kind"), "kind", &path)?),
        );
        attrs.insert(
            "label".to_owned(),
            json!(require_string(object.get("label"), "label", &path)?),
        );
        attrs.insert(
            "date".to_owned(),
            json!(require_string(object.get("date"), "date", &path)?),
        );
        attrs.insert(
            "published_at".to_owned(),
            json!(require_string(
                object.get("published_at"),
                "published_at",
                &path
            )?),
        );
        attrs.insert(
            "topic".to_owned(),
            json!(require_string(object.get("topic"), "topic", &path)?),
        );
        if let Some(window) = object.get("window").and_then(Value::as_object) {
            attrs.insert(
                "window_start".to_owned(),
                json!(require_string(window.get("start"), "window.start", &path)?),
            );
            attrs.insert(
                "window_end".to_owned(),
                json!(require_string(window.get("end"), "window.end", &path)?),
            );
        }
        insert_optional_u64_attr(&mut attrs, "series_number", object.get("series_number"));
        insert_optional_string_attr(&mut attrs, "ledger_entry_id", object.get("ledger_entry_id"));
        insert_optional_u64_attr(
            &mut attrs,
            "zulip_message_id",
            object.get("zulip_message_id"),
        );
        if let Some(sections) = object.get("sections") {
            attrs.insert("sections".to_owned(), sections.clone());
        }
        updates.push(UpdateRecord { id, attrs });
    }
    Ok(updates)
}

fn group_docs_by_project(
    docs: Vec<GraphDocRecord>,
) -> BTreeMap<(String, String), Vec<GraphDocRecord>> {
    let mut grouped = BTreeMap::new();
    for record in docs {
        grouped
            .entry((
                record.entry.project_kind.clone(),
                record.entry.project_slug.clone(),
            ))
            .or_insert_with(Vec::new)
            .push(record);
    }
    grouped
}

fn add_project_subgraph(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    registry: Option<&registry::Registry>,
    docs: Option<&Vec<GraphDocRecord>>,
    options: GraphBuildOptions,
) -> Result<()> {
    let project_id = project_node_id(manifest);
    let manifest_path = repo_rel(repo_root, &manifest.path)?;
    let project_root = repo_rel(repo_root, &manifest.root)?;
    let series_id = project_series_id(registry, manifest);
    let effective_hub_path = effective_site_hub_path(manifest);
    let docs_root = manifest
        .spctr
        .as_ref()
        .and_then(|spctr| spctr.docs.as_ref())
        .map(|docs| manifest.root.join(&docs.root))
        .unwrap_or_else(|| manifest.root.join("docs"));
    let docs_landing = manifest
        .spctr
        .as_ref()
        .and_then(|spctr| spctr.docs.as_ref())
        .and_then(|docs| docs.landing.as_ref())
        .map(|landing| manifest.root.join(landing))
        .unwrap_or_else(|| manifest.root.join("docs/README.md"));
    let mut project_attrs = base_attrs("manifest", manifest_path.clone());
    project_attrs.insert("kind".to_owned(), json!(manifest.kind));
    project_attrs.insert("slug".to_owned(), json!(manifest.slug));
    project_attrs.insert("manifest_path".to_owned(), json!(manifest_path));
    project_attrs.insert("root".to_owned(), json!(project_root));
    project_attrs.insert("repo_path".to_owned(), json!(project_root));
    project_attrs.insert("title".to_owned(), json!(manifest.title));
    project_attrs.insert("summary".to_owned(), json!(manifest.summary));
    project_attrs.insert("license".to_owned(), json!(manifest.license));
    project_attrs.insert("status".to_owned(), json!(manifest.status));
    project_attrs.insert("labels".to_owned(), json!(manifest.labels));
    project_attrs.insert("site_visible".to_owned(), json!(manifest.site.visible));
    project_attrs.insert("site_featured".to_owned(), json!(manifest.site.featured));
    project_attrs.insert(
        "site_featured_order".to_owned(),
        optional_value(manifest.site.featured_order),
    );
    project_attrs.insert(
        "site_hub_path".to_owned(),
        optional_value(manifest.site.hub_path.as_ref()),
    );
    project_attrs.insert(
        "site_effective_hub_path".to_owned(),
        optional_value(effective_hub_path.as_ref()),
    );
    project_attrs.insert(
        "site_hub_generated".to_owned(),
        json!(hub_path_is_generated(manifest)),
    );
    project_attrs.insert(
        "site_publish_docs".to_owned(),
        json!(manifest.site.publish_docs),
    );
    project_attrs.insert("has_docs_dir".to_owned(), json!(docs_root.is_dir()));
    project_attrs.insert("has_docs_readme".to_owned(), json!(docs_landing.is_file()));
    project_attrs.insert(
        "release_stage".to_owned(),
        json!(manifest.release.stage.as_str()),
    );
    project_attrs.insert(
        "related_dossier".to_owned(),
        optional_value(manifest.related_dossier.as_ref()),
    );
    project_attrs.insert("series_id".to_owned(), optional_value(series_id.as_ref()));
    if let Some(spctr) = &manifest.spctr {
        project_attrs.insert("spctr_project".to_owned(), json!(spctr.project));
        project_attrs.insert(
            "default_durable_surface".to_owned(),
            optional_value(spctr.default_surface.as_ref()),
        );
    }
    builder.upsert_node(project_id.clone(), "project", project_attrs);

    if let Some(series_id) = &series_id {
        ensure_series_node(repo_root, builder, registry, manifest, series_id)?;
        builder.add_edge(
            project_id.clone(),
            "project_in_series",
            series_node_id(series_id),
            BTreeMap::new(),
        );
    }

    if let Some(related_dossier) = &manifest.related_dossier {
        let related_id = format!("project:dossier:{related_dossier}");
        if builder.nodes.contains_key(&related_id) {
            builder.add_edge(
                project_id.clone(),
                "addendum_for_dossier",
                related_id,
                BTreeMap::new(),
            );
        }
    }

    add_durable_surfaces(repo_root, builder, manifest, &project_id)?;
    add_release_surfaces(repo_root, builder, manifest, &project_id)?;
    add_expected_outputs(repo_root, builder, manifest)?;
    add_exec_actions(repo_root, builder, manifest, &project_id)?;
    add_site_data_mounts(repo_root, builder, manifest, &project_id)?;
    if options.include_docs {
        add_doc_nodes(
            repo_root,
            builder,
            manifest,
            docs,
            registry,
            series_id.as_deref(),
            &project_id,
        )?;
    }
    if options.include_evidence {
        add_exec_evidence(repo_root, builder, manifest, &project_id)?;
        add_release_evidence(repo_root, builder, manifest, &project_id)?;
    }
    Ok(())
}

fn add_durable_surfaces(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    project_id: &str,
) -> Result<()> {
    let Some(spctr) = &manifest.spctr else {
        return Ok(());
    };
    for (name, surface) in &spctr.surfaces {
        let mut attrs = base_attrs("manifest", repo_rel(repo_root, &manifest.path)?);
        attrs.insert("project_kind".to_owned(), json!(manifest.kind));
        attrs.insert("project_slug".to_owned(), json!(manifest.slug));
        attrs.insert("name".to_owned(), json!(name));
        attrs.insert("kind".to_owned(), json!(surface.kind));
        attrs.insert(
            "local_db_path".to_owned(),
            optional_value(surface.local_db_path.as_ref()),
        );
        attrs.insert(
            "db_raw_root".to_owned(),
            optional_value(surface.db_raw_root),
        );
        attrs.insert(
            "refresh_commands".to_owned(),
            json!(durable_refresh_commands(surface)),
        );
        attrs.insert(
            "remote_raw_namespace".to_owned(),
            optional_value(surface.remote_raw_namespace.as_ref()),
        );
        attrs.insert(
            "remote_snapshot_namespace".to_owned(),
            optional_value(surface.remote_snapshot_namespace.as_ref()),
        );
        attrs.insert("raw_roots".to_owned(), raw_roots_value(surface));
        let surface_id = durable_surface_node_id(manifest, name);
        builder.upsert_node(surface_id.clone(), "durable_surface", attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_declares_durable_surface",
            surface_id.clone(),
            BTreeMap::new(),
        );
        if spctr.default_surface.as_deref() == Some(name.as_str()) {
            builder.add_edge(
                project_id.to_owned(),
                "default_durable_surface",
                surface_id,
                BTreeMap::new(),
            );
        }
    }
    Ok(())
}

fn add_release_surfaces(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    project_id: &str,
) -> Result<()> {
    let public_links = release::public_surface_links(manifest)
        .into_iter()
        .map(|link| (link.name.clone(), link))
        .collect::<BTreeMap<_, _>>();
    for (ordinal, surface) in manifest.release.surfaces.iter().enumerate() {
        let mut attrs = base_attrs("manifest", repo_rel(repo_root, &manifest.path)?);
        attrs.insert("project_kind".to_owned(), json!(manifest.kind));
        attrs.insert("project_slug".to_owned(), json!(manifest.slug));
        attrs.insert("name".to_owned(), json!(surface.name));
        attrs.insert("kind".to_owned(), json!(surface.kind.as_str()));
        attrs.insert(
            "label".to_owned(),
            json!(public_links
                .get(&surface.name)
                .map(|link| link.label.as_str())
                .unwrap_or_default()),
        );
        attrs.insert("publish".to_owned(), json!(surface.publish));
        attrs.insert("ordinal".to_owned(), json!(ordinal));
        attrs.insert("path".to_owned(), json!(surface.path));
        attrs.insert("include_docs".to_owned(), json!(surface.include_docs));
        attrs.insert("support_paths".to_owned(), json!(surface.support_paths));
        attrs.insert(
            "language".to_owned(),
            optional_value(surface.language.map(|language| language.as_str())),
        );
        attrs.insert(
            "registry".to_owned(),
            optional_value(surface.registry.as_ref()),
        );
        attrs.insert(
            "distribution_channel".to_owned(),
            optional_value(surface.distribution_channel.as_ref()),
        );
        attrs.insert(
            "publish_mode".to_owned(),
            optional_value(surface.publish_mode.map(|mode| mode.as_str())),
        );
        attrs.insert(
            "mirror_repo".to_owned(),
            optional_value(surface.mirror_repo.as_ref()),
        );
        attrs.insert(
            "package_source_path".to_owned(),
            optional_value(surface.source_path.as_ref()),
        );
        attrs.insert(
            "public_namespace".to_owned(),
            optional_value(surface.public_namespace.as_ref()),
        );
        attrs.insert(
            "href".to_owned(),
            optional_value(
                public_links
                    .get(&surface.name)
                    .and_then(|link| link.href.as_ref()),
            ),
        );
        let surface_id = release_surface_node_id(manifest, &surface.name);
        builder.upsert_node(surface_id.clone(), "release_surface", attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_declares_surface",
            surface_id,
            BTreeMap::new(),
        );
    }
    Ok(())
}

fn add_expected_outputs(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
) -> Result<()> {
    let Some(spctr) = &manifest.spctr else {
        return Ok(());
    };
    for output in &spctr.expected_outputs {
        let mut attrs = base_attrs("manifest", repo_rel(repo_root, &manifest.path)?);
        attrs.insert("project_kind".to_owned(), json!(manifest.kind));
        attrs.insert("project_slug".to_owned(), json!(manifest.slug));
        attrs.insert("name".to_owned(), json!(output.name));
        attrs.insert("path".to_owned(), json!(output.path));
        attrs.insert("kind".to_owned(), json!(output.kind));
        attrs.insert("required".to_owned(), json!(output.required));
        attrs.insert(
            "surface".to_owned(),
            optional_value(output.surface.as_ref()),
        );
        let output_id = expected_output_node_id(manifest, &output.name);
        builder.upsert_node(output_id.clone(), "expected_output", attrs);
        if let Some(surface_name) = &output.surface {
            builder.add_edge(
                output_id,
                "surface_targets_output",
                release_surface_node_id(manifest, surface_name),
                BTreeMap::new(),
            );
        }
    }
    Ok(())
}

fn add_exec_actions(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    project_id: &str,
) -> Result<()> {
    let Some(spctr) = &manifest.spctr else {
        return Ok(());
    };
    for action_name in spctr.exec.keys() {
        let plan = exec::build_plan(repo_root, manifest, action_name)?;
        let mut attrs = base_attrs("manifest", repo_rel(repo_root, &manifest.path)?);
        attrs.insert("project_kind".to_owned(), json!(manifest.kind));
        attrs.insert("project_slug".to_owned(), json!(manifest.slug));
        attrs.insert("name".to_owned(), json!(plan.action));
        attrs.insert(
            "description".to_owned(),
            optional_value(plan.description.as_ref()),
        );
        attrs.insert("workdir".to_owned(), json!(plan.workdir));
        attrs.insert("commands".to_owned(), json!(plan.commands));
        attrs.insert("env".to_owned(), json!(plan.env));
        attrs.insert("timeout_sec".to_owned(), optional_value(plan.timeout_sec));
        attrs.insert("network".to_owned(), optional_value(plan.network.as_ref()));
        attrs.insert("requires".to_owned(), json!(plan.requires));
        let action_id = exec_action_node_id(manifest, action_name);
        builder.upsert_node(action_id.clone(), "exec_action", attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_declares_exec",
            action_id.clone(),
            BTreeMap::new(),
        );
        for output in &plan.expected_outputs {
            builder.add_edge(
                action_id.clone(),
                "exec_expects_output",
                expected_output_node_id(manifest, &output.name),
                BTreeMap::new(),
            );
        }
    }
    Ok(())
}

fn add_site_data_mounts(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    project_id: &str,
) -> Result<()> {
    let Some(spctr) = &manifest.spctr else {
        return Ok(());
    };
    for site_data in &spctr.site_data {
        let mut attrs = base_attrs("manifest", repo_rel(repo_root, &manifest.path)?);
        attrs.insert("project_kind".to_owned(), json!(manifest.kind));
        attrs.insert("project_slug".to_owned(), json!(manifest.slug));
        attrs.insert("name".to_owned(), json!(site_data.name));
        attrs.insert("site_path".to_owned(), json!(site_data.site_path));
        attrs.insert("local_source".to_owned(), json!(site_data.local_source));
        let mount_id = site_data_mount_node_id(manifest, &site_data.name);
        builder.upsert_node(mount_id.clone(), "site_data_mount", attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_mounts_site_data",
            mount_id,
            BTreeMap::new(),
        );
    }
    Ok(())
}

fn add_doc_nodes(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    docs: Option<&Vec<GraphDocRecord>>,
    registry: Option<&registry::Registry>,
    series_id: Option<&str>,
    project_id: &str,
) -> Result<()> {
    let Some(docs) = docs else {
        return Ok(());
    };
    for record in docs {
        let doc_id_value = series_id.and_then(|series_id| {
            registry
                .and_then(|loaded| registry::doc_id_for_slug(loaded, series_id, &record.entry.slug))
        });
        let mut attrs = base_attrs("doc", repo_rel(repo_root, &record.entry.path)?);
        attrs.insert("project_kind".to_owned(), json!(record.entry.project_kind));
        attrs.insert("project_slug".to_owned(), json!(record.entry.project_slug));
        attrs.insert("slug".to_owned(), json!(record.entry.slug));
        attrs.insert(
            "path".to_owned(),
            json!(repo_rel(repo_root, &record.entry.path)?),
        );
        attrs.insert(
            "docs_root".to_owned(),
            json!(repo_rel(repo_root, &record.entry.docs_root)?),
        );
        attrs.insert("title".to_owned(), json!(record.entry.title));
        attrs.insert("category".to_owned(), json!(record.entry.category));
        attrs.insert("published".to_owned(), json!(record.published));
        attrs.insert("doc_id".to_owned(), optional_value(doc_id_value));
        let node_id = doc_node_id(manifest, &record.entry.slug);
        builder.upsert_node(node_id.clone(), "doc", attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_has_doc",
            node_id.clone(),
            BTreeMap::new(),
        );
        if let Some(series_id) = series_id {
            ensure_series_node(repo_root, builder, registry, manifest, series_id)?;
            let mut edge_attrs = BTreeMap::new();
            if let Some(doc_id_value) = doc_id_value {
                edge_attrs.insert("doc_id".to_owned(), json!(doc_id_value));
            }
            builder.add_edge(
                node_id,
                "doc_in_series",
                series_node_id(series_id),
                edge_attrs,
            );
        }
    }
    Ok(())
}

fn add_exec_evidence(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    project_id: &str,
) -> Result<()> {
    for record in discover_exec_evidence(repo_root, manifest)? {
        let node_id = exec_evidence_node_id(manifest, &record.action);
        builder.upsert_node(node_id.clone(), "evidence_card", record.attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_has_evidence",
            node_id.clone(),
            BTreeMap::new(),
        );
        builder.add_edge(
            node_id,
            "evidence_for_exec",
            exec_action_node_id(manifest, &record.action),
            BTreeMap::new(),
        );
    }
    Ok(())
}

fn add_release_evidence(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    manifest: &ProjectManifest,
    project_id: &str,
) -> Result<()> {
    for record in discover_release_evidence(repo_root, manifest)? {
        let node_id = release_evidence_node_id(manifest, &repo_rel(repo_root, &record.path)?);
        builder.upsert_node(node_id.clone(), "evidence_card", record.attrs);
        builder.add_edge(
            project_id.to_owned(),
            "project_has_evidence",
            node_id.clone(),
            BTreeMap::new(),
        );
        if let Some(surface_name) = &record.surface {
            builder.add_edge(
                node_id,
                "evidence_for_surface",
                release_surface_node_id(manifest, surface_name),
                BTreeMap::new(),
            );
        }
    }
    Ok(())
}

fn add_article_subgraph(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    registry: Option<&registry::Registry>,
) -> Result<Vec<String>> {
    let mut article_ids = Vec::new();
    for post in discover::discover_published_blog_posts(repo_root)? {
        let slug = discover::blog_slug_from_href(&post.href)?;
        let source_path = discover::blog_markdown_relpath(slug);
        let series_id = published_article_series_id(registry, &post, &slug)?;
        let article_id = article_node_id(&slug);
        let mut attrs = base_attrs("blog_post", source_path.clone());
        attrs.insert("slug".to_owned(), json!(slug));
        attrs.insert("title".to_owned(), json!(post.title));
        attrs.insert("href".to_owned(), json!(post.href));
        attrs.insert("summary".to_owned(), json!(post.summary));
        attrs.insert("series_id".to_owned(), optional_value(series_id.as_ref()));
        attrs.insert("release".to_owned(), json!(post.release));
        builder.upsert_node(article_id.clone(), "article", attrs);
        if let Some(series_id) = series_id.as_deref() {
            ensure_article_series_node(repo_root, builder, registry, series_id, &source_path)?;
            builder.add_edge(
                article_id.clone(),
                "article_in_series",
                series_node_id(series_id),
                BTreeMap::new(),
            );
        }
        article_ids.push(article_id);
    }
    article_ids.sort();
    Ok(article_ids)
}

#[derive(Clone)]
struct SiteProjectRecord {
    id: String,
    slug: String,
    kind: String,
    root: String,
    featured: bool,
    hub_path: Option<String>,
    related_dossier: Option<String>,
}

fn add_site_output_subgraph(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    _options: GraphBuildOptions,
    article_ids: &[String],
) -> Result<()> {
    let visible_projects = builder
        .nodes
        .values()
        .filter(|node| node.kind == "project" && attr_bool(node, "site_visible") == Some(true))
        .map(|node| SiteProjectRecord {
            id: node.id.clone(),
            slug: attr_str(node, "slug").unwrap_or_default().to_owned(),
            kind: attr_str(node, "kind").unwrap_or_default().to_owned(),
            root: attr_str(node, "root").unwrap_or_default().to_owned(),
            featured: attr_bool(node, "site_featured") == Some(true),
            hub_path: attr_str(node, "site_effective_hub_path").map(str::to_owned),
            related_dossier: attr_str(node, "related_dossier").map(str::to_owned),
        })
        .collect::<Vec<_>>();
    let visible_project_ids = visible_projects
        .iter()
        .map(|project| project.id.clone())
        .collect::<BTreeSet<_>>();
    let visible_dossier_ids = visible_projects
        .iter()
        .filter(|project| project.kind == "dossier")
        .map(|project| project.id.clone())
        .collect::<Vec<_>>();
    let visible_addenda_ids = visible_projects
        .iter()
        .filter(|project| project.kind == "addendum")
        .map(|project| project.id.clone())
        .collect::<Vec<_>>();
    let featured_project_ids = visible_projects
        .iter()
        .filter(|project| project.featured)
        .map(|project| project.id.clone())
        .collect::<Vec<_>>();
    let mut dossier_hub_ids = BTreeMap::new();
    let hub_output_ids = visible_projects
        .iter()
        .filter_map(|project| {
            let hub_path = project.hub_path.as_deref()?;
            let output_id = upsert_site_output(builder, hub_path, "project_hub");
            builder.add_edge(
                output_id.clone(),
                "output_depends_on",
                project.id.clone(),
                BTreeMap::new(),
            );
            if project.kind == "dossier" {
                dossier_hub_ids.insert(project.slug.clone(), output_id.clone());
            }
            Some(output_id)
        })
        .collect::<Vec<_>>();
    for addendum in visible_projects
        .iter()
        .filter(|project| project.kind == "addendum")
    {
        let Some(dossier_slug) = addendum.related_dossier.as_deref() else {
            continue;
        };
        let Some(hub_id) = dossier_hub_ids.get(dossier_slug) else {
            continue;
        };
        builder.add_edge(
            hub_id.clone(),
            "output_depends_on",
            addendum.id.clone(),
            BTreeMap::new(),
        );
    }
    let doc_ids = collect_edge_targets(builder, &visible_project_ids, "project_has_doc");
    let evidence_ids = collect_edge_targets(builder, &visible_project_ids, "project_has_evidence");
    let durable_surface_ids = collect_edge_targets(
        builder,
        &visible_project_ids,
        "project_declares_durable_surface",
    );
    let site_data_mount_ids =
        collect_edge_targets(builder, &visible_project_ids, "project_mounts_site_data");
    let evidence_source_ids = visible_projects
        .iter()
        .flat_map(|project| {
            [
                ensure_source_pattern_node(
                    builder,
                    &format!("{}/artifacts/evidence/*.json", project.root),
                ),
                ensure_source_pattern_node(builder, &format!("{}/**/*evidence.json", project.root)),
            ]
        })
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let sitemap_source_ids = generated_sitemap_page_paths(repo_root)
        .into_iter()
        .map(|path| {
            let output_id = site_output_node_id(&path);
            if builder.nodes.contains_key(&output_id) {
                output_id
            } else {
                ensure_source_file_node(builder, &path)
            }
        })
        .collect::<Vec<_>>();

    let home_template_id = ensure_source_file_node(builder, "site/templates/index.html");
    let home_id = upsert_site_output(builder, "site/index.html", "home_page");
    add_output_dependencies(
        builder,
        &home_id,
        featured_project_ids
            .iter()
            .cloned()
            .chain(article_ids.iter().cloned())
            .chain([home_template_id]),
    );

    let dossiers_template_id =
        ensure_source_file_node(builder, "site/templates/dossiers/index.html");
    let dossiers_id = upsert_site_output(builder, "site/dossiers/index.html", "dossiers_index");
    add_output_dependencies(
        builder,
        &dossiers_id,
        visible_dossier_ids
            .into_iter()
            .chain([dossiers_template_id]),
    );

    let addenda_template_id = ensure_source_file_node(builder, "site/templates/addenda/index.html");
    let addenda_id = upsert_site_output(builder, "site/addenda/index.html", "addenda_index");
    add_output_dependencies(
        builder,
        &addenda_id,
        visible_addenda_ids.into_iter().chain([addenda_template_id]),
    );

    let blog_template_id = ensure_source_file_node(builder, "site/templates/blog/index.html");
    let blog_id = upsert_site_output(builder, "site/blog/index.html", "blog_index");
    add_output_dependencies(
        builder,
        &blog_id,
        article_ids
            .iter()
            .cloned()
            .chain([blog_template_id.clone()]),
    );

    let research_notes_template_id =
        ensure_source_file_node(builder, "site/templates/research-notes/index.html");
    let research_note_template_id =
        ensure_source_file_node(builder, "site/research-notes/pandoc-template.html");
    let registry_source_id = ensure_source_file_node(builder, "spctr-registry.json");
    let research_note_sources = research_note_source_paths(repo_root)?;
    let research_note_source_ids = research_note_sources
        .iter()
        .map(|(_, source_path)| ensure_source_file_node(builder, source_path))
        .collect::<Vec<_>>();
    let research_notes_id = upsert_site_output(
        builder,
        "site/research-notes/index.html",
        "research_notes_index",
    );
    add_output_dependencies(
        builder,
        &research_notes_id,
        research_note_source_ids
            .iter()
            .cloned()
            .chain([research_notes_template_id, registry_source_id.clone()]),
    );
    for ((slug, _), source_id) in research_note_sources
        .into_iter()
        .zip(research_note_source_ids.into_iter())
    {
        let output_id = upsert_site_output(
            builder,
            &format!("site/research-notes/{slug}/index.html"),
            "research_note_page",
        );
        add_output_dependencies(
            builder,
            &output_id,
            [
                source_id,
                research_note_template_id.clone(),
                registry_source_id.clone(),
            ],
        );
    }

    let blog_pdf_template_id =
        ensure_source_file_node(builder, "addenda/typst-field-manual/specter-paper.typ");
    let article_outputs = article_ids
        .iter()
        .filter_map(|article_id| {
            let node = builder.nodes.get(article_id)?;
            Some((
                article_id.clone(),
                attr_str(node, "slug")?.to_owned(),
                attr_str(node, "href")?.to_owned(),
            ))
        })
        .collect::<Vec<_>>();
    for (article_id, slug, href) in article_outputs {
        let article_page_id = upsert_site_output(
            builder,
            &site_output_path_from_href(&href),
            "blog_post_page",
        );
        add_output_dependencies(
            builder,
            &article_page_id,
            [article_id.clone(), blog_template_id.clone()],
        );

        let figure_source_ids = blog::figure_source_patterns(&slug)
            .into_iter()
            .map(|pattern| ensure_source_pattern_node(builder, &pattern))
            .collect::<Vec<_>>();
        let article_pdf_id = upsert_site_output(
            builder,
            &format!("site/blog/{slug}/{slug}.pdf"),
            "blog_post_pdf",
        );
        add_output_dependencies(
            builder,
            &article_pdf_id,
            [article_id]
                .into_iter()
                .chain([blog_pdf_template_id.clone()])
                .chain(figure_source_ids),
        );
    }

    let cabinet_project_ids = builder
        .nodes
        .values()
        .filter(|node| node.kind == "project" && attr_bool(node, "site_publish_docs") == Some(true))
        .map(|node| node.id.clone())
        .collect::<BTreeSet<_>>();
    let cabinet_doc_ids = collect_edge_targets(builder, &cabinet_project_ids, "project_has_doc")
        .into_iter()
        .filter(|doc_id| {
            builder
                .nodes
                .get(doc_id)
                .is_some_and(|node| attr_bool(node, "published") == Some(true))
        })
        .collect::<Vec<_>>();
    if !cabinet_doc_ids.is_empty() {
        let cabinet_doc_id_set = cabinet_doc_ids.iter().cloned().collect::<BTreeSet<_>>();
        let cabinet_series_ids = builder
            .edges
            .iter()
            .filter(|edge| edge.kind == "doc_in_series" && cabinet_doc_id_set.contains(&edge.src))
            .map(|edge| edge.dst.clone())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        let cabinet_data_ids = cabinet_project_ids
            .iter()
            .cloned()
            .chain(cabinet_doc_ids.iter().cloned())
            .chain(cabinet_series_ids.iter().cloned())
            .collect::<Vec<_>>();
        let cabinet_doc_outputs = cabinet_doc_ids
            .iter()
            .filter_map(|doc_id| {
                let node = builder.nodes.get(doc_id)?;
                Some((
                    required_attr(node, "project_slug").ok()?.to_owned(),
                    required_attr(node, "slug").ok()?.to_owned(),
                ))
            })
            .collect::<Vec<_>>();
        let cabinet_index_template_id =
            ensure_source_file_node(builder, "site/cabinet/index-template.html");
        let cabinet_index_id =
            upsert_site_output(builder, "site/cabinet/index.html", "cabinet_index");
        add_output_dependencies(
            builder,
            &cabinet_index_id,
            cabinet_data_ids
                .iter()
                .cloned()
                .chain([cabinet_index_template_id]),
        );
        let cabinet_template_id =
            ensure_source_file_node(builder, "site/cabinet/cabinet-template.html");
        for (project_slug, slug) in cabinet_doc_outputs {
            let cabinet_doc_id = upsert_site_output(
                builder,
                &format!("site/cabinet/{project_slug}/{slug}/index.html"),
                "cabinet_doc_page",
            );
            add_output_dependencies(
                builder,
                &cabinet_doc_id,
                cabinet_data_ids
                    .iter()
                    .cloned()
                    .chain([cabinet_template_id.clone()]),
            );
        }
    }

    let sitemap_template_id = ensure_source_file_node(builder, "site/templates/sitemap/index.html");
    let sitemap_id = upsert_site_output(builder, "site/sitemap/index.html", "sitemap");
    add_output_dependencies(
        builder,
        &sitemap_id,
        visible_project_ids
            .iter()
            .cloned()
            .chain(article_ids.iter().cloned())
            .chain(sitemap_source_ids)
            .chain([sitemap_template_id]),
    );

    let catalog_id = upsert_site_output(builder, "site/projects/catalog.json", "project_catalog");
    add_output_dependencies(
        builder,
        &catalog_id,
        visible_project_ids
            .iter()
            .cloned()
            .chain(hub_output_ids.iter().cloned()),
    );

    let health_template_id =
        ensure_source_file_node(builder, "site/templates/projects/health/index.html");
    let health_data_ids = visible_project_ids
        .iter()
        .cloned()
        .chain(doc_ids.iter().cloned())
        .chain(evidence_ids.iter().cloned())
        .chain(evidence_source_ids.iter().cloned())
        .collect::<Vec<_>>();
    let health_page_id = upsert_site_output(
        builder,
        "site/projects/health/index.html",
        "project_health_page",
    );
    add_output_dependencies(
        builder,
        &health_page_id,
        health_data_ids.iter().cloned().chain([health_template_id]),
    );
    let health_json_id =
        upsert_site_output(builder, "site/projects/health.json", "project_health_json");
    add_output_dependencies(builder, &health_json_id, health_data_ids.iter().cloned());

    let artifact_data_ids = visible_project_ids
        .iter()
        .cloned()
        .chain(durable_surface_ids.iter().cloned())
        .chain(site_data_mount_ids.iter().cloned())
        .collect::<Vec<_>>();
    let artifacts_json_id = upsert_site_output(
        builder,
        "site/projects/artifacts.json",
        "project_artifacts_json",
    );
    add_output_dependencies(builder, &artifacts_json_id, artifact_data_ids);

    let status_page_id = upsert_site_output(builder, "site/status/index.html", "status_page");
    let site_publish_source_id = ensure_source_file_node(builder, "ops/spctr/src/site/publish.rs");
    let report_source_id = ensure_source_file_node(builder, "ops/spctr/src/report.rs");
    let config_source_id = ensure_source_file_node(builder, "ops/spctr/src/config.rs");
    add_output_dependencies(
        builder,
        &status_page_id,
        [site_publish_source_id, report_source_id, config_source_id],
    );

    Ok(())
}

fn add_archive_surface_subgraph(builder: &mut GraphBuilder) {
    let projects_by_slug = builder
        .nodes
        .values()
        .filter(|node| node.kind == "project")
        .filter_map(|node| {
            Some((
                attr_str(node, "slug")?.to_owned(),
                (attr_str(node, "kind")?.to_owned(), node.id.clone()),
            ))
        })
        .collect::<BTreeMap<_, _>>();

    for surface in archive::canonical_archive_surfaces() {
        let project_ref = match surface.project.as_str() {
            "site" => None,
            slug => match projects_by_slug.get(slug) {
                Some(project_ref) => Some(project_ref.clone()),
                None => continue,
            },
        };

        let namespace = surface.namespace_relative();
        let mut attrs = base_attrs("code_spec", archive::PORTAL_MANIFEST_SOURCE_PATH.to_owned());
        attrs.insert("project".to_owned(), json!(&surface.project));
        attrs.insert("surface".to_owned(), json!(&surface.surface));
        attrs.insert("namespace".to_owned(), json!(namespace));
        attrs.insert("title".to_owned(), json!(&surface.title));
        attrs.insert("summary".to_owned(), json!(&surface.summary));
        attrs.insert("primary_label".to_owned(), json!(&surface.primary_label));
        attrs.insert("current_label".to_owned(), json!(&surface.current_label));
        attrs.insert("current_url".to_owned(), json!(&surface.current_url));
        attrs.insert(
            "current_archive_url".to_owned(),
            json!(surface.current_archive_url()),
        );
        attrs.insert(
            "release_index_url".to_owned(),
            json!(surface.release_index_url()),
        );
        attrs.insert(
            "metadata_path".to_owned(),
            json!(archive::PORTAL_MANIFEST_RELATIVE_PATH),
        );
        if let Some((kind, _project_id)) = project_ref.as_ref().map(|(kind, id)| (kind, id)) {
            attrs.insert("project_kind".to_owned(), json!(kind));
        }

        let node_id = archive_surface_node_id(&surface.project, &surface.surface);
        builder.upsert_node(node_id.clone(), "archive_surface", attrs);

        if let Some((_, project_id)) = project_ref {
            builder.add_edge(
                node_id,
                "archive_surface_tracks_project",
                project_id,
                BTreeMap::new(),
            );
        }
    }
}

fn collect_edge_targets(
    builder: &GraphBuilder,
    src_ids: &BTreeSet<String>,
    edge_kind: &str,
) -> Vec<String> {
    builder
        .edges
        .iter()
        .filter(|edge| edge.kind == edge_kind && src_ids.contains(&edge.src))
        .map(|edge| edge.dst.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn upsert_site_output(builder: &mut GraphBuilder, path: &str, output_kind: &str) -> String {
    let node_id = site_output_node_id(path);
    let mut attrs = base_attrs("generated_output", path.to_owned());
    attrs.insert("path".to_owned(), json!(path));
    attrs.insert("output_kind".to_owned(), json!(output_kind));
    builder.upsert_node(node_id.clone(), "site_output", attrs);
    node_id
}

fn ensure_source_file_node(builder: &mut GraphBuilder, path: &str) -> String {
    let node_id = source_file_node_id(path);
    let mut attrs = base_attrs("file", path.to_owned());
    attrs.insert("path".to_owned(), json!(path));
    builder.upsert_node(node_id.clone(), "source_file", attrs);
    node_id
}

fn ensure_source_pattern_node(builder: &mut GraphBuilder, pattern: &str) -> String {
    let node_id = source_pattern_node_id(pattern);
    let mut attrs = base_attrs("pattern", pattern.to_owned());
    attrs.insert("path".to_owned(), json!(pattern));
    builder.upsert_node(node_id.clone(), "source_pattern", attrs);
    node_id
}

fn add_output_dependencies<I>(builder: &mut GraphBuilder, output_id: &str, deps: I)
where
    I: IntoIterator<Item = String>,
{
    for dep in deps {
        builder.add_edge(
            output_id.to_owned(),
            "output_depends_on",
            dep,
            BTreeMap::new(),
        );
    }
}

fn discover_exec_evidence(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
) -> Result<Vec<ExecEvidenceRecord>> {
    let Some(spctr) = &manifest.spctr else {
        return Ok(Vec::new());
    };
    let configured_path = exec::configured_evidence_card_path(manifest);
    let mut records = Vec::new();
    for action in spctr.exec.keys() {
        let mut candidates = Vec::new();
        if let Some(path) = exec::action_evidence_card_path(manifest, action) {
            candidates.push(path);
        }
        if let Some(path) = configured_path.clone() {
            candidates.push(path);
        }
        let mut parsed = None;
        for path in candidates {
            if !path.is_file() {
                continue;
            }
            let Some(record) = parse_exec_evidence_card(repo_root, manifest, &path, action)? else {
                continue;
            };
            parsed = Some(record);
            break;
        }
        if let Some(record) = parsed {
            records.push(record);
        }
    }
    Ok(records)
}

fn parse_exec_evidence_card(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    path: &Utf8Path,
    action: &str,
) -> Result<Option<ExecEvidenceRecord>> {
    let text = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let raw: Value =
        serde_json::from_str(&text).with_context(|| format!("invalid JSON in {path}"))?;
    let Some(object) = raw.as_object() else {
        anyhow::bail!("{path}: exec evidence card must be a JSON object");
    };
    if object.get("action").and_then(Value::as_str) != Some(action) {
        return Ok(None);
    }
    let mut attrs = base_attrs("exec_evidence_card", repo_rel(repo_root, path)?);
    attrs.insert("scope".to_owned(), json!("exec"));
    attrs.insert("project_kind".to_owned(), json!(manifest.kind));
    attrs.insert("project_slug".to_owned(), json!(manifest.slug));
    attrs.insert("action".to_owned(), json!(action));
    insert_optional_u64_attr(&mut attrs, "version", object.get("version"));
    insert_optional_string_attr(&mut attrs, "status", object.get("status"));
    insert_optional_string_attr(&mut attrs, "started_at", object.get("started_at"));
    insert_optional_string_attr(&mut attrs, "finished_at", object.get("finished_at"));
    insert_optional_string_attr(&mut attrs, "description", object.get("description"));
    insert_optional_string_attr(&mut attrs, "error", object.get("error"));
    if let Some(commands) = object.get("commands") {
        attrs.insert("commands".to_owned(), commands.clone());
    }
    if let Some(requires) = object.get("requires") {
        attrs.insert("requires".to_owned(), requires.clone());
    }
    if let Some(inputs) = object.get("inputs") {
        attrs.insert("inputs".to_owned(), inputs.clone());
    }
    if let Some(outputs) = object.get("outputs") {
        attrs.insert("outputs".to_owned(), outputs.clone());
    }
    if let Some(runtime) = object.get("runtime") {
        attrs.insert("runtime".to_owned(), runtime.clone());
    }
    if let Some(git) = object.get("git") {
        attrs.insert("git".to_owned(), git.clone());
    }
    if let Some(manifest_record) = object.get("manifest") {
        attrs.insert("manifest".to_owned(), manifest_record.clone());
    }
    Ok(Some(ExecEvidenceRecord {
        action: action.to_owned(),
        attrs,
    }))
}

fn discover_release_evidence(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
) -> Result<Vec<ReleaseEvidenceRecord>> {
    let mut paths = Vec::new();
    collect_release_evidence_paths(&manifest.root, &mut paths)?;
    paths.sort();
    let mut records = Vec::new();
    for path in paths {
        if let Some(record) = parse_release_evidence_card(repo_root, manifest, &path)? {
            records.push(record);
        }
    }
    Ok(records)
}

fn collect_release_evidence_paths(dir: &Utf8Path, out: &mut Vec<Utf8PathBuf>) -> Result<()> {
    for entry in fs::read_dir(dir).with_context(|| format!("failed to read {dir}"))? {
        let entry = entry.with_context(|| format!("failed to read entry in {dir}"))?;
        let path: Utf8PathBuf = entry
            .path()
            .try_into()
            .context("non-UTF-8 release evidence path")?;
        if path.is_dir() {
            if should_skip_release_evidence_dir(&path) {
                continue;
            }
            collect_release_evidence_paths(&path, out)?;
            continue;
        }
        let Some(file_name) = path.file_name() else {
            continue;
        };
        if file_name.ends_with("evidence.json") {
            out.push(path);
        }
    }
    Ok(())
}

fn should_skip_release_evidence_dir(path: &Utf8Path) -> bool {
    matches!(
        path.file_name(),
        Some(
            ".git" | ".jj" | ".build" | ".swiftpm" | ".direnv" | ".venv" | "node_modules"
            | "target" | "DerivedData" | "compendium" | "exports" | "flow-universe-runs"
            | "logs" | "outputs" | "tmp" | ".pytest_cache" | ".ruff_cache" | "__pycache__",
        )
    )
}

fn parse_release_evidence_card(
    repo_root: &Utf8Path,
    manifest: &ProjectManifest,
    path: &Utf8Path,
) -> Result<Option<ReleaseEvidenceRecord>> {
    let text = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let raw: Value =
        serde_json::from_str(&text).with_context(|| format!("invalid JSON in {path}"))?;
    let Some(object) = raw.as_object() else {
        anyhow::bail!("{path}: release evidence card must be a JSON object");
    };
    if object.get("project").and_then(Value::as_str) != Some(manifest.slug.as_str()) {
        return Ok(None);
    }
    let mut attrs = base_attrs("release_evidence_card", repo_rel(repo_root, path)?);
    attrs.insert("scope".to_owned(), json!("release"));
    attrs.insert("project_kind".to_owned(), json!(manifest.kind));
    attrs.insert("project_slug".to_owned(), json!(manifest.slug));
    insert_optional_u64_attr(&mut attrs, "version", object.get("version"));
    insert_optional_string_attr(&mut attrs, "action", object.get("action"));
    insert_optional_string_attr(&mut attrs, "generated_at", object.get("generated_at"));
    insert_optional_string_attr(&mut attrs, "surface", object.get("surface"));
    insert_optional_string_attr(&mut attrs, "surface_kind", object.get("surface_kind"));
    insert_optional_string_attr(&mut attrs, "language", object.get("language"));
    insert_optional_string_attr(&mut attrs, "release_id", object.get("release_id"));
    insert_optional_string_attr(&mut attrs, "stage", object.get("stage"));
    insert_optional_string_attr(&mut attrs, "title", object.get("title"));
    insert_optional_string_attr(&mut attrs, "series", object.get("series"));
    insert_optional_string_attr(&mut attrs, "manifest_path", object.get("manifest_path"));
    if let Some(inputs) = object.get("inputs") {
        attrs.insert("inputs".to_owned(), inputs.clone());
    }
    if let Some(outputs) = object.get("outputs") {
        attrs.insert("outputs".to_owned(), outputs.clone());
    }
    if let Some(git) = object.get("git") {
        attrs.insert("git".to_owned(), git.clone());
    }
    Ok(Some(ReleaseEvidenceRecord {
        surface: object
            .get("surface")
            .and_then(Value::as_str)
            .map(str::to_owned),
        path: path.to_owned(),
        attrs,
    }))
}

fn ensure_series_node(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    registry: Option<&registry::Registry>,
    manifest: &ProjectManifest,
    series_id: &str,
) -> Result<()> {
    let fallback_path = repo_rel(repo_root, &manifest.path)?;
    upsert_series_node(
        repo_root,
        builder,
        registry,
        series_id,
        "manifest",
        &fallback_path,
    )
}

fn ensure_article_series_node(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    registry: Option<&registry::Registry>,
    series_id: &str,
    source_path: &str,
) -> Result<()> {
    upsert_series_node(
        repo_root,
        builder,
        registry,
        series_id,
        "blog_post",
        source_path,
    )
}

fn upsert_series_node(
    repo_root: &Utf8Path,
    builder: &mut GraphBuilder,
    registry: Option<&registry::Registry>,
    series_id: &str,
    fallback_source_kind: &str,
    fallback_source_path: &str,
) -> Result<()> {
    let mut attrs = if let Some(loaded) = registry {
        if let Some(entry) = loaded.series.get(series_id) {
            let mut attrs = base_attrs(
                "registry",
                repo_rel(repo_root, &registry::registry_path(repo_root))?,
            );
            attrs.insert("slug".to_owned(), json!(entry.slug));
            attrs.insert("title".to_owned(), json!(entry.title));
            attrs
        } else {
            base_attrs(fallback_source_kind, fallback_source_path.to_owned())
        }
    } else {
        base_attrs(fallback_source_kind, fallback_source_path.to_owned())
    };
    attrs.insert("series_id".to_owned(), json!(series_id));
    attrs.insert(
        "type_prefix".to_owned(),
        json!(series_id.split('-').next().unwrap_or_default()),
    );
    builder.upsert_node(series_node_id(series_id), "series", attrs);
    Ok(())
}

fn effective_site_hub_path(manifest: &ProjectManifest) -> Option<String> {
    if manifest.kind != "dossier" || !manifest.site.visible {
        return None;
    }
    Some(
        manifest
            .site
            .hub_path
            .clone()
            .unwrap_or_else(|| default_dossier_hub_path(&manifest.slug)),
    )
}

fn hub_path_is_generated(manifest: &ProjectManifest) -> bool {
    manifest.kind == "dossier" && manifest.site.visible && manifest.site.hub_path.is_none()
}

fn generated_sitemap_page_paths(repo_root: &Utf8Path) -> Vec<String> {
    let mut paths = Vec::new();
    for group in discover::discover_sitemap_pages(repo_root) {
        if let Some(index) = group.index {
            paths.push(site_output_path_from_href(&index.href));
        }
        for child in group.children {
            paths.push(site_output_path_from_href(&child.href));
        }
    }
    paths
        .into_iter()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn research_note_source_paths(repo_root: &Utf8Path) -> Result<Vec<(String, String)>> {
    let notes_root = repo_root.join("site/research-notes");
    if !notes_root.is_dir() {
        return Ok(Vec::new());
    }

    let mut records = Vec::new();
    for entry in
        fs::read_dir(&notes_root).with_context(|| format!("failed to read {notes_root}"))?
    {
        let entry = entry?;
        if !entry.path().is_dir() {
            continue;
        }
        let slug = entry.file_name().to_string_lossy().to_string();
        let path = notes_root.join(&slug).join("index.md");
        if !path.is_file() {
            continue;
        }
        records.push((slug, repo_rel(repo_root, &path)?));
    }
    records.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(records)
}

fn site_output_path_from_href(href: &str) -> String {
    if href.is_empty() {
        "site/index.html".to_owned()
    } else {
        format!("site/{href}index.html")
    }
}

fn project_series_id(
    registry: Option<&registry::Registry>,
    manifest: &ProjectManifest,
) -> Option<String> {
    manifest.series.clone().or_else(|| {
        let type_prefix = match manifest.kind.as_str() {
            "dossier" => "D",
            "addendum" => "A",
            _ => return None,
        };
        registry
            .and_then(|loaded| registry::series_for_slug(loaded, type_prefix, &manifest.slug))
            .map(str::to_owned)
    })
}

fn published_article_series_id(
    registry: Option<&registry::Registry>,
    post: &discover::BlogPostRecord,
    slug: &str,
) -> Result<Option<String>> {
    let Some(registry) = registry else {
        return Ok(post.series.clone());
    };
    let Some(frontmatter_series) = post.series.as_deref() else {
        anyhow::bail!("blog/{slug}/index.md: missing series assignment; run `spctr registry sync`");
    };
    match registry::series_for_slug(registry, "B", slug) {
        Some(registry_series) if registry_series == frontmatter_series => {
            Ok(Some(frontmatter_series.to_owned()))
        }
        Some(registry_series) => anyhow::bail!(
            "blog/{slug}/index.md: series mismatch: frontmatter says '{frontmatter_series}' but registry says '{registry_series}'"
        ),
        None => anyhow::bail!(
            "blog/{slug}/index.md: series '{frontmatter_series}' declared but slug not in registry"
        ),
    }
}

fn project_node_id(manifest: &ProjectManifest) -> String {
    format!("project:{}:{}", manifest.kind, manifest.slug)
}

fn article_node_id(slug: &str) -> String {
    format!("article:{slug}")
}

fn series_node_id(series_id: &str) -> String {
    format!("series:{series_id}")
}

fn doc_node_id(manifest: &ProjectManifest, slug: &str) -> String {
    format!("doc:{}:{}:{slug}", manifest.kind, manifest.slug)
}

fn durable_surface_node_id(manifest: &ProjectManifest, name: &str) -> String {
    format!("durable_surface:{}:{}:{name}", manifest.kind, manifest.slug)
}

fn release_surface_node_id(manifest: &ProjectManifest, name: &str) -> String {
    format!("release_surface:{}:{}:{name}", manifest.kind, manifest.slug)
}

fn archive_surface_node_id(project: &str, surface: &str) -> String {
    format!("archive_surface:{project}:{surface}")
}

fn exec_action_node_id(manifest: &ProjectManifest, action: &str) -> String {
    format!("exec_action:{}:{}:{action}", manifest.kind, manifest.slug)
}

fn expected_output_node_id(manifest: &ProjectManifest, name: &str) -> String {
    format!("expected_output:{}:{}:{name}", manifest.kind, manifest.slug)
}

fn site_data_mount_node_id(manifest: &ProjectManifest, name: &str) -> String {
    format!("site_data_mount:{}:{}:{name}", manifest.kind, manifest.slug)
}

fn exec_evidence_node_id(manifest: &ProjectManifest, action: &str) -> String {
    format!(
        "evidence_card:exec:{}:{}:{action}",
        manifest.kind, manifest.slug
    )
}

fn release_evidence_node_id(manifest: &ProjectManifest, card_path: &str) -> String {
    format!(
        "evidence_card:release:{}:{}:{card_path}",
        manifest.kind, manifest.slug
    )
}

fn update_node_id(id: &str) -> String {
    format!("update:{id}")
}

fn site_output_node_id(path: &str) -> String {
    format!("site_output:{path}")
}

fn source_file_node_id(path: &str) -> String {
    format!("source_file:{path}")
}

fn source_pattern_node_id(pattern: &str) -> String {
    format!("source_pattern:{pattern}")
}

fn durable_refresh_commands(surface: &manifest::SurfaceConfig) -> Vec<Vec<String>> {
    match (&surface.refresh_command, &surface.refresh_commands) {
        (Some(command), _) => vec![command.clone()],
        (None, Some(commands)) => commands.clone(),
        (None, None) => Vec::new(),
    }
}

fn raw_roots_value(surface: &manifest::SurfaceConfig) -> Value {
    Value::Array(
        surface
            .raw_roots
            .iter()
            .map(|root| {
                json!({
                    "path": root.path,
                    "remote_base": root.remote_base,
                    "excludes": root.excludes,
                    "sync_mode": root.sync_mode,
                    "resolve": root.resolve,
                    "runtime_slug": root.runtime_slug,
                    "project_fallback": root.project_fallback,
                })
            })
            .collect(),
    )
}

fn base_attrs(source_kind: &str, source_path: String) -> BTreeMap<String, Value> {
    let mut attrs = BTreeMap::new();
    attrs.insert("source_kind".to_owned(), json!(source_kind));
    attrs.insert("source_path".to_owned(), json!(source_path));
    attrs
}

fn repo_rel(repo_root: &Utf8Path, path: &Utf8Path) -> Result<String> {
    Ok(path
        .strip_prefix(repo_root)
        .unwrap_or(path)
        .as_str()
        .to_owned())
}

fn optional_value<T>(value: Option<T>) -> Value
where
    T: Serialize,
{
    value.map_or(Value::Null, |value| json!(value))
}

fn insert_optional_string_attr(
    attrs: &mut BTreeMap<String, Value>,
    key: &str,
    value: Option<&Value>,
) {
    if let Some(text) = value.and_then(Value::as_str) {
        attrs.insert(key.to_owned(), json!(text));
    }
}

fn insert_optional_u64_attr(attrs: &mut BTreeMap<String, Value>, key: &str, value: Option<&Value>) {
    if let Some(number) = value.and_then(Value::as_u64) {
        attrs.insert(key.to_owned(), json!(number));
    }
}

fn require_string(value: Option<&Value>, field_name: &str, path: &Utf8Path) -> Result<String> {
    let text = value
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("{path}: {field_name} must be a non-empty string"))?
        .trim()
        .to_owned();
    if text.is_empty() {
        anyhow::bail!("{path}: {field_name} must be a non-empty string");
    }
    Ok(text)
}
