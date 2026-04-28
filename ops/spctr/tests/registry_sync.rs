use camino::Utf8Path;
use serde_json::Value;
use std::fs;

fn write(root: &Utf8Path, rel: &str, content: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, content).unwrap();
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

fn minimal_registry(root: &Utf8Path) {
    write(
        root,
        "spctr-registry.json",
        r#"{
  "version": 1,
  "counters": {
    "A": 10,
    "B": 1,
    "D": 1
  },
  "series": {
    "A-009": {
      "slug": "k-semantics-reference",
      "title": "k-semantics-reference"
    }
  },
  "docs": {}
}
"#,
    );
}

fn addendum_manifest() -> &'static str {
    r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "k-semantics-reference"
series = "A-009"
summary = "reference"
status = "active"

[site]
visible = true
featured = false

[labels]
type = "research"

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
"#
}

#[test]
fn sync_assigns_missing_cabinet_doc_ids() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    minimal_registry(root);
    write(
        root,
        "addenda/k-semantics-reference/spctr.toml",
        addendum_manifest(),
    );
    write(
        root,
        "addenda/k-semantics-reference/docs/k-equations.md",
        "# K Equations\n",
    );

    let report = spctr::registry_sync::plan(root).unwrap();
    assert_eq!(report.doc_assignments.len(), 1);
    assert_eq!(report.doc_assignments[0].doc_id, "A-009.001");

    let applied = spctr::registry_sync::sync(root).unwrap();
    assert_eq!(applied.doc_assignments.len(), 1);
    spctr::registry_sync::ensure_clean(root).unwrap();

    let registry: Value =
        serde_json::from_str(&fs::read_to_string(root.join("spctr-registry.json")).unwrap())
            .unwrap();
    assert_eq!(
        registry["docs"]["A-009"]["entries"]["k-equations"],
        Value::String("A-009.001".to_owned())
    );
}

#[test]
fn sync_ignores_local_dirs_when_docs_root_is_project_root() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    minimal_registry(root);
    write(
        root,
        "addenda/k-semantics-reference/spctr.toml",
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "k-semantics-reference"
series = "A-009"
summary = "reference"
status = "active"

[site]
visible = true
featured = false
publish_docs = true

[labels]
type = "research"

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true

[spctr.docs]
root = "."
landing = "README.md"
require_frontmatter = false
"#,
    );
    write(
        root,
        "addenda/k-semantics-reference/README.md",
        "# K Semantics Reference\n",
    );
    write(
        root,
        "addenda/k-semantics-reference/.venv/lib/python/site-packages/pkg/README.md",
        "# Vendored Package README\n",
    );
    write(
        root,
        "addenda/k-semantics-reference/logs/run.md",
        "# Runtime Log\n",
    );
    write(
        root,
        "addenda/k-semantics-reference/artifacts/report.md",
        "# Generated Report\n",
    );
    write(
        root,
        "addenda/k-semantics-reference/docs/contracts/logs/schema.md",
        "# Log Schema\n",
    );

    let report = spctr::registry_sync::plan(root).unwrap();
    let slugs = report
        .doc_assignments
        .iter()
        .map(|assignment| assignment.doc_slug.as_str())
        .collect::<Vec<_>>();
    assert_eq!(slugs, vec!["README", "docs/contracts/logs/schema"]);
}

#[test]
fn sync_assigns_research_note_series_without_patching_frontmatter() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    minimal_registry(root);
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

    let report = spctr::registry_sync::plan(root).unwrap();
    assert_eq!(report.series_assignments.len(), 1);
    assert_eq!(report.series_assignments[0].slug, "field-note");
    assert_eq!(report.series_assignments[0].series_id, "B-001");
    assert!(!report.series_assignments[0].patch_source);

    let before_note =
        fs::read_to_string(root.join("site/research-notes/field-note/index.md")).unwrap();
    let applied = spctr::registry_sync::sync(root).unwrap();
    assert_eq!(applied.series_assignments.len(), 1);
    let after_note =
        fs::read_to_string(root.join("site/research-notes/field-note/index.md")).unwrap();
    assert_eq!(before_note, after_note);

    let registry: Value =
        serde_json::from_str(&fs::read_to_string(root.join("spctr-registry.json")).unwrap())
            .unwrap();
    assert_eq!(
        registry["series"]["B-001"]["slug"],
        Value::String("field-note".to_owned())
    );
}

#[test]
fn research_note_addendum_source_does_not_render_missing_href() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    write(
        root,
        "spctr-registry.json",
        r#"{
  "version": 1,
  "counters": { "A": 2, "B": 2, "D": 1 },
  "series": {
    "A-001": { "slug": "tooling", "title": "Tooling" },
    "B-001": { "slug": "field-note", "title": "Field Note" }
  },
  "docs": {}
}
"#,
    );
    write(
        root,
        "site/templates/index.html",
        "<html><body>\n<!-- GENERATED:HOME_ACTIVE_PROJECTS START -->\n<!-- GENERATED:HOME_ACTIVE_PROJECTS END -->\n<!-- GENERATED:HOME_FEATURED_ADDENDA START -->\n<!-- GENERATED:HOME_FEATURED_ADDENDA END -->\n<!-- GENERATED:HOME_BLOG_POSTS START -->\n<!-- GENERATED:HOME_BLOG_POSTS END -->\n</body></html>",
    );
    write(
        root,
        "site/templates/dossiers/index.html",
        "<html><body>\n<!-- GENERATED:DOSSIER_INDEX_GRID START -->\n<!-- GENERATED:DOSSIER_INDEX_GRID END -->\n</body></html>",
    );
    write(
        root,
        "site/templates/addenda/index.html",
        "<html><body>\n<!-- GENERATED:ADDENDA_INDEX_GRID START -->\n<!-- GENERATED:ADDENDA_INDEX_GRID END -->\n</body></html>",
    );
    write(
        root,
        "site/templates/blog/index.html",
        "<html><body>\n<!-- GENERATED:BLOG_INDEX_POSTS START -->\n<!-- GENERATED:BLOG_INDEX_POSTS END -->\n</body></html>",
    );
    write(
        root,
        "site/templates/research-notes/index.html",
        "<html><body></body></html>",
    );
    write(
        root,
        "site/templates/sitemap/index.html",
        "<html><body>\n<!-- GENERATED:SITEMAP_SECTIONS START -->\n<!-- GENERATED:SITEMAP_SECTIONS END -->\n<!-- GENERATED:SITEMAP_REGISTRY START -->\n<!-- GENERATED:SITEMAP_REGISTRY END -->\n</body></html>",
    );
    write(
        root,
        "site/templates/projects/health/index.html",
        "<html><body>\n<!-- GENERATED:PROJECT_HEALTH_CONTENT START -->\n<!-- GENERATED:PROJECT_HEALTH_CONTENT END -->\n</body></html>",
    );
    write(
        root,
        "site/templates/projects/artifacts/index.html",
        "<html><body>\n<!-- GENERATED:PROJECT_ARTIFACTS_CONTENT START -->\n<!-- GENERATED:PROJECT_ARTIFACTS_CONTENT END -->\n</body></html>",
    );
    write(
        root,
        "site/research-notes/pandoc-template.html",
        r#"$if(source_id)$
$if(source_href)$<a href="$source_href$">$source_id$</a>$else$<span>$source_id$</span>$endif$
$endif$
$body$"#,
    );
    write(
        root,
        "site/research-notes/field-note/index.md",
        r#"---
title: "Field Note"
release: "draft"
provenance: "assistant-drafted"
source_id: "A-001"
---

# Field Note
"#,
    );

    spctr::site::build(root, true).unwrap();
    let html = fs::read_to_string(root.join("site/research-notes/field-note/index.html")).unwrap();
    assert!(html.contains("<span>A-001</span>"));
    assert!(!html.contains("../../addenda/tooling/"));
}

#[test]
fn site_build_no_longer_assigns_series_implicitly() {
    let tmp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    write(
        root,
        "spctr-registry.json",
        r#"{
  "version": 1,
  "counters": {
    "A": 1,
    "B": 1,
    "D": 1
  },
  "series": {},
  "docs": {}
}
"#,
    );
    write(
        root,
        "site/templates/index.html",
        "<html><body>\n\
         <!-- GENERATED:HOME_ACTIVE_PROJECTS START -->\n\
         <!-- GENERATED:HOME_ACTIVE_PROJECTS END -->\n\
         <!-- GENERATED:HOME_FEATURED_ADDENDA START -->\n\
         <!-- GENERATED:HOME_FEATURED_ADDENDA END -->\n\
         <!-- GENERATED:HOME_BLOG_POSTS START -->\n\
         <!-- GENERATED:HOME_BLOG_POSTS END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/dossiers/index.html",
        "<html><body>\n\
         <!-- GENERATED:DOSSIER_INDEX_GRID START -->\n\
         <!-- GENERATED:DOSSIER_INDEX_GRID END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/addenda/index.html",
        "<html><body>\n\
         <!-- GENERATED:ADDENDA_INDEX_GRID START -->\n\
         <!-- GENERATED:ADDENDA_INDEX_GRID END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/blog/index.html",
        "<html><body>\n\
         <!-- GENERATED:BLOG_INDEX_POSTS START -->\n\
         <!-- GENERATED:BLOG_INDEX_POSTS END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/research-notes/index.html",
        "<html><body>\n\
         <!-- GENERATED:RESEARCH_NOTES_INDEX START -->\n\
         <!-- GENERATED:RESEARCH_NOTES_INDEX END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/sitemap/index.html",
        "<html><body>\n\
         <!-- GENERATED:SITEMAP_SECTIONS START -->\n\
         <!-- GENERATED:SITEMAP_SECTIONS END -->\n\
         <!-- GENERATED:SITEMAP_REGISTRY START -->\n\
         <!-- GENERATED:SITEMAP_REGISTRY END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/projects/health/index.html",
        "<html><body>\n\
         <!-- GENERATED:PROJECT_HEALTH_CONTENT START -->\n\
         <!-- GENERATED:PROJECT_HEALTH_CONTENT END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "site/templates/dossiers/default-hub.html",
        "<html><head><title>\n\
         <!-- GENERATED:DOSSIER_HUB_TITLE START -->\n\
         <!-- GENERATED:DOSSIER_HUB_TITLE END --> | SPECTER Labs</title></head><body>\n\
         <!-- GENERATED:DOSSIER_HUB_CONTENT START -->\n\
         <!-- GENERATED:DOSSIER_HUB_CONTENT END -->\n\
         </body></html>\n",
    );
    write(
        root,
        "dossiers/alpha/spctr.toml",
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "alpha"
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

    let before_manifest = fs::read_to_string(root.join("dossiers/alpha/spctr.toml")).unwrap();
    let before_registry = fs::read_to_string(root.join("spctr-registry.json")).unwrap();

    spctr::site::build(root, true).unwrap();

    let after_manifest = fs::read_to_string(root.join("dossiers/alpha/spctr.toml")).unwrap();
    let after_registry = fs::read_to_string(root.join("spctr-registry.json")).unwrap();
    assert_eq!(before_manifest, after_manifest);
    assert_eq!(before_registry, after_registry);
}
