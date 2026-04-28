use camino::Utf8Path;
use spctr::graph::{build, build_with_options, GraphBuildOptions};
use std::collections::BTreeMap;
use std::fs;
use tempfile::TempDir;

fn write(path: &Utf8Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

fn minimal_design_tokens(root: &Utf8Path) {
    write(
        &root.join("addenda/design-tokens/base.toml"),
        r##"
[colors]
ink = "#0b0e14"

[badges.project-status]
dossier = ["concept", "active", "active-writing", "hold"]
addenda = ["concept", "active", "operational", "hold", "archived"]

[badges.project-status.concept]
color = "ink"

[badges.project-status.active]
color = "ink"

[badges.project-status.active-writing]
color = "ink"

[badges.project-status.hold]
color = "ink"

[badges.project-status.operational]
color = "ink"

[badges.project-status.archived]
color = "ink"

[badges.addenda-type]
values = ["tooling", "research", "dataset", "benchmark"]

[badges.addenda-type.tooling]
color = "ink"

[badges.addenda-type.research]
color = "ink"

[badges.addenda-type.dataset]
color = "ink"

[badges.addenda-type.benchmark]
color = "ink"
"##,
    );
    write(&root.join("addenda/design-tokens/web.toml"), "");
}

fn node_attrs<'a>(
    graph: &'a spctr::graph::RegistryGraph,
    id: &str,
) -> &'a BTreeMap<String, serde_json::Value> {
    &graph
        .nodes
        .iter()
        .find(|node| node.id == id)
        .unwrap_or_else(|| panic!("missing node {id}"))
        .attrs
}

#[test]
fn build_compiles_manifest_docs_updates_and_evidence_into_graph() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);

    write(
        &root.join("spctr-registry.json"),
        r#"{
  "version": 1,
  "counters": { "D": 2, "A": 1, "B": 1 },
  "series": {
    "B-001": { "slug": "hello-world", "title": "Hello World" },
    "D-001": { "slug": "alpha", "title": "Alpha" }
  },
  "docs": {
    "D-001": {
      "next_counter": 2,
      "entries": {
        "intro": "D-001.001"
      }
    }
  }
}
"#,
    );

    write(
        &root.join("dossiers/alpha/spctr.toml"),
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"
series = "D-001"

[site]
visible = true
featured = false
publish_docs = true

[release]
stage = "promoted"

[[release.surfaces]]
name = "python"
kind = "package"
publish = true
path = "."
include_docs = true
language = "python"
registry = "pypi"
publish_mode = "subdir"

[spctr]
project = "alpha"
default_surface = "lake"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]
expected_outputs = ["smoke-report"]

[spctr.runtime]
platforms = ["linux"]
requires = ["python"]
network = "bootstrap"
cache_paths = ["tmp/cache"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "smoke-report"
path = "artifacts/smoke/report.json"
kind = "status_json"
required = true
surface = "python"

[spctr.docs]
root = "notes"
landing = "notes/README.md"
require_frontmatter = false

[spctr.surfaces.lake]
kind = "raw_plus_db"
raw_roots = ["artifacts/raw"]
local_db_path = "artifacts/lake.sqlite"
refresh_command = ["python3", "-c", "print('refresh')"]
remote_raw_namespace = "alpha"
remote_snapshot_namespace = "lake"

[[spctr.site_data]]
name = "dashboard"
site_path = "dossiers/alpha/dashboard/data"
local_source = "artifacts/site-data"
"#,
    );

    write(
        &root.join("dossiers/alpha/notes/README.md"),
        "# Alpha Notes\n",
    );
    write(
        &root.join("dossiers/alpha/notes/intro.md"),
        "# Intro\n\nPublished doc.\n",
    );
    write(
        &root.join("dossiers/alpha/notes/hidden.md"),
        "---\npublish: false\n---\n# Hidden\n\nNot public.\n",
    );
    write(
        &root.join("dossiers/alpha/artifacts/evidence/check.json"),
        r#"{
  "version": 2,
  "project": "alpha",
  "kind": "dossier",
  "action": "check",
  "status": "ok",
  "started_at": "2026-04-06T12:00:00Z",
  "finished_at": "2026-04-06T12:00:10Z",
  "commands": [["python3", "-c", "print('check')"]],
  "inputs": [{ "kind": "manifest", "path": "dossiers/alpha/spctr.toml", "sha256": "abc", "size_bytes": 10 }],
  "outputs": [{ "name": "smoke-report", "path": "artifacts/smoke/report.json", "kind": "status_json", "required": true, "surface": "python", "matches": [] }]
}
"#,
    );
    write(
        &root.join("dossiers/alpha/artifacts/releases/alpha-python.evidence.json"),
        r#"{
  "version": 1,
  "action": "package_surface",
  "generated_at": "2026-04-06T12:01:00Z",
  "project": "alpha",
  "title": "Alpha",
  "series": "D-001",
  "stage": "promoted",
  "surface": "python",
  "surface_kind": "package",
  "language": "python",
  "release_id": "alpha-001",
  "manifest_path": "dossiers/alpha/spctr.toml",
  "inputs": [],
  "outputs": []
}
"#,
    );
    write(
        &root.join("site/updates/entries/spctr-update-001.json"),
        r#"{
  "id": "spctr-update-001",
  "kind": "main",
  "label": "SPCTR-UPDATE-001",
  "date": "2026-04-06",
  "published_at": "2026-04-06T12:00:00Z",
  "topic": "weekly / spctr-update-001",
  "window": { "start": "2026-04-01", "end": "2026-04-06" },
  "series_number": 1,
  "sections": {
    "dossiers": ["alpha: graph build landed."],
    "addenda": [],
    "ops": [],
    "lab": []
  }
}
"#,
    );
    write(
        &root.join("site/blog/hello-world/index.md"),
        r#"---
title: Hello World
release: published
series: B-001
---

# Hello World

Graph-native article.
"#,
    );

    let graph = build(root, None).unwrap();

    assert_eq!(graph.version, 1);
    assert!(graph.scope_project.is_none());
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "project:dossier:alpha" && node.kind == "project"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "series:D-001" && node.kind == "series"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "release_surface:dossier:alpha:python"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "durable_surface:dossier:alpha:lake"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "exec_action:dossier:alpha:check"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "expected_output:dossier:alpha:smoke-report"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_data_mount:dossier:alpha:dashboard"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/projects/catalog.json"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/projects/artifacts.json"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/projects/health.json"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/blog/hello-world/index.html"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/blog/hello-world/hello-world.pdf"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/cabinet/index.html"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/cabinet/alpha/intro/index.html"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "site_output:site/status/index.html"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "archive_surface:site:root" && node.kind == "archive_surface"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "evidence_card:exec:dossier:alpha:check"));
    assert!(graph.nodes.iter().any(|node| {
        node.id
            == "evidence_card:release:dossier:alpha:dossiers/alpha/artifacts/releases/alpha-python.evidence.json"
    }));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "update:spctr-update-001" && node.kind == "update"));
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "article:hello-world" && node.kind == "article"));

    let intro = node_attrs(&graph, "doc:dossier:alpha:intro");
    assert_eq!(intro.get("doc_id").unwrap(), "D-001.001");
    assert_eq!(intro.get("published").unwrap(), true);

    let hidden = node_attrs(&graph, "doc:dossier:alpha:hidden");
    assert_eq!(hidden.get("published").unwrap(), false);
    assert_eq!(hidden.get("docs_root").unwrap(), "dossiers/alpha/notes");

    let project = node_attrs(&graph, "project:dossier:alpha");
    assert_eq!(
        project.get("site_effective_hub_path").unwrap(),
        "site/dossiers/alpha/index.html"
    );
    assert_eq!(project.get("site_hub_generated").unwrap(), true);
    assert_eq!(project.get("has_docs_dir").unwrap(), true);
    assert_eq!(project.get("has_docs_readme").unwrap(), true);

    let exec_card = node_attrs(&graph, "evidence_card:exec:dossier:alpha:check");
    assert_eq!(exec_card.get("scope").unwrap(), "exec");
    assert_eq!(exec_card.get("status").unwrap(), "ok");

    let archive_surface = node_attrs(&graph, "archive_surface:site:root");
    assert_eq!(archive_surface.get("namespace").unwrap(), "site");
    assert_eq!(
        archive_surface.get("current_url").unwrap(),
        "https://specterlab.org/"
    );
    assert_eq!(
        archive_surface.get("metadata_path").unwrap(),
        ".spctr/portal-surfaces.json"
    );

    assert!(graph.edges.iter().any(|edge| {
        edge.src == "project:dossier:alpha"
            && edge.kind == "project_in_series"
            && edge.dst == "series:D-001"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "project:dossier:alpha"
            && edge.kind == "project_has_doc"
            && edge.dst == "doc:dossier:alpha:intro"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "exec_action:dossier:alpha:check"
            && edge.kind == "exec_expects_output"
            && edge.dst == "expected_output:dossier:alpha:smoke-report"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "expected_output:dossier:alpha:smoke-report"
            && edge.kind == "surface_targets_output"
            && edge.dst == "release_surface:dossier:alpha:python"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "evidence_card:exec:dossier:alpha:check"
            && edge.kind == "evidence_for_exec"
            && edge.dst == "exec_action:dossier:alpha:check"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "article:hello-world"
            && edge.kind == "article_in_series"
            && edge.dst == "series:B-001"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/blog/index.html"
            && edge.kind == "output_depends_on"
            && edge.dst == "article:hello-world"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/blog/hello-world/index.html"
            && edge.kind == "output_depends_on"
            && edge.dst == "article:hello-world"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/cabinet/alpha/intro/index.html"
            && edge.kind == "output_depends_on"
            && edge.dst == "doc:dossier:alpha:intro"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/projects/catalog.json"
            && edge.kind == "output_depends_on"
            && edge.dst == "project:dossier:alpha"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/projects/artifacts.json"
            && edge.kind == "output_depends_on"
            && edge.dst == "durable_surface:dossier:alpha:lake"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/projects/health.json"
            && edge.kind == "output_depends_on"
            && edge.dst == "source_pattern:dossiers/alpha/artifacts/evidence/*.json"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src == "site_output:site/status/index.html"
            && edge.kind == "output_depends_on"
            && edge.dst == "source_file:ops/spctr/src/report.rs"
    }));
    assert!(graph.edges.iter().any(|edge| {
        edge.src
            == "evidence_card:release:dossier:alpha:dossiers/alpha/artifacts/releases/alpha-python.evidence.json"
            && edge.kind == "evidence_for_surface"
            && edge.dst == "release_surface:dossier:alpha:python"
    }));
}

#[test]
fn build_fails_loudly_when_registry_file_is_invalid() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);

    write(
        &root.join("spctr-registry.json"),
        r#"{
  "version": 1,
  "counters": { "D": 1, "A": 0, "B": 0 },
  "series": {
    "D-001": { "slug": "alpha", "title": "Alpha" }
  },
  "docs": {
    "D-001": {
      "entries": {
        "intro": "D-001.001"
      }
    }
  }
}
"#,
    );
    write(
        &root.join("dossiers/alpha/spctr.toml"),
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"
series = "D-001"

[site]
visible = true
featured = false

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
"#,
    );

    let err = build(root, None).unwrap_err();
    let msg = format!("{err:#}");
    assert!(
        msg.contains("spctr-registry.json"),
        "expected registry validation failure, got: {msg}"
    );
}

#[test]
fn build_rejects_published_article_without_registry_series() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);

    write(
        &root.join("spctr-registry.json"),
        r#"{
  "version": 1,
  "counters": { "D": 1, "A": 0, "B": 1 },
  "series": {
    "B-001": { "slug": "hello-world", "title": "Hello World" },
    "D-001": { "slug": "alpha", "title": "Alpha" }
  },
  "docs": {}
}
"#,
    );
    write(
        &root.join("dossiers/alpha/spctr.toml"),
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"
series = "D-001"

[site]
visible = true
featured = false

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
"#,
    );
    write(
        &root.join("site/blog/hello-world/index.md"),
        r#"---
title: Hello World
release: published
---

# Hello World
"#,
    );

    let err = build(root, None).unwrap_err();
    let msg = format!("{err:#}");
    assert!(
        msg.contains("missing series assignment"),
        "expected blog registry validation failure, got: {msg}"
    );
}

#[test]
fn targeted_build_reuses_selected_manifests_for_docs() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);

    write(
        &root.join("dossiers/alpha/spctr.toml"),
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = true
featured = false
publish_docs = true

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
"#,
    );
    write(&root.join("dossiers/alpha/docs/README.md"), "# Alpha\n");
    write(
        &root.join("dossiers/beta/spctr.toml"),
        r#"version = 1
title = "Beta"
summary = "Broken."
status = "active"

[site]
visible = true
featured = false

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
"#,
    );

    let graph = build_with_options(
        root,
        Some("alpha"),
        GraphBuildOptions {
            include_docs: true,
            include_evidence: false,
            include_updates: false,
        },
    )
    .unwrap();

    assert_eq!(
        graph.scope_project.as_deref(),
        Some("project:dossier:alpha")
    );
    assert!(graph
        .nodes
        .iter()
        .any(|node| node.id == "doc:dossier:alpha:README"));
}
