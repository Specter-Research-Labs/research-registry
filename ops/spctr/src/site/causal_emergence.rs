use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use chrono::NaiveDate;
use maud::{html, Markup};
use serde::Deserialize;
use std::collections::HashSet;
use std::fs;

use super::discover::SitePageRecord;

pub(crate) const CATALOG_PATH: &str = "site/dossiers/lenia-swarm/causal-emergence/catalog.json";
const RELEASE_ROUTE: &str = "https://releases.specterlab.org/lenia-swarm/causal-emergence/releases";

pub const LANDING_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/index.html";
pub const LIBRARY_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/library/index.html";
pub const ARCHIVE_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/archive/index.html";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalog {
    pub(crate) schema_version: u32,
    pub(crate) reports: Vec<Report>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Report {
    pub(crate) id: String,
    pub(crate) title: String,
    pub(crate) date: String,
    pub(crate) dek: String,
    pub(crate) question: String,
    pub(crate) answer: String,
    pub(crate) next_question: String,
    pub(crate) category: String,
    pub(crate) status: String,
    pub(crate) evidence_class: String,
    pub(crate) featured: bool,
    pub(crate) archive: bool,
    pub(crate) supersedes: Vec<String>,
    pub(crate) sha256: String,
    pub(crate) release_id: String,
}

/// Loads the public causal-emergence catalog when the dossier publishes one.
///
/// # Errors
///
/// Returns an error when the catalog cannot be read, parsed, or validated.
pub fn load_catalog(repo_root: &Utf8Path) -> Result<Option<Catalog>> {
    let path = repo_root.join(CATALOG_PATH);
    if !path.is_file() {
        return Ok(None);
    }
    let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
    let catalog: Catalog =
        serde_json::from_str(&text).with_context(|| format!("failed to parse {path}"))?;
    validate_catalog(&catalog).with_context(|| format!("invalid {CATALOG_PATH}"))?;
    Ok(Some(catalog))
}

pub(crate) fn validate_catalog(catalog: &Catalog) -> Result<()> {
    if catalog.schema_version != 1 {
        bail!("schema_version must be 1, got {}", catalog.schema_version);
    }
    if catalog.reports.is_empty() {
        bail!("reports must contain at least one entry");
    }

    let mut ids = HashSet::new();
    let mut release_ids = HashSet::new();
    for (index, report) in catalog.reports.iter().enumerate() {
        let label = format!("reports[{index}]");
        for (field, value) in [
            ("id", report.id.as_str()),
            ("title", report.title.as_str()),
            ("date", report.date.as_str()),
            ("dek", report.dek.as_str()),
            ("question", report.question.as_str()),
            ("answer", report.answer.as_str()),
            ("next_question", report.next_question.as_str()),
            ("category", report.category.as_str()),
            ("status", report.status.as_str()),
            ("evidence_class", report.evidence_class.as_str()),
            ("sha256", report.sha256.as_str()),
            ("release_id", report.release_id.as_str()),
        ] {
            if value.trim().is_empty() {
                bail!("{label}.{field} must not be empty");
            }
            reject_internal_path(&label, field, value)?;
        }
        for field in [
            ("title", report.title.as_str()),
            ("dek", report.dek.as_str()),
            ("question", report.question.as_str()),
            ("answer", report.answer.as_str()),
            ("next_question", report.next_question.as_str()),
        ] {
            reject_prose_anti_patterns(&label, field.0, field.1)?;
        }
        for superseded in &report.supersedes {
            if superseded.trim().is_empty() {
                bail!("{label}.supersedes must not contain an empty id");
            }
            reject_internal_path(&label, "supersedes", superseded)?;
            if !is_safe_segment(superseded) {
                bail!("{label}.supersedes contains an unsafe id '{superseded}'");
            }
        }
        if !is_safe_segment(&report.id) {
            bail!("{label}.id must be a lowercase public URL segment");
        }
        if !is_safe_segment(&report.category) {
            bail!("{label}.category must be a lowercase public URL segment");
        }
        if !is_safe_segment(&report.release_id) {
            bail!("{label}.release_id must be a lowercase public URL segment");
        }
        if NaiveDate::parse_from_str(&report.date, "%Y-%m-%d").is_err() {
            bail!("{label}.date must use YYYY-MM-DD");
        }
        if report.sha256.len() != 64
            || !report
                .sha256
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        {
            bail!("{label}.sha256 must be 64 lowercase hexadecimal characters");
        }
        if !matches!(report.status.as_str(), "feature" | "library" | "archive") {
            bail!("{label}.status must be feature, library, or archive");
        }
        if report.featured != (report.status == "feature") {
            bail!("{label}.featured must be true exactly when status is feature");
        }
        if report.archive != (report.status == "archive") {
            bail!("{label}.archive must be true exactly when status is archive");
        }
        if report.supersedes.iter().any(|id| id == &report.id) {
            bail!("{label}.supersedes must not contain its own id");
        }
        let mut supersedes = HashSet::new();
        if report
            .supersedes
            .iter()
            .any(|superseded| !supersedes.insert(superseded))
        {
            bail!("{label}.supersedes must not contain duplicate ids");
        }
        if !ids.insert(report.id.as_str()) {
            bail!("duplicate report id '{}'", report.id);
        }
        if !release_ids.insert(report.release_id.as_str()) {
            bail!("duplicate release_id '{}'", report.release_id);
        }
    }

    if !catalog.reports.iter().any(|report| report.featured) {
        bail!("catalog must contain at least one featured report");
    }
    Ok(())
}

fn is_safe_segment(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.first().is_some_and(u8::is_ascii_alphanumeric)
        && bytes.last().is_some_and(u8::is_ascii_alphanumeric)
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || *byte == b'-')
}

fn reject_internal_path(label: &str, field: &str, value: &str) -> Result<()> {
    let lower = value.to_ascii_lowercase();
    let looks_internal = lower.contains(".codex")
        || lower.contains("file://")
        || lower.contains("/users/")
        || lower.contains("/home/")
        || lower.contains("\\users\\")
        || value.trim_start().starts_with('/')
        || value.as_bytes().windows(3).any(|window| {
            window[0].is_ascii_alphabetic() && window[1] == b':' && window[2] == b'\\'
        });
    if looks_internal {
        bail!("{label}.{field} contains an internal or absolute path");
    }
    Ok(())
}

fn reject_prose_anti_patterns(label: &str, field: &str, value: &str) -> Result<()> {
    let lower = value.to_ascii_lowercase();
    for phrase in [
        "carried the claim",
        "what emerged instead",
        "productive failure",
        "research programme",
        "research program",
    ] {
        if lower.contains(phrase) {
            bail!("{label}.{field} contains rejected public prose phrase '{phrase}'");
        }
    }
    Ok(())
}

#[must_use]
pub fn sitemap_pages() -> Vec<SitePageRecord> {
    vec![
        SitePageRecord {
            title: "Causal Emergence in Flow Lenia".into(),
            href: "dossiers/lenia-swarm/causal-emergence/".into(),
        },
        SitePageRecord {
            title: "Flow Lenia Causal Emergence Report Library".into(),
            href: "dossiers/lenia-swarm/causal-emergence/library/".into(),
        },
        SitePageRecord {
            title: "Flow Lenia Causal Emergence Archive".into(),
            href: "dossiers/lenia-swarm/causal-emergence/archive/".into(),
        },
    ]
}

fn release_href(report: &Report) -> String {
    format!("{RELEASE_ROUTE}/{}/", report.release_id)
}

fn report_href(report: &Report) -> String {
    release_href(report)
}

fn exact_report_href(report: &Report) -> String {
    format!("{}report.html", release_href(report))
}

#[must_use]
pub fn render_page_title(title: &str) -> String {
    html! { title { (title) " | SPECTER Labs" } }.into_string()
}

#[must_use]
pub fn render_page_meta(title: &str, description: &str, canonical_path: &str) -> String {
    let canonical = format!("https://specterlab.org{canonical_path}");
    html! {
        meta name="description" content=(description);
        meta property="og:type" content="website";
        meta property="og:site_name" content="SPECTER Labs";
        meta property="og:title" content=(title);
        meta property="og:description" content=(description);
        meta property="og:url" content=(&canonical);
        link rel="canonical" href=(&canonical);
    }
    .into_string()
}

fn category_label(category: &str) -> String {
    let words = category.replace('-', " ");
    let mut chars = words.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().collect::<String>() + chars.as_str(),
        None => words,
    }
}

fn report_links(report: &Report) -> Markup {
    html! {
        div class="ce-report-links" {
            a class="ce-button ce-button-primary" href=(report_href(report)) { "Read report" }
            a class="ce-button" href=(exact_report_href(report)) { "Report HTML" }
        }
    }
}

fn report_receipt(report: &Report) -> Markup {
    html! {
        details class="ce-receipt" {
            summary { "Evidence receipt" }
            dl {
                div {
                    dt { "Report date" }
                    dd { time datetime=(&report.date) { (&report.date) } }
                }
                div {
                    dt { "Evidence" }
                    dd { (&report.evidence_class) }
                }
                div {
                    dt { "Release" }
                    dd { code { (&report.release_id) } }
                }
                div {
                    dt { "Sealed source SHA-256" }
                    dd { code { (&report.sha256[..12]) "..." } }
                }
                @if !report.supersedes.is_empty() {
                    div {
                        dt { "Supersedes" }
                        dd { (report.supersedes.join(", ")) }
                    }
                }
            }
        }
    }
}

fn question_triptych(report: &Report) -> Markup {
    html! {
        div class="ce-question-grid" {
            div class="ce-question-cell" {
                div class="ce-question-label" { "We were asking" }
                p { (&report.question) }
            }
            div class="ce-question-cell ce-answer-cell" {
                div class="ce-question-label" { "This experiment found" }
                p { (&report.answer) }
            }
            div class="ce-question-cell" {
                div class="ce-question-label" { "That sent us to" }
                p { (&report.next_question) }
            }
        }
    }
}

fn report_card(report: &Report) -> Markup {
    html! {
        article class="ce-report-card" id=(report.id) {
            h3 { a href=(report_href(report)) { (&report.title) } }
            p class="ce-dek" { (&report.dek) }
            (question_triptych(report))
            div class="ce-card-footer" {
                (report_links(report))
                (report_receipt(report))
            }
        }
    }
}

fn page_nav(current: &str) -> Markup {
    html! {
        nav class="ce-section-nav" aria-label="Causal emergence pages" {
            a href="/dossiers/lenia-swarm/causal-emergence/" aria-current=[(current == "overview").then_some("page")] { "Overview" }
            a href="/dossiers/lenia-swarm/causal-emergence/library/" aria-current=[(current == "library").then_some("page")] { "Report library" }
            a href="/dossiers/lenia-swarm/causal-emergence/archive/" aria-current=[(current == "archive").then_some("page")] { "Archive" }
        }
    }
}

fn grouped_reports<'a>(reports: &'a [&'a Report]) -> Vec<(&'a str, Vec<&'a Report>)> {
    let mut groups: Vec<(&str, Vec<&Report>)> = Vec::new();
    for report in reports {
        if let Some((_, entries)) = groups
            .iter_mut()
            .find(|(category, _)| *category == report.category)
        {
            entries.push(*report);
        } else {
            groups.push((&report.category, vec![*report]));
        }
    }
    groups
}

#[must_use]
pub fn render_landing(catalog: &Catalog) -> String {
    let featured: Vec<&Report> = catalog
        .reports
        .iter()
        .filter(|report| report.featured)
        .collect();
    let lead = featured[0];
    let remaining = &featured[1..];

    html! {
        (page_nav("overview"))
        header class="ce-hero" {
            div class="ce-kicker" { "Flow Lenia / causal emergence" }
            h1 { "When does a developing system begin to become itself?" }
            p class="ce-hero-dek" {
                "Flow Lenia begins here as a seeded field that is still reorganizing; over hundreds of updates, some fields settle into persistent, organic-looking bodies, while others fragment or take another route through shape space. We disturbed that process at different moments and measured how the available futures changed, because the first signs of an organism may appear in what a state can still become before they are obvious in its shape."
            }
        }

        section class="ce-lead-report" aria-labelledby="ce-lead-title" {
            div class="ce-section-heading" {
                div class="ce-kicker" { "Begin with the synthesis" }
                h2 id="ce-lead-title" { a href=(report_href(lead)) { (&lead.title) } }
                p class="ce-dek" { (&lead.dek) }
            }
            (question_triptych(lead))
            div class="ce-card-footer" {
                (report_links(lead))
                (report_receipt(lead))
            }
        }

        @if !remaining.is_empty() {
            section class="ce-report-section" aria-labelledby="featured-experiments" {
                div class="ce-section-heading" {
                    div class="ce-kicker" { "Follow the experiments" }
                    h2 id="featured-experiments" { "The experiments that opened the next questions" }
                    p { "These are the strongest places to enter after the synthesis, kept in editorial order so that each answer leads naturally into the question that followed it." }
                }
                div class="ce-card-grid" {
                    @for report in remaining {
                        (report_card(report))
                    }
                }
            }
        }

        aside class="ce-library-invite" {
            div {
                div class="ce-kicker" { "The complete record" }
                h2 { "Go deeper into the experimental record" }
                p { "The library keeps every current report in the order in which its question belongs, while the archive retains pilots and superseded syntheses without asking a new reader to mistake them for the present account." }
            }
            div class="ce-report-links" {
                a class="ce-button ce-button-primary" href="/dossiers/lenia-swarm/causal-emergence/library/" { "Browse the library" }
                a class="ce-button" href="/dossiers/lenia-swarm/causal-emergence/archive/" { "Open the archive" }
            }
        }
    }
    .into_string()
}

#[must_use]
pub fn render_library(catalog: &Catalog) -> String {
    let reports: Vec<&Report> = catalog
        .reports
        .iter()
        .filter(|report| !report.archive)
        .collect();
    let groups = grouped_reports(&reports);

    html! {
        (page_nav("library"))
        header class="ce-page-header" {
            div class="ce-kicker" { "Current reports / " (reports.len()) }
            h1 { "Report library" }
            p { "Each report begins with the question we could actually test, says what happened in that experiment, and leaves the next question visible; together they show how the work moved from early steering to commitment, hidden state, developmental history, and the changing possibilities of the body." }
        }
        nav class="ce-category-nav" aria-label="Report categories" {
            @for (category, entries) in &groups {
                a href=(format!("#{category}")) { (category_label(category)) " " span { (entries.len()) } }
            }
        }
        @for (category, entries) in &groups {
            section class="ce-report-section" aria-labelledby=(format!("{category}-heading")) {
                div class="ce-section-heading ce-section-heading-row" {
                    div {
                        div class="ce-kicker" { "Chapter" }
                        h2 id=(format!("{category}-heading")) { (category_label(category)) }
                    }
                    div class="ce-count" { (entries.len()) " reports" }
                }
                div class="ce-card-grid" id=(*category) {
                    @for report in entries {
                        (report_card(report))
                    }
                }
            }
        }
    }
    .into_string()
}

#[must_use]
pub fn render_archive(catalog: &Catalog) -> String {
    let reports: Vec<&Report> = catalog
        .reports
        .iter()
        .filter(|report| report.archive)
        .collect();
    let groups = grouped_reports(&reports);

    html! {
        (page_nav("archive"))
        header class="ce-page-header" {
            div class="ce-kicker" { "Experimental record / " (reports.len()) }
            h1 { "Archive" }
            p { "These pilots and earlier syntheses are no longer the shortest route into the work, although they still show which questions were tried, where an apparent pattern weakened, and why the next experiment took the shape it did." }
        }
        @if reports.is_empty() {
            p class="ce-empty" { "No reports are currently archived." }
        }
        @for (category, entries) in &groups {
            section class="ce-report-section" aria-labelledby=(format!("archive-{category}-heading")) {
                div class="ce-section-heading ce-section-heading-row" {
                    div {
                        div class="ce-kicker" { "Archive chapter" }
                        h2 id=(format!("archive-{category}-heading")) { (category_label(category)) }
                    }
                    div class="ce-count" { (entries.len()) " reports" }
                }
                div class="ce-card-grid" id=(format!("archive-{category}")) {
                    @for report in entries {
                        (report_card(report))
                    }
                }
            }
        }
    }
    .into_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_catalog_json() -> String {
        serde_json::json!({
            "schema_version": 1,
            "reports": [{
                "id": "organism-appears-first",
                "title": "The organism appears first in possibility space",
                "date": "2026-08-30",
                "dek": "A synthesis of the developmental experiments.",
                "question": "When does a seeded field begin to constrain its own futures?",
                "answer": "The response repertoire narrowed before morphology settled.",
                "next_question": "Which hidden variables preserve that developmental history?",
                "category": "synthesis",
                "status": "feature",
                "evidence_class": "multi-cohort synthesis",
                "featured": true,
                "archive": false,
                "supersedes": [],
                "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "release_id": "flce-organism-appears-first-aaaaaaaaaaaa"
            }]
        })
        .to_string()
    }

    #[test]
    fn valid_catalog_renders_all_three_surfaces() {
        let catalog: Catalog = serde_json::from_str(&valid_catalog_json()).unwrap();
        validate_catalog(&catalog).unwrap();

        let landing = render_landing(&catalog);
        let library = render_library(&catalog);
        let archive = render_archive(&catalog);
        assert!(landing.contains("Begin with the synthesis"));
        assert!(landing.contains("organism-appears-first"));
        assert!(!landing.contains("ce-chip"));
        assert!(!landing.contains("ce-report-meta"));
        assert!(landing.contains("Report date"));
        assert!(landing.contains("2026-08-30"));
        assert!(library.contains("This experiment found"));
        assert!(!library.contains("ce-chip"));
        assert!(archive.contains("No reports are currently archived"));
    }

    #[test]
    fn duplicate_ids_are_rejected() {
        let mut value: serde_json::Value = serde_json::from_str(&valid_catalog_json()).unwrap();
        let duplicate = value["reports"][0].clone();
        value["reports"].as_array_mut().unwrap().push(duplicate);
        let catalog: Catalog = serde_json::from_value(value).unwrap();
        let error = validate_catalog(&catalog).unwrap_err().to_string();
        assert!(error.contains("duplicate report id"));
    }

    #[test]
    fn internal_paths_are_rejected() {
        let mut value: serde_json::Value = serde_json::from_str(&valid_catalog_json()).unwrap();
        value["reports"][0]["dek"] = serde_json::Value::String(
            "The report lives in file:///Users/example/.codex/report.html".into(),
        );
        let catalog: Catalog = serde_json::from_value(value).unwrap();
        let error = validate_catalog(&catalog).unwrap_err().to_string();
        assert!(error.contains("internal or absolute path"));
    }

    #[test]
    fn rejected_public_prose_is_rejected() {
        let mut value: serde_json::Value = serde_json::from_str(&valid_catalog_json()).unwrap();
        value["reports"][0]["dek"] =
            serde_json::Value::String("What emerged instead was a productive failure.".into());
        let catalog: Catalog = serde_json::from_value(value).unwrap();
        let error = validate_catalog(&catalog).unwrap_err().to_string();
        assert!(error.contains("rejected public prose phrase"));
    }
}
