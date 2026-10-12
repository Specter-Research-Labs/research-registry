use anyhow::Result;
use camino::{Utf8Path, Utf8PathBuf};
use std::collections::HashMap;

use crate::graph::{self, RegistryGraph};
use crate::manifest::ProjectManifest;
use crate::markdown;

#[derive(Clone, Debug)]
pub struct DocEntry {
    pub path: Utf8PathBuf,
    pub docs_root: Utf8PathBuf,
    pub project_kind: String,
    pub project_slug: String,
    pub publish_docs: bool,
    pub published: bool,
    pub title: String,
    pub slug: String,
    pub category: String,
    pub doc_id: String,
    pub project_display: String,
    pub series_id: Option<String>,
    pub render_markdown: Option<String>,
}

pub(crate) fn find_docs_for_manifests(manifests: &[ProjectManifest]) -> Result<Vec<DocEntry>> {
    let mut entries = Vec::new();
    for project in project_docs_from_manifests(manifests) {
        let mut md_files = Vec::new();
        collect_md_files(&project.docs_root, &project.docs_root, &mut md_files)?;
        md_files.sort();

        for md_path in md_files {
            let rel = md_path
                .strip_prefix(&project.docs_root)
                .expect("md is under docs_root");
            let slug = rel.with_extension("").as_str().replace('\\', "/");
            let doc = scan_doc(&md_path)?;
            let category = if rel.components().count() > 1 {
                rel.components()
                    .next()
                    .map(|c| c.as_str().to_owned())
                    .unwrap_or_default()
            } else {
                String::new()
            };
            entries.push(DocEntry {
                title: doc.title,
                path: md_path,
                docs_root: project.docs_root.clone(),
                project_kind: project.kind.clone(),
                project_slug: project.slug.clone(),
                publish_docs: project.publish_docs,
                published: doc.published,
                slug,
                category,
                doc_id: String::new(),
                project_display: String::new(),
                series_id: None,
                render_markdown: None,
            });
        }
    }
    Ok(entries)
}

pub fn find_published_docs_from_graph(
    repo_root: &Utf8Path,
    graph: &RegistryGraph,
) -> Result<Vec<DocEntry>> {
    let project_meta = graph
        .nodes_of_kind("project")
        .map(|node| {
            let slug = required_attr(node, "slug")?.to_owned();
            let project_display = required_attr(node, "title")?.to_owned();
            let series_id = graph::attr_str(node, "series_id").map(ToOwned::to_owned);
            Ok((
                node.id.clone(),
                ProjectMeta {
                    publish_docs: graph::attr_bool(node, "publishes_cabinet_docs") == Some(true),
                    project_display,
                    series_id,
                    slug,
                },
            ))
        })
        .collect::<Result<HashMap<_, _>>>()?;

    let mut entries = Vec::new();
    for node in graph.nodes_of_kind("doc") {
        if graph::attr_bool(node, "published") != Some(true) {
            continue;
        }

        let path = repo_root.join(required_attr(node, "path")?);
        let mut owners = graph.incoming_edges(&node.id, "project_has_doc");
        let Some(project_edge) = owners.next() else {
            anyhow::bail!("{path}: graph missing cabinet project owner");
        };
        if owners.next().is_some() {
            anyhow::bail!("{path}: graph has multiple cabinet project owners");
        }
        let project = project_meta
            .get(&project_edge.src)
            .ok_or_else(|| anyhow::anyhow!("{path}: graph missing cabinet project metadata"))?;
        if !project.publish_docs {
            continue;
        }
        let Some(series_id) = project.series_id.clone() else {
            anyhow::bail!(
                "{path}: registry missing series assignment for published cabinet doc; run `spctr registry sync`"
            );
        };
        let doc_id = graph::attr_str(node, "doc_id").ok_or_else(|| {
            anyhow::anyhow!("{path}: registry missing cabinet doc id; run `spctr registry sync`")
        })?;
        entries.push(DocEntry {
            path,
            docs_root: repo_root.join(required_attr(node, "docs_root")?),
            project_kind: required_attr(node, "project_kind")?.to_owned(),
            project_slug: project.slug.clone(),
            publish_docs: true,
            published: true,
            title: required_attr(node, "title")?.to_owned(),
            slug: required_attr(node, "slug")?.to_owned(),
            category: graph::attr_str(node, "category")
                .unwrap_or_default()
                .to_owned(),
            doc_id: doc_id.to_owned(),
            project_display: project.project_display.clone(),
            series_id: Some(series_id),
            render_markdown: None,
        });
    }
    entries.sort_by(|left, right| left.path.cmp(&right.path));
    Ok(entries)
}

#[derive(Clone)]
struct ProjectDocs {
    kind: String,
    slug: String,
    docs_root: Utf8PathBuf,
    publish_docs: bool,
}

fn project_docs_from_manifests(manifests: &[ProjectManifest]) -> Vec<ProjectDocs> {
    let mut projects = manifests
        .iter()
        .filter_map(|manifest| {
            let docs_root = manifest
                .spctr
                .as_ref()
                .and_then(|spctr| spctr.docs.as_ref())
                .map(|docs| manifest.root.join(&docs.root))
                .unwrap_or_else(|| manifest.root.join("docs"));
            docs_root.is_dir().then(|| ProjectDocs {
                kind: manifest.kind.clone(),
                slug: manifest.slug.clone(),
                docs_root,
                publish_docs: manifest.site.publishes_cabinet_docs(),
            })
        })
        .collect::<Vec<_>>();
    projects.sort_by(|left, right| {
        left.kind
            .cmp(&right.kind)
            .then_with(|| left.slug.cmp(&right.slug))
            .then_with(|| left.docs_root.cmp(&right.docs_root))
    });
    projects
}

struct DocScan {
    title: String,
    published: bool,
}

fn collect_md_files(
    docs_root: &Utf8Path,
    dir: &Utf8Path,
    out: &mut Vec<Utf8PathBuf>,
) -> Result<()> {
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let path: Utf8PathBuf = entry.path().try_into().expect("docs path is UTF-8");
        if path.is_dir() {
            if is_local_doc_skip_dir(docs_root, &path) {
                continue;
            }
            collect_md_files(docs_root, &path, out)?;
        } else if path.extension().is_some_and(|ext| ext == "md") {
            out.push(path);
        }
    }
    Ok(())
}

fn is_local_doc_skip_dir(docs_root: &Utf8Path, path: &Utf8Path) -> bool {
    if is_generated_root_doc_dir(docs_root, path) {
        return true;
    }

    matches!(
        path.file_name(),
        Some(
            ".git"
                | ".jj"
                | ".venv"
                | ".tox"
                | ".nox"
                | ".mypy_cache"
                | ".ruff_cache"
                | ".pytest_cache"
                | "__pycache__"
                | "node_modules"
                | "target"
                | "dist"
                | "build"
        )
    )
}

fn is_generated_root_doc_dir(docs_root: &Utf8Path, path: &Utf8Path) -> bool {
    if docs_root.file_name() == Some("docs") || path.parent() != Some(docs_root) {
        return false;
    }

    matches!(
        path.file_name(),
        Some("artifacts" | "logs" | "tmp" | "temp")
    )
}

pub fn is_published(md_path: &Utf8Path) -> Result<bool> {
    Ok(scan_doc(md_path)?.published)
}

fn scan_doc(md_path: &Utf8Path) -> Result<DocScan> {
    let text = std::fs::read_to_string(md_path)
        .map_err(|error| anyhow::anyhow!("failed to read cabinet doc {md_path}: {error}"))?;
    let front_matter = markdown::parse_front_matter(&text);
    let published = !matches!(
        front_matter.get("publish").map(String::as_str),
        Some("false")
    );
    let title = match front_matter.get("title").filter(|title| !title.is_empty()) {
        Some(title) => title.clone(),
        None => markdown::extract_title(&text),
    };
    if title.is_empty() {
        anyhow::bail!("{md_path}: cabinet doc needs a frontmatter `title` or a `# ` heading");
    }
    Ok(DocScan { title, published })
}

pub fn group_by_project(entries: &[DocEntry]) -> Vec<(&str, Vec<usize>)> {
    let mut map: std::collections::BTreeMap<&str, Vec<usize>> = std::collections::BTreeMap::new();
    for (i, entry) in entries.iter().enumerate() {
        map.entry(&entry.project_slug).or_default().push(i);
    }
    map.into_iter().collect()
}

struct ProjectMeta {
    publish_docs: bool,
    project_display: String,
    series_id: Option<String>,
    slug: String,
}

fn required_attr<'a>(node: &'a graph::GraphNode, key: &str) -> Result<&'a str> {
    graph::attr_str(node, key)
        .ok_or_else(|| anyhow::anyhow!("{}: missing graph attr `{key}`", node.id))
}
