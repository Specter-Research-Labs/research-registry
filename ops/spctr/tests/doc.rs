use camino::{Utf8Path, Utf8PathBuf};
use spctr::doc::Target;
use std::fs;

fn repo_root() -> Utf8PathBuf {
    Utf8Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn write(root: &Utf8Path, rel: &str, content: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, content).unwrap();
}

const BIB: &str = r"@article{levin2025,
  title = {Mind Everywhere},
  author = {Levin, Michael and Resnik, David},
  journal = {Example Journal},
  year = {2025},
  url = {https://example.org/mind-everywhere}
}
";

fn report(body: &str) -> String {
    format!(
        r"---
title: Arrest after release
subtitle: Why a freed pair stays put
kicker: Specter Labs · Flow Lenia
authors: Ada Example
document_id: RPT-001
revision: 3
year: 2026
url: https://lab.specterlab.org/reports/rpt-001/
abstract: |
  A temporary obstacle leaves the pair *arrested*.
bibliography: refs.bib
---

{body}
"
    )
}

const BODY: &str = r#"# The arrest

Pairs stop after release [@levin2025].[^why]

[^why]: The lobes decouple.

## Lobe directions

See the [arrest receipt](assets/arrest.json) and the [trace](assets/trace.csv).

<figure><img src="assets/pair.png" alt="pair"><figcaption>The pair.</figcaption></figure>

<figure><table><tr><td>1</td></tr></table><figcaption>Counts.</figcaption></figure>

# Restoring travel

Text.

# Methods {.appendix}

## Simulator

Engine details.

## Run ledger

The [ledger](assets/run-ledger.md).
"#;

fn build(body: &str) -> anyhow::Result<String> {
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    write(dir, "report.md", &report(body));
    write(dir, "refs.bib", BIB);
    spctr::doc::build(&repo_root(), dir, Target::Lab, None)?;
    Ok(fs::read_to_string(dir.join("report.html")).unwrap())
}

#[test]
fn numbers_sections_appendix_and_citations() {
    let html = build(BODY).unwrap();
    assert!(html.contains("<title>Arrest after release | Specter Labs</title>"));
    assert!(!html.contains(r#"<meta name="description""#));
    assert!(html.contains(r#"<span class="rk-num">1</span>The arrest"#));
    assert!(html.contains(r#"<span class="rk-num">1.1</span>Lobe directions"#));
    assert!(html.contains(r#"<span class="rk-num">1.1</span><span>Lobe directions</span>"#));
    assert!(html.contains(r#"<span class="rk-num">2</span>Restoring travel"#));
    assert!(html.contains(r#"<span class="rk-num">A.1</span>Simulator"#));
    assert!(html.contains(r#"<span class="rk-num">A.2</span>Run ledger"#));
    assert!(html.contains(r##"<a href="#ref-levin2025" role="doc-biblioref">[1]</a>"##));
    assert!(html.contains("Report · revision 3 · 1 min read"));
    assert!(html.contains("<em>arrested</em>"));
    assert!(!html.contains("<script"));
    assert!(html.contains("data:font/woff2;base64,"));
    assert!(html.contains(r#"<img src="assets/pair.png""#));
}

#[test]
fn footnotes_become_margin_notes_and_endnotes() {
    let html = build(BODY).unwrap();
    assert!(
        html.contains(r##"<sup class="rk-noteref" id="noteref-1"><a href="#note-1">1</a></sup>"##)
    );
    assert!(html.contains(r#"<span class="rk-sidenote" aria-hidden="true"><span class="rk-sidenote-num">1</span> The lobes decouple.</span>"#));
    assert!(html.contains(r#"<li id="note-1">The lobes decouple."#));
    assert!(!html.contains("footnotes"));
}

#[test]
fn endmatter_lists_cite_references_notes_and_data_in_order() {
    let html = build(BODY).unwrap();
    let positions: Vec<usize> = [
        r#"<section id="cite-this">"#,
        r#"<section id="references">"#,
        r#"<section id="notes">"#,
        r#"<section id="data">"#,
    ]
    .iter()
    .map(|marker| {
        html.find(marker)
            .unwrap_or_else(|| panic!("missing {marker}"))
    })
    .collect();
    assert!(positions.windows(2).all(|pair| pair[0] < pair[1]));
    assert!(html.contains("@techreport{specter-RPT-001-3,"));
    assert!(html.contains("https://example.org/mind-everywhere"));
    let data = &html[positions[3]..];
    assert!(data.contains(r#"<a href="assets/arrest.json">arrest receipt</a> <span class="rk-path">arrest.json</span>"#));
    assert!(data.contains(r#"<a href="assets/trace.csv">trace</a>"#));
    assert!(data.contains(r#"<a href="assets/run-ledger.md">ledger</a>"#));
}

#[test]
fn refuses_external_links_in_body() {
    let body = "# One\n\nSee [the paper](https://example.org/paper) and <a href=\"http://example.com/x\">x</a>.\n";
    let error = format!("{:#}", build(body).unwrap_err());
    assert!(error.contains("external links in the body"), "{error}");
    assert!(error.contains("https://example.org/paper"), "{error}");
    assert!(error.contains("http://example.com/x"), "{error}");
}

fn build_with_terms(terms: &str, body: &str) -> anyhow::Result<String> {
    let source = report(body).replacen(
        "bibliography: refs.bib\n",
        &format!("bibliography: refs.bib\nterms:\n{terms}"),
        1,
    );
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    write(dir, "report.md", &source);
    write(dir, "refs.bib", BIB);
    write(dir, "assets/strip.png", "png");
    spctr::doc::build(&repo_root(), dir, Target::Lab, None)?;
    Ok(fs::read_to_string(dir.join("report.html")).unwrap())
}

const TERMS: &str = "  b7f3:
    note: A gliding pair from the *September* cohort.
    image: assets/strip.png
    caption: Four steps on a log scale.
  arrest:
    note: The centre of mass stops moving.
";

#[test]
fn terms_become_css_notes_with_optional_strips() {
    let html = build_with_terms(
        TERMS,
        "# One\n\nThe pair [B7F3]{term=b7f3} shows [arrest]{term=arrest}.\n",
    )
    .unwrap();
    assert!(html.contains(r#"<span class="rk-term" tabindex="0">B7F3<span class="rk-term-note" role="tooltip"><img src="assets/strip.png" alt=""><span class="rk-term-caption">Four steps on a log scale.</span>A gliding pair from the <em>September</em> cohort.</span></span>"#), "{html}");
    assert!(html.contains(r#"<span class="rk-term" tabindex="0">arrest<span class="rk-term-note" role="tooltip">The centre of mass stops moving.</span></span>"#));
    assert!(!html.contains("term=") && !html.contains("data-term"));
    assert!(html.contains(".rk-term:hover>.rk-term-note"));
    assert!(!html.contains("<script"));
}

#[test]
fn terms_work_in_footnotes_and_the_abstract() {
    let terms = "  arrest:\n    note: The centre of mass stops moving.\n";
    let source = report("# One\n\nText.[^n]\n\n[^n]: An [arrest]{term=arrest} again.\n")
        .replace("the pair *arrested*", "the pair [arrested]{term=arrest}");
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    write(
        dir,
        "report.md",
        &source.replacen(
            "bibliography: refs.bib\n",
            &format!("bibliography: refs.bib\nterms:\n{terms}"),
            1,
        ),
    );
    write(dir, "refs.bib", BIB);
    spctr::doc::build(&repo_root(), dir, Target::Lab, None).unwrap();
    let html = fs::read_to_string(dir.join("report.html")).unwrap();
    let abstract_start = html.find(r#"<section class="rk-abstract""#).unwrap();
    assert!(html[abstract_start..].contains(r#"<span class="rk-term" tabindex="0">arrested"#));
    assert!(html.contains(r#"<li id="note-1">An <span class="rk-term" tabindex="0">arrest"#));
}

fn term_error(terms: &str, body: &str) -> String {
    format!("{:#}", build_with_terms(terms, body).unwrap_err())
}

#[test]
fn unknown_term_is_an_error() {
    let error = term_error(
        TERMS,
        "# One\n\n[B7F3]{term=b7f3} [arrest]{term=arrest} [x]{term=missing}\n",
    );
    assert!(error.contains("unknown term 'missing'"), "{error}");
}

#[test]
fn unused_term_is_an_error() {
    let error = term_error(TERMS, "# One\n\n[B7F3]{term=b7f3}\n");
    assert!(
        error.contains("terms defined but never used: arrest"),
        "{error}"
    );
}

#[test]
fn nested_term_is_an_error() {
    let error = term_error(
        TERMS,
        "# One\n\n[[arrest]{term=arrest} of B7F3]{term=b7f3}\n",
    );
    assert!(
        error.contains("'arrest' is nested inside term 'b7f3'"),
        "{error}"
    );
}

#[test]
fn term_in_heading_is_an_error() {
    let error = term_error(TERMS, "# The [arrest]{term=arrest}\n\n[B7F3]{term=b7f3}\n");
    assert!(
        error.contains("terms are not allowed in headings"),
        "{error}"
    );
}

#[test]
fn malformed_glossary_entries_are_errors() {
    let missing = term_error(
        "  b7f3:\n    note: A pair.\n    image: assets/absent.png\n    caption: Strip.\n",
        "# One\n\n[B7F3]{term=b7f3}\n",
    );
    assert!(
        missing.contains("image is missing: assets/absent.png"),
        "{missing}"
    );
    let uncaptioned = term_error(
        "  b7f3:\n    note: A pair.\n    image: assets/strip.png\n",
        "# One\n\n[B7F3]{term=b7f3}\n",
    );
    assert!(
        uncaptioned.contains("needs both image and caption"),
        "{uncaptioned}"
    );
    let unknown_field = term_error(
        "  b7f3:\n    note: A pair.\n    text: Old field.\n",
        "# One\n\n[B7F3]{term=b7f3}\n",
    );
    assert!(
        unknown_field.contains("unknown field 'text'"),
        "{unknown_field}"
    );
    let no_note = term_error(
        "  b7f3:\n    caption: Strip.\n",
        "# One\n\n[B7F3]{term=b7f3}\n",
    );
    assert!(no_note.contains("'b7f3' needs a note"), "{no_note}");
}

const PUBLISHED: &str = r#"{
  "rpt-001": {"revision": "003", "path": "/dossiers/lenia-swarm/arrest/"},
  "rpt-002": {"revision": "005", "path": "/dossiers/lenia-swarm/siblings/"}
}"#;

struct Site {
    _temp: tempfile::TempDir,
    root: Utf8PathBuf,
    report: Utf8PathBuf,
}

/// A repository root that shares the real templates, fonts and design tokens
/// but has its own site/publications.json and site output.
fn site(publications: &str) -> Site {
    let temp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(temp.path()).unwrap().to_owned();
    let real = repo_root();
    fs::create_dir_all(root.join("site")).unwrap();
    fs::create_dir_all(root.join("addenda")).unwrap();
    for rel in ["site/templates", "site/fonts", "addenda/design-tokens"] {
        std::os::unix::fs::symlink(real.join(rel), root.join(rel)).unwrap();
    }
    write(&root, "site/publications.json", publications);
    let report = root.join("source");
    copy_dir(&fixture(), &report);
    Site {
        _temp: temp,
        root,
        report,
    }
}

fn fixture() -> Utf8PathBuf {
    Utf8Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/report")
}

fn copy_dir(from: &Utf8Path, to: &Utf8Path) {
    fs::create_dir_all(to).unwrap();
    for entry in fs::read_dir(from).unwrap() {
        let entry = entry.unwrap();
        let path = Utf8PathBuf::from_path_buf(entry.path()).unwrap();
        let target = to.join(path.file_name().unwrap());
        if path.is_dir() {
            copy_dir(&path, &target);
        } else {
            fs::copy(&path, &target).unwrap();
        }
    }
}

fn edit_report(site: &Site, from: &str, to: &str) {
    let path = site.report.join("report.md");
    let text = fs::read_to_string(&path).unwrap();
    assert!(text.contains(from), "fixture lacks {from:?}");
    fs::write(&path, text.replacen(from, to, 1)).unwrap();
}

fn site_error(site: &Site) -> String {
    format!(
        "{:#}",
        spctr::doc::build(&site.root, &site.report, Target::Site, None).unwrap_err()
    )
}

#[test]
fn fixture_renders_for_the_lab() {
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    copy_dir(&fixture(), dir);
    let out = spctr::doc::build(&repo_root(), dir, Target::Lab, None).unwrap();
    assert_eq!(out, dir.join("report.html"));
    let html = fs::read_to_string(out).unwrap();
    assert!(html.contains(
        r#"<a href="https://lab.specterlab.org/#/p/rpt-002?revision=005&amp;section=siblings">companion report</a>"#
    ));
    assert!(html.contains("data:font/woff2;base64,"));
    assert!(html.contains(r#"<span class="rk-term" tabindex="0">B7F3"#));
    assert!(!html.contains("publication-header\""));
    assert!(!html.contains(r#"<meta name="description""#));
    assert!(!html.contains("og:image"));
    assert!(!html.contains("<script"));
}

#[test]
fn fixture_renders_for_the_site() {
    let site = site(PUBLISHED);
    let out = spctr::doc::build(&site.root, &site.report, Target::Site, None).unwrap();
    let page_dir = site.root.join("site/dossiers/lenia-swarm/arrest");
    assert_eq!(out, page_dir.join("index.html"));
    let html = fs::read_to_string(&out).unwrap();
    assert!(html.contains("<title>Arrest after release | Specter Labs</title>"));
    assert!(html.contains(r#"<meta name="description" content="A temporary obstacle leaves a gliding pair arrested after release.">"#));
    assert!(html.contains(
        r#"<meta property="og:image" content="/dossiers/lenia-swarm/arrest/assets/pair.png">"#
    ));
    assert!(html.contains(r#"<header class="publication-header">"#));
    assert!(html.contains(r#"<footer class="publication-footer">"#));
    assert!(
        html.contains(r#"<a href="/dossiers/lenia-swarm/siblings/#siblings">companion report</a>"#)
    );
    assert!(html.contains("https://specterlab.org/dossiers/lenia-swarm/arrest/"));
    assert!(html.contains("src:url(/fonts/IBMPlexSerif-Regular.woff2)"));
    assert!(!html.contains("data:font/woff2"));
    assert!(!html.contains("specterlab.org/#/p/"));
    assert!(!html.contains("lab.specterlab.org"));
    assert!(!html.contains("<script"));
    assert!(!html.contains(r#"rel="canonical""#));
    for asset in ["pair.png", "strip.png", "arrest.json"] {
        assert!(
            page_dir.join("assets").join(asset).is_file(),
            "{asset} not copied"
        );
    }
    assert_eq!(fs::read_dir(page_dir.join("assets")).unwrap().count(), 3);

    let report = spctr::site::finalize::finalize_site(
        &site.root.join("site"),
        Utf8Path::new("fonts"),
        "https://specterlab.org",
    )
    .unwrap();
    assert_eq!(
        report.canonical_urls,
        vec!["https://specterlab.org/dossiers/lenia-swarm/arrest/".to_owned()]
    );
    let finalized = fs::read_to_string(&out).unwrap();
    assert_eq!(finalized.matches(r#"rel="canonical""#).count(), 1);
    assert!(finalized.contains(r#"<meta property="og:description" content="A temporary obstacle"#));
}

#[test]
fn site_refuses_unpublished_or_stale_documents() {
    let unpublished = site(r#"{"rpt-002": {"revision": "005", "path": "/blog/siblings/"}}"#);
    let error = site_error(&unpublished);
    assert!(error.contains("rpt-001 is not published"), "{error}");

    let stale = site(&PUBLISHED.replace(r#""revision": "003""#, r#""revision": "002""#));
    let error = site_error(&stale);
    assert!(
        error.contains("published at revision 002, but report.md is revision 003"),
        "{error}"
    );
}

#[test]
fn site_refuses_review_links_it_cannot_resolve() {
    let unpublished =
        site(r#"{"rpt-001": {"revision": "003", "path": "/dossiers/lenia-swarm/arrest/"}}"#);
    let error = site_error(&unpublished);
    assert!(error.contains("rpt-002 is not published"), "{error}");

    let stale = site(&PUBLISHED.replace(r#""revision": "005""#, r#""revision": "006""#));
    let error = site_error(&stale);
    assert!(
        error.contains("cites revision 005, but rpt-002 is published at revision 006"),
        "{error}"
    );

    let malformed = site(PUBLISHED);
    edit_report(
        &malformed,
        "revision=005&section=siblings",
        "section=siblings",
    );
    let error = site_error(&malformed);
    assert!(
        error.contains("review links must name a revision"),
        "{error}"
    );

    let page = site(PUBLISHED);
    edit_report(
        &page,
        "/#/p/rpt-002?revision=005&section=siblings",
        "/reports/rpt-002/",
    );
    let error = site_error(&page);
    assert!(error.contains("review links must have the form"), "{error}");

    let legacy = site(PUBLISHED);
    edit_report(
        &legacy,
        "https://lab.specterlab.org/#/p/rpt-002",
        "https://review.specterlab.org/#/p/rpt-002",
    );
    let out = spctr::doc::build(&legacy.root, &legacy.report, Target::Site, None).unwrap();
    assert!(fs::read_to_string(out)
        .unwrap()
        .contains(r#"href="/dossiers/lenia-swarm/siblings/#siblings""#));
}

#[test]
fn site_refuses_review_host_mentions_and_scripts() {
    let mention = site(PUBLISHED);
    edit_report(
        &mention,
        "Engine details.",
        "Reviewed on lab.specterlab.org.",
    );
    let error = site_error(&mention);
    assert!(
        error.contains("still mentions the review host lab.specterlab.org"),
        "{error}"
    );

    let script = site(PUBLISHED);
    edit_report(&script, "Engine details.", "<script>alert(1)</script>");
    let error = site_error(&script);
    assert!(error.contains("site page carries a script"), "{error}");
}

#[test]
fn site_refuses_private_paths() {
    for path in [
        "/dossiers/lenia-swarm/causal-emergence/",
        "/dossiers/lenia-swarm/causal-emergence/reports/x/",
        "/home-prototype/",
    ] {
        let private = site(&PUBLISHED.replace("/dossiers/lenia-swarm/arrest/", path));
        let error = site_error(&private);
        assert!(error.contains("stays private"), "{path}: {error}");
        assert!(!private
            .root
            .join("site")
            .join(path.trim_start_matches('/'))
            .exists());
    }
    let escaping = site(&PUBLISHED.replace(
        "/dossiers/lenia-swarm/arrest/",
        "/dossiers/../home-prototype/",
    ));
    assert!(site_error(&escaping).contains("site path must look like"));
}

#[test]
fn site_needs_description_image_and_no_out() {
    let no_description = site(PUBLISHED);
    edit_report(
        &no_description,
        "description: A temporary obstacle leaves a gliding pair arrested after release.\n",
        "",
    );
    assert!(site_error(&no_description).contains("description"));

    let numeric_revision = site(PUBLISHED);
    edit_report(&numeric_revision, r#"revision: "003""#, "revision: 3");
    assert!(site_error(&numeric_revision).contains("string fields"));

    let with_out = site(PUBLISHED);
    let error = format!(
        "{:#}",
        spctr::doc::build(
            &with_out.root,
            &with_out.report,
            Target::Site,
            Some(Utf8Path::new("x.html"))
        )
        .unwrap_err()
    );
    assert!(error.contains("drop --out"), "{error}");
}
