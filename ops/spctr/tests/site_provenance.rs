use camino::Utf8Path;
use std::fs;

fn write(root: &Utf8Path, rel: &str, content: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, content).unwrap();
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

fn dossier_manifest(title: &str, visible: bool, featured: bool, hub_path: Option<&str>) -> String {
    let mut lines = vec![
        "version = 1".to_owned(),
        "license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"".to_owned(),
        format!("title = \"{title}\""),
        format!("summary = \"Dossier summary for {title}.\""),
        "status = \"active\"".to_owned(),
        String::new(),
        "[site]".to_owned(),
        format!("visible = {visible}"),
        format!("featured = {featured}"),
    ];
    if let Some(hub_path) = hub_path {
        lines.push(format!("hub_path = \"{hub_path}\""));
    }
    if featured {
        lines.push("featured_order = 1".to_owned());
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

fn published_blog_post() -> &'static str {
    r#"---
title: Hello World
release: published
series: B-001
---

# Hello World

Graph-native article.
"#
}

fn publish_docs_dossier_manifest(title: &str) -> String {
    format!(
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "{title}"
summary = "Dossier summary for {title}."
status = "active"

[site]
visible = true
featured = true
publish_docs = true
featured_order = 1

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
"#
    )
}

fn with_repo(test: impl FnOnce(&Utf8Path)) {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    test(root);
}

#[test]
fn repo_aware_non_generated_changes_are_ignored() {
    with_repo(|root| {
        let violations =
            spctr::site::provenance::find_provenance_violations_for_repo(root, ["README.md"])
                .unwrap();
        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_catalog_allows_output_only_sync() {
    with_repo(|root| {
        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/projects/catalog.json"],
        )
        .unwrap();
        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_home_accepts_manifest_change() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, true, None),
        );
        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/index.html", "dossiers/alpha/spctr.toml"],
        )
        .unwrap();
        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_catalog_ignores_hidden_manifest_changes() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, true, None),
        );
        write(
            root,
            "dossiers/hidden/spctr.toml",
            &dossier_manifest("Hidden", false, false, None),
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/projects/catalog.json", "dossiers/hidden/spctr.toml"],
        )
        .unwrap();

        assert_eq!(violations.len(), 1);
        assert!(violations[0].contains("site/projects/catalog.json"));
    });
}

#[test]
fn repo_aware_home_ignores_nonfeatured_visible_manifest_changes() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, false, None),
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/index.html", "dossiers/alpha/spctr.toml"],
        )
        .unwrap();

        assert_eq!(violations.len(), 1);
        assert!(violations[0].contains("site/index.html"));
    });
}

#[test]
fn repo_aware_catalog_accepts_visible_hub_page_changes() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, true, Some("site/dossiers/alpha/index.html")),
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            [
                "site/projects/catalog.json",
                "site/dossiers/alpha/index.html",
            ],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_sitemap_accepts_visible_hub_page_changes() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, true, Some("site/dossiers/alpha/index.html")),
        );
        write(
            root,
            "site/index.html",
            "<html><title>Home</title></html>\n",
        );
        write(
            root,
            "site/dossiers/index.html",
            "<html><title>Dossiers</title></html>\n",
        );
        write(
            root,
            "site/dossiers/alpha/index.html",
            "<html><title>Alpha</title></html>\n",
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/sitemap/index.html", "site/dossiers/alpha/index.html"],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_health_accepts_exec_evidence_changes() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, true, None),
        );
        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            [
                "site/projects/health/index.html",
                "site/projects/health.json",
                "dossiers/alpha/artifacts/evidence/check.json",
            ],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_artifacts_accept_manifest_changes() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &dossier_manifest("Alpha", true, true, None),
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/projects/artifacts.json", "dossiers/alpha/spctr.toml"],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_blog_post_page_accepts_markdown_change() {
    with_repo(|root| {
        write(
            root,
            "site/blog/hello-world/index.md",
            published_blog_post(),
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            [
                "site/blog/hello-world/index.html",
                "site/blog/hello-world/index.md",
            ],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_research_note_page_accepts_markdown_change() {
    with_repo(|root| {
        write(
            root,
            "spctr-registry.json",
            r#"{
  "version": 1,
  "counters": { "A": 0, "B": 2, "D": 0 },
  "series": {
    "B-001": { "slug": "field-note", "title": "Field Note" }
  },
  "docs": {}
}
"#,
        );
        write(
            root,
            "site/research-notes/field-note/index.md",
            r#"---
title: "Field Note"
release: "draft"
provenance: "assistant-drafted"
toc: true
---

# Field Note
"#,
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            [
                "site/research-notes/field-note/index.html",
                "site/research-notes/field-note/index.md",
            ],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_blog_pdf_accepts_markdown_change() {
    with_repo(|root| {
        write(
            root,
            "site/blog/hello-world/index.md",
            published_blog_post(),
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            [
                "site/blog/hello-world/hello-world.pdf",
                "site/blog/hello-world/index.md",
            ],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_cabinet_page_accepts_doc_change() {
    with_repo(|root| {
        write(
            root,
            "dossiers/alpha/spctr.toml",
            &publish_docs_dossier_manifest("Alpha"),
        );
        write(
            root,
            "dossiers/alpha/docs/intro.md",
            "# Intro\n\nPublic doc.\n",
        );

        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            [
                "site/cabinet/index.html",
                "site/cabinet/alpha/intro/index.html",
                "dossiers/alpha/docs/intro.md",
            ],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}

#[test]
fn repo_aware_status_page_accepts_report_source_change() {
    with_repo(|root| {
        let violations = spctr::site::provenance::find_provenance_violations_for_repo(
            root,
            ["site/status/index.html", "ops/spctr/src/report.rs"],
        )
        .unwrap();

        assert!(violations.is_empty());
    });
}
