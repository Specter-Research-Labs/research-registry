use camino::Utf8Path;
use std::fs;

fn write(root: &Utf8Path, rel: &str, content: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, content).unwrap();
}

fn dossier_manifest(
    title: &str,
    status: &str,
    visible: bool,
    featured: bool,
    featured_order: Option<u32>,
    hub_path: Option<&str>,
) -> String {
    let mut lines = vec![
        "version = 1".to_owned(),
        "license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"".to_owned(),
        format!("title = \"{title}\""),
        format!("summary = \"Dossier summary for {title}.\""),
        format!("status = \"{status}\""),
        String::new(),
        "[site]".to_owned(),
        format!("visible = {visible}"),
        format!("featured = {featured}"),
    ];
    if let Some(order) = featured_order {
        lines.push(format!("featured_order = {order}"));
    }
    if let Some(hp) = hub_path {
        lines.push(format!("hub_path = \"{hp}\""));
    }
    lines.push(String::new());
    lines.push("[release]".to_owned());
    lines.push("stage = \"promoted\"".to_owned());
    lines.push(String::new());
    lines.push("[[release.surfaces]]".to_owned());
    lines.push("name = \"source\"".to_owned());
    lines.push("kind = \"source_bundle\"".to_owned());
    lines.push("publish = true".to_owned());
    lines.join("\n") + "\n"
}

fn addendum_manifest(
    title: &str,
    status: &str,
    addendum_type: &str,
    visible: bool,
    featured: bool,
    featured_order: Option<u32>,
    related_dossier: Option<&str>,
) -> String {
    let mut lines = vec![
        "version = 1".to_owned(),
        "license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"".to_owned(),
        format!("title = \"{title}\""),
        format!("summary = \"Addendum summary for {title}.\""),
        format!("status = \"{status}\""),
        String::new(),
        "[site]".to_owned(),
        format!("visible = {visible}"),
        format!("featured = {featured}"),
    ];
    if let Some(order) = featured_order {
        lines.push(format!("featured_order = {order}"));
    }
    lines.push(String::new());
    lines.push("[labels]".to_owned());
    lines.push(format!("type = \"{addendum_type}\""));
    if let Some(dossier) = related_dossier {
        lines.push(String::new());
        lines.push("[relations]".to_owned());
        lines.push(format!("dossier = \"{dossier}\""));
    }
    lines.push(String::new());
    lines.push("[release]".to_owned());
    lines.push("stage = \"promoted\"".to_owned());
    lines.push(String::new());
    lines.push("[[release.surfaces]]".to_owned());
    lines.push("name = \"source\"".to_owned());
    lines.push("kind = \"source_bundle\"".to_owned());
    lines.push("publish = true".to_owned());
    lines.join("\n") + "\n"
}

fn minimal_design_tokens(root: &Utf8Path) {
    write(
        root,
        "addenda/design-tokens/base.toml",
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
    write(root, "addenda/design-tokens/web.toml", "");
}

fn minimal_templates(root: &Utf8Path) {
    minimal_design_tokens(root);
    write(
        root,
        "site/templates/index.html",
        "\
<html>
<body>
<!-- GENERATED:HOME_ACTIVE_PROJECTS START -->
<!-- GENERATED:HOME_ACTIVE_PROJECTS END -->
<!-- GENERATED:HOME_FEATURED_ADDENDA START -->
<!-- GENERATED:HOME_FEATURED_ADDENDA END -->
<!-- GENERATED:HOME_BLOG_POSTS START -->
<!-- GENERATED:HOME_BLOG_POSTS END -->
</body>
</html>
",
    );
    write(
        root,
        "site/templates/dossiers/index.html",
        "\
<html>
<body>
<!-- GENERATED:DOSSIER_INDEX_GRID START -->
<!-- GENERATED:DOSSIER_INDEX_GRID END -->
</body>
</html>
",
    );
    write(
        root,
        "site/templates/addenda/index.html",
        "\
<html>
<body>
<!-- GENERATED:ADDENDA_INDEX_GRID START -->
<!-- GENERATED:ADDENDA_INDEX_GRID END -->
</body>
</html>
",
    );
    write(
        root,
        "site/templates/blog/index.html",
        "\
<html>
<body>
<!-- GENERATED:BLOG_INDEX_POSTS START -->
<!-- GENERATED:BLOG_INDEX_POSTS END -->
</body>
</html>
",
    );
    write(
        root,
        "site/templates/research-notes/index.html",
        "\
<html>
<body>
</body>
</html>
",
    );
    write(
        root,
        "site/templates/sitemap/index.html",
        "\
<html>
<body>
<!-- GENERATED:SITEMAP_SECTIONS START -->
<!-- GENERATED:SITEMAP_SECTIONS END -->
<!-- GENERATED:SITEMAP_REGISTRY START -->
<!-- GENERATED:SITEMAP_REGISTRY END -->
</body>
</html>
",
    );
    write(
        root,
        "site/templates/projects/health/index.html",
        "\
<html>
<body>
<!-- GENERATED:PROJECT_HEALTH_CONTENT START -->
<!-- GENERATED:PROJECT_HEALTH_CONTENT END -->
</body>
</html>
",
    );
    write(
        root,
        "site/templates/dossiers/default-hub.html",
        "\
<html>
<head>
<title>
<!-- GENERATED:DOSSIER_HUB_TITLE START -->
<!-- GENERATED:DOSSIER_HUB_TITLE END --> | SPECTER Labs</title>
</head>
<body>
<!-- GENERATED:DOSSIER_HUB_CONTENT START -->
<!-- GENERATED:DOSSIER_HUB_CONTENT END -->
</body>
</html>
",
    );
}

#[test]
fn invalid_dossier_status_is_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "operational", true, false, None, None),
    );

    let err = spctr::site::records::load_site_records(root).unwrap_err();
    let msg = format!("{err:#}");
    assert!(msg.contains("status must be one of"), "got: {msg}");
}

#[test]
fn duplicate_featured_order_is_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(
        root,
        "dossiers/beta/spctr.toml",
        &dossier_manifest("Beta", "active", true, true, Some(1), None),
    );

    let err = spctr::site::records::load_site_records(root).unwrap_err();
    let msg = format!("{err:#}");
    assert!(msg.contains("duplicate featured order"), "got: {msg}");
}

#[test]
fn hidden_project_excluded_from_output() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(
        root,
        "dossiers/hidden/spctr.toml",
        &dossier_manifest("HiddenDossier", "hold", false, false, None, None),
    );
    write(
        root,
        "addenda/tool-a/spctr.toml",
        &addendum_manifest("ToolA", "operational", "tooling", true, false, None, None),
    );
    write(
        root,
        "addenda/tool-hidden/spctr.toml",
        &addendum_manifest(
            "HiddenTool",
            "operational",
            "tooling",
            false,
            false,
            None,
            None,
        ),
    );

    spctr::site::build(root, true).unwrap();

    let home = fs::read_to_string(root.join("site/index.html")).unwrap();
    let dossier_idx = fs::read_to_string(root.join("site/dossiers/index.html")).unwrap();
    let addenda_idx = fs::read_to_string(root.join("site/addenda/index.html")).unwrap();
    let catalog = fs::read_to_string(root.join("site/projects/catalog.json")).unwrap();

    assert!(home.contains("Alpha"), "home should contain Alpha");
    assert!(
        dossier_idx.contains("Alpha"),
        "dossier index should contain Alpha"
    );
    assert!(
        addenda_idx.contains("ToolA"),
        "addenda index should contain ToolA"
    );

    assert!(
        !home.contains("HiddenDossier"),
        "home should not contain HiddenDossier"
    );
    assert!(
        !dossier_idx.contains("HiddenDossier"),
        "dossier index should not contain HiddenDossier"
    );
    assert!(
        !addenda_idx.contains("HiddenTool"),
        "addenda index should not contain HiddenTool"
    );

    assert!(
        !catalog.contains("hidden"),
        "catalog should not contain hidden slug"
    );
    assert!(
        !catalog.contains("tool-hidden"),
        "catalog should not contain tool-hidden slug"
    );
}

#[test]
fn site_build_renders_blog_from_graph_articles() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "spctr-registry.json",
        r#"{
  "version": 1,
  "counters": { "D": 1, "A": 0, "B": 1 },
  "series": {
    "B-001": { "slug": "hello-world", "title": "Hello World" },
    "D-001": { "slug": "alpha", "title": "Alpha Project" }
  },
  "docs": {}
}
"#,
    );
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(
        root,
        "site/blog/hello-world/index.md",
        r#"---
title: Hello World
release: published
series: B-001
summary: Graph-native article.
---

# Hello World

Graph-native article.
"#,
    );

    spctr::site::build(root, true).unwrap();

    let home = fs::read_to_string(root.join("site/index.html")).unwrap();
    let blog = fs::read_to_string(root.join("site/blog/index.html")).unwrap();
    let sitemap = fs::read_to_string(root.join("site/sitemap/index.html")).unwrap();

    assert!(
        home.contains("Hello World"),
        "home should contain article title"
    );
    assert!(
        blog.contains("Hello World"),
        "blog index should contain article title"
    );
    assert!(
        sitemap.contains("SPCTR B-001") && sitemap.contains("Hello World"),
        "sitemap registry should contain graph-backed article entry"
    );
}

#[test]
fn bad_linked_dossier_reference_is_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "addenda/tool-a/spctr.toml",
        &addendum_manifest(
            "ToolA",
            "operational",
            "tooling",
            true,
            false,
            None,
            Some("missing-dossier"),
        ),
    );

    let err = spctr::site::records::load_site_records(root).unwrap_err();
    let msg = format!("{err:#}");
    assert!(msg.contains("unknown or hidden dossier"), "got: {msg}");
}

#[test]
fn missing_hub_marker_is_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "site/templates/dossiers/alpha/index.html",
        "<html><body><section>no markers here</section></body></html>\n",
    );
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest(
            "Alpha",
            "active",
            true,
            true,
            Some(1),
            Some("site/dossiers/alpha/index.html"),
        ),
    );

    let err = spctr::site::build(root, true).unwrap_err();
    let msg = format!("{err:#}");
    assert!(
        msg.contains("missing generated region markers"),
        "got: {msg}"
    );
}

#[test]
fn spctr_table_is_ignored_for_site_metadata() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "site/templates/dossiers/alpha/index.html",
        "<html><body>\n\
         <!-- GENERATED:DOSSIER_HUB_HEADER START -->\n\
         <!-- GENERATED:DOSSIER_HUB_HEADER END -->\n\
         </body></html>\n",
    );
    let mut manifest = dossier_manifest(
        "Alpha",
        "active",
        true,
        true,
        Some(1),
        Some("site/dossiers/alpha/index.html"),
    );
    manifest.push_str("\n[spctr]\nproject = \"alpha\"\ndefault_surface = \"demo\"\n\n[spctr.surfaces.demo]\nkind = \"raw\"\nraw_roots = [\"logs\"]\n");
    write(root, "dossiers/alpha/spctr.toml", &manifest);

    let mut addendum = addendum_manifest(
        "ToolA",
        "operational",
        "tooling",
        true,
        true,
        Some(1),
        Some("alpha"),
    );
    addendum.push_str("\n[spctr]\nproject = \"tool-a\"\n");
    write(root, "addenda/tool-a/spctr.toml", &addendum);

    spctr::site::build(root, true).unwrap();

    let catalog = fs::read_to_string(root.join("site/projects/catalog.json")).unwrap();
    let home = fs::read_to_string(root.join("site/index.html")).unwrap();

    assert!(
        catalog.contains("\"slug\": \"alpha\""),
        "catalog should contain alpha"
    );
    assert!(
        catalog.contains("\"slug\": \"tool-a\""),
        "catalog should contain tool-a"
    );
    assert!(home.contains("Alpha"), "home should contain Alpha");
    assert!(home.contains("ToolA"), "home should contain ToolA");
}

#[test]
fn hub_header_is_injected_into_output() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "site/templates/dossiers/alpha/index.html",
        "<html><body>\n\
         <!-- GENERATED:DOSSIER_HUB_HEADER START -->\n\
         <!-- GENERATED:DOSSIER_HUB_HEADER END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest(
            "Alpha Project",
            "active",
            true,
            true,
            Some(1),
            Some("site/dossiers/alpha/index.html"),
        ),
    );

    spctr::site::build(root, true).unwrap();

    let hub = fs::read_to_string(root.join("site/dossiers/alpha/index.html")).unwrap();
    assert!(
        hub.contains("Alpha Project"),
        "hub should contain the project title"
    );
    assert!(
        hub.contains("project-status active") && hub.contains(">active<"),
        "hub should contain the status chip"
    );
    assert!(
        hub.contains("hub-meta-row"),
        "hub should contain meta table rows"
    );
}

#[test]
fn visible_dossier_without_declared_hub_gets_generated_public_hub() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha Project", "active", true, true, Some(1), None),
    );
    write(root, "dossiers/alpha/docs/README.md", "# Alpha Docs\n");
    write(
        root,
        "addenda/tool-a/spctr.toml",
        &addendum_manifest(
            "ToolA",
            "operational",
            "tooling",
            true,
            false,
            None,
            Some("alpha"),
        ),
    );

    spctr::site::build(root, true).unwrap();

    let hub = fs::read_to_string(root.join("site/dossiers/alpha/index.html")).unwrap();
    let home = fs::read_to_string(root.join("site/index.html")).unwrap();
    let addenda = fs::read_to_string(root.join("site/addenda/index.html")).unwrap();
    let catalog_text = fs::read_to_string(root.join("site/projects/catalog.json")).unwrap();
    let catalog: serde_json::Value = serde_json::from_str(&catalog_text).unwrap();

    assert!(
        hub.contains("Alpha Project"),
        "hub should contain the title"
    );
    assert!(
        hub.contains("Cabinet Docs"),
        "hub should contain cabinet docs links"
    );
    assert!(
        hub.contains("Related Addenda") && hub.contains("ToolA"),
        "hub should contain linked addenda"
    );
    assert!(
        home.contains("href=dossiers/alpha/") || home.contains("href=\"dossiers/alpha/\""),
        "home should link to the generated hub"
    );
    assert!(
        addenda.contains("Linked Dossier"),
        "addenda index should link back to the generated hub"
    );
    assert_eq!(
        catalog["dossiers"][0]["hub_path"],
        "site/dossiers/alpha/index.html"
    );
    assert_eq!(catalog["dossiers"][0]["hub_href"], "dossiers/alpha/");
    assert_eq!(
        catalog["addenda"][0]["linked_dossier_href"],
        "dossiers/alpha/"
    );
}

#[test]
fn site_build_writes_project_health_page_and_json() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha Project"
summary = "Alpha summary."
status = "active"
series = "D-001"

[site]
visible = true
featured = true
featured_order = 1
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

[spctr.surfaces.lake]
kind = "raw_plus_db"
raw_roots = ["artifacts/raw"]
local_db_path = "artifacts/lake.sqlite"
refresh_command = ["python3", "-c", "print('refresh')"]
remote_raw_namespace = "alpha"
remote_snapshot_namespace = "lake"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]
expected_outputs = ["smoke-report"]

[spctr.exec.smoke]
command = ["python3", "-c", "print('smoke')"]
expected_outputs = ["smoke-report"]

[spctr.exec.build]
command = ["python3", "-c", "print('build')"]
expected_outputs = ["wheel"]

[spctr.exec.publish]
command = ["python3", "-c", "print('publish')"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "smoke-report"
path = "artifacts/smoke/report.json"
kind = "status_json"
required = true

[[spctr.expected_outputs]]
name = "wheel"
path = "dist/*.whl"
kind = "python_wheel"
required = true
surface = "python"

[spctr.docs]
root = "docs"
landing = "docs/README.md"
require_frontmatter = false

[[spctr.site_data]]
name = "dashboard"
site_path = "dossiers/alpha/dashboard/data"
local_source = "artifacts/site-data"
"#,
    );
    write(root, "dossiers/alpha/docs/README.md", "# Alpha Docs\n");
    write(root, "dossiers/alpha/artifacts/site-data/.keep", "");
    write(
        root,
        "dossiers/alpha/artifacts/evidence/check.json",
        r#"{
  "version": 1,
  "project": "alpha",
  "kind": "dossier",
  "action": "check",
  "status": "ok",
  "finished_at": "2026-04-07T10:00:00Z"
}
"#,
    );
    write(
        root,
        "dossiers/alpha/artifacts/evidence/smoke.json",
        r#"{
  "version": 1,
  "project": "alpha",
  "kind": "dossier",
  "action": "smoke",
  "status": "ok",
  "finished_at": "2026-04-07T10:10:00Z"
}
"#,
    );
    write(
        root,
        "dossiers/alpha/artifacts/evidence/build.json",
        r#"{
  "version": 1,
  "project": "alpha",
  "kind": "dossier",
  "action": "build",
  "status": "ok",
  "finished_at": "2026-04-07T10:20:00Z"
}
"#,
    );
    write(
        root,
        "dossiers/alpha/artifacts/evidence/publish.json",
        r#"{
  "version": 1,
  "project": "alpha",
  "kind": "dossier",
  "action": "publish",
  "status": "ok",
  "finished_at": "2026-04-07T10:25:00Z"
}
"#,
    );
    write(
        root,
        "dossiers/alpha/artifacts/releases/alpha-python.evidence.json",
        r#"{
  "version": 1,
  "action": "package_surface",
  "generated_at": "2026-04-07T10:30:00Z",
  "project": "alpha",
  "title": "Alpha Project",
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

    spctr::site::build(root, true).unwrap();

    let page = fs::read_to_string(root.join("site/projects/health/index.html")).unwrap();
    let json_text = fs::read_to_string(root.join("site/projects/health.json")).unwrap();
    let artifact_json_text = fs::read_to_string(root.join("site/projects/artifacts.json")).unwrap();
    let health: serde_json::Value = serde_json::from_str(&json_text).unwrap();
    let artifacts: serde_json::Value = serde_json::from_str(&artifact_json_text).unwrap();

    assert!(page.contains("Project Health"), "page should contain title");
    assert!(
        page.contains("Alpha Project") && page.contains("Proof Paths Ready"),
        "page should contain project and summary"
    );
    assert!(
        page.contains("check: ok")
            && page.contains("smoke: ok")
            && page.contains("build: ok")
            && page.contains("publish: ok"),
        "page should contain canonical action state"
    );
    assert!(
        !root.join("site/projects/artifacts/index.html").exists(),
        "artifact inventory should not be published on the main site"
    );
    assert_eq!(health["summary"]["visible_projects"], 1);
    assert_eq!(health["summary"]["proof_ready_projects"], 1);
    assert_eq!(health["summary"]["release_tracked_projects"], 1);
    assert_eq!(health["dossiers"][0]["gate_state"], "ready");
    assert_eq!(health["dossiers"][0]["hub_mode"], "generated");
    assert_eq!(health["dossiers"][0]["check"]["status"], "ok");
    assert_eq!(health["dossiers"][0]["smoke"]["status"], "ok");
    assert_eq!(health["dossiers"][0]["build"]["status"], "ok");
    assert_eq!(health["dossiers"][0]["release_coverage_state"], "tracked");
    assert_eq!(
        health["dossiers"][0]["published_surfaces"][0]["name"],
        "python"
    );
    assert_eq!(
        health["dossiers"][0]["published_surfaces"][0]["kind"],
        "package"
    );
    assert_eq!(artifacts["summary"]["durable_surfaces"], 1);
    assert_eq!(artifacts["summary"]["site_data_mounts"], 1);
    assert_eq!(
        artifacts["dossiers"][0]["durable_surfaces"][0]["name"],
        "lake"
    );
    assert_eq!(
        artifacts["dossiers"][0]["site_data_mounts"][0]["name"],
        "dashboard"
    );
}

#[test]
fn export_project_feeds_writes_catalog_health_and_artifacts_without_templates() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha Project"
summary = "Alpha summary."
status = "active"

[site]
visible = true
featured = true
featured_order = 1
publish_docs = true

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true

[spctr]
project = "alpha"
default_surface = "lake"

[spctr.surfaces.lake]
kind = "raw_plus_db"
raw_roots = ["artifacts/raw"]
local_db_path = "artifacts/lake.sqlite"
refresh_command = ["python3", "-c", "print('refresh')"]
remote_raw_namespace = "alpha"
remote_snapshot_namespace = "lake"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]
expected_outputs = ["check-report"]

[spctr.exec.smoke]
command = ["python3", "-c", "print('smoke')"]
expected_outputs = ["smoke-report"]

[spctr.exec.build]
command = ["python3", "-c", "print('build')"]
expected_outputs = ["build-report"]

[spctr.exec.publish]
command = ["python3", "-c", "print('publish')"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "check-report"
path = "artifacts/check/report.json"
kind = "status_json"
required = true

[[spctr.expected_outputs]]
name = "smoke-report"
path = "artifacts/smoke/report.json"
kind = "status_json"
required = true

[[spctr.expected_outputs]]
name = "build-report"
path = "artifacts/build/report.json"
kind = "status_json"
required = true

[spctr.docs]
root = "docs"
landing = "docs/README.md"
require_frontmatter = false

[[spctr.site_data]]
name = "dashboard"
site_path = "dossiers/alpha/dashboard/data"
local_source = "artifacts/site-data"
"#,
    );
    write(root, "dossiers/alpha/docs/README.md", "# Alpha Docs\n");
    write(root, "dossiers/alpha/artifacts/site-data/.keep", "");
    write(
        root,
        "dossiers/alpha/artifacts/evidence/check.json",
        r#"{
  "version": 1,
  "project": "alpha",
  "kind": "dossier",
  "action": "check",
  "status": "ok",
  "finished_at": "2026-04-07T10:00:00Z"
}
"#,
    );

    spctr::site::export_project_feeds(root, true).unwrap();

    let catalog_text = fs::read_to_string(root.join("site/projects/catalog.json")).unwrap();
    let artifacts_text = fs::read_to_string(root.join("site/projects/artifacts.json")).unwrap();
    let health_text = fs::read_to_string(root.join("site/projects/health.json")).unwrap();
    let catalog: serde_json::Value = serde_json::from_str(&catalog_text).unwrap();
    let artifacts: serde_json::Value = serde_json::from_str(&artifacts_text).unwrap();
    let health: serde_json::Value = serde_json::from_str(&health_text).unwrap();

    assert_eq!(catalog["dossiers"][0]["slug"], "alpha");
    assert_eq!(artifacts["dossiers"][0]["slug"], "alpha");
    assert_eq!(artifacts["summary"]["durable_surfaces"], 1);
    assert_eq!(health["summary"]["visible_projects"], 1);
    assert_eq!(health["dossiers"][0]["slug"], "alpha");
}

#[test]
fn catalog_json_has_correct_structure() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(
        root,
        "addenda/tool-a/spctr.toml",
        &addendum_manifest("ToolA", "operational", "tooling", true, false, None, None),
    );

    spctr::site::build(root, true).unwrap();

    let catalog_text = fs::read_to_string(root.join("site/projects/catalog.json")).unwrap();
    let catalog: serde_json::Value = serde_json::from_str(&catalog_text).unwrap();

    assert_eq!(catalog["version"], 1);
    let dossiers = catalog["dossiers"]
        .as_array()
        .expect("dossiers should be an array");
    let addenda = catalog["addenda"]
        .as_array()
        .expect("addenda should be an array");
    assert_eq!(dossiers.len(), 1);
    assert_eq!(addenda.len(), 1);

    assert_eq!(dossiers[0]["slug"], "alpha");
    assert_eq!(dossiers[0]["title"], "Alpha");
    assert_eq!(dossiers[0]["status"], "active");

    assert_eq!(addenda[0]["slug"], "tool-a");
    assert_eq!(addenda[0]["title"], "ToolA");

    let featured = &catalog["featured"];
    let feat_dossiers = featured["dossiers"].as_array().unwrap();
    assert_eq!(feat_dossiers.len(), 1);
    assert_eq!(feat_dossiers[0], "alpha");
    assert!(featured["addenda"].as_array().unwrap().is_empty());
}

#[test]
fn catalog_marks_docs_presence_from_graph_backed_site_records() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(root, "dossiers/alpha/docs/README.md", "# Alpha Docs\n");

    spctr::site::build(root, true).unwrap();

    let catalog_text = fs::read_to_string(root.join("site/projects/catalog.json")).unwrap();
    let catalog: serde_json::Value = serde_json::from_str(&catalog_text).unwrap();

    assert_eq!(catalog["dossiers"][0]["has_docs"], true);
    assert_eq!(catalog["dossiers"][0]["has_docs_readme"], true);
    assert_eq!(
        catalog["dossiers"][0]["cabinet_href"],
        "cabinet/alpha/README/"
    );
}

#[test]
fn site_records_ignore_invalid_updates_and_evidence_cards() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(root, "site/updates/entries/bad.json", "{ not valid json\n");
    write(
        root,
        "dossiers/alpha/artifacts/evidence/check.json",
        "{ not valid json\n",
    );

    let records = spctr::site::records::load_site_records(root).unwrap();

    assert_eq!(records.len(), 1);
    assert_eq!(records[0].slug, "alpha");
}

#[test]
fn replace_region_injects_content() {
    let template = "\
<html>
<body>
    <!-- GENERATED:TEST START -->
    <!-- GENERATED:TEST END -->
</body>
</html>";

    let result =
        spctr::site::inject::replace_region(template, "TEST", "<p>injected</p>", "test.html")
            .unwrap();

    assert!(
        result.contains("<p>injected</p>"),
        "should contain injected content"
    );
    assert!(
        result.contains("<!-- GENERATED:TEST START -->"),
        "should keep start marker"
    );
    assert!(
        result.contains("<!-- GENERATED:TEST END -->"),
        "should keep end marker"
    );
}

#[test]
fn sitemap_auto_discovers_new_section() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(
        root,
        "site/foo/index.html",
        "\
<html>
<head>
<title>
<!-- GENERATED:FOO_TITLE START -->
Foo Section
<!-- GENERATED:FOO_TITLE END --> | SPECTER Labs
</title>
</head>
<body></body>
</html>
",
    );

    spctr::site::build(root, true).unwrap();

    let sitemap = fs::read_to_string(root.join("site/sitemap/index.html")).unwrap();
    assert!(
        sitemap.contains("Foo Section"),
        "sitemap should auto-discover site/foo/"
    );
    assert!(
        !sitemap.contains("GENERATED:FOO_TITLE"),
        "sitemap title should strip generated-region comments"
    );
}

#[test]
fn sitemap_excludes_templates_and_sitemap() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );

    spctr::site::build(root, true).unwrap();

    let sitemap = fs::read_to_string(root.join("site/sitemap/index.html")).unwrap();
    assert!(
        !sitemap.contains("href=\"../templates"),
        "sitemap should exclude templates/"
    );
    assert!(
        !sitemap.contains("href=\"./\"") && !sitemap.contains("href=\"../sitemap"),
        "sitemap should exclude sitemap/"
    );
    assert!(
        !sitemap.contains("href=\"../research-notes"),
        "sitemap should exclude hidden research notes/"
    );
}

#[test]
fn sitemap_shallow_excludes_cabinet_children() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_templates(root);
    write(
        root,
        "dossiers/alpha/spctr.toml",
        &dossier_manifest("Alpha", "active", true, true, Some(1), None),
    );
    write(
        root,
        "site/cabinet/index.html",
        "<html><head><title>Cabinet | SPECTER Labs</title></head><body></body></html>\n",
    );
    write(
        root,
        "site/cabinet/some-project/README/index.html",
        "<html><head><title>Some Doc | SPECTER Labs</title></head><body></body></html>\n",
    );

    spctr::site::build(root, true).unwrap();

    let sitemap = fs::read_to_string(root.join("site/sitemap/index.html")).unwrap();
    assert!(
        sitemap.contains("Cabinet"),
        "sitemap should include cabinet index"
    );
    assert!(
        !sitemap.contains("Some Doc"),
        "sitemap should exclude cabinet children in shallow mode"
    );
}

#[test]
fn replace_region_rejects_missing_markers() {
    let template = "<html><body>no markers</body></html>";
    let err = spctr::site::inject::replace_region(template, "TEST", "<p>content</p>", "test.html")
        .unwrap_err();
    let msg = format!("{err:#}");
    assert!(
        msg.contains("missing generated region markers"),
        "got: {msg}"
    );
}

#[test]
fn cabinet_index_requires_drawers_marker() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    write(
        root,
        "site/cabinet/index-template.html",
        "<html><body><section>no drawers marker</section></body></html>\n",
    );

    let err = spctr::site::cabinet::render::build_index(&[], &root.join("site")).unwrap_err();
    let msg = format!("{err:#}");
    assert!(
        msg.contains("template missing drawers marker"),
        "got: {msg}"
    );
}

#[test]
fn cabinet_docs_from_graph_use_series_titles_and_doc_ids() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    write(
        root,
        "spctr-registry.json",
        r#"{
  "version": 1,
  "counters": {
    "A": 0,
    "B": 0,
    "D": 1
  },
  "series": {
    "D-001": {
      "slug": "alpha",
      "title": "Alpha Series"
    }
  },
  "docs": {
    "D-001": {
      "next_counter": 2,
      "entries": {
        "README": "D-001.001"
      }
    }
  }
}
"#,
    );
    write(
        root,
        "dossiers/alpha/spctr.toml",
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha Project"
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
name = "source"
kind = "source_bundle"
publish = true
"#,
    );
    write(root, "dossiers/alpha/docs/README.md", "# Alpha Docs\n");

    let graph = spctr::graph::build_with_options(
        root,
        None,
        spctr::graph::GraphBuildOptions {
            include_docs: true,
            include_evidence: false,
            include_updates: false,
        },
    )
    .unwrap();
    let entries = spctr::site::cabinet::docs::find_published_docs_from_graph(root, &graph).unwrap();

    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].doc_id, "D-001.001");
    assert_eq!(entries[0].project_display, "Alpha Series");
    assert_eq!(entries[0].series_id.as_deref(), Some("D-001"));
}
