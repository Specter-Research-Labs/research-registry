use camino::{Utf8Path, Utf8PathBuf};
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
    spctr::doc::build(&repo_root(), dir, None)?;
    Ok(fs::read_to_string(dir.join("report.html")).unwrap())
}

#[test]
fn numbers_sections_appendix_and_citations() {
    let html = build(BODY).unwrap();
    assert!(html.contains("<title>Arrest after release | Specter Labs</title>"));
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
