use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use chrono::NaiveDate;
use maud::{html, Markup};
use serde::Deserialize;
use std::collections::HashSet;
use std::fs;

use super::discover::SitePageRecord;

pub(crate) const CATALOG_PATH: &str = "site/dossiers/lenia-swarm/causal-emergence/catalog.json";
const RELEASE_ROUTE: &str = "/dossiers/lenia-swarm/causal-emergence/reports";

pub const LANDING_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/index.html";
pub const REPORTS_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/reports/index.html";
pub const LIBRARY_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/library/index.html";
pub const ARCHIVE_OUTPUT: &str = "site/dossiers/lenia-swarm/causal-emergence/archive/index.html";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalog {
    pub(crate) schema_version: u32,
    pub(crate) categories: Vec<Category>,
    pub(crate) reports: Vec<Report>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Category {
    pub(crate) id: String,
    pub(crate) label: String,
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

    let mut categories = HashSet::new();
    for (index, category) in catalog.categories.iter().enumerate() {
        if !is_safe_segment(&category.id) {
            bail!("categories[{index}].id must be a lowercase public URL segment");
        }
        if category.label.trim().is_empty() {
            bail!("categories[{index}].label must not be empty");
        }
        reject_prose_anti_patterns(&format!("categories[{index}]"), "label", &category.label)?;
        if !categories.insert(category.id.as_str()) {
            bail!("duplicate category id '{}'", category.id);
        }
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
            ("evidence_class", report.evidence_class.as_str()),
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
        if !categories.contains(report.category.as_str()) {
            bail!("{label}.category has no display label");
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
    if contains_internal_checkpoint_notation(value) {
        bail!("{label}.{field} contains internal checkpoint notation; write 'passage N' instead");
    }
    let lower = value.to_ascii_lowercase();
    for phrase in [
        "carried the claim",
        "what emerged instead",
        "productive failure",
        "research programme",
        "research program",
        "sealed",
        "mega report",
        "public edition",
        "public projection",
        "exact predecessor",
        "source-bound",
        "superseded",
    ] {
        if lower.contains(phrase) {
            bail!("{label}.{field} contains rejected public prose phrase '{phrase}'");
        }
    }
    Ok(())
}

fn contains_internal_checkpoint_notation(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.iter().enumerate().any(|(index, byte)| {
        matches!(byte, b'q' | b'Q')
            && bytes.get(index + 1).is_some_and(u8::is_ascii_digit)
            && (index == 0 || !bytes[index - 1].is_ascii_alphanumeric())
    })
}

#[must_use]
pub fn sitemap_pages(catalog: &Catalog) -> Vec<SitePageRecord> {
    let mut pages = vec![
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
    ];
    pages.extend(catalog.reports.iter().map(|report| SitePageRecord {
        title: report.title.clone(),
        href: format!(
            "dossiers/lenia-swarm/causal-emergence/reports/{}/",
            report.id
        ),
    }));
    pages.extend(reading_structure().articles.into_iter().map(|article| SitePageRecord {
        title: article.title,
        href: format!("dossiers/lenia-swarm/causal-emergence/articles/{}/",article.id),
    }));
    pages
}

fn release_href(report: &Report) -> String {
    format!("{RELEASE_ROUTE}/{}/", report.id)
}

fn report_href(report: &Report) -> String {
    release_href(report)
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

fn page_nav(current: &str) -> Markup {
    html! {
        nav class="ce-section-nav" aria-label="Causal emergence pages" {
            a href="/dossiers/lenia-swarm/causal-emergence/" aria-current=[(current == "overview").then_some("page")] { "Overview" }
            a href="/dossiers/lenia-swarm/causal-emergence/library/" aria-current=[(current == "library").then_some("page")] { "Report library" }
            a href="/dossiers/lenia-swarm/causal-emergence/archive/" aria-current=[(current == "archive").then_some("page")] { "Archive" }
        }
    }
}

#[derive(Deserialize)]
pub(crate) struct ReadingArticle {
    pub id: String,
    pub title: String,
    pub dek: String,
    pub reports: Vec<String>,
}
#[derive(Deserialize)]
struct ReadingStructure {
    articles: Vec<ReadingArticle>,
    #[serde(default, rename = "draft_articles")]
    _draft_articles: Vec<ReadingArticle>,
    historical_syntheses: Vec<String>,
}
fn reading_structure() -> ReadingStructure {
    serde_json::from_str(include_str!("../../../../site/dossiers/lenia-swarm/causal-emergence/reading-structure.json"))
        .expect("the authored reading structure must be valid JSON")
}
pub(crate) fn record_reading_context(id: &str, date: &str) -> String {
    let structure = reading_structure();
    let article = structure.articles.iter().find(|a| a.reports.iter().any(|r| r == id));
    html! {
        aside class="ce-record-context" data-reading-context="v1" style="max-width:76rem;margin:1.5rem auto;padding:1rem 1.5rem;border-block:1px solid #999;font:16px/1.5 Georgia,serif" {
            @if let Some(article) = article {
                "Experimental record · " (date) ". "
                a href=(format!("/dossiers/lenia-swarm/causal-emergence/articles/{}/",article.id)) { "Read the consolidated article: " (&article.title) }
            } @else {
                "Historical experimental record · " (date) ". "
                a href="/dossiers/lenia-swarm/causal-emergence/" { "Read the current synthesis and three research questions" }
            }
        }
    }.into_string()
}

fn article_index() -> Markup {
    html! {
        section class="ce-reading-list" aria-label="Three research questions" {
            @for article in reading_structure().articles {
                article class="ce-report-card" {
                    h2 { a href=(format!("/dossiers/lenia-swarm/causal-emergence/articles/{}/", article.id)) { (article.title) } }
                    p { (article.dek) }
                }
            }
        }
    }
}
#[must_use]
pub fn render_landing(_catalog: &Catalog) -> String {
    html! {
        (page_nav("overview"))
        header class="ce-hero" {
            div class="ce-kicker" { "Current synthesis" }
            h1 { "What must we know about a body to change it?" }
        }
        (maud::PreEscaped(include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/research-reading.html")))
        (article_index())
        p { a href="/dossiers/lenia-swarm/causal-emergence/archive/" { "Search the experimental record" } }
    }.into_string()
}
#[must_use]
pub fn render_library(_catalog: &Catalog) -> String {
    html! {
        (page_nav("library"))
        header class="ce-page-header" {
            h1 { "Three questions about a developing body" }
            p { "These articles bring successive experiments together around the questions they answer. Each follows the result through its controls, limitations, and next discriminating test." }
            p { a href="/dossiers/lenia-swarm/causal-emergence/" { "Read the short synthesis" } }
        }
        (article_index())
        p { "The " a href="/dossiers/lenia-swarm/causal-emergence/archive/" { "experimental record" } " retains all 81 reports and earlier syntheses. Their presence records the investigation; it does not endorse every historical interpretation." }
    }.into_string()
}
pub(crate) fn article_pages(catalog: &Catalog) -> Vec<(String, String, String, String, String)> {
    reading_structure().articles.into_iter().map(|article| {
        let body = match article.id.as_str() {
            "developmental-sensitivity" => include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/article-developmental-sensitivity.html"),
            "hidden-composition" => include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/article-hidden-composition.html"),
            "organization-prediction-control" => include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/article-organization-prediction-control.html"),
            _ => unreachable!("unknown article"),
        };
        let route = format!("/dossiers/lenia-swarm/causal-emergence/articles/{}/",article.id);
        let content = html! {
            (page_nav("library"))
            header class="ce-page-header" { h1 { (&article.title) } p { (&article.dek) } }
            article class="ce-research-reading" { (maud::PreEscaped(body)) }
            details class="ce-reading-list" {
                summary { "Supporting experimental records" }
                p { "These records preserve the investigation, including exploratory and unresolved results. The article specifies which comparisons support its argument." }
                ul {
                    @for id in &article.reports {
                        @if let Some(report) = catalog.reports.iter().find(|r| &r.id == id) {
                            li { a href=(report_href(report)) { (&report.title) } }
                        }
                    }
                }
                @if article.id == "developmental-sensitivity" || article.id == "organization-prediction-control" {
                    p { "Later dose controls and the corrected controller comparison are preserved in " a href="/dossiers/lenia-swarm/causal-emergence/reports/synthesis-v7/" { "the detailed campaign synthesis" } "." }
                }
            }
            p { a href="/dossiers/lenia-swarm/causal-emergence/reports/" { "Return to the three questions" } }
        }.into_string();
        (format!("site{}index.html",route),article.title,article.dek,route,content)
    }).collect()
}

#[must_use]
pub fn render_archive(catalog: &Catalog) -> String {
    let structure = reading_structure();
    html! {
        (page_nav("archive"))
        header class="ce-page-header" {
            h1 { "Experimental record" }
            p { "All " (catalog.reports.len()) " reports, grouped by the question they contribute to. Earlier syntheses retain the account at the time; start with the current articles for the revised interpretation." }
            label for="record-search" { "Find a report" }
            input id="record-search" type="search" placeholder="Search titles and questions";
            p id="record-count" role="status" { (catalog.reports.len()) " records" }
        }
        @for (title, ids) in structure.articles.iter().map(|a| (a.title.as_str(), &a.reports)).chain(std::iter::once(("Earlier guides and syntheses", &structure.historical_syntheses))) {
            section class="ce-record-group" {
                h2 { (title) }
                ul {
                    @for id in ids {
                        @if let Some(report) = catalog.reports.iter().find(|r| &r.id == id) {
                            li class="ce-record" data-search=(format!("{} {} {}",report.title,report.question,report.id).to_lowercase()) {
                                a href=(report_href(report)) { (&report.title) }
                                p { (&report.question) }
                            }
                        }
                    }
                }
            }
        }
        script { (maud::PreEscaped(r#"document.getElementById('record-search').addEventListener('input',function(){const q=this.value.toLowerCase().trim();let count=0;document.querySelectorAll('.ce-record').forEach(row=>{row.hidden=!row.dataset.search.includes(q);if(!row.hidden)count++});document.querySelectorAll('.ce-record-group').forEach(group=>{group.hidden=![...group.querySelectorAll('.ce-record')].some(row=>!row.hidden)});document.getElementById('record-count').textContent=count+' records';});"#)) }
    }.into_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_catalog_json() -> String {
        serde_json::json!({
            "schema_version": 1,
            "categories": [{"id": "synthesis", "label": "Synthesis"}],
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
        assert!(landing.contains("Current synthesis"));
        assert!(landing.contains("What must we know about a body"));
        assert!(library.contains("Three questions about a developing body"));
        assert_eq!(library.matches("class=\"ce-report-card\"").count(), 3);
        assert!(archive.contains("Experimental record"));
        assert!(archive.contains("record-search"));
    }

    #[test]
    fn reading_structure_assigns_every_report_once() {
        let catalog: Catalog = serde_json::from_str(include_str!("../../../../site/dossiers/lenia-swarm/causal-emergence/catalog.json")).unwrap();
        let structure = reading_structure();
        let ids: Vec<_> = structure.articles.iter().chain(structure._draft_articles.iter()).flat_map(|a| a.reports.iter()).chain(structure.historical_syntheses.iter()).collect();
        assert_eq!(ids.len(),catalog.reports.len());
        let unique: HashSet<_> = ids.iter().copied().collect();
        assert_eq!(unique.len(),ids.len());
        for report in &catalog.reports { assert!(unique.contains(&report.id)); }
        let pages = article_pages(&catalog);
        assert_eq!(pages.len(),3);
        assert!(!render_library(&catalog).contains("articles/history-and-response/"));
        assert!(pages.iter().all(|(route, _, _, _, _)| !route.contains("history-and-response")));
        for (_, _, _, _, html) in pages { assert!(html.contains("Supporting experimental records")); }
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

    #[test]
    fn internal_checkpoint_notation_is_rejected_in_public_prose() {
        let mut value: serde_json::Value = serde_json::from_str(&valid_catalog_json()).unwrap();
        value["reports"][0]["title"] =
            serde_json::Value::String("The response disappears by q48".into());
        let catalog: Catalog = serde_json::from_value(value).unwrap();
        let error = validate_catalog(&catalog).unwrap_err().to_string();
        assert!(error.contains("internal checkpoint notation"));
        assert!(error.contains("passage N"));
    }
}
