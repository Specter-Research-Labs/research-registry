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
kind: report
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
    spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None)?;
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
    assert!(!html.contains(r#"rel="preload""#));
    assert!(html.contains(r#"<img src="assets/pair.png""#));
}

#[test]
fn kind_names_the_document_in_byline_and_citation() {
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    write(dir, "refs.bib", BIB);
    write(dir, "report.md", &report(BODY).replacen("kind: report", "kind: proposal", 1));
    spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None).unwrap();
    let html = fs::read_to_string(dir.join("report.html")).unwrap();
    assert!(html.contains("Proposal · revision 3 · 1 min read"));
    assert!(html.contains("<h2>Cite this proposal</h2>"));
    assert!(html.contains("Specter Labs proposal, revision 3."));
    assert!(!html.contains("Cite this report"));

    for (front, message) in [
        ("", "missing metadata field 'kind'"),
        ("kind: memo\n", "kind must be report, proposal or synthesis, found 'memo'"),
    ] {
        write(dir, "report.md", &report(BODY).replacen("kind: report\n", front, 1));
        let error = spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None).unwrap_err();
        assert!(format!("{error:#}").contains(message), "{error:#}");
    }
}

#[test]
fn footnotes_become_margin_notes_and_endnotes() {
    let html = build(BODY).unwrap();
    assert!(html.contains(r##"<sup class="rk-noteref" id="noteref-1"><a href="#note-1">1</a><span class="rk-pop" role="tooltip"><span class="rk-num">1</span> The lobes decouple.</span></sup>"##));
    assert!(html.contains(r#"<span class="rk-sidenote" aria-hidden="true"><span class="rk-sidenote-body"><span class="rk-sidenote-num">1</span> The lobes decouple.</span></span>"#));
    assert!(html.contains(r#"<li id="note-1">The lobes decouple."#));
    assert!(!html.contains("footnotes"));
}

#[test]
fn citations_carry_their_reference_entry() {
    let html = build(BODY).unwrap();
    let cite = html
        .split(r#"<span class="rk-cite">"#)
        .nth(1)
        .expect("citation wrapper");
    let pop = cite
        .split(r#"<span class="rk-pop" role="tooltip">"#)
        .nth(1)
        .expect("citation preview");
    assert!(pop.starts_with(r#"<span class="rk-pop-entry"><span class="rk-num">[1]</span>"#));
    assert!(pop.contains("Mind everywhere"));
}

#[test]
fn citation_without_a_reference_entry_is_an_error() {
    let err = build("# A\n\nText [@missing2025].\n").unwrap_err();
    assert!(format!("{err:#}").contains("missing2025"), "{err:#}");
}

#[test]
fn contents_track_the_current_section_without_scripts() {
    let html = build(BODY).unwrap();
    assert!(html.contains(".rk-layout{timeline-scope:--rk-toc,--rk-s1,--rk-s2,--rk-s3,--rk-s4}"));
    assert!(html.contains("section.rk-s1{view-timeline-name:--rk-s1}"));
    assert!(html.contains(".rk-t1{animation-timeline:--rk-s1}"));
    assert!(html.contains(r#"<div class="rk-tocbar"><details><summary>"#));
    assert!(html.contains(r#"<section id="the-arrest" class="level2 rk-s1">"#));
    assert!(!html.contains("<script"));
}

fn build_with_hero(hero: &str, files: &[&str]) -> anyhow::Result<String> {
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    let source = report("# The arrest\n\nText.\n").replacen(
        "bibliography: refs.bib\n",
        &format!("bibliography: refs.bib\nhero:\n{hero}"),
        1,
    );
    write(dir, "report.md", &source);
    write(dir, "refs.bib", BIB);
    for file in files {
        write(dir, file, "x");
    }
    spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None)?;
    Ok(fs::read_to_string(dir.join("report.html")).unwrap())
}

#[test]
fn hero_renders_between_subtitle_and_byline() {
    let html = build_with_hero(
        "  image: assets/hero.png\n  caption: The pair *before* release.\n",
        &["assets/hero.png"],
    )
    .unwrap();
    let hero = html
        .find(r#"<figure class="rk-hero-figure"><img src="assets/hero.png" alt="">"#)
        .expect("hero");
    assert!(html.contains("<figcaption>The pair <em>before</em> release.</figcaption>"));
    assert!(html.find("Why a freed pair stays put").unwrap() < hero);
    assert!(hero < html.find("Ada Example").unwrap());
    let video = build_with_hero(
        "  image: assets/hero.mp4\n  caption: Release.\n",
        &["assets/hero.mp4"],
    )
    .unwrap();
    assert!(video.contains(r#"<video src="assets/hero.mp4" autoplay muted loop playsinline>"#));
    assert!(!build(BODY).unwrap().contains(r#"class="rk-hero-figure""#));
}

#[test]
fn malformed_hero_is_an_error() {
    for (hero, files, expected) in [
        (
            "  image: assets/hero.png\n",
            &["assets/hero.png"][..],
            "caption",
        ),
        ("  caption: Release.\n", &[][..], "image"),
        (
            "  image: assets/gone.png\n  caption: Release.\n",
            &[][..],
            "assets/gone.png",
        ),
        (
            "  image: hero.png\n  caption: Release.\n",
            &["hero.png"][..],
            "assets/",
        ),
        (
            "  image: assets/hero.gif\n  caption: Release.\n",
            &["assets/hero.gif"][..],
            "gif",
        ),
        (
            "  image: assets/hero.png\n  caption: Release.\n  alt: x\n",
            &["assets/hero.png"][..],
            "alt",
        ),
    ] {
        let err = build_with_hero(hero, files).unwrap_err();
        assert!(format!("{err:#}").contains(expected), "{hero}: {err:#}");
    }
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
    spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None)?;
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
    spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None).unwrap();
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
    siblings: Utf8PathBuf,
}

/// A repository root that shares the real templates, fonts and design tokens
/// but has its own site/publications.json and site output.
fn site(publications: &str) -> Site {
    let temp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(temp.path()).unwrap().to_owned();
    let real = repo_root();
    fs::create_dir_all(root.join("site/assets")).unwrap();
    fs::create_dir_all(root.join("addenda")).unwrap();
    for rel in [
        "site/templates",
        "site/fonts",
        "site/assets/site-shell.css",
        "addenda/design-tokens",
    ] {
        std::os::unix::fs::symlink(real.join(rel), root.join(rel)).unwrap();
    }
    write(&root, "site/publications.json", publications);
    let report = root.join("source");
    copy_dir(&fixture("report"), &report);
    let siblings = root.join("siblings");
    copy_dir(&fixture("siblings"), &siblings);
    Site {
        _temp: temp,
        root,
        report,
        siblings,
    }
}

fn fixture(name: &str) -> Utf8PathBuf {
    Utf8Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
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
    edit(&site.report, from, to);
}

fn edit(dir: &Utf8Path, from: &str, to: &str) {
    let path = dir.join("report.md");
    let text = fs::read_to_string(&path).unwrap();
    assert!(text.contains(from), "fixture lacks {from:?}");
    fs::write(&path, text.replacen(from, to, 1)).unwrap();
}

fn site_build(site: &Site, dirs: &[&Utf8PathBuf]) -> anyhow::Result<Vec<Utf8PathBuf>> {
    let dirs: Vec<Utf8PathBuf> = dirs.iter().map(|dir| (*dir).clone()).collect();
    spctr::doc::build(&site.root, &dirs, Target::Site, None)
}

/// Builds the fixture together with the companion report it links to.
fn site_error(site: &Site) -> String {
    format!(
        "{:#}",
        site_build(site, &[&site.report, &site.siblings]).unwrap_err()
    )
}

#[test]
fn fixture_renders_for_the_lab() {
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    copy_dir(&fixture("report"), dir);
    let out = spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None).unwrap();
    assert_eq!(out, vec![dir.join("report.html")]);
    let out = &out[0];
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
    let out = site_build(&site, &[&site.report, &site.siblings]).unwrap();
    let page_dir = site.root.join("site/dossiers/lenia-swarm/arrest");
    assert_eq!(
        out,
        vec![
            page_dir.join("index.html"),
            site.root
                .join("site/dossiers/lenia-swarm/siblings/index.html")
        ]
    );
    let out = &out[0];
    let html = fs::read_to_string(out).unwrap();
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
    assert!(html.contains(r#"<link rel="preload" href="/fonts/IBMPlexSerif-Medium.woff2" as="font" type="font/woff2" crossorigin>"#));
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
        vec![
            "https://specterlab.org/dossiers/lenia-swarm/arrest/".to_owned(),
            "https://specterlab.org/dossiers/lenia-swarm/siblings/".to_owned()
        ]
    );
    let finalized = fs::read_to_string(out).unwrap();
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
    let error = format!(
        "{:#}",
        site_build(&unpublished, &[&unpublished.report]).unwrap_err()
    );
    assert!(error.contains("rpt-002 is not published"), "{error}");

    let stale = site(&PUBLISHED.replace(r#""revision": "005""#, r#""revision": "006""#));
    let error = format!("{:#}", site_build(&stale, &[&stale.report]).unwrap_err());
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
    let out = site_build(&legacy, &[&legacy.report, &legacy.siblings]).unwrap();
    assert!(fs::read_to_string(&out[0])
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
            std::slice::from_ref(&with_out.report),
            Target::Site,
            Some(Utf8Path::new("x.html"))
        )
        .unwrap_err()
    );
    assert!(error.contains("drop --out"), "{error}");
}

#[test]
fn review_links_must_name_an_existing_section() {
    let published = site(PUBLISHED);
    site_build(&published, &[&published.siblings]).unwrap();
    let out = site_build(&published, &[&published.report]).unwrap();
    assert!(fs::read_to_string(&out[0])
        .unwrap()
        .contains(r#"href="/dossiers/lenia-swarm/siblings/#siblings""#));

    let missing_section = site(PUBLISHED);
    edit_report(&missing_section, "section=siblings", "section=cousins");
    let error = site_error(&missing_section);
    assert!(error.contains("rpt-002 has no section cousins"), "{error}");
    assert!(!missing_section
        .root
        .join("site/dossiers/lenia-swarm/siblings")
        .exists());

    let unbuilt = site(PUBLISHED);
    let error = format!(
        "{:#}",
        site_build(&unbuilt, &[&unbuilt.report]).unwrap_err()
    );
    assert!(
        error.contains("rpt-002 has no page at")
            && error.contains("build it first or in the same batch"),
        "{error}"
    );
}

#[test]
fn documents_that_link_to_each_other_build_as_one_batch() {
    let cycle = site(PUBLISHED);
    edit(
        &cycle.siblings,
        "Siblings respond alike.",
        "Siblings respond alike, as [the arrested pair](https://lab.specterlab.org/#/p/rpt-001?revision=003&section=the-arrest) does.",
    );
    let error = format!("{:#}", site_build(&cycle, &[&cycle.siblings]).unwrap_err());
    assert!(error.contains("rpt-001 has no page at"), "{error}");
    let out = site_build(&cycle, &[&cycle.report, &cycle.siblings]).unwrap();
    assert!(fs::read_to_string(&out[1])
        .unwrap()
        .contains(r#"href="/dossiers/lenia-swarm/arrest/#the-arrest""#));

    let twice = site(PUBLISHED);
    let error = format!(
        "{:#}",
        site_build(&twice, &[&twice.report, &twice.siblings, &twice.report]).unwrap_err()
    );
    assert!(error.contains("rpt-001 is in the batch twice"), "{error}");
}

#[test]
fn site_refuses_to_leave_files_it_did_not_write() {
    let nested = PUBLISHED.replace(
        "/dossiers/lenia-swarm/siblings/",
        "/dossiers/lenia-swarm/arrest/siblings/",
    );
    let site = site(&nested);
    site_build(&site, &[&site.report, &site.siblings]).unwrap();
    site_build(&site, &[&site.report, &site.siblings]).unwrap();

    let page_dir = site.root.join("site/dossiers/lenia-swarm/arrest");
    write(&page_dir, "old.html", "old");
    write(&page_dir, "assets/old.png", "old");
    let before = fs::read_to_string(page_dir.join("index.html")).unwrap();
    edit_report(&site, "Engine details.", "Engine details, revised.");
    let error = site_error(&site);
    assert!(
        error.contains("holds files this build would not write")
            && error.contains("\n  assets/old.png\n  old.html"),
        "{error}"
    );
    assert!(page_dir.join("old.html").is_file());
    assert_eq!(
        fs::read_to_string(page_dir.join("index.html")).unwrap(),
        before
    );
}

#[test]
fn each_document_has_one_public_url() {
    let shared = site(&PUBLISHED.replace(
        "/dossiers/lenia-swarm/siblings/",
        "/dossiers/lenia-swarm/arrest/",
    ));
    let error = site_error(&shared);
    assert!(
        error.contains("rpt-001 and rpt-002 are both published at /dossiers/lenia-swarm/arrest/"),
        "{error}"
    );

    let experiments = site(&PUBLISHED.replace(
        "/dossiers/lenia-swarm/arrest/",
        "/experiments/exp-001/rpt-001/",
    ));
    let error = site_error(&experiments);
    assert!(error.contains("which the review app serves"), "{error}");
}

#[test]
fn site_copies_a_narrow_picture_source() {
    let site = site(PUBLISHED);
    write(&site.report, "assets/pair-narrow.png", "narrow");
    edit_report(
        &site,
        r#"<img src="assets/pair.png" alt="The pair at release">"#,
        r#"<picture><source media="(max-width: 640px)" srcset="assets/pair-narrow.png"><img src="assets/pair.png" alt="The pair at release"></picture>"#,
    );
    site_build(&site, &[&site.report, &site.siblings]).unwrap();
    let page_dir = site.root.join("site/dossiers/lenia-swarm/arrest");
    let html = fs::read_to_string(page_dir.join("index.html")).unwrap();
    assert!(
        html.contains(r#"srcset="assets/pair-narrow.png""#),
        "{html}"
    );
    assert!(page_dir.join("assets/pair-narrow.png").is_file());
}

#[test]
fn site_refuses_srcset_with_several_candidates() {
    let site = site(PUBLISHED);
    edit_report(
        &site,
        r#"<img src="assets/pair.png" alt="The pair at release">"#,
        r#"<img src="assets/pair.png" srcset="assets/pair.png 1x, assets/pair.png 2x" alt="The pair at release">"#,
    );
    let error = site_error(&site);
    assert!(
        error.contains("srcset must name one file under assets/"),
        "{error}"
    );
}

const MAP: &str = r#"::: {#map data-widget="route-map" data-src="assets/map.json" data-defaults='{"network":"a","budget":4,"breakLink":false}'}
<figure><form>
<label><input id="network-a" name="network" type="radio" value="a" checked> A</label>
<label><input id="network-b" name="network" type="radio" value="b"> B</label>
<input id="budget" name="budget" type="range" min="1" max="6" value="4">
<input id="break-link" name="breakLink" type="checkbox">
</form><figcaption>Routes.</figcaption></figure>
:::"#;

fn build_layout(front: &str, body: &str) -> anyhow::Result<String> {
    let temp = tempfile::tempdir().unwrap();
    let dir = Utf8Path::from_path(temp.path()).unwrap();
    let source = report(body).replacen(
        "bibliography: refs.bib\n",
        &format!("bibliography: refs.bib\n{front}"),
        1,
    );
    write(dir, "report.md", &source);
    write(dir, "refs.bib", BIB);
    write(dir, "assets/map.json", r#"{"nodes":[]}"#);
    spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None)?;
    Ok(fs::read_to_string(dir.join("report.html")).unwrap())
}

fn explorer(body: &str) -> anyhow::Result<String> {
    build_layout("layout: explorer\n", body)
}

fn layout_error(front: &str, body: &str) -> String {
    format!("{:#}", build_layout(front, body).unwrap_err())
}

#[test]
fn layout_defaults_to_essay_and_rejects_unknown_values() {
    let essay = build_layout("layout: essay\n", BODY).unwrap();
    assert_eq!(essay, build(BODY).unwrap());
    assert!(!essay.contains("<script"));
    assert!(!essay.contains("rk-explorer"));
    assert!(layout_error("layout: magazine\n", BODY)
        .contains(r#"layout must be essay or explorer, found "magazine""#));
}

#[test]
fn explorer_embeds_the_widget_library_once() {
    let html = explorer(&format!("# Routes\n\n{MAP}\n\n# Next\n\nText.\n")).unwrap();
    assert!(html.contains(r#"<body class="rk-explorer">"#));
    assert_eq!(html.matches("<script").count(), 1);
    assert!(html.contains(r#"<script type="module">"#));
    assert!(html.contains("IntersectionObserver"));
    assert!(html.contains(".rk-hub"));
    assert!(html.contains(r#"class="rk-widget""#));
    assert!(html.contains(r#"data-src="data:application/json;base64,"#));
}

#[test]
fn explorer_hub_links_chapters_and_marks_interactive_ones() {
    let html = explorer(&format!(
        "# Routes\n\n{MAP}\n\n# Next\n\nText.\n\n# Methods {{.appendix}}\n\nDetails.\n"
    ))
    .unwrap();
    let hub = html
        .split(r#"<nav class="rk-hub" aria-label="Chapters">"#)
        .nth(1)
        .expect("hub")
        .split("</nav>")
        .next()
        .unwrap();
    assert!(hub.contains(r##"<a href="#routes"><span class="rk-num">1</span><span class="rk-hub-title">Routes</span><span class="rk-hub-tag">Interactive</span></a>"##));
    assert!(hub.contains(r##"<a href="#next"><span class="rk-num">2</span><span class="rk-hub-title">Next</span></a>"##));
    assert!(!hub.contains("Methods"));
}

#[test]
fn explorer_makes_subtitle_optional() {
    let body = "# A\n\nText.\n";
    let no_subtitle = |front: &str| {
        let temp = tempfile::tempdir().unwrap();
        let dir = Utf8Path::from_path(temp.path()).unwrap();
        let source = report(body)
            .replacen("subtitle: Why a freed pair stays put\n", "", 1)
            .replacen(
                "bibliography: refs.bib\n",
                &format!("bibliography: refs.bib\n{front}"),
                1,
            );
        write(dir, "report.md", &source);
        write(dir, "refs.bib", BIB);
        spctr::doc::build(&repo_root(), &[dir.to_owned()], Target::Lab, None).map(|_| ())
    };
    no_subtitle("layout: explorer\n").unwrap();
    let err = format!("{:#}", no_subtitle("").unwrap_err());
    assert!(err.contains("subtitle"), "{err}");
}

#[test]
fn hero_can_hold_a_widget_on_explorer_pages() {
    let html = build_layout(
        "layout: explorer\nhero:\n  widget: map\n",
        &format!("{MAP}\n\n# Routes\n\nText.\n"),
    )
    .unwrap();
    let hero = html
        .find(r#"<div class="rk-hero-widget"><div id="map" class="rk-widget""#)
        .expect("hero widget");
    let byline = html.find(r#"<p class="rk-byline">Ada Example"#).unwrap();
    let abstract_start = html.find(r#"<section class="rk-abstract""#).unwrap();
    assert!(byline < abstract_start && abstract_start < hero);
    assert!(hero < html.find(r#"<main class="rk-article">"#).unwrap());
    assert_eq!(html.matches(r#"<section class="rk-abstract""#).count(), 1);
    assert_eq!(html.matches(r#"id="map""#).count(), 1);
    assert!(!html.contains(r#"<span class="rk-hub-tag">"#));
}

#[test]
fn malformed_widget_hero_is_an_error() {
    let at_top = format!("{MAP}\n\n# Routes\n\nText.\n");
    for (front, body, expected) in [
        (
            "hero:\n  widget: map\n",
            at_top.as_str(),
            "widget blocks need layout: explorer",
        ),
        (
            "layout: explorer\nhero:\n  widget: gone\n",
            at_top.as_str(),
            "hero widget 'gone' is not a top-level block",
        ),
        (
            "layout: explorer\nhero:\n  widget: map\n  caption: x\n",
            at_top.as_str(),
            "a widget hero takes no 'caption'",
        ),
        (
            "layout: explorer\nhero:\n  widget: plain\n",
            "::: {#plain}\nText.\n:::\n\n# A\n\nB.\n",
            "hero widget 'plain' is not a widget block",
        ),
    ] {
        let err = layout_error(front, body);
        assert!(err.contains(expected), "{front}: {err}");
    }
}

#[test]
fn malformed_widget_blocks_are_errors() {
    let in_chapter = |block: &str| format!("# Routes\n\n{block}\n");
    for (block, expected) in [
        (MAP.replace("route-map", "orbit"), "unknown widget 'orbit'"),
        (MAP.replace("#map ", ""), "route-map widget needs an id"),
        (
            MAP.replace("assets/map.json", "assets/gone.json"),
            "data file is missing: assets/gone.json",
        ),
        (
            MAP.replace("assets/map.json", "../map.json"),
            "data-src must name a .json file under assets/",
        ),
        (
            MAP.replace(r#"'{"network""#, r#"'["network""#)
                .replace("false}'", "false]'"),
            "data-defaults must be a JSON object",
        ),
        (
            MAP.replace(r#"id="budget" "#, ""),
            "every control needs an id",
        ),
        (
            MAP.replace(r#""budget":4,"#, ""),
            "control 'budget' has no default",
        ),
        (
            MAP.replace(r#""budget":4"#, r#""budget":4,"speed":2"#),
            "default 'speed' has no control",
        ),
        (
            MAP.replace(r#""budget":4"#, r#""budget":5"#),
            "control 'budget' starts at 4, but data-defaults says 5",
        ),
        (
            MAP.replace(
                r#"data-widget="route-map""#,
                r#"data-widget="route-map" data-mode="x""#,
            ),
            "unknown attribute 'data-mode'",
        ),
        (
            r#"<figure data-widget="route-map" data-src="assets/map.json"></figure>"#.to_string(),
            "declare widgets as fenced divs, not raw HTML",
        ),
    ] {
        let err = format!("{:#}", explorer(&in_chapter(&block)).unwrap_err());
        assert!(err.contains(expected), "{expected}: {err}");
    }
    let essay = format!("{:#}", build(&in_chapter(MAP)).unwrap_err());
    assert!(
        essay.contains("widget blocks need layout: explorer"),
        "{essay}"
    );
}

#[test]
fn site_allows_only_the_widget_library_on_explorer_pages() {
    let page = site(PUBLISHED);
    edit_report(
        &page,
        "bibliography: refs.bib\n",
        "bibliography: refs.bib\nlayout: explorer\n",
    );
    edit_report(
        &page,
        "Engine details.",
        &format!("Engine details.\n\n{MAP}"),
    );
    write(&page.report, "assets/map.json", r#"{"nodes":[]}"#);
    let out = site_build(&page, &[&page.report, &page.siblings]).unwrap();
    let html = fs::read_to_string(&out[0]).unwrap();
    assert_eq!(html.matches("<script").count(), 1);
    assert!(html.contains(r#"data-src="assets/map.json""#));
    assert!(out[0].parent().unwrap().join("assets/map.json").exists());

    let extra = site(PUBLISHED);
    edit_report(
        &extra,
        "bibliography: refs.bib\n",
        "bibliography: refs.bib\nlayout: explorer\n",
    );
    edit_report(&extra, "Engine details.", "<script>alert(1)</script>");
    let error = site_error(&extra);
    assert!(
        error.contains("site page carries a script other than the widget library"),
        "{error}"
    );
}
