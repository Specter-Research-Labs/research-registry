use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use chrono::{DateTime, NaiveDate};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::env;
use std::fs;
use std::io::{self, IsTerminal, Read};

use crate::dispatch::client::{
    post_admin_ledger_entry_blocking, resolve_dispatch_secret as client_resolve_dispatch_secret,
    resolve_dispatch_url as client_resolve_dispatch_url,
};
use crate::dispatch::types::AdminLedgerPostRequest;
use crate::updates_archive;

const ENTRY_SOURCE_DIR: &str = "site/updates/entries";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UpdateKind {
    Window,
    Main,
}

pub struct CreateOptions {
    pub repo_root: Option<Utf8PathBuf>,
    pub kind: UpdateKind,
    pub date: Option<String>,
    pub published_at: Option<String>,
    pub window_start: Option<String>,
    pub window_end: Option<String>,
    pub label: Option<String>,
    pub topic: Option<String>,
    pub entry_id: Option<String>,
    pub series_number: Option<u32>,
    pub ledger_entry_id: Option<String>,
    pub zulip_message_id: Option<u64>,
    pub body_file: Option<Utf8PathBuf>,
    pub force: bool,
    pub report: bool,
    pub json: bool,
}

pub struct ApprovalOptions {
    pub create: CreateOptions,
    pub dispatch_url: Option<String>,
    pub dispatch_secret: Option<String>,
    pub requested_by_email: Option<String>,
    pub requested_by_name: Option<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct UpdateWindow {
    start: String,
    end: String,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
struct Sections {
    dossiers: Vec<String>,
    addenda: Vec<String>,
    ops: Vec<String>,
    lab: Vec<String>,
}

impl Sections {
    fn is_empty(&self) -> bool {
        self.dossiers.is_empty()
            && self.addenda.is_empty()
            && self.ops.is_empty()
            && self.lab.is_empty()
    }

    fn bucket_mut(&mut self, key: &str) -> Option<&mut Vec<String>> {
        match key {
            "dossiers" => Some(&mut self.dossiers),
            "addenda" => Some(&mut self.addenda),
            "ops" => Some(&mut self.ops),
            "lab" => Some(&mut self.lab),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct DraftParse {
    sections: Sections,
    window: Option<UpdateWindow>,
    series_number: Option<u32>,
}

struct ResolvedCreateDraft {
    repo_root: Utf8PathBuf,
    entry_path: Utf8PathBuf,
    entry_id: String,
    label: String,
    topic: String,
    stamp: String,
    sections: Sections,
    kind: UpdateKind,
    window: UpdateWindow,
    series_number: Option<u32>,
    force: bool,
    report: bool,
    requested_published_at: Option<String>,
    requested_ledger_entry_id: Option<String>,
    requested_zulip_message_id: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct LedgerPostResponse {
    #[serde(rename = "entryId")]
    entry_id: String,
    #[serde(rename = "createdAt")]
    created_at: String,
    #[serde(rename = "messageId")]
    message_id: Option<u64>,
}

#[derive(Debug, Serialize)]
struct UpdateEntryPayload {
    id: String,
    kind: String,
    label: String,
    date: String,
    published_at: String,
    topic: String,
    window: UpdateWindowPayload,
    #[serde(skip_serializing_if = "Option::is_none")]
    series_number: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    ledger_entry_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    zulip_message_id: Option<u64>,
    sections: SectionsPayload,
}

#[derive(Debug, Serialize)]
struct UpdateWindowPayload {
    start: String,
    end: String,
}

#[derive(Debug, Serialize)]
struct SectionsPayload {
    dossiers: Vec<String>,
    addenda: Vec<String>,
    ops: Vec<String>,
    lab: Vec<String>,
}

fn discover_repo_root(start: Option<&Utf8Path>) -> Result<Utf8PathBuf> {
    let current: Utf8PathBuf = match start {
        Some(path) => path.to_owned(),
        None => env::current_dir()
            .context("failed to read current directory")?
            .try_into()
            .context("current directory is not valid UTF-8")?,
    };
    for candidate in current.ancestors() {
        let entry_dir = candidate.join(ENTRY_SOURCE_DIR);
        if entry_dir.is_dir() {
            return Ok(candidate.to_owned());
        }
    }
    bail!("could not find repository root containing {ENTRY_SOURCE_DIR} from {current}",);
}

fn parse_date(text: &str, field_name: &str) -> Result<String> {
    NaiveDate::parse_from_str(text, "%Y-%m-%d")
        .with_context(|| format!("{field_name} must be YYYY-MM-DD"))?;
    Ok(text.to_owned())
}

fn parse_timestamp(text: &str) -> Result<String> {
    DateTime::parse_from_rfc3339(text)
        .with_context(|| format!("published_at must be ISO 8601, got {text}"))?;
    Ok(text.to_owned())
}

fn normalize_heading(line: &str) -> Option<&'static str> {
    let normalized = line
        .trim()
        .trim_end_matches(':')
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase();
    match normalized.as_str() {
        "dossiers" => Some("dossiers"),
        "addenda" => Some("addenda"),
        "ops" | "ops / infra" | "ops/infra" => Some("ops"),
        "lab" | "lab news" => Some("lab"),
        _ => None,
    }
}

fn parse_draft(text: &str) -> Result<DraftParse> {
    let mut sections = Sections::default();
    let mut current_section: Option<&'static str> = None;
    let mut window: Option<UpdateWindow> = None;
    let mut series_number: Option<u32> = None;
    let mut saw_section = false;

    for (index, raw_line) in text.lines().enumerate() {
        let line_number = index + 1;
        let line = raw_line.trim();
        if line.is_empty() {
            continue;
        }

        let parsed_main_number = line
            .strip_prefix("SPCTR-UPDATE-")
            .and_then(|value| value.parse::<u32>().ok());
        if let Some(number) = parsed_main_number {
            if let Some(existing) = series_number {
                if existing != number {
                    bail!("draft line {line_number}: conflicting SPCTR-UPDATE codes");
                }
            }
            series_number = Some(number);
            continue;
        }

        if let Some(window_body) = line.strip_prefix("Window:") {
            let trimmed = window_body.trim();
            let separator = if let Some((start, end)) = trimmed.split_once(" through ") {
                Some((start, end))
            } else {
                trimmed.split_once(" to ")
            };
            let Some((start, end)) = separator else {
                bail!("draft line {line_number}: Window line must use 'through' or 'to'");
            };
            let parsed = UpdateWindow {
                start: parse_date(start.trim(), "window.start")?,
                end: parse_date(end.trim(), "window.end")?,
            };
            if parsed.start > parsed.end {
                bail!("draft line {line_number}: window start must be on or before end");
            }
            if let Some(existing) = &window {
                if existing != &parsed {
                    bail!("draft line {line_number}: conflicting Window lines");
                }
            }
            window = Some(parsed);
            continue;
        }

        if let Some(section) = normalize_heading(line) {
            current_section = Some(section);
            saw_section = true;
            continue;
        }

        if let Some(item) = line.strip_prefix("- ") {
            let Some(section) = current_section else {
                bail!("draft line {line_number}: bullet item must appear under a named section");
            };
            let trimmed = item.trim();
            if trimmed.is_empty() {
                bail!("draft line {line_number}: bullet item cannot be empty");
            }
            sections
                .bucket_mut(section)
                .expect("section normalization must stay in sync")
                .push(trimmed.to_owned());
            continue;
        }

        if saw_section {
            bail!("draft line {line_number}: unsupported content after sections began: {line}");
        }
    }

    if sections.is_empty() {
        bail!("draft must contain at least one section item");
    }
    Ok(DraftParse {
        sections,
        window,
        series_number,
    })
}

fn format_main_update_code(series_number: u32) -> String {
    format!("SPCTR-UPDATE-{series_number:03}")
}

fn default_entry_id(
    kind: UpdateKind,
    stamp: &str,
    window: &UpdateWindow,
    series_number: Option<u32>,
) -> Result<String> {
    match kind {
        UpdateKind::Main => {
            let number = series_number.context("main entries require a series number")?;
            Ok(format!("spctr-update-{number:03}"))
        }
        UpdateKind::Window => {
            let stamp = stamp.replace('-', "");
            Ok(format!(
                "slu-{stamp}-window-{}-to-{}",
                window.start, window.end
            ))
        }
    }
}

fn default_label(
    kind: UpdateKind,
    window: &UpdateWindow,
    series_number: Option<u32>,
) -> Result<String> {
    match kind {
        UpdateKind::Main => Ok(format_main_update_code(
            series_number.context("main entries require a series number")?,
        )),
        UpdateKind::Window => Ok(format!("Window {} to {}", window.start, window.end)),
    }
}

fn default_topic(
    kind: UpdateKind,
    window: &UpdateWindow,
    series_number: Option<u32>,
) -> Result<String> {
    match kind {
        UpdateKind::Main => Ok(format!(
            "weekly / {}",
            format_main_update_code(series_number.context("main entries require a series number")?)
                .to_lowercase()
        )),
        UpdateKind::Window => Ok(format!("weekly / {} to {}", window.start, window.end)),
    }
}

fn default_published_at(stamp: &str) -> String {
    format!("{stamp}T00:00:00Z")
}

fn trimmed_option(value: Option<&str>, field_name: &str) -> Result<Option<String>> {
    let Some(text) = value else {
        return Ok(None);
    };
    let trimmed = text.trim();
    if trimmed.is_empty() {
        bail!("{field_name} must be a non-empty string");
    }
    Ok(Some(trimmed.to_owned()))
}

fn read_body_text(path: Option<&Utf8Path>) -> Result<String> {
    match path {
        Some(body_path) => {
            fs::read_to_string(body_path).with_context(|| format!("failed to read {body_path}"))
        }
        None => {
            if io::stdin().is_terminal() {
                bail!("updates create requires --body-file or piped stdin");
            }
            let mut body = String::new();
            io::stdin()
                .read_to_string(&mut body)
                .context("failed to read update draft from stdin")?;
            Ok(body)
        }
    }
}

fn next_main_series_number(entry_dir: &Utf8Path) -> Result<u32> {
    let mut max_number = 0_u32;
    for entry in fs::read_dir(entry_dir).with_context(|| format!("failed to read {entry_dir}"))? {
        let entry = entry.with_context(|| format!("failed to read {entry_dir}"))?;
        let path = entry.path();
        if path.extension().and_then(|ext| ext.to_str()) != Some("json") {
            continue;
        }
        let raw = fs::read_to_string(&path)
            .with_context(|| format!("failed to read {}", path.display()))?;
        let value: Value = serde_json::from_str(&raw)
            .with_context(|| format!("invalid JSON in {}", path.display()))?;
        let Some(number) = value.get("series_number").and_then(Value::as_u64) else {
            continue;
        };
        let parsed = u32::try_from(number)
            .with_context(|| format!("series_number out of range in {}", path.display()))?;
        max_number = max_number.max(parsed);
    }
    Ok(max_number + 1)
}

fn run_archive_render(repo_root: &Utf8Path, report: bool) -> Result<()> {
    let status = updates_archive::apply_or_check(repo_root, true, report)
        .context("failed to render updates archive")?;
    if status != 0 {
        bail!("updates archive render exited with status {status}");
    }
    Ok(())
}

fn resolve_create_draft(options: CreateOptions) -> Result<ResolvedCreateDraft> {
    let repo_root = discover_repo_root(options.repo_root.as_deref())?;
    let body_text = read_body_text(options.body_file.as_deref())?;
    let draft = parse_draft(&body_text)?;

    let start = options
        .window_start
        .clone()
        .or_else(|| draft.window.as_ref().map(|window| window.start.clone()))
        .context("updates create requires --window-start/--window-end or a draft Window line")?;
    let end = options
        .window_end
        .clone()
        .or_else(|| draft.window.as_ref().map(|window| window.end.clone()))
        .context("updates create requires --window-start/--window-end or a draft Window line")?;
    let window = UpdateWindow {
        start: parse_date(&start, "window.start")?,
        end: parse_date(&end, "window.end")?,
    };
    if window.start > window.end {
        bail!("window.start must be on or before window.end");
    }
    if let Some(draft_window) = &draft.window {
        if draft_window != &window {
            bail!("draft Window line does not match --window-start/--window-end");
        }
    }

    let entry_dir = repo_root.join(ENTRY_SOURCE_DIR);
    let mut series_number = options.series_number;
    if let Some(draft_number) = draft.series_number {
        if let Some(explicit) = series_number {
            if explicit != draft_number {
                bail!("draft SPCTR-UPDATE code does not match --series-number");
            }
        }
        series_number = Some(draft_number);
    }
    if options.kind == UpdateKind::Main && series_number.is_none() {
        series_number = Some(next_main_series_number(&entry_dir)?);
    }
    if options.kind == UpdateKind::Window && series_number.is_some() {
        bail!("window entries cannot define a series number");
    }

    let stamp = parse_date(options.date.as_deref().unwrap_or(&window.end), "date")?;
    let label = match &options.label {
        Some(label) => label.trim().to_owned(),
        None => default_label(options.kind, &window, series_number)?,
    };
    if label.is_empty() {
        bail!("label must be a non-empty string");
    }
    let topic = match &options.topic {
        Some(topic) => topic.trim().to_owned(),
        None => default_topic(options.kind, &window, series_number)?,
    };
    if topic.is_empty() {
        bail!("topic must be a non-empty string");
    }
    let entry_id = match &options.entry_id {
        Some(entry_id) => entry_id.trim().to_owned(),
        None => default_entry_id(options.kind, &stamp, &window, series_number)?,
    };
    if entry_id.is_empty() {
        bail!("id must be a non-empty string");
    }

    let requested_published_at = match &options.published_at {
        Some(text) => Some(parse_timestamp(text)?),
        None => None,
    };

    Ok(ResolvedCreateDraft {
        repo_root,
        entry_path: entry_dir.join(format!("{entry_id}.json")),
        entry_id,
        label,
        topic,
        stamp,
        sections: draft.sections,
        kind: options.kind,
        window,
        series_number,
        force: options.force,
        report: options.report,
        requested_published_at,
        requested_ledger_entry_id: match &options.ledger_entry_id {
            Some(text) => trimmed_option(Some(text), "ledger_entry_id")?,
            None => None,
        },
        requested_zulip_message_id: options.zulip_message_id,
    })
}

fn write_update_entry(
    draft: &ResolvedCreateDraft,
    published_at: &str,
    ledger_entry_id: Option<&str>,
    zulip_message_id: Option<u64>,
) -> Result<()> {
    if draft.entry_path.exists() && !draft.force {
        bail!(
            "entry already exists at {}; rerun with --force to overwrite it",
            draft.entry_path
        );
    }

    let published_at = parse_timestamp(published_at)?;

    if let Some(ledger_id) = ledger_entry_id {
        let trimmed = ledger_id.trim();
        if trimmed.is_empty() {
            bail!("ledger_entry_id must be a non-empty string");
        }
    }

    let payload = UpdateEntryPayload {
        id: draft.entry_id.clone(),
        kind: match draft.kind {
            UpdateKind::Window => "window".to_owned(),
            UpdateKind::Main => "main".to_owned(),
        },
        label: draft.label.clone(),
        date: draft.stamp.clone(),
        published_at,
        topic: draft.topic.clone(),
        window: UpdateWindowPayload {
            start: draft.window.start.clone(),
            end: draft.window.end.clone(),
        },
        series_number: draft.series_number,
        ledger_entry_id: ledger_entry_id.map(|s| s.trim().to_owned()),
        zulip_message_id,
        sections: SectionsPayload {
            dossiers: draft.sections.dossiers.clone(),
            addenda: draft.sections.addenda.clone(),
            ops: draft.sections.ops.clone(),
            lab: draft.sections.lab.clone(),
        },
    };

    let entry_dir = draft
        .entry_path
        .parent()
        .context("entry path is missing a parent directory")?;
    fs::create_dir_all(entry_dir).with_context(|| format!("failed to create {entry_dir}"))?;
    let rendered =
        serde_json::to_string_pretty(&payload).context("failed to serialize update entry")?;
    fs::write(&draft.entry_path, format!("{rendered}\n"))
        .with_context(|| format!("failed to write {}", draft.entry_path))?;
    Ok(())
}

#[derive(Debug, Serialize)]
struct CreateResult {
    path: String,
    id: String,
    label: String,
}

#[derive(Debug, Serialize)]
struct ApproveResult {
    path: String,
    id: String,
    label: String,
    topic: String,
    ledger_entry_id: String,
    zulip_message_id: Option<u64>,
}

fn finalize_update_entry(
    draft: &ResolvedCreateDraft,
    published_at: &str,
    ledger_entry_id: Option<&str>,
    zulip_message_id: Option<u64>,
) -> Result<CreateResult> {
    write_update_entry(draft, published_at, ledger_entry_id, zulip_message_id)?;
    run_archive_render(&draft.repo_root, draft.report)?;
    let rel_path = draft
        .entry_path
        .strip_prefix(&draft.repo_root)
        .unwrap_or(&draft.entry_path)
        .to_string();
    Ok(CreateResult {
        path: rel_path,
        id: draft.entry_id.clone(),
        label: draft.label.clone(),
    })
}

fn resolve_dispatch_url(value: Option<&str>) -> Result<String> {
    client_resolve_dispatch_url(value)
}

fn resolve_dispatch_secret(value: Option<&str>) -> Result<String> {
    client_resolve_dispatch_secret(value)
}

fn render_sections_for_ledger(sections: &Sections) -> String {
    let mut lines = Vec::new();
    for (heading, items) in [
        ("Dossiers:", &sections.dossiers),
        ("Addenda:", &sections.addenda),
        ("Ops:", &sections.ops),
        ("Lab:", &sections.lab),
    ] {
        if items.is_empty() {
            continue;
        }
        lines.push(heading.to_owned());
        for item in items {
            lines.push(format!("- {item}"));
        }
        lines.push(String::new());
    }
    while lines.last().is_some_and(|line| line.is_empty()) {
        lines.pop();
    }
    lines.join("\n")
}

fn post_approved_ledger_entry(
    dispatch_url: &str,
    dispatch_secret: &str,
    topic: &str,
    sections: &Sections,
    requested_by_email: Option<&str>,
    requested_by_name: Option<&str>,
) -> Result<LedgerPostResponse> {
    let response = post_admin_ledger_entry_blocking(
        dispatch_url,
        dispatch_secret,
        &AdminLedgerPostRequest {
            topic: topic.to_owned(),
            body: render_sections_for_ledger(sections),
            requested_by_email: trimmed_option(requested_by_email, "requested_by_email")?,
            requested_by_name: trimmed_option(requested_by_name, "requested_by_name")?,
        },
    )?;
    Ok(LedgerPostResponse {
        entry_id: response.entry_id,
        created_at: response.created_at,
        message_id: response
            .message_id
            .map(u64::try_from)
            .transpose()
            .context("dispatch returned negative Zulip message id")?,
    })
}

pub fn create(options: CreateOptions) -> Result<()> {
    let json = options.json;
    let draft = resolve_create_draft(options)?;
    let published_at = draft
        .requested_published_at
        .clone()
        .unwrap_or_else(|| default_published_at(&draft.stamp));
    let result = finalize_update_entry(
        &draft,
        &published_at,
        draft.requested_ledger_entry_id.as_deref(),
        draft.requested_zulip_message_id,
    )?;
    if json {
        println!("{}", serde_json::to_string_pretty(&result)?);
    } else {
        println!(
            "created={} id={} label={}",
            result.path, result.id, result.label
        );
    }
    Ok(())
}

pub fn approve(options: ApprovalOptions) -> Result<()> {
    let json = options.create.json;
    let dispatch_url = resolve_dispatch_url(options.dispatch_url.as_deref())?;
    let dispatch_secret = resolve_dispatch_secret(options.dispatch_secret.as_deref())?;
    let draft = resolve_create_draft(options.create)?;
    let ledger = post_approved_ledger_entry(
        &dispatch_url,
        &dispatch_secret,
        &draft.topic,
        &draft.sections,
        options.requested_by_email.as_deref(),
        options.requested_by_name.as_deref(),
    )?;
    let published_at = draft
        .requested_published_at
        .clone()
        .unwrap_or_else(|| ledger.created_at.clone());
    let result = finalize_update_entry(
        &draft,
        &published_at,
        Some(&ledger.entry_id),
        ledger.message_id,
    )
    .with_context(|| {
        format!(
            "approved update was already posted to Zulip as ledger entry {}",
            ledger.entry_id
        )
    })?;
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&ApproveResult {
                path: result.path,
                id: result.id,
                label: result.label,
                topic: draft.topic.clone(),
                ledger_entry_id: ledger.entry_id,
                zulip_message_id: ledger.message_id,
            })?
        );
    } else {
        println!(
            "approved topic={} ledger_entry_id={} zulip_message_id={}",
            draft.topic,
            ledger.entry_id,
            ledger
                .message_id
                .map_or_else(|| "null".to_owned(), |value| value.to_string())
        );
    }
    Ok(())
}
