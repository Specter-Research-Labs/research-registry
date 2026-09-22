use std::collections::HashMap;
use std::fs;

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use maud::{html, DOCTYPE};
use regex_lite::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::causal_emergence::{self, Catalog, Report};

const RELEASE_SCHEMA: &str = "specter_flow_lenia_report_release_v3";
const BUNDLE_SCHEMA: &str = "specter_flow_lenia_report_library_bundle_v3";
const EDITORIAL_REPLACEMENTS_PATH: &str =
    "site/dossiers/lenia-swarm/causal-emergence/editorial-replacements.json";
const REPORT_POLISH_PATH: &str = "site/dossiers/lenia-swarm/causal-emergence/report-polish.css";
const REDACT_SOURCE_PREFIX: &str = "redact_internal_source_prefix_v1";
const NEUTRALIZE_LOCAL_LINKS: &str = "neutralize_unpublished_relative_links_v1";
const NORMALIZE_PUBLIC_EDITORIAL: &str = "normalize_public_editorial_language_v1";
const EXPAND_INTERNAL_CHECKPOINTS: &str = "expand_internal_checkpoint_notation_v1";
const NORMALIZE_MOBILE_WRAP: &str = "normalize_public_mobile_wrapping_v1";
const APPLY_REPORT_POLISH: &str = "apply_shared_report_polish_v1";
const PUBLIC_MOBILE_STYLE: &str = r#"<style data-public-projection="mobile-wrap">code,figcaption,.hash,.receipt{overflow-wrap:anywhere!important;word-break:break-word!important}@media(max-width:420px){.mechanism{grid-template-columns:minmax(0,1fr)!important;min-width:0!important}.mechanism>*{width:100%!important;max-width:100%!important;min-width:0!important;margin-inline:0!important}.outcome-matrix,.mapping{width:100%!important;min-width:0!important;max-width:100%!important;table-layout:fixed!important}.outcome-matrix th,.outcome-matrix td{padding-inline:.15rem!important;font-size:clamp(.55rem,2.5vw,.75rem)!important}.mapping th,.mapping td{overflow-wrap:anywhere!important;word-break:break-word!important}.status-bar{width:100%!important;min-width:0!important;max-width:100%!important;overflow-x:auto!important;flex-wrap:wrap!important}.status-bar>*{min-width:0!important;flex:1 1 5rem!important}.stat-grid{grid-template-columns:1fr!important}.zero-box{width:100%!important;max-width:100%!important;min-width:0!important}}</style>"#;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ReleaseReceipt<'a> {
    schema: &'static str,
    id: &'a str,
    release_id: &'a str,
    title: &'a str,
    date: &'a str,
    status: &'a str,
    evidence_class: &'a str,
    source_report_sha256: &'a str,
    public_report_sha256: String,
    transformations: Vec<&'static str>,
    context_sha256: String,
    catalog_sha256: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    upstream_receipt_sha256: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct BundleEntry<'a> {
    id: &'a str,
    release_id: &'a str,
    source_report_sha256: String,
    public_report_sha256: String,
    transformations: Vec<&'static str>,
    context_sha256: String,
    receipt_sha256: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct BundleManifest<'a> {
    schema: &'static str,
    catalog_sha256: &'a str,
    lead_release_id: &'a str,
    reports: Vec<BundleEntry<'a>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StageResult {
    pub output: String,
    pub catalog_sha256: String,
    pub lead_release_id: String,
    pub report_count: usize,
}

#[derive(Debug)]
struct PublicProjection {
    bytes: Vec<u8>,
    transformations: Vec<&'static str>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EditorialConfig {
    schema_version: u32,
    replacements: Vec<EditorialReplacement>,
    #[serde(default)]
    report_replacements: HashMap<String, Vec<EditorialReplacement>>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct EditorialReplacement {
    from: String,
    to: String,
}

pub fn stage_library(
    repo_root: &Utf8Path,
    input_root: &Utf8Path,
    output_root: &Utf8Path,
    only_id: Option<&str>,
) -> Result<StageResult> {
    if output_root.exists() {
        bail!("causal-emergence release output already exists: {output_root}");
    }
    if !input_root.is_dir() {
        bail!("causal-emergence report input root not found: {input_root}");
    }

    let catalog = causal_emergence::load_catalog(repo_root)?
        .ok_or_else(|| anyhow::anyhow!("causal-emergence catalog not found"))?;
    let editorial_config = load_editorial_config(repo_root)?;
    let report_polish = load_report_polish(repo_root)?;
    let selected = selected_reports(&catalog, only_id)?;
    let lead = catalog
        .reports
        .first()
        .ok_or_else(|| anyhow::anyhow!("causal-emergence catalog is empty"))?;
    let catalog_path = repo_root.join(causal_emergence::CATALOG_PATH);
    let catalog_sha256 = sha256_file(&catalog_path)?;
    // A previously projected library is a valid migration input only when its
    // manifest authenticates every report. Keep that receipt chain with the new page.
    let imported = input_root.join("manifest.json").is_file();
    let selected_sources = if imported {
        let manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(input_root.join("manifest.json"))?)?;
        selected
            .iter()
            .map(|report| {
                let entry = manifest["reports"]
                    .as_array()
                    .context("library manifest has no reports")?
                    .iter()
                    .find(|entry| entry["releaseId"] == report.release_id)
                    .with_context(|| format!("library manifest is missing {}", report.id))?;
                let source = match manifest["schema"].as_str() {
                    Some("specter_flow_lenia_report_library_bundle_v2") => input_root
                        .join("releases")
                        .join(&report.release_id)
                        .join("report.html"),
                    Some(BUNDLE_SCHEMA) => input_root
                        .join("reports")
                        .join(&report.id)
                        .join("index.html"),
                    _ => bail!("unsupported input library manifest schema"),
                };
                if entry["publicReportSha256"].as_str() != Some(sha256_file(&source)?.as_str()) {
                    bail!("public report hash mismatch: {}", report.id);
                }
                let receipt = source.parent().unwrap().join("release-receipt.json");
                if entry["receiptSha256"].as_str() != Some(sha256_file(&receipt)?.as_str()) {
                    bail!("upstream receipt hash mismatch: {}", report.id);
                }
                Ok((*report, source))
            })
            .collect::<Result<Vec<_>>>()?
    } else {
        let candidates = discover_html_by_sha(input_root)?;
        selected
            .iter()
            .map(|report| {
                unique_source(&candidates, report).map(|source| (*report, source.to_owned()))
            })
            .collect::<Result<Vec<_>>>()?
    };

    let releases_root = output_root.join("reports");
    fs::create_dir_all(&releases_root)
        .with_context(|| format!("failed to create {releases_root}"))?;

    let mut manifest_entries = Vec::with_capacity(selected.len());
    for (report, source) in selected_sources {
        let report_release_dir = releases_root.join(&report.id);
        fs::create_dir_all(&report_release_dir)
            .with_context(|| format!("failed to create {report_release_dir}"))?;

        let report_bytes = fs::read(&source).with_context(|| format!("failed to read {source}"))?;
        let mut public_report = if imported {
            let upstream = source.parent().unwrap().join("release-receipt.json");
            fs::copy(upstream, report_release_dir.join("upstream-receipt.json"))?;
            let mut html = String::from_utf8(report_bytes)?;
            if !html.contains("class=\"publication-header\"") {
                html = html.replace(
                    "<body>",
                    &format!(
                        "<body>{}",
                        include_str!("../../../../site/templates/publication-header.html")
                    ),
                );
            }
            if !html.contains("/assets/publication-layout.css") {
                html = html.replace("</head>", "<link rel=\"stylesheet\" href=\"/assets/publication-layout.css?v=20260914-logo\"></head>");
            }
            html = html
                .replace("href=\"index.html\"", "href=\"about.html\"")
                .replace("https://specterlab.org/", "/");
            html =
                Regex::new(r#"<a[^>]+href="https://releases\.specterlab\.org/cdn-cgi/[^>]+></a>"#)?
                    .replace_all(&html, "")
                    .into_owned();
            // Refresh the shared style when an already verified projection is imported.
            // Keep its authored figures and earlier projection layers intact.
            let polish = format!(
                "<style data-specter-public-polish>\n{}\n</style>",
                report_polish.trim()
            );
            let previous_polish = Regex::new(r"(?s)<style data-specter-public-polish>.*?</style>")?;
            if previous_polish.is_match(&html) {
                html = previous_polish
                    .replace_all(&html, regex_lite::NoExpand(&polish))
                    .into_owned();
            } else {
                html = html.replace("</head>", &format!("{polish}</head>"));
            }
            PublicProjection {
                bytes: html.into_bytes(),
                transformations: vec!["import_verified_public_projection_v1", APPLY_REPORT_POLISH],
            }
        } else {
            project_public_report(
                report,
                &report_bytes,
                &editorial_config.replacements,
                &report_polish,
            )?
        };
        let mut linked = String::from_utf8(public_report.bytes)?;
        for target in &catalog.reports {
            let old = format!(
                "https://releases.specterlab.org/lenia-swarm/causal-emergence/releases/{}/",
                target.release_id
            );
            let new = format!(
                "/dossiers/lenia-swarm/causal-emergence/reports/{}/",
                target.id
            );
            linked = linked
                .replace(&format!("{old}report.html"), &new)
                .replace(&old, &format!("{new}about.html"));
        }
        linked = Regex::new(r#"<link[^>]+rel="canonical"[^>]*>"#)?
            .replace_all(&linked, "")
            .into_owned();
        let canonical = format!(
            r#"<link rel="canonical" href="https://specterlab.org/dossiers/lenia-swarm/causal-emergence/reports/{}/">"#,
            report.id
        );
        if !linked.contains(&canonical) {
            linked = linked.replace("</head>", &format!("{canonical}</head>"));
        }
        if report.id == "synthesis-v7" {
            for (from, to) in [
                (">instrument</a>", ">How we measured</a>"),
                (">future</a>", ">Possible futures</a>"),
                (">closure</a>", ">Development</a>"),
                (">impedance</a>", ">The same push, later</a>"),
                (">control</a>", ">Steering</a>"),
                (">passport</a>", ">Recognizing a response</a>"),
                (">ledger</a>", ">Evidence</a>"),
            ] {
                linked = linked.replace(from, to);
            }
        }
        let (edited, changed) = normalize_public_editorial(&linked, &editorial_config.replacements);
        linked = edited;
        if changed {
            public_report
                .transformations
                .push(NORMALIZE_PUBLIC_EDITORIAL);
        }
        if report.id == "synthesis-v7" {
            linked = apply_synthesis_publication(&linked)?;
            public_report
                .transformations
                .push("synthesis_publication_instruments_v1");
        }
        if let Some(replacements) = editorial_config.report_replacements.get(&report.id) {
            let (edited, changed) = normalize_public_editorial(&linked, replacements);
            linked = edited;
            if changed && !public_report.transformations.contains(&NORMALIZE_PUBLIC_EDITORIAL) {
                public_report.transformations.push(NORMALIZE_PUBLIC_EDITORIAL);
            }
        }
        linked = linked
            .replace("<span>Earlier report · retained in the archive</span>", "")
            .replace("<span>Supporting experimental record</span>", "");
        if report.archive {
            linked = linked.replace("href=\"about.html\">About this report</a>", "href=\"about.html\">About this report</a><span>Supporting experimental record</span>");
        }
        public_report.bytes = linked.into_bytes();
        public_report
            .transformations
            .push("move_reports_to_website_v1");
        let public_report_sha256 = sha256_bytes(&public_report.bytes);
        let report_path = report_release_dir.join("index.html");
        fs::write(&report_path, &public_report.bytes)
            .with_context(|| format!("failed to write {report_path}"))?;

        let context = render_context(
            report,
            &public_report_sha256,
            &public_report.transformations,
        );
        let context_sha256 = sha256_bytes(context.as_bytes());
        let context_path = report_release_dir.join("about.html");
        fs::write(&context_path, context)
            .with_context(|| format!("failed to write {context_path}"))?;

        let input_sha256 = sha256_file(&source)?;
        let receipt = ReleaseReceipt {
            schema: RELEASE_SCHEMA,
            id: &report.id,
            release_id: &report.release_id,
            title: &report.title,
            date: &report.date,
            status: &report.status,
            evidence_class: &report.evidence_class,
            source_report_sha256: if imported {
                &input_sha256
            } else {
                &report.sha256
            },
            public_report_sha256: public_report_sha256.clone(),
            transformations: public_report.transformations.clone(),
            context_sha256: context_sha256.clone(),
            catalog_sha256: &catalog_sha256,
            upstream_receipt_sha256: if imported {
                Some(sha256_file(
                    &report_release_dir.join("upstream-receipt.json"),
                )?)
            } else {
                None
            },
        };
        let mut receipt_bytes = serde_json::to_vec_pretty(&receipt)?;
        receipt_bytes.push(b'\n');
        let receipt_sha256 = sha256_bytes(&receipt_bytes);
        let receipt_path = report_release_dir.join("release-receipt.json");
        fs::write(&receipt_path, receipt_bytes)
            .with_context(|| format!("failed to write {receipt_path}"))?;

        manifest_entries.push(BundleEntry {
            id: &report.id,
            release_id: &report.release_id,
            source_report_sha256: input_sha256,
            public_report_sha256,
            transformations: public_report.transformations,
            context_sha256,
            receipt_sha256,
        });
    }

    let manifest = BundleManifest {
        schema: BUNDLE_SCHEMA,
        catalog_sha256: &catalog_sha256,
        lead_release_id: &lead.release_id,
        reports: manifest_entries,
    };
    let manifest_path = output_root.join("manifest.json");
    let mut manifest_bytes = serde_json::to_vec_pretty(&manifest)?;
    manifest_bytes.push(b'\n');
    fs::write(&manifest_path, manifest_bytes)
        .with_context(|| format!("failed to write {manifest_path}"))?;

    Ok(StageResult {
        output: output_root.to_string(),
        catalog_sha256: catalog_sha256.clone(),
        lead_release_id: lead.release_id.clone(),
        report_count: manifest.reports.len(),
    })
}

pub fn validate_website_library(repo_root: &Utf8Path) -> Result<()> {
    let root = repo_root.join("site/dossiers/lenia-swarm/causal-emergence/reports");
    let catalog = causal_emergence::load_catalog(repo_root)?;
    let Some(catalog) = catalog else {
        return Ok(());
    };
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("manifest.json")).context(
            "website report library is missing; stage and install the report bundle first",
        )?)?;
    if manifest["schema"].as_str() != Some(BUNDLE_SCHEMA) {
        bail!("unsupported website report manifest schema");
    }
    let entries = manifest["reports"]
        .as_array()
        .context("website report manifest has no reports")?;
    for report in &catalog.reports {
        let entry = entries
            .iter()
            .find(|entry| entry["id"] == report.id)
            .with_context(|| format!("website report is missing from manifest: {}", report.id))?;
        for (file, field) in [
            ("index.html", "publicReportSha256"),
            ("about.html", "contextSha256"),
            ("release-receipt.json", "receiptSha256"),
        ] {
            let path = root.join(&report.id).join(file);
            if entry[field].as_str() != Some(sha256_file(&path)?.as_str()) {
                bail!("website report integrity check failed: {path}");
            }
        }
        let receipt: serde_json::Value = serde_json::from_slice(&fs::read(
            root.join(&report.id).join("release-receipt.json"),
        )?)?;
        if let Some(expected) = receipt["upstreamReceiptSha256"].as_str() {
            if sha256_file(&root.join(&report.id).join("upstream-receipt.json"))? != expected {
                bail!("upstream receipt integrity check failed: {}", report.id);
            }
        }
    }
    Ok(())
}

fn load_editorial_config(repo_root: &Utf8Path) -> Result<EditorialConfig> {
    let path = repo_root.join(EDITORIAL_REPLACEMENTS_PATH);
    let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
    let config: EditorialConfig =
        serde_json::from_str(&text).with_context(|| format!("failed to parse {path}"))?;
    if config.schema_version != 1 {
        bail!(
            "editorial replacement schema_version must be 1, got {}",
            config.schema_version
        );
    }
    for (scope, replacements) in std::iter::once(("global", &config.replacements))
        .chain(config.report_replacements.iter().map(|(id, items)| (id.as_str(), items)))
    {
        let mut seen = std::collections::HashSet::new();
        for (index, replacement) in replacements.iter().enumerate() {
            if replacement.from.is_empty() {
                bail!("editorial {scope}[{index}].from must not be empty");
            }
            if replacement.from == replacement.to {
                bail!("editorial {scope}[{index}] does not change the text");
            }
            if !seen.insert(replacement.from.as_str()) {
                bail!("duplicate editorial replacement source in {scope}: {}", replacement.from);
            }
        }
    }
    Ok(config)
}

fn load_report_polish(repo_root: &Utf8Path) -> Result<String> {
    let path = repo_root.join(REPORT_POLISH_PATH);
    let css = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
    if css.trim().is_empty() {
        bail!("causal-emergence report polish stylesheet is empty: {path}");
    }
    if css.contains("</style") {
        bail!("causal-emergence report polish stylesheet contains a closing style tag: {path}");
    }
    Ok(css)
}

fn selected_reports<'a>(catalog: &'a Catalog, only_id: Option<&str>) -> Result<Vec<&'a Report>> {
    match only_id {
        None => Ok(catalog.reports.iter().collect()),
        Some(id) => catalog
            .reports
            .iter()
            .find(|report| report.id == id)
            .map(|report| vec![report])
            .ok_or_else(|| anyhow::anyhow!("report id not found in catalog: {id}")),
    }
}

fn unique_source<'a>(
    candidates: &'a HashMap<String, Vec<Utf8PathBuf>>,
    report: &Report,
) -> Result<&'a Utf8Path> {
    let matches = candidates
        .get(&report.sha256)
        .map(Vec::as_slice)
        .unwrap_or_default();
    match matches {
        [source] => Ok(source),
        [] => bail!(
            "no report beneath the input root matches {} ({})",
            report.id,
            report.sha256
        ),
        _ => bail!(
            "multiple reports beneath the input root match {} ({}): {}",
            report.id,
            report.sha256,
            matches
                .iter()
                .map(|path| path.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn discover_html_by_sha(root: &Utf8Path) -> Result<HashMap<String, Vec<Utf8PathBuf>>> {
    let mut files = Vec::new();
    discover_html(root, &mut files)?;
    let mut by_sha: HashMap<String, Vec<Utf8PathBuf>> = HashMap::new();
    for path in files {
        by_sha.entry(sha256_file(&path)?).or_default().push(path);
    }
    Ok(by_sha)
}

fn discover_html(root: &Utf8Path, output: &mut Vec<Utf8PathBuf>) -> Result<()> {
    for entry in fs::read_dir(root).with_context(|| format!("failed to read {root}"))? {
        let entry = entry?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow::anyhow!("report path is not valid UTF-8"))?;
        let file_type = entry.file_type()?;
        if file_type.is_symlink() {
            bail!("report input root contains a symlink: {path}");
        }
        if file_type.is_dir() {
            discover_html(&path, output)?;
        } else if file_type.is_file() && path.extension() == Some("html") {
            output.push(path);
        }
    }
    Ok(())
}

fn render_context(
    report: &Report,
    public_report_sha256: &str,
    transformations: &[&'static str],
) -> String {
    let publication_changes = transformations
        .iter()
        .filter_map(|transformation| match *transformation {
            "synthesis_publication_instruments_v1" => Some("interactive views were derived from the recorded fields and measurements, and the channel decoder was repaired"),
            REDACT_SOURCE_PREFIX => Some("internal file paths were shortened"),
            NEUTRALIZE_LOCAL_LINKS => {
                Some("links to files that are not published here were disabled")
            }
            NORMALIZE_PUBLIC_EDITORIAL => {
                Some("public-facing wording and explanations were revised without changing the recorded measurements")
            }
            EXPAND_INTERNAL_CHECKPOINTS => {
                Some("internal checkpoint labels were written out as developmental passages")
            }
            NORMALIZE_MOBILE_WRAP => Some("small-screen wrapping was added"),
            "import_verified_public_projection_v1" => Some("the previously published projection was verified against its manifest and moved into the website"),
            "move_reports_to_website_v1" => Some("report links now use website routes"),
            APPLY_REPORT_POLISH => Some("shared report and chart styling was applied"),
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("; ");
    let release_url = format!(
        "https://specterlab.org/dossiers/lenia-swarm/causal-emergence/reports/{}/",
        report.id
    );
    html! {
        (DOCTYPE)
        html lang="en" {
            head {
                meta charset="utf-8";
                meta name="viewport" content="width=device-width, initial-scale=1";
                meta name="color-scheme" content="light";
                meta name="description" content=(&report.dek);
                meta property="og:type" content="article";
                meta property="og:title" content=(&report.title);
                meta property="og:description" content=(&report.dek);
                meta property="og:url" content=(&release_url);
                title { (&report.title) " | SPECTER Labs" }
                style { (maud::PreEscaped(CONTEXT_CSS)) }
                link rel="stylesheet" href="/assets/publication-layout.css?v=20260914-logo";
            }
            body class="publication-context" {
                (maud::PreEscaped(include_str!("../../../../site/templates/publication-header.html")))
                main {
                    nav aria-label="Report navigation" {
                        a href="https://specterlab.org/dossiers/lenia-swarm/causal-emergence/" { "Causal emergence" }
                        a href="https://specterlab.org/dossiers/lenia-swarm/causal-emergence/library/" { "Report library" }
                    }
                    header {
                        div class="eyebrow" { "Flow Lenia / " (&report.category) }
                        h1 { (&report.title) }
                        p class="dek" { (&report.dek) }
                        div class="chips" {
                            span { (&report.evidence_class) }
                            time datetime=(&report.date) { (&report.date) }
                        }
                    }
                    section class="questions" aria-label="Report context" {
                        article {
                            h2 { "Question" }
                            p { (&report.question) }
                        }
                        article class="answer" {
                            h2 { "Result" }
                            p { (&report.answer) }
                        }
                        article {
                            h2 { "Next question" }
                            p { (&report.next_question) }
                        }
                    }
                    div class="actions" {
                        a class="primary" href="index.html" { "Read the full report" }
                        a href="release-receipt.json" { "Publication details" }
                    }
                    footer {
                        @if transformations.is_empty() {
                            details {
                                summary { "About this publication" }
                                p { "The full report matches its source file. Source checksum: " code { (&report.sha256) } "." }
                            }
                        } @else {
                            details {
                                summary { "About this publication" }
                                p {
                                    @if transformations.contains(&"synthesis_publication_instruments_v1") {
                                        "The recorded measurements are retained. For publication, "
                                    } @else {
                                        "The figures and results match the source file. For publication, "
                                    }
                                    (publication_changes)
                                    ". Source checksum: "
                                    code { (&report.sha256) }
                                    ". Published report checksum: "
                                    code { (public_report_sha256) }
                                    "."
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    .into_string()
}

fn project_public_report(
    report: &Report,
    source: &[u8],
    replacements: &[EditorialReplacement],
    report_polish: &str,
) -> Result<PublicProjection> {
    let source =
        std::str::from_utf8(source).context("causal-emergence report is not valid UTF-8")?;
    let mut transformations = Vec::new();
    let mut projected = source.to_owned();

    if projected.contains("</head>") {
        projected = ensure_report_root_class(&projected)?;
        let head_end = projected
            .find("</head>")
            .context("projected public report has no closing head element")?;
        let style = format!(
            "<style data-specter-public-polish>\n{}\n</style>",
            report_polish.trim()
        );
        projected.insert_str(head_end, &style);
        transformations.push(APPLY_REPORT_POLISH);
    }

    let (title_projection, title_changed) = normalize_public_title(&projected, &report.title)?;
    projected = title_projection;

    let (editorial_projection, editorial_changed) =
        normalize_public_editorial(&projected, replacements);
    projected = editorial_projection;
    if title_changed || editorial_changed {
        transformations.push(NORMALIZE_PUBLIC_EDITORIAL);
    }

    let (checkpoint_projection, checkpoints_changed) =
        expand_internal_checkpoint_notation(&projected)?;
    projected = checkpoint_projection;
    if checkpoints_changed {
        transformations.push(EXPAND_INTERNAL_CHECKPOINTS);
    }

    if report.id == "synthesis-v7" {
        projected = refine_synthesis_reading(&projected)?;
        transformations.push("refine_synthesis_reading_v1");
    }

    if projected.contains(".codex/") || projected.contains("artifacts/replication-precursor/") {
        projected = projected.replace(".codex/", "evidence-source/").replace(
            "artifacts/replication-precursor/",
            "evidence-source/visuals/",
        );
        transformations.push(REDACT_SOURCE_PREFIX);
    }

    let (with_public_links, links_changed) = neutralize_relative_hrefs(&projected);
    projected = with_public_links;
    if links_changed {
        transformations.push(NEUTRALIZE_LOCAL_LINKS);
    }

    if let Some(body_start) = projected.find("<body") {
        let body_end = body_start
            + projected[body_start..]
                .find('>')
                .context("report body is unterminated")?
            + 1;
        let archive = if report.archive {
            "<span>Earlier report · retained in the archive</span>"
        } else {
            ""
        };
        projected.insert_str(body_end, &format!(r#"{}<nav class="publication-navigation" aria-label="Research publication"><a href="/dossiers/lenia-swarm/">Lenia Swarm</a><a href="/dossiers/lenia-swarm/causal-emergence/library/">Report library</a><a href="about.html">About this report</a>{archive}</nav>"#, include_str!("../../../../site/templates/publication-header.html")));
        transformations.push("add_publication_navigation_v1");
    }

    if let Some(head_end) = projected.find("</head>") {
        projected.insert_str(head_end, r#"<link rel="stylesheet" href="/assets/publication-layout.css?v=20260914-logo"><link rel="icon" href="/assets/logo-black.svg">"#);
    }
    projected = Regex::new(r#"<a[^>]+href="https://releases\.specterlab\.org/cdn-cgi/[^>]+></a>"#)?
        .replace_all(&projected, "")
        .into_owned();

    let needs_mobile_normalization = !transformations.is_empty()
        || matches!(
            report.id.as_str(),
            "tangent-memory-dose-response"
                | "reservoir-recurrence-census"
                | "fresh-organic-q40-replication"
                | "tangent-induced-causal-grammar"
        );
    if needs_mobile_normalization {
        let head_end = projected
            .find("</head>")
            .context("projected public report has no closing head element")?;
        projected.insert_str(head_end, PUBLIC_MOBILE_STYLE);
        transformations.push(NORMALIZE_MOBILE_WRAP);
    }

    for forbidden in [
        ".codex/",
        "artifacts/replication-precursor/",
        "file://",
        "/Users/",
        "/home/",
    ] {
        if projected.contains(forbidden) {
            bail!("public report projection still contains private reference: {forbidden}");
        }
    }

    Ok(PublicProjection {
        bytes: projected.into_bytes(),
        transformations,
    })
}

fn expand_internal_checkpoint_notation(source: &str) -> Result<(String, bool)> {
    let checkpoint = Regex::new(r"(?i)\bq([0-9]+)\b")?;
    let mut projected = String::with_capacity(source.len());
    let mut cursor = 0;
    let mut raw_element: Option<&str> = None;

    while cursor < source.len() {
        if let Some(raw) = raw_element {
            let closing = format!("</{raw}");
            let Some(offset) = source[cursor..].to_ascii_lowercase().find(&closing) else {
                projected.push_str(&source[cursor..]);
                break;
            };
            let close_start = cursor + offset;
            projected.push_str(&source[cursor..close_start]);
            cursor = close_start;
            raw_element = None;
            continue;
        }

        let Some(offset) = source[cursor..].find('<') else {
            projected.push_str(&checkpoint.replace_all(&source[cursor..], "passage $1"));
            break;
        };
        let tag_start = cursor + offset;
        projected.push_str(&checkpoint.replace_all(&source[cursor..tag_start], "passage $1"));
        let tag_end = source[tag_start..]
            .find('>')
            .map(|end| tag_start + end + 1)
            .context("projected public report contains an unterminated HTML tag")?;
        let tag = &source[tag_start..tag_end];
        projected.push_str(tag);
        let lower = tag.to_ascii_lowercase();
        if lower.starts_with("<style") && !lower.starts_with("</") {
            raw_element = Some("style");
        } else if lower.starts_with("<script") && !lower.starts_with("</") {
            raw_element = Some("script");
        }
        cursor = tag_end;
    }

    for attribute in ["alt", "title", "aria-label"] {
        let pattern = Regex::new(&format!(r#"(?i)({attribute}\s*=\s*\")([^\"]*)(\")"#))?;
        projected = pattern
            .replace_all(&projected, |captures: &regex_lite::Captures<'_>| {
                format!(
                    "{}{}{}",
                    &captures[1],
                    checkpoint.replace_all(&captures[2], "passage $1"),
                    &captures[3]
                )
            })
            .into_owned();
    }

    Ok((projected.clone(), projected != source))
}

fn refine_synthesis_reading(source: &str) -> Result<String> {
    let mut projected = source.replace(
        "<header class=\"hero\" id=\"top\">",
        "<header class=\"hero editorial-synthesis\" id=\"top\">",
    );
    let dek = Regex::new(r#"<p class="dek">[\s\S]*?</p>"#)?;
    let opening = [
        r#"<p class="dek">Before a persistent body is visible, a developing Flow Lenia field already responds differently to nearby interventions. Later, the same push has less influence—yet sibling runs keep reaching different shapes.</p>"#,
        r##"<p class="dek">We began by asking whether a disturbed run could recover the organization and trajectory of its undisturbed counterpart. That recovery was not clean or consistent. Following the different futures instead led to the experiments below: forecasts, branching interventions, feedback, and hidden-state rewrites.</p><nav class="reading-route" aria-label="Follow the investigation"><a href="#future">Watch futures separate →</a><a href="#control">Test steering and release →</a><a href="#passport">Recognize a response →</a></nav>"##,
    ];
    let matches = dek.find_iter(&projected).take(2).collect::<Vec<_>>();
    if matches.len() != 2 {
        bail!("synthesis opening must contain two introductory paragraphs");
    }
    let ranges = matches.iter().map(|m| m.range()).collect::<Vec<_>>();
    for (range, replacement) in ranges.into_iter().zip(opening).rev() {
        projected.replace_range(range, replacement);
    }
    let aside = Regex::new(r#"(<aside class="hero-answer">[\s\S]*?<p>)[\s\S]*?(</p>)"#)?;
    projected = aside.replace(&projected, "${1}The prospective cohort shows constrained futures before a persistent silhouette. A separate cohort shows recognizable responses by passages 12–24. These are complementary findings, not one shared developmental clock.${2}").into_owned();
    for (from, to) in [
        ("To see this, we had to look beyond the picture.", "One visible field can have different futures."),
        ("Before a persistent body can be seen, interventions already open different futures.", "Different futures open before a persistent body appears."),
        ("Development closes some possibilities while leaving shape plural.", "Harder to redirect. Still many possible shapes."),
        ("The small shape effect did not repeat cleanly, and the distinction became sharper.", "The small shape effect did not repeat cleanly."),
        ("The same standardized write produces less future change as the body ages.", "The same push loses influence with age."),
        ("Whole-state feedback reaches the target while it is active, although its unique edge disappears.", "Steering works while the controller is on."),
        ("The recognizable response is field-like, distributed, and slow to read.", "The fingerprint is spread across the field."),
        ("The strange observations only matter if the misses remain visible beside them.", "What passed, what failed, and what we corrected."),
        ("which left-censors its onset rather than locating a birth at passage 12 or anywhere else inside that window.", "so it may have appeared earlier; this test does not locate its onset."),
    ] {
        projected = projected.replace(from, to);
    }
    for (from, to) in [
        ("possibility first, form later", "Different responses before a persistent body"),
        ("action-world", "set of intervention outcomes"),
        ("We found this in two independent ways: a fresh prospective run showed the whole-over-parts relation rising during the reorganization that precedes sustained form, while a fixed-age branching assay found that the alternative futures opened at passage 8 were already at least as separated as those opened at passage 32.", "We saved early fields, applied different interventions, and let each copy continue. The futures opened at passage 8 were already at least as separated as those at passage 32. A separate forecasting experiment asked how well the whole field predicts its future compared with its parts."),
        ("Across forecasting, branching, transplantation, and control, the same picture keeps returning: organization appears first as a changing relation among possible futures, interventions, and remembered history, while visible morphology remains plural and autonomous replication has not yet appeared.", "The experiments separate properties that a still image cannot distinguish. A field can become harder to redirect while sibling runs keep reaching different shapes. Its response can identify the source across time, yet transferring hidden composition does not reliably transfer that identity. These findings come from separate comparisons and cohorts."),
        ("The system is genuinely steerable during the active window", "Feedback steers the system during the active window"),
        (", or informally a causal address", ""),
        ("09 · the next large swings", "09 · the next experiments"),
        ("The system becomes an individual by changing what can happen next.", "A persistent shape is only part of the story."),
        ("followed an address through fission", "followed a response fingerprint through fission"),
        ("Closed-loop release ecology", "After feedback stops"),
        ("a more local response syntax", "a smaller region of the field"),
        ("one that merely leaves a divergent scar", "one whose effects persist without maintaining the target"),
        ("learned, portable, and generative", "shaped by life history, transferable, and inherited"),
    ] {
        projected = projected.replace(from, to);
    }
    for (section, fragment) in [
        ("impedance", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-age-comparison.html")),
        ("control", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-control-comparison.html")),
        ("passport", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-hidden-comparison.html")),
    ] {
        if let Some(start) = projected.find(&format!("id=\"{section}\"")) {
            let insertion = if section == "passport" {
                start + projected[start..].find("<div class=\"patch-grid\">").context("passport paired fields missing")?
            } else {
                start + projected[start..].find("</header>").context("comparison section has no header")? + "</header>".len()
            };
            projected.insert_str(insertion, fragment);
        }
    }
    let image_digest = Regex::new(r"Embedded PNG SHA ([a-f0-9]{64})\.")?;
    projected = image_digest.replace_all(&projected, "").into_owned();
    let legend = Regex::new(r#"<div class="evidence-legend"[^>]*>[\s\S]*?</div>"#)?;
    projected = legend.replace(&projected, "").into_owned();
    let exploration =
        Regex::new(r#"<section aria-labelledby="exploration-title">[\s\S]*?</section>"#)?;
    projected = exploration.replace(&projected, |caps: &regex_lite::Captures| {
        format!("<details class=\"research-detail\"><summary>Further analyses: where the response fingerprint is detectable</summary>{}</details>", &caps[0])
    }).into_owned();
    let numerical_cards = Regex::new(r#"<div class="metric-grid[^"]*">[\s\S]*?</div>"#)?;
    projected = numerical_cards.replace_all(&projected, |caps: &regex_lite::Captures| {
        format!("<details class=\"research-detail\"><summary>Estimates, uncertainty, and additional checks</summary>{}</details>", &caps[0])
    }).into_owned();
    let card_labels =
        Regex::new(r#"(<article class="explore-card">)<span class="evidence [^"]*">[^<]*</span>"#)?;
    projected = card_labels.replace_all(&projected, "$1").into_owned();
    let figures = Regex::new(r#"<figure class="figure"><svg[\s\S]*?</figure>"#)?;
    projected = figures.replace_all(&projected, |caps: &regex_lite::Captures| {
        let figure = &caps[0];
        let detail = if figure.contains("impedance-heatmap") {
            Some(("Inspect both intervention arms across all ages and horizons", ""))
        } else if figure.contains("dose-chart") {
            Some(("Inspect the requested dose and the realized initial effect", ""))
        } else if figure.contains("route-fingerprint") {
            Some(("Inspect how the controllers chose different action sequences", ""))
        } else if figure.contains("transplant-chart") {
            Some(("Inspect the full transplant estimates", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-transplant-comparison.html")))
        } else if figure.contains("early-forecasting-and-future-separation-results") {
            Some(("Inspect the prospective forecasting estimates", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-early-comparison.html")))
        } else if figure.contains("five-developmental-evidence-axes") {
            Some(("Compare the separate experimental timelines", ""))
        } else { None };
        match detail {
            Some((label, replacement)) => format!("{replacement}<details class=\"research-detail\"><summary>{label}</summary>{figure}</details>"),
            None => figure.to_owned(),
        }
    }).into_owned();
    let explorer_script = format!(
        "<script>{}</script>",
        include_str!(
            "../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-explorers.js"
        )
    );
    if let Some(end) = projected.rfind("</body>") {
        projected.insert_str(end, &explorer_script);
    }
    let marker =
        "<header class=\"section-head\"><div><span class=\"section-no\">01 · how we looked</span>";
    if !projected.contains(marker) {
        bail!("synthesis instrument section missing");
    }
    projected = projected.replace(marker, &format!("<p class=\"passage-note\">Passage numbers count forward from the seeded starting field. Passages 8, 12, and later checkpoints are scheduled observations, not life stages inferred from appearance.</p>{marker}"));
    Ok(projected)
}

fn ensure_report_root_class(source: &str) -> Result<String> {
    let html_start = source
        .find("<html")
        .context("projected public report has no html element")?;
    let tag_end = source[html_start..]
        .find('>')
        .map(|offset| html_start + offset)
        .context("projected public report has an unterminated html element")?;
    let tag = &source[html_start..=tag_end];
    if tag.contains("specter-report") {
        return Ok(source.to_owned());
    }
    if tag.contains("class=") {
        bail!("projected public report has an unsupported html class attribute");
    }

    let mut projected = source.to_owned();
    projected.insert_str(tag_end, " class=\"specter-report\"");
    Ok(projected)
}

fn normalize_public_title(source: &str, public_title: &str) -> Result<(String, bool)> {
    if !source.contains("</head>") {
        return Ok((source.to_owned(), false));
    }

    let escaped_text = escape_html_text(public_title);
    let (projected, document_title_changed) =
        replace_element_contents(source, "title", &escaped_text, false)?;
    let (projected, heading_changed) =
        replace_element_contents(&projected, "h1", &escaped_text, true)?;
    let (projected, social_title_changed) = replace_social_title(&projected, public_title);

    Ok((
        projected,
        document_title_changed || heading_changed || social_title_changed,
    ))
}

fn replace_element_contents(
    source: &str,
    tag_name: &str,
    replacement: &str,
    remove_aria_label: bool,
) -> Result<(String, bool)> {
    let opening_marker = format!("<{tag_name}");
    let Some(opening_start) = source.find(&opening_marker) else {
        return Ok((source.to_owned(), false));
    };
    let opening_end = source[opening_start..]
        .find('>')
        .map(|offset| opening_start + offset)
        .with_context(|| format!("public report has an unterminated {tag_name} element"))?;
    let closing_marker = format!("</{tag_name}>");
    let closing_start = source[opening_end + 1..]
        .find(&closing_marker)
        .map(|offset| opening_end + 1 + offset)
        .with_context(|| format!("public report has no closing {tag_name} element"))?;

    let opening = &source[opening_start..=opening_end];
    let opening = if remove_aria_label {
        Regex::new(r#"\s+aria-label\s*=\s*("[^"]*"|'[^']*')"#)?
            .replace(opening, "")
            .to_string()
    } else {
        opening.to_owned()
    };

    let mut projected = String::with_capacity(source.len() + replacement.len());
    projected.push_str(&source[..opening_start]);
    projected.push_str(&opening);
    projected.push_str(replacement);
    projected.push_str(&source[closing_start..]);
    let changed = projected != source;
    Ok((projected, changed))
}

fn replace_social_title(source: &str, public_title: &str) -> (String, bool) {
    const MARKER: &str = "<meta property=\"og:title\" content=\"";
    let Some(value_start) = source.find(MARKER).map(|index| index + MARKER.len()) else {
        return (source.to_owned(), false);
    };
    let Some(value_end) = source[value_start..]
        .find('"')
        .map(|offset| value_start + offset)
    else {
        return (source.to_owned(), false);
    };

    let escaped_attribute = escape_html_attribute(public_title);
    let mut projected = String::with_capacity(source.len() + escaped_attribute.len());
    projected.push_str(&source[..value_start]);
    projected.push_str(&escaped_attribute);
    projected.push_str(&source[value_end..]);
    let changed = projected != source;
    (projected, changed)
}

fn escape_html_text(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn escape_html_attribute(value: &str) -> String {
    escape_html_text(value).replace('"', "&quot;")
}

fn apply_synthesis_publication(source: &str) -> Result<String> {
    let image_provenance = Regex::new(r#"(?s)<details class="image-provenance">.*?</details>"#)?;
    let source = image_provenance.replace_all(source, "");
    let mut html = source.replace(
        "class=\"specter-report\"",
        "class=\"specter-report synthesis-publication\"",
    );
    let observation = Regex::new(r#"(?s)<section class="synthesis-observation".*?</section>\s*"#)?;
    html = observation.replace_all(&html, "").into_owned();
    let hero = Regex::new(r#"(?s)<header class="hero editorial-synthesis" id="top">.*?</header>\s*"#)?;
    if !hero.is_match(&html) {
        bail!("synthesis publication opening is missing");
    }
    html = hero.replace_all(&html, regex_lite::NoExpand(include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-opening.html"))).into_owned();
    let forecast = Regex::new(
        r#"(?s)<figure class="figure"><svg[^>]+aria-labelledby="how-whole-state-and-separable-forecasting-are-compared-title[^>]*>.*?</figure>\s*|<figure class="synthesis-forecast".*?</figure>\s*"#,
    )?;
    html = forecast.replace_all(&html, regex_lite::NoExpand(include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-forecast.html"))).into_owned();
    for (before, after) in [
        ("Futures are already distinct. Forecasting is still catching up.", "Distinct futures appear before accurate forecasts"),
        ("The visible matter is held fixed. Its composition changes.", "Changing composition while holding visible matter fixed"),
        ("Both transplants move donor-ward. Does the arrangement matter?", "Does arrangement explain why both transplants move toward the donor?"),
        ("However, the geometry behaved like a clock", "Developmental geometry"),
        ("it did not behave like a lever", "Tracking development did not make it easier to control"),
        ("the same picture can contain a different future", "Composition changed growth; donor identity did not reliably transfer"),
        ("Harder to redirect. Still many possible shapes.", "Older bodies resist redirection without converging on one shape"),
        ("A persistent shape is only part of the story.", "Stability, identity, and shape develop differently"),
        ("Those results made the geometry useful in a different way, because it could tell us where a run was in its reorganization even though pushing the score itself did not reliably advance that process.", "The score tracked reorganization, but interventions that raised it did not consistently accelerate development."),
    ] {
        html = html.replace(before, after);
    }
    let resources = Regex::new(r#"(?s)<nav class="publication-navigation"[^>]*>.*?</nav>"#)?;
    html = resources.replace_all(&html, "").into_owned();
    let labels = Regex::new(
        r#"<span class="micro">(?:Future fan|Visible / hidden|Frozen / post-hoc)</span>"#,
    )?;
    html = labels.replace_all(&html, "").into_owned();
    let footer = Regex::new(r#"(?s)<footer class="footer">.*?</footer>"#)?;
    html = footer.replace_all(&html, r##"<footer class="footer"><nav class="wrap footer-grid" aria-label="Report resources"><a href="/dossiers/lenia-swarm/">Lenia Swarm dossier</a><a href="#ledger">Methods and sources</a><a href="about.html">About this report</a></nav></footer>"##).into_owned();
    let graphical_details = Regex::new(r#"<details class="(synthesis-native-inspection|research-detail)"(?: open)?>"#)?;
    html = graphical_details.replace_all(&html, "<details class=\"$1\" open>").into_owned();
    // The upstream patch payloads contain little-endian Float32 bytes, not an array.
    let decoder = r#"function renderPatch(canvas, patch, hidden) {
  if (typeof patch.data === 'string') {
    const bytes = Uint8Array.from(atob(patch.data), c => c.charCodeAt(0));
    if (bytes.length !== patch.width * patch.height * patch.channels * 4) throw new Error('Invalid field payload length');
    const view = new DataView(bytes.buffer);
    patch.data = Float32Array.from({length: bytes.length / 4}, (_, i) => view.getFloat32(i * 4, true));
  }"#;
    if !html.contains("Invalid field payload length") {
        if !html.contains("function renderPatch(canvas, patch, hidden) {") {
            bail!("synthesis channel renderer is missing");
        }
        html = html.replace("function renderPatch(canvas, patch, hidden) {", decoder);
    }
    for (tag, contents) in [
        ("style", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-publication.css")),
        ("script", include_str!("../../../../site/templates/dossiers/lenia-swarm/causal-emergence/synthesis-publication.js")),
    ] {
        let previous = Regex::new(&format!(r#"(?s)<{tag} data-synthesis-publication>.*?</{tag}>"#))?;
        html = previous.replace_all(&html, "").into_owned();
        let end = if tag == "style" { "</head>" } else { "</body>" };
        html = html.replace(end, &format!("<{tag} data-synthesis-publication>{contents}</{tag}>{end}"));
    }
    Ok(html)
}

fn normalize_public_editorial(
    source: &str,
    replacements: &[EditorialReplacement],
) -> (String, bool) {
    let mut projected = source.to_owned();
    for replacement in replacements {
        projected = projected.replace(&replacement.from, &replacement.to);
    }
    let changed = projected != source;
    (projected, changed)
}

fn neutralize_relative_hrefs(source: &str) -> (String, bool) {
    let mut output = String::with_capacity(source.len());
    let mut cursor = 0;
    let mut changed = false;

    while let Some(relative_start) = source[cursor..].find("href=") {
        let attribute_start = cursor + relative_start;
        output.push_str(&source[cursor..attribute_start]);

        let quote_index = attribute_start + "href=".len();
        let Some(quote) = source.as_bytes().get(quote_index).copied() else {
            output.push_str(&source[attribute_start..]);
            return (output, changed);
        };
        if quote != b'\'' && quote != b'"' {
            output.push_str("href=");
            cursor = quote_index;
            continue;
        }

        let value_start = quote_index + 1;
        let Some(value_length) = source[value_start..].find(char::from(quote)) else {
            output.push_str(&source[attribute_start..]);
            return (output, changed);
        };
        let value_end = value_start + value_length;
        let value = &source[value_start..value_end];

        if is_public_href(value) {
            output.push_str(&source[attribute_start..=value_end]);
        } else {
            let reference = &sha256_bytes(value.as_bytes())[..12];
            output.push_str("data-evidence-ref=");
            output.push(char::from(quote));
            output.push_str("src-");
            output.push_str(reference);
            output.push(char::from(quote));
            changed = true;
        }
        cursor = value_end + 1;
    }

    output.push_str(&source[cursor..]);
    (output, changed)
}

fn is_public_href(value: &str) -> bool {
    value.is_empty()
        || value.starts_with('#')
        || value.starts_with('/')
        || value.starts_with("https://")
        || value.starts_with("http://")
        || value.starts_with("mailto:")
        || value.starts_with("tel:")
        || value.starts_with("data:")
}

fn sha256_file(path: &Utf8Path) -> Result<String> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {path}"))?;
    Ok(sha256_bytes(&bytes))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    let mut digest = Sha256::new();
    digest.update(bytes);
    format!("{:x}", digest.finalize())
}

const CONTEXT_CSS: &str = r"
:root{--ink:#111722;--paper:#f4f0e5;--blue:#2853d8;--acid:#d9ff27;--coral:#f45237;--line:#b9b3a7}*{box-sizing:border-box}html{background:#e8e2d5}body{margin:0;color:var(--ink);background:linear-gradient(rgba(17,23,34,.055) 1px,transparent 1px),linear-gradient(90deg,rgba(17,23,34,.055) 1px,transparent 1px),var(--paper);background-size:28px 28px;font:16px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}main{width:min(1120px,calc(100% - 2rem));min-height:100vh;margin:auto;padding:1.2rem 0 4rem}nav{display:flex;flex-wrap:wrap;gap:1rem;padding:.5rem 0 1.2rem;border-bottom:2px solid var(--ink);font-size:.75rem;text-transform:uppercase;letter-spacing:.08em}a{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px}header{padding:clamp(2.5rem,7vw,5rem) 0 2.3rem}.eyebrow{color:var(--blue);font-size:.75rem;font-weight:800;letter-spacing:.11em;text-transform:uppercase}h1{max-width:980px;margin:.6rem 0 1.2rem;font:900 clamp(2.7rem,5vw,5rem)/.92 system-ui,sans-serif;letter-spacing:-.06em;overflow-wrap:anywhere}.dek{max-width:880px;font:400 clamp(1.15rem,2vw,1.55rem)/1.5 Georgia,serif}.chips{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:1.4rem}.chips>*{padding:.25rem .45rem;background:var(--paper);border:1.5px solid var(--ink);font-size:.68rem;font-weight:800;text-transform:uppercase}.questions{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--ink);border:2px solid var(--ink);box-shadow:8px 8px 0 rgba(17,23,34,.15)}.questions article{padding:1.35rem;background:var(--paper)}.questions .answer{background:var(--acid)}h2{margin:0 0 1rem;font:850 1rem/1.15 system-ui,sans-serif}.questions p{margin:0;font:400 1.08rem/1.55 Georgia,serif}.actions{display:flex;flex-wrap:wrap;gap:.75rem;margin:1.6rem 0}.actions a{align-items:center;display:inline-flex;justify-content:center;min-height:3rem;padding:.65rem .85rem;border:2px solid var(--ink);background:var(--paper);font-weight:850;line-height:1.2;text-align:center;text-transform:uppercase;text-decoration:none}.actions .primary{background:var(--ink);color:var(--paper);box-shadow:5px 5px 0 var(--coral)}footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);font-size:.72rem;overflow-wrap:anywhere}footer summary{cursor:pointer;font-weight:800;text-transform:uppercase;letter-spacing:.06em}footer p{max-width:90ch}footer code{font-size:inherit}@media(max-width:720px){.questions{grid-template-columns:1fr}.questions article{min-height:0}h1{font-size:clamp(2.7rem,15vw,4.6rem)}}
";

#[cfg(test)]
mod tests {
    use super::*;

    fn write_editorial_config(root: &Utf8Path, replacements: &[(&str, &str)]) {
        let path = root.join(EDITORIAL_REPLACEMENTS_PATH);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        let replacements = replacements
            .iter()
            .map(|(from, to)| serde_json::json!({"from": from, "to": to}))
            .collect::<Vec<_>>();
        let config = serde_json::json!({
            "schema_version": 1,
            "replacements": replacements,
        });
        fs::write(path, serde_json::to_vec_pretty(&config).unwrap()).unwrap();
        fs::write(
            root.join(REPORT_POLISH_PATH),
            "html.specter-report{color-scheme:light}\n",
        )
        .unwrap();
    }

    #[test]
    fn synthesis_publication_refresh_preserves_evidence_and_single_instruments() {
        let evidence = r#"<svg data-evidence="original"><text>0.008877</text></svg><script>const PATCHES = {"data":"AACAPw=="};function renderPatch(canvas, patch, hidden) { return patch; }</script>"#;
        let source = format!(
            r#"<html class="specter-report"><head></head><body><header class="hero editorial-synthesis" id="top"><h1>Old heading</h1></header><main>{evidence}</main></body></html>"#
        );
        let first = apply_synthesis_publication(&source).unwrap();
        let refreshed = apply_synthesis_publication(&first).unwrap();
        assert_eq!(
            refreshed.matches("id=\"development-observation\"").count(),
            1
        );
        assert_eq!(refreshed.matches("id=\"synthesis-field\"").count(), 1);
        assert_eq!(
            refreshed
                .matches("<style data-synthesis-publication>")
                .count(),
            1
        );
        assert_eq!(
            refreshed
                .matches("<script data-synthesis-publication>")
                .count(),
            1
        );
        assert_eq!(refreshed.matches("Invalid field payload length").count(), 1);
        assert!(refreshed.contains(r#"<svg data-evidence="original"><text>0.008877</text></svg>"#));
        assert!(refreshed.contains(r#"const PATCHES = {"data":"AACAPw=="};"#));
        assert!(apply_synthesis_publication("<p>No opening</p>").is_err());
    }

    #[test]
    fn synthesis_reading_keeps_evidence_and_defines_passages() {
        let source = r#"<header class="hero" id="top"><p class="dek">Old opening.</p><p class="dek">Old continuation.</p><aside class="hero-answer"><strong>Finding</strong><p>Old answer.</p></aside></header><header class="section-head"><div><span class="section-no">01 · how we looked</span></div></header><svg data-evidence="unchanged"><text>−6.5831</text></svg><script>const data = [12,72];</script><p class="dek">Later paragraph.</p><section id="impedance"><header></header></section><section id="control"><header></header></section><section id="passport"><header></header><div class="patch-grid"></div></section>"#;
        let result = refine_synthesis_reading(source).unwrap();
        assert!(result.contains("editorial-synthesis"));
        assert!(result.contains(
            "<aside class=\"hero-answer\"><strong>Finding</strong><p>The prospective cohort"
        ));
        assert!(result.contains("response-by-age"));
        assert!(result.contains("losing an advantage does not mean losing all absolute progress"));
        assert!(result.contains("Changing composition while holding visible matter fixed"));
        assert!(result.contains("Passage numbers count forward"));
        assert!(result.contains(r#"<svg data-evidence="unchanged"><text>−6.5831</text></svg>"#));
        assert!(result.contains("<script>const data = [12,72];</script>"));
        assert!(result.contains(r#"<p class="dek">Later paragraph.</p>"#));
        assert!(refine_synthesis_reading("<p>No expected opening</p>").is_err());
    }

    #[test]
    fn public_editorial_projection_removes_release_management_language() {
        let source = "Flow Lenia mega synthesis · public edition. This source-bound standalone report leaves the sealed result available.";
        let replacements = [
            EditorialReplacement {
                from: "Flow Lenia mega synthesis".into(),
                to: "Flow Lenia synthesis".into(),
            },
            EditorialReplacement {
                from: "public edition".into(),
                to: "current synthesis".into(),
            },
            EditorialReplacement {
                from: "source-bound".into(),
                to: "documented".into(),
            },
            EditorialReplacement {
                from: "sealed".into(),
                to: "recorded".into(),
            },
        ];
        let (projected, changed) = normalize_public_editorial(source, &replacements);
        assert!(changed);
        assert!(!projected.to_ascii_lowercase().contains("sealed"));
        assert!(!projected.to_ascii_lowercase().contains("source-bound"));
        assert!(!projected.to_ascii_lowercase().contains("mega synthesis"));
        assert!(!projected.to_ascii_lowercase().contains("public edition"));
        assert!(projected.contains("Flow Lenia synthesis"));
    }

    #[test]
    fn public_title_projection_uses_the_catalog_title_for_each_report() {
        let report = Report {
            id: "example".into(),
            title: "A Clear Result".into(),
            date: "2026-08-30".into(),
            dek: "A concrete summary.".into(),
            question: "What happens?".into(),
            answer: "The field changed.".into(),
            next_question: "Why here?".into(),
            category: "development".into(),
            status: "feature".into(),
            evidence_class: "direct".into(),
            featured: true,
            archive: false,
            supersedes: Vec::new(),
            sha256: "a".repeat(64),
            release_id: "example-aaaaaaaaaaaa".into(),
        };
        let source = "<!doctype html><html><head><meta property=\"og:title\" content=\"The Future Speaks\"><title>The Future Speaks</title></head><body><h1 aria-label=\"The Future Speaks\"><span>The Future</span> Speaks</h1></body></html>";
        let projection = project_public_report(
            &report,
            source.as_bytes(),
            &[],
            "html.specter-report{color-scheme:light}",
        )
        .unwrap();
        let public = String::from_utf8(projection.bytes).unwrap();
        assert_eq!(public.matches("A Clear Result").count(), 3);
        assert!(public.contains("content=\"A Clear Result\""));
        assert!(!public.contains("The Future Speaks"));
        assert!(!public.contains("<h1 aria-label"));
        assert!(public.contains("href=\"about.html\">About this report</a>"));
        assert!(projection
            .transformations
            .contains(&NORMALIZE_PUBLIC_EDITORIAL));
    }

    #[test]
    fn context_escapes_prose_and_exposes_exact_report() {
        let report = Report {
            id: "example".into(),
            title: "A <body> responds".into(),
            date: "2026-08-30".into(),
            dek: "A concrete summary.".into(),
            question: "What happens?".into(),
            answer: "The field changed.".into(),
            next_question: "Why here?".into(),
            category: "development".into(),
            status: "feature".into(),
            evidence_class: "frozen direct".into(),
            featured: true,
            archive: false,
            supersedes: Vec::new(),
            sha256: "a".repeat(64),
            release_id: "example-aaaaaaaaaaaa".into(),
        };
        let page = render_context(&report, &report.sha256, &[]);
        assert!(page.contains("A &lt;body&gt; responds"));
        assert!(page.contains("href=\"index.html\""));
        assert!(!page.contains(".codex"));
    }

    #[test]
    fn public_projection_expands_checkpoint_shorthand_only_in_reading_copy() {
        let source = r#"<!doctype html><html><head><style>.q48{color:red}</style><title>At q48</title></head><body><p>From Q8 to q48.</p><img src="data:image/png;base64,q48" alt="body at q48"></body></html>"#;
        let (projected, changed) = expand_internal_checkpoint_notation(source).unwrap();
        assert!(changed);
        assert!(projected.contains("<title>At passage 48</title>"));
        assert!(projected.contains("From passage 8 to passage 48."));
        assert!(projected.contains("alt=\"body at passage 48\""));
        assert!(projected.contains(".q48{color:red}"));
        assert!(projected.contains("base64,q48"));
    }

    #[test]
    fn stage_library_preserves_exact_report_and_hides_input_path() {
        let temp = tempfile::tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write_editorial_config(root, &[]);
        let input = root.join("private-input");
        fs::create_dir_all(&input).unwrap();
        let report_bytes = b"<!doctype html><title>Exact report</title>\n";
        fs::write(input.join("source.html"), report_bytes).unwrap();
        let report_sha256 = sha256_bytes(report_bytes);

        let catalog_path = root.join(causal_emergence::CATALOG_PATH);
        fs::create_dir_all(catalog_path.parent().unwrap()).unwrap();
        let catalog = serde_json::json!({
            "schema_version": 1,
            "categories": [{"id": "development", "label": "Development"}],
            "reports": [{
                "id": "exact-report",
                "title": "The exact report",
                "date": "2026-08-30",
                "dek": "A versioned report with a public introduction.",
                "question": "What did the field do?",
                "answer": "It changed its reachable futures.",
                "next_question": "Which part of the state remembers that change?",
                "category": "development",
                "status": "feature",
                "evidence_class": "frozen direct",
                "featured": true,
                "archive": false,
                "supersedes": [],
                "sha256": report_sha256,
                "release_id": "exact-report-aaaaaaaaaaaa"
            }]
        });
        fs::write(&catalog_path, serde_json::to_vec_pretty(&catalog).unwrap()).unwrap();

        let output = root.join("public-bundle");
        let result = stage_library(root, &input, &output, None).unwrap();
        assert_eq!(result.report_count, 1);

        let release = output.join("reports/exact-report");
        assert_eq!(fs::read(release.join("index.html")).unwrap(), report_bytes);
        let context = fs::read_to_string(release.join("about.html")).unwrap();
        let receipt = fs::read_to_string(release.join("release-receipt.json")).unwrap();
        let manifest = fs::read_to_string(output.join("manifest.json")).unwrap();
        assert!(context.contains("Result"));
        assert!(!context.contains("private-input"));
        assert!(!receipt.contains("private-input"));
        assert!(!manifest.contains("private-input"));
        assert!(receipt.contains("move_reports_to_website_v1"));
        assert!(receipt.contains(&format!("\"publicReportSha256\": \"{report_sha256}\"")));
        let scoped_config = serde_json::json!({
            "schema_version": 1,
            "replacements": [],
            "report_replacements": {
                "unrelated-report": [{"from": "Exact report", "to": "Unrelated title"}]
            }
        });
        fs::write(root.join(EDITORIAL_REPLACEMENTS_PATH), scoped_config.to_string()).unwrap();
        let scoped_output = root.join("scoped-output");
        stage_library(root, &input, &scoped_output, None).unwrap();
        assert_eq!(fs::read(scoped_output.join("reports/exact-report/index.html")).unwrap(), report_bytes);

        let mut matching_config = scoped_config;
        matching_config["report_replacements"]["exact-report"] =
            serde_json::json!([{"from": "Exact report", "to": "Reframed report"}]);
        fs::write(root.join(EDITORIAL_REPLACEMENTS_PATH), matching_config.to_string()).unwrap();
        let edited_output = root.join("edited-output");
        stage_library(root, &input, &edited_output, None).unwrap();
        let edited = fs::read_to_string(edited_output.join("reports/exact-report/index.html")).unwrap();
        assert!(edited.contains("Reframed report"));
        assert!(!edited.contains("Unrelated title"));
        assert_eq!(fs::read(input.join("source.html")).unwrap(), report_bytes);

    }

    #[test]
    fn stage_library_projects_private_references_without_touching_source() {
        let temp = tempfile::tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write_editorial_config(root, &[]);
        let input = root.join("private-input");
        fs::create_dir_all(&input).unwrap();
        let report_bytes = br##"<!doctype html><html><head><title>Projected</title></head><body>
<a href="../analysis/results.json">local evidence</a>
<a href="#finding">finding</a>
<a href="https://example.com/source">external</a>
<code>.codex/campaign/analysis/results.json</code>
<code>artifacts/replication-precursor/campaign/frames/frame_000032.png</code>
</body></html>
"##;
        let source = input.join("source.html");
        fs::write(&source, report_bytes).unwrap();
        let report_sha256 = sha256_bytes(report_bytes);

        let catalog_path = root.join(causal_emergence::CATALOG_PATH);
        fs::create_dir_all(catalog_path.parent().unwrap()).unwrap();
        let catalog = serde_json::json!({
            "schema_version": 1,
            "categories": [{"id": "development", "label": "Development"}],
            "reports": [{
                "id": "projected-report",
                "title": "The projected report",
                "date": "2026-08-30",
                "dek": "A versioned report with private source references.",
                "question": "What did the field do?",
                "answer": "It changed its reachable futures.",
                "next_question": "Which part remembers?",
                "category": "development",
                "status": "feature",
                "evidence_class": "documented exploration",
                "featured": true,
                "archive": false,
                "supersedes": [],
                "sha256": report_sha256,
                "release_id": "projected-report-aaaaaaaaaaaa"
            }]
        });
        fs::write(&catalog_path, serde_json::to_vec_pretty(&catalog).unwrap()).unwrap();

        let output = root.join("public-bundle");
        stage_library(root, &input, &output, None).unwrap();
        let release = output.join("reports/projected-report");
        let public = fs::read_to_string(release.join("index.html")).unwrap();
        let receipt = fs::read_to_string(release.join("release-receipt.json")).unwrap();
        let context = fs::read_to_string(release.join("about.html")).unwrap();

        assert_eq!(fs::read(&source).unwrap(), report_bytes);
        assert!(public.contains("<html class=\"specter-report\">"));
        assert!(public.contains("data-specter-public-polish"));
        assert!(!public.contains(".codex/"));
        assert!(!public.contains("../analysis/results.json"));
        assert!(public.contains("data-evidence-ref=\"src-"));
        assert!(public.contains("href=\"#finding\""));
        assert!(public.contains("href=\"https://example.com/source\""));
        assert!(public.contains("evidence-source/campaign/analysis/results.json"));
        assert!(public.contains("evidence-source/visuals/campaign/frames/frame_000032.png"));
        assert!(receipt.contains(REDACT_SOURCE_PREFIX));
        assert!(receipt.contains(NEUTRALIZE_LOCAL_LINKS));
        assert!(receipt.contains(APPLY_REPORT_POLISH));
        assert!(receipt.contains(NORMALIZE_MOBILE_WRAP));
        assert!(receipt.contains(&report_sha256));
        assert!(public.contains(PUBLIC_MOBILE_STYLE));
        assert!(context.contains("About this publication"));
        assert!(context.contains("internal file paths were shortened"));
        assert!(context.contains("links to files that are not published here were disabled"));
        assert!(context.contains("small-screen wrapping was added"));
        let legacy = root.join("legacy");
        let legacy_report = legacy.join("releases/projected-report-aaaaaaaaaaaa");
        fs::create_dir_all(&legacy_report).unwrap();
        fs::copy(
            release.join("index.html"),
            legacy_report.join("report.html"),
        )
        .unwrap();
        fs::copy(
            release.join("release-receipt.json"),
            legacy_report.join("release-receipt.json"),
        )
        .unwrap();
        let mut legacy_manifest: serde_json::Value =
            serde_json::from_slice(&fs::read(output.join("manifest.json")).unwrap()).unwrap();
        legacy_manifest["schema"] =
            serde_json::json!("specter_flow_lenia_report_library_bundle_v2");
        fs::write(
            legacy.join("manifest.json"),
            serde_json::to_vec(&legacy_manifest).unwrap(),
        )
        .unwrap();
        let migrated = root.join("migrated");
        stage_library(root, &legacy, &migrated, None).unwrap();
        assert!(migrated
            .join("reports/projected-report/upstream-receipt.json")
            .is_file());
        let migrated_receipt =
            fs::read_to_string(migrated.join("reports/projected-report/release-receipt.json"))
                .unwrap();
        assert!(migrated_receipt.contains(&sha256_bytes(public.as_bytes())));
        fs::write(
            root.join(REPORT_POLISH_PATH),
            ".specimen figcaption { color: #fff; }",
        )
        .unwrap();
        let refreshed = root.join("refreshed");
        stage_library(root, &migrated, &refreshed, None).unwrap();
        let refreshed_html =
            fs::read_to_string(refreshed.join("reports/projected-report/index.html")).unwrap();
        assert!(refreshed_html.contains(".specimen figcaption { color: #fff; }"));
        assert_eq!(
            refreshed_html.matches("data-specter-public-polish").count(),
            1
        );
        assert_eq!(
            refreshed_html
                .matches("/assets/publication-layout.css")
                .count(),
            1
        );
        let repeated = root.join("repeated");
        stage_library(root, &refreshed, &repeated, None).unwrap();
        assert_eq!(
            refreshed_html,
            fs::read_to_string(repeated.join("reports/projected-report/index.html")).unwrap()
        );

        fs::write(
            legacy_report.join("report.html"),
            "modified after publication",
        )
        .unwrap();
        let error = stage_library(root, &legacy, &root.join("corrupt"), None).unwrap_err();
        assert!(error.to_string().contains("public report hash mismatch"));
    }

    #[test]
    fn stage_library_clarifies_the_single_legacy_program_phrase() {
        let private_phrase =
            "The old <code>stop_without_phi</code> gate was too narrow to end the research program.";
        let public_phrase = "The old <code>stop_without_phi</code> gate ruled out restoration, but it did not explain the temporal structure we could still see.";
        let report = Report {
            id: "reservoir-temporal-precursor".into(),
            title: "A temporal precursor".into(),
            date: "2026-08-12".into(),
            dek: "A legacy exploratory report.".into(),
            question: "What happens before onset?".into(),
            answer: "A sparse temporal pattern appears.".into(),
            next_question: "Does it recur prospectively?".into(),
            category: "legacy / instrument".into(),
            status: "archive".into(),
            evidence_class: "post-outcome exploratory".into(),
            featured: false,
            archive: true,
            supersedes: Vec::new(),
            sha256: "a".repeat(64),
            release_id: "reservoir-temporal-precursor-aaaaaaaaaaaa".into(),
        };
        let source = format!(
            "<!doctype html><html><head></head><body><p>{private_phrase}</p></body></html>"
        );
        let replacements = [EditorialReplacement {
            from: private_phrase.into(),
            to: public_phrase.into(),
        }];

        let projection = project_public_report(
            &report,
            source.as_bytes(),
            &replacements,
            "html.specter-report{color-scheme:light}",
        )
        .unwrap();
        let public = String::from_utf8(projection.bytes).unwrap();
        assert!(!public.contains(private_phrase));
        assert!(public.contains(public_phrase));
        assert_eq!(
            projection.transformations,
            vec![
                APPLY_REPORT_POLISH,
                NORMALIZE_PUBLIC_EDITORIAL,
                "add_publication_navigation_v1",
                NORMALIZE_MOBILE_WRAP,
            ]
        );

        let context = render_context(
            &report,
            &sha256_bytes(public.as_bytes()),
            &projection.transformations,
        );
        assert!(context.contains("public-facing wording and explanations were revised"));
        assert!(!context.contains("scientific prose"));
    }
}
