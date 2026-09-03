use std::collections::HashMap;
use std::fs;

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use maud::{html, DOCTYPE};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::causal_emergence::{self, Catalog, Report};

const RELEASE_SCHEMA: &str = "specter_flow_lenia_report_release_v2";
const BUNDLE_SCHEMA: &str = "specter_flow_lenia_report_library_bundle_v2";
const EDITORIAL_REPLACEMENTS_PATH: &str =
    "site/dossiers/lenia-swarm/causal-emergence/editorial-replacements.json";
const REPORT_POLISH_PATH: &str = "site/dossiers/lenia-swarm/causal-emergence/report-polish.css";
const REDACT_SOURCE_PREFIX: &str = "redact_internal_source_prefix_v1";
const NEUTRALIZE_LOCAL_LINKS: &str = "neutralize_unpublished_relative_links_v1";
const NORMALIZE_PUBLIC_EDITORIAL: &str = "normalize_public_editorial_language_v1";
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
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct BundleEntry<'a> {
    id: &'a str,
    release_id: &'a str,
    source_report_sha256: &'a str,
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
    let candidates = discover_html_by_sha(input_root)?;
    let selected_sources = selected
        .iter()
        .map(|report| unique_source(&candidates, report).map(|source| (*report, source.to_owned())))
        .collect::<Result<Vec<_>>>()?;

    let releases_root = output_root.join("releases");
    fs::create_dir_all(&releases_root)
        .with_context(|| format!("failed to create {releases_root}"))?;

    let mut manifest_entries = Vec::with_capacity(selected.len());
    for (report, source) in selected_sources {
        let report_release_dir = releases_root.join(&report.release_id);
        fs::create_dir_all(&report_release_dir)
            .with_context(|| format!("failed to create {report_release_dir}"))?;

        let report_bytes = fs::read(&source).with_context(|| format!("failed to read {source}"))?;
        let public_report = project_public_report(
            report,
            &report_bytes,
            &editorial_config.replacements,
            &report_polish,
        )?;
        let public_report_sha256 = sha256_bytes(&public_report.bytes);
        let report_path = report_release_dir.join("report.html");
        fs::write(&report_path, &public_report.bytes)
            .with_context(|| format!("failed to write {report_path}"))?;

        let context = render_context(
            report,
            &public_report_sha256,
            &public_report.transformations,
        );
        let context_sha256 = sha256_bytes(context.as_bytes());
        let context_path = report_release_dir.join("index.html");
        fs::write(&context_path, context)
            .with_context(|| format!("failed to write {context_path}"))?;

        let receipt = ReleaseReceipt {
            schema: RELEASE_SCHEMA,
            id: &report.id,
            release_id: &report.release_id,
            title: &report.title,
            date: &report.date,
            status: &report.status,
            evidence_class: &report.evidence_class,
            source_report_sha256: &report.sha256,
            public_report_sha256: public_report_sha256.clone(),
            transformations: public_report.transformations.clone(),
            context_sha256: context_sha256.clone(),
            catalog_sha256: &catalog_sha256,
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
            source_report_sha256: &report.sha256,
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
    let mut seen = std::collections::HashSet::new();
    for (index, replacement) in config.replacements.iter().enumerate() {
        if replacement.from.is_empty() {
            bail!("editorial replacements[{index}].from must not be empty");
        }
        if replacement.from == replacement.to {
            bail!("editorial replacements[{index}] does not change the text");
        }
        if !seen.insert(replacement.from.as_str()) {
            bail!(
                "duplicate editorial replacement source: {}",
                replacement.from
            );
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
            REDACT_SOURCE_PREFIX => Some("internal file paths were shortened"),
            NEUTRALIZE_LOCAL_LINKS => {
                Some("links to files that are not published here were disabled")
            }
            NORMALIZE_PUBLIC_EDITORIAL => {
                Some("release-management labels were removed from the reading copy")
            }
            NORMALIZE_MOBILE_WRAP => Some("small-screen wrapping was added"),
            APPLY_REPORT_POLISH => Some("shared report and chart styling was applied"),
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("; ");
    let release_url = format!(
        "https://releases.specterlab.org/lenia-swarm/causal-emergence/releases/{}/",
        report.release_id
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
            }
            body {
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
                        a class="primary" href="report.html" { "Read the full report" }
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
                                    "The figures and results match the source file. For publication, "
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

    let (editorial_projection, editorial_changed) =
        normalize_public_editorial(&projected, replacements);
    projected = editorial_projection;
    if editorial_changed {
        transformations.push(NORMALIZE_PUBLIC_EDITORIAL);
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
        assert!(page.contains("href=\"report.html\""));
        assert!(!page.contains(".codex"));
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

        let release = output.join("releases/exact-report-aaaaaaaaaaaa");
        assert_eq!(fs::read(release.join("report.html")).unwrap(), report_bytes);
        let context = fs::read_to_string(release.join("index.html")).unwrap();
        let receipt = fs::read_to_string(release.join("release-receipt.json")).unwrap();
        let manifest = fs::read_to_string(output.join("manifest.json")).unwrap();
        assert!(context.contains("Result"));
        assert!(!context.contains("private-input"));
        assert!(!receipt.contains("private-input"));
        assert!(!manifest.contains("private-input"));
        assert!(receipt.contains("\"transformations\": []"));
        assert!(receipt.contains(&format!("\"publicReportSha256\": \"{report_sha256}\"")));
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
        let release = output.join("releases/projected-report-aaaaaaaaaaaa");
        let public = fs::read_to_string(release.join("report.html")).unwrap();
        let receipt = fs::read_to_string(release.join("release-receipt.json")).unwrap();
        let context = fs::read_to_string(release.join("index.html")).unwrap();

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
                NORMALIZE_MOBILE_WRAP,
            ]
        );

        let context = render_context(
            &report,
            &sha256_bytes(public.as_bytes()),
            &projection.transformations,
        );
        assert!(context.contains("release-management labels were removed"));
        assert!(!context.contains("scientific prose"));
    }
}
