use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use chrono::{DateTime, NaiveDate};
use maud::{html, Markup, DOCTYPE};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;

const ENTRY_SOURCE_DIR: &str = "site/updates/entries";
const INDEX_OUTPUT_PATH: &str = "site/updates/index.html";
const FEED_OUTPUT_PATH: &str = "site/updates/index.json";
const SECTION_ORDER: [&str; 4] = ["dossiers", "addenda", "ops", "lab"];

fn section_title(key: &str) -> &'static str {
    match key {
        "dossiers" => "Dossiers",
        "addenda" => "Addenda",
        "ops" => "Ops / Infra",
        "lab" => "Lab News",
        _ => unreachable!("section key must be validated before rendering"),
    }
}

#[derive(Debug)]
pub struct UpdateArchiveError(String);

impl std::fmt::Display for UpdateArchiveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for UpdateArchiveError {}

#[derive(Clone, Debug, Eq, PartialEq)]
struct UpdateWindow {
    start: String,
    end: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct UpdateEntry {
    id: String,
    kind: String,
    label: String,
    date: String,
    published_at: String,
    topic: String,
    window: UpdateWindow,
    series_number: Option<u32>,
    ledger_entry_id: Option<String>,
    zulip_message_id: Option<u64>,
    sections: BTreeMap<String, Vec<String>>,
}

impl UpdateEntry {
    fn href(&self) -> String {
        format!("updates/{}/", self.id)
    }
}

#[derive(Debug)]
pub struct BuildArtifacts {
    pub feed_json: String,
    pub rendered_files: BTreeMap<Utf8PathBuf, String>,
    pub stale_paths: Vec<Utf8PathBuf>,
}

fn archive_error(path: &Utf8Path, message: impl Into<String>) -> UpdateArchiveError {
    UpdateArchiveError(format!("{path}: {}", message.into()))
}

fn require_string(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<String, UpdateArchiveError> {
    let Some(value) = value else {
        return Err(archive_error(
            path,
            format!("{field_name} must be a non-empty string"),
        ));
    };
    let Some(text) = value.as_str() else {
        return Err(archive_error(
            path,
            format!("{field_name} must be a non-empty string"),
        ));
    };
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err(archive_error(
            path,
            format!("{field_name} must be a non-empty string"),
        ));
    }
    Ok(trimmed.to_owned())
}

fn optional_string(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<Option<String>, UpdateArchiveError> {
    let Some(value) = value else {
        return Ok(None);
    };
    let Some(text) = value.as_str() else {
        return Err(archive_error(
            path,
            format!("{field_name} must be a string"),
        ));
    };
    let trimmed = text.trim();
    if trimmed.is_empty() {
        Ok(None)
    } else {
        Ok(Some(trimmed.to_owned()))
    }
}

fn optional_u32(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<Option<u32>, UpdateArchiveError> {
    let Some(value) = value else {
        return Ok(None);
    };
    let Some(number) = value.as_u64() else {
        return Err(archive_error(
            path,
            format!("{field_name} must be an integer"),
        ));
    };
    let parsed = u32::try_from(number)
        .map_err(|_| archive_error(path, format!("{field_name} must fit in u32")))?;
    Ok(Some(parsed))
}

fn optional_u64(
    value: Option<&Value>,
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<Option<u64>, UpdateArchiveError> {
    let Some(value) = value else {
        return Ok(None);
    };
    let Some(number) = value.as_u64() else {
        return Err(archive_error(
            path,
            format!("{field_name} must be an integer"),
        ));
    };
    Ok(Some(number))
}

fn parse_date(
    value: &str,
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<String, UpdateArchiveError> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d")
        .map_err(|_| archive_error(path, format!("{field_name} must be YYYY-MM-DD")))?;
    Ok(value.to_owned())
}

fn parse_timestamp(
    value: &str,
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<String, UpdateArchiveError> {
    let normalized = value.replace('Z', "+00:00");
    DateTime::parse_from_rfc3339(&normalized)
        .map_err(|_| archive_error(path, format!("{field_name} must be an ISO 8601 timestamp")))?;
    Ok(value.to_owned())
}

fn ensure_only_keys(
    object: &Map<String, Value>,
    allowed: &[&str],
    field_name: &str,
    path: &Utf8Path,
) -> std::result::Result<(), UpdateArchiveError> {
    let allowed: BTreeSet<&str> = allowed.iter().copied().collect();
    let unknown = object
        .keys()
        .filter(|key| !allowed.contains(key.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    if unknown.is_empty() {
        Ok(())
    } else {
        Err(archive_error(
            path,
            format!("unsupported {field_name} keys: {}", unknown.join(", ")),
        ))
    }
}

fn parse_window(
    value: Option<&Value>,
    path: &Utf8Path,
) -> std::result::Result<UpdateWindow, UpdateArchiveError> {
    let Some(value) = value else {
        return Err(archive_error(path, "window must be an object"));
    };
    let Some(object) = value.as_object() else {
        return Err(archive_error(path, "window must be an object"));
    };
    ensure_only_keys(object, &["start", "end"], "window", path)?;
    let start = parse_date(
        &require_string(object.get("start"), "window.start", path)?,
        "window.start",
        path,
    )?;
    let end = parse_date(
        &require_string(object.get("end"), "window.end", path)?,
        "window.end",
        path,
    )?;
    if start > end {
        return Err(archive_error(
            path,
            "window.start must be on or before window.end",
        ));
    }
    Ok(UpdateWindow { start, end })
}

fn parse_sections(
    value: Option<&Value>,
    path: &Utf8Path,
) -> std::result::Result<BTreeMap<String, Vec<String>>, UpdateArchiveError> {
    let Some(value) = value else {
        return Err(archive_error(path, "sections must be an object"));
    };
    let Some(object) = value.as_object() else {
        return Err(archive_error(path, "sections must be an object"));
    };
    ensure_only_keys(object, &SECTION_ORDER, "section", path)?;
    let mut parsed = BTreeMap::new();
    let mut total_items = 0usize;
    for key in SECTION_ORDER {
        let raw_items = object
            .get(key)
            .and_then(Value::as_array)
            .ok_or_else(|| archive_error(path, format!("sections.{key} must be a list")))?;
        let mut items = Vec::with_capacity(raw_items.len());
        for (index, raw_item) in raw_items.iter().enumerate() {
            items.push(require_string(
                Some(raw_item),
                &format!("sections.{key}[{index}]"),
                path,
            )?);
        }
        total_items += items.len();
        parsed.insert(key.to_owned(), items);
    }
    if total_items == 0 {
        return Err(archive_error(
            path,
            "sections must contain at least one item",
        ));
    }
    Ok(parsed)
}

fn load_entry(path: &Utf8Path) -> std::result::Result<UpdateEntry, UpdateArchiveError> {
    let raw = fs::read_to_string(path)
        .map_err(|error| archive_error(path, format!("failed to read entry: {error}")))?;
    let value: Value = serde_json::from_str(&raw)
        .map_err(|error| archive_error(path, format!("invalid JSON: {error}")))?;
    let Some(object) = value.as_object() else {
        return Err(archive_error(path, "entry root must be an object"));
    };
    ensure_only_keys(
        object,
        &[
            "id",
            "kind",
            "label",
            "date",
            "published_at",
            "topic",
            "window",
            "series_number",
            "ledger_entry_id",
            "zulip_message_id",
            "sections",
        ],
        "top-level",
        path,
    )?;
    let id = require_string(object.get("id"), "id", path)?;
    let kind = require_string(object.get("kind"), "kind", path)?;
    if kind != "main" && kind != "window" {
        return Err(archive_error(path, "kind must be 'main' or 'window'"));
    }
    let label = require_string(object.get("label"), "label", path)?;
    let date = parse_date(
        &require_string(object.get("date"), "date", path)?,
        "date",
        path,
    )?;
    let published_at = parse_timestamp(
        &require_string(object.get("published_at"), "published_at", path)?,
        "published_at",
        path,
    )?;
    let topic = require_string(object.get("topic"), "topic", path)?;
    let window = parse_window(object.get("window"), path)?;
    let series_number = optional_u32(object.get("series_number"), "series_number", path)?;
    match (kind.as_str(), series_number) {
        ("main", Some(number)) if number > 0 => {}
        ("main", _) => {
            return Err(archive_error(
                path,
                "main entries require a positive series_number",
            ));
        }
        ("window", Some(_)) => {
            return Err(archive_error(
                path,
                "only main entries may define series_number",
            ));
        }
        ("window", None) => {}
        _ => unreachable!("kind was validated above"),
    }
    let ledger_entry_id = optional_string(object.get("ledger_entry_id"), "ledger_entry_id", path)?;
    let zulip_message_id = optional_u64(object.get("zulip_message_id"), "zulip_message_id", path)?;
    let sections = parse_sections(object.get("sections"), path)?;
    if path.file_stem() != Some(id.as_str()) {
        return Err(archive_error(
            path,
            format!("filename must match entry id {id}"),
        ));
    }
    Ok(UpdateEntry {
        id,
        kind,
        label,
        date,
        published_at,
        topic,
        window,
        series_number,
        ledger_entry_id,
        zulip_message_id,
        sections,
    })
}

fn load_update_entries(repo_root: &Utf8Path) -> Result<Vec<UpdateEntry>> {
    let entry_root = repo_root.join(ENTRY_SOURCE_DIR);
    if !entry_root.is_dir() {
        bail!("missing update entry directory: {entry_root}");
    }
    let mut entries = Vec::new();
    for entry in
        fs::read_dir(&entry_root).with_context(|| format!("failed to read {entry_root}"))?
    {
        let entry = entry.with_context(|| format!("failed to read {entry_root}"))?;
        let path = Utf8PathBuf::from_path_buf(entry.path()).map_err(|path| {
            anyhow::anyhow!("non-UTF-8 path in update entries: {}", path.display())
        })?;
        if path.extension() != Some("json") {
            continue;
        }
        entries.push(load_entry(&path).map_err(anyhow::Error::new)?);
    }
    if entries.is_empty() {
        bail!("no update entries found in {entry_root}");
    }
    entries.sort_by(|left, right| {
        right
            .published_at
            .cmp(&left.published_at)
            .then_with(|| right.id.cmp(&left.id))
    });
    Ok(entries)
}

fn section_count_labels(entry: &UpdateEntry) -> String {
    SECTION_ORDER
        .iter()
        .filter_map(|key| {
            let count = entry.sections.get(*key).map_or(0usize, Vec::len);
            (count > 0).then(|| format!("{count} {}", section_title(key).to_lowercase()))
        })
        .collect::<Vec<_>>()
        .join(" | ")
}

fn format_main_update_code(series_number: u32) -> String {
    format!("SPCTR-UPDATE-{series_number:03}")
}

enum MetaValue {
    Text(String),
    Code(String),
}

fn entry_meta_rows(entry: &UpdateEntry) -> Vec<(String, MetaValue)> {
    let mut rows = vec![
        ("ID".to_owned(), MetaValue::Code(entry.id.clone())),
        (
            "Published".to_owned(),
            MetaValue::Text(entry.published_at.clone()),
        ),
        (
            "Window".to_owned(),
            MetaValue::Text(format!("{} to {}", entry.window.start, entry.window.end)),
        ),
    ];
    if let Some(series_number) = entry.series_number {
        rows.insert(
            2,
            (
                "Code".to_owned(),
                MetaValue::Text(format_main_update_code(series_number)),
            ),
        );
    }
    if let Some(ledger_entry_id) = &entry.ledger_entry_id {
        rows.push((
            "Ledger Entry".to_owned(),
            MetaValue::Code(ledger_entry_id.clone()),
        ));
    }
    if let Some(zulip_message_id) = entry.zulip_message_id {
        rows.push((
            "Zulip Message".to_owned(),
            MetaValue::Code(zulip_message_id.to_string()),
        ));
    }
    rows
}

fn render_meta_list(entry: &UpdateEntry) -> Markup {
    html! {
        ul class="update-meta-list" {
            @for (label, value) in entry_meta_rows(entry) {
                li class="update-meta-item" {
                    span class="update-meta-label" { (label) }
                    @match value {
                        MetaValue::Text(text) => span { (text) },
                        MetaValue::Code(text) => code class="update-code" { (text) },
                    }
                }
            }
        }
    }
}

fn render_entry_section(entry: &UpdateEntry, key: &str) -> Markup {
    let Some(items) = entry.sections.get(key) else {
        return html! {};
    };
    if items.is_empty() {
        return html! {};
    }
    html! {
        section class="section-block" id=(key) {
            div class="site-section-title" { (section_title(key)) }
            ul class="update-section-list" {
                @for item in items {
                    li { (item) }
                }
            }
        }
    }
}

fn page_shell(title: &str, root_prefix: &str, body: Markup) -> String {
    let mut rendered = html! {
        (DOCTYPE)
        html lang="en" {
            head {
                meta charset="UTF-8";
                meta name="viewport" content="width=device-width, initial-scale=1.0";
                meta name="color-scheme" content="light";
                title { (title) " | SPECTER Labs" }
                link rel="icon" href=(format!("{root_prefix}/assets/logo-black.svg")) type="image/svg+xml";
                link rel="stylesheet" href=(format!("{root_prefix}/style.css"));
            }
            body {
                div class="site-shell" {
                    header class="site-topnav" {
                        a class="site-brand" href=(format!("{root_prefix}/")) {
                            img src=(format!("{root_prefix}/assets/logo-black.svg")) alt="SPECTER Labs logo" class="logo";
                            span class="site-brand-name" { "SPECTER LABS" }
                        }
                        nav class="site-topnav-links" aria-label="Site navigation" {
                            a class="nav-link" href=(format!("{root_prefix}/dossiers/")) { "Dossiers" }
                            a class="nav-link" href=(format!("{root_prefix}/addenda/")) { "Addenda" }
                            a class="nav-link" href=(format!("{root_prefix}/blog/")) { "Blog" }
                            a class="nav-link" href=(format!("{root_prefix}/cabinet/")) { "Cabinet" }
                        }
                    }
                    div class="site-rules" aria-hidden="true" {
                        div class="site-rule strong" {}
                        div class="site-rule" {}
                    }
                    main class="site-main" {
                        (body)
                    }
                }
            }
        }
    }
    .into_string();
    rendered.push('\n');
    rendered
}

fn render_index_page(entries: &[UpdateEntry]) -> String {
    let body = html! {
        section class="section-block" id="overview" {
            div class="site-page-title" { "Update Archive" }
            p class="section-lead" {
                "Approved rollups and notebook-style windows promoted into stable public artifacts."
            }
            p class="section-lead" {
                "Internal dispatch ledger traffic stays separate; only curated entries land here."
            }
        }
        section class="section-block" id="entries" {
            div class="update-list" {
                @for entry in entries {
                    article class="update-card" {
                        div class="update-card-header" {
                            a class="update-card-title" href=(format!("./{}/", entry.id)) { (&entry.label) }
                            span class="badge" { (&entry.date) }
                        }
                        p class="update-summary-line" { (&entry.window.start) " to " (&entry.window.end) }
                        p class="update-summary-line" { (section_count_labels(entry)) }
                    }
                }
            }
        }
    };
    page_shell("Updates", "..", body)
}

fn render_entry_page(entry: &UpdateEntry) -> String {
    let body = html! {
        section class="section-block" id="overview" {
            div class="site-page-title" { (&entry.label) }
            p class="section-lead" {
                "Canonical archive entry for " (&entry.window.start) " to " (&entry.window.end) "."
            }
            (render_meta_list(entry))
        }
        @for key in SECTION_ORDER {
            @if entry.sections.get(key).is_some_and(|items| !items.is_empty()) {
                (render_entry_section(entry, key))
            }
        }
    };
    page_shell(&entry.label, "../..", body)
}

fn feed_item(entry: &UpdateEntry) -> Value {
    let mut payload = Map::new();
    payload.insert("id".to_owned(), Value::String(entry.id.clone()));
    payload.insert("kind".to_owned(), Value::String(entry.kind.clone()));
    payload.insert("label".to_owned(), Value::String(entry.label.clone()));
    payload.insert("date".to_owned(), Value::String(entry.date.clone()));
    payload.insert(
        "published_at".to_owned(),
        Value::String(entry.published_at.clone()),
    );
    payload.insert("topic".to_owned(), Value::String(entry.topic.clone()));
    payload.insert(
        "href".to_owned(),
        Value::String(format!("/{}", entry.href())),
    );
    payload.insert(
        "window".to_owned(),
        Value::Object(
            [
                (
                    "start".to_owned(),
                    Value::String(entry.window.start.clone()),
                ),
                ("end".to_owned(), Value::String(entry.window.end.clone())),
            ]
            .into_iter()
            .collect(),
        ),
    );
    payload.insert(
        "sections".to_owned(),
        Value::Object(
            SECTION_ORDER
                .iter()
                .map(|key| {
                    (
                        (*key).to_owned(),
                        Value::Array(
                            entry
                                .sections
                                .get(*key)
                                .cloned()
                                .unwrap_or_default()
                                .into_iter()
                                .map(Value::String)
                                .collect(),
                        ),
                    )
                })
                .collect(),
        ),
    );
    if let Some(series_number) = entry.series_number {
        payload.insert("series_number".to_owned(), Value::from(series_number));
    }
    if let Some(ledger_entry_id) = &entry.ledger_entry_id {
        payload.insert(
            "ledger_entry_id".to_owned(),
            Value::String(ledger_entry_id.clone()),
        );
    }
    if let Some(zulip_message_id) = entry.zulip_message_id {
        payload.insert("zulip_message_id".to_owned(), Value::from(zulip_message_id));
    }
    Value::Object(payload)
}

pub fn build_update_artifacts(repo_root: &Utf8Path) -> Result<BuildArtifacts> {
    let entries = load_update_entries(repo_root)?;
    let feed_json = serde_json::to_string_pretty(&Value::Object(
        [
            ("version".to_owned(), Value::from(1)),
            (
                "entries".to_owned(),
                Value::Array(entries.iter().map(feed_item).collect()),
            ),
        ]
        .into_iter()
        .collect(),
    ))
    .context("failed to serialize update feed")?
        + "\n";

    let mut rendered_files = BTreeMap::new();
    rendered_files.insert(
        repo_root.join(INDEX_OUTPUT_PATH),
        render_index_page(&entries),
    );
    rendered_files.insert(repo_root.join(FEED_OUTPUT_PATH), feed_json.clone());
    for entry in &entries {
        rendered_files.insert(
            repo_root.join(format!("site/updates/{}/index.html", entry.id)),
            render_entry_page(entry),
        );
    }

    let updates_root = repo_root.join("site/updates");
    let expected_entry_dirs = entries
        .iter()
        .map(|entry| updates_root.join(&entry.id))
        .collect::<BTreeSet<_>>();
    let stale_paths = if updates_root.exists() {
        fs::read_dir(&updates_root)
            .with_context(|| format!("failed to read {updates_root}"))?
            .filter_map(|entry| {
                let entry = entry.ok()?;
                let path = Utf8PathBuf::from_path_buf(entry.path()).ok()?;
                if !path.is_dir()
                    || path.file_name() == Some("entries")
                    || expected_entry_dirs.contains(&path)
                {
                    None
                } else {
                    Some(path)
                }
            })
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };

    Ok(BuildArtifacts {
        feed_json,
        rendered_files,
        stale_paths,
    })
}

pub fn apply_or_check(repo_root: &Utf8Path, write: bool, report: bool) -> Result<i32> {
    let artifacts = build_update_artifacts(repo_root)?;
    let mut changed_files = Vec::new();

    for (path, rendered) in &artifacts.rendered_files {
        let current = match fs::read_to_string(path) {
            Ok(text) => text,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
            Err(error) => {
                return Err(error).with_context(|| format!("failed to read {path}"));
            }
        };
        if current != *rendered {
            changed_files.push(path.clone());
            if write {
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)
                        .with_context(|| format!("failed to create {parent}"))?;
                }
                fs::write(path, rendered).with_context(|| format!("failed to write {path}"))?;
            }
        } else if report {
            println!("ok {}", path.strip_prefix(repo_root).unwrap_or(path));
        }
    }

    for path in &artifacts.stale_paths {
        changed_files.push(path.clone());
        if write {
            fs::remove_dir_all(path)
                .with_context(|| format!("failed to remove stale archive path {path}"))?;
        } else if report {
            println!("stale {}", path.strip_prefix(repo_root).unwrap_or(path));
        }
    }

    if report {
        for path in &changed_files {
            let marker = if artifacts.stale_paths.contains(path) {
                if write {
                    "removed"
                } else {
                    "stale"
                }
            } else {
                "updated"
            };
            println!("{marker} {}", path.strip_prefix(repo_root).unwrap_or(path));
        }
    }

    if changed_files.is_empty() || write {
        Ok(0)
    } else {
        Ok(1)
    }
}
