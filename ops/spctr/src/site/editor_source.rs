use std::fs;
use std::io::Write;

use anyhow::{bail, Context, Result};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::Regex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tempfile::NamedTempFile;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ResolvedSource {
    pub source: String,
    pub label: String,
    pub value: String,
}

#[derive(Debug)]
pub struct AppliedEdit {
    pub path: Utf8PathBuf,
    pub original: String,
    updated: String,
}

#[derive(Debug)]
pub struct ElementHint {
    pub tag_name: String,
    pub class_name: String,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum SourceKind {
    HtmlText,
    MarkdownText,
    MarkdownCode,
    MarkdownLinkText,
    QuotedString,
}

#[derive(Debug, Serialize, Deserialize)]
struct SourceToken {
    version: u8,
    path: String,
    start: usize,
    end: usize,
    file_sha256: String,
    value: String,
    kind: SourceKind,
}

#[derive(Clone, Debug)]
struct Candidate {
    path: Utf8PathBuf,
    start: usize,
    end: usize,
    score: u16,
}

pub fn resolve(
    repo_root: &Utf8Path,
    page: &str,
    value: &str,
    hint: Option<&ElementHint>,
) -> Result<ResolvedSource> {
    let value = value.trim();
    if value.is_empty() {
        bail!("empty text has no editable source");
    }

    let files = editable_files(repo_root)?;
    let mut candidates = find_candidates(repo_root, &files, page, value, false, false)?;
    if candidates.is_empty() && value.chars().any(char::is_whitespace) {
        candidates = find_candidates(repo_root, &files, page, value, true, false)?;
    }
    if candidates.is_empty() && value.is_ascii() {
        candidates = find_candidates(repo_root, &files, page, value, false, true)?;
    }
    if candidates.is_empty() && value.is_ascii() && value.chars().any(char::is_whitespace) {
        candidates = find_candidates(repo_root, &files, page, value, true, true)?;
    }
    candidates.retain(|candidate| candidate.score > 0);

    let Some(best_score) = candidates.iter().map(|candidate| candidate.score).max() else {
        bail!("no canonical authored source contains this text");
    };
    candidates.retain(|candidate| candidate.score == best_score);
    if candidates.len() > 1 {
        disambiguate_with_element_hint(repo_root, &mut candidates, hint)?;
    }
    if candidates.len() != 1 {
        let labels = candidates
            .iter()
            .take(4)
            .map(|candidate| candidate.path.as_str())
            .collect::<Vec<_>>()
            .join(", ");
        bail!("authored text is ambiguous across: {labels}");
    }

    let candidate = candidates.pop().expect("one candidate retained");
    let absolute = repo_root.join(&candidate.path);
    let text = fs::read_to_string(&absolute)
        .with_context(|| format!("failed to read editable source {absolute}"))?;
    let source_value = normalize_whitespace(&text[candidate.start..candidate.end]);
    let kind = kind_for_candidate(&candidate.path, &text, candidate.start, candidate.end, hint)
        .ok_or_else(|| anyhow::anyhow!("unsupported editable source: {}", candidate.path))?;
    let token = SourceToken {
        version: 1,
        path: candidate.path.to_string(),
        start: candidate.start,
        end: candidate.end,
        file_sha256: sha256(text.as_bytes()),
        value: source_value.clone(),
        kind,
    };
    Ok(ResolvedSource {
        source: URL_SAFE_NO_PAD.encode(serde_json::to_vec(&token)?),
        label: candidate.path.to_string(),
        value: source_value,
    })
}

pub fn apply(
    repo_root: &Utf8Path,
    source: &str,
    old_value: &str,
    new_value: &str,
) -> Result<AppliedEdit> {
    let bytes = URL_SAFE_NO_PAD
        .decode(source)
        .context("invalid site editor source token")?;
    let token: SourceToken =
        serde_json::from_slice(&bytes).context("invalid site editor source token")?;
    if token.version != 1 {
        bail!("unsupported site editor source token version");
    }
    if token.value != old_value {
        bail!("stale edit: displayed text changed since source resolution");
    }

    let relative = Utf8Path::new(&token.path);
    if !is_safe_relative_path(relative) || !is_editable_path(relative) {
        bail!("source path is not an editable site source: {relative}");
    }
    if !path_supports_kind(relative, token.kind) {
        bail!("source token type does not match editable source: {relative}");
    }
    let path = repo_root.join(relative);
    if fs::symlink_metadata(&path)
        .with_context(|| format!("failed to inspect editable source {path}"))?
        .file_type()
        .is_symlink()
    {
        bail!("editable source must not be a symbolic link: {relative}");
    }
    let canonical_root = fs::canonicalize(repo_root)
        .with_context(|| format!("failed to resolve repository root {repo_root}"))?;
    let canonical_path = fs::canonicalize(&path)
        .with_context(|| format!("failed to resolve editable source {path}"))?;
    if !canonical_path.starts_with(&canonical_root) {
        bail!("editable source escaped repository root: {relative}");
    }

    let original = fs::read_to_string(&path)
        .with_context(|| format!("failed to read editable source {path}"))?;
    if sha256(original.as_bytes()) != token.file_sha256 {
        bail!("stale edit: source file changed since source resolution");
    }
    if token.start > token.end
        || token.end > original.len()
        || !original.is_char_boundary(token.start)
        || !original.is_char_boundary(token.end)
    {
        bail!("stale edit: source range is no longer valid");
    }
    let current = &original[token.start..token.end];
    if normalize_whitespace(current) != normalize_whitespace(old_value) {
        bail!("stale edit: source text changed since source resolution");
    }

    let replacement = encode_replacement(token.kind, new_value)?;
    let mut updated = String::with_capacity(original.len() + replacement.len());
    updated.push_str(&original[..token.start]);
    updated.push_str(&replacement);
    updated.push_str(&original[token.end..]);
    atomic_write(&path, updated.as_bytes())?;
    Ok(AppliedEdit {
        path,
        original,
        updated,
    })
}

pub fn restore(edit: &AppliedEdit) -> Result<()> {
    let current = fs::read_to_string(&edit.path)
        .with_context(|| format!("failed to read edited source {} for rollback", edit.path))?;
    if current != edit.updated {
        bail!(
            "edited source changed concurrently; refusing to overwrite it during rollback: {}",
            edit.path
        );
    }
    atomic_write(&edit.path, edit.original.as_bytes())
        .with_context(|| format!("failed to restore edited source {}", edit.path))
}

fn find_candidates(
    repo_root: &Utf8Path,
    files: &[Utf8PathBuf],
    page: &str,
    value: &str,
    flexible_whitespace: bool,
    case_insensitive: bool,
) -> Result<Vec<Candidate>> {
    let lookup_value = if case_insensitive {
        value.to_ascii_lowercase()
    } else {
        value.to_owned()
    };
    let pattern = flexible_whitespace
        .then(|| {
            let words = lookup_value
                .split_whitespace()
                .map(regex_lite::escape)
                .collect::<Vec<_>>();
            Regex::new(&words.join(r"\s+")).context("invalid text lookup pattern")
        })
        .transpose()?;
    let mut candidates = Vec::new();
    for relative in files {
        let path = repo_root.join(relative);
        let text = fs::read_to_string(&path)
            .with_context(|| format!("failed to read editable source {path}"))?;
        let searchable = if case_insensitive {
            text.to_ascii_lowercase()
        } else {
            text.clone()
        };
        if let Some(pattern) = &pattern {
            for matched in pattern.find_iter(&searchable) {
                push_candidate(
                    &mut candidates,
                    page,
                    relative,
                    &text,
                    matched.start(),
                    matched.end(),
                );
            }
        } else {
            for (start, _) in searchable.match_indices(&lookup_value) {
                push_candidate(
                    &mut candidates,
                    page,
                    relative,
                    &text,
                    start,
                    start + lookup_value.len(),
                );
            }
        }
    }
    Ok(candidates)
}

fn push_candidate(
    candidates: &mut Vec<Candidate>,
    page: &str,
    relative: &Utf8Path,
    text: &str,
    start: usize,
    end: usize,
) {
    if candidate_is_text(relative, text, start, end) {
        candidates.push(Candidate {
            path: relative.to_owned(),
            start,
            end,
            score: page_score(page, relative) + projection_bonus(page, relative, text, start),
        });
    }
}

fn editable_files(repo_root: &Utf8Path) -> Result<Vec<Utf8PathBuf>> {
    let mut files = Vec::new();
    collect_files(repo_root, repo_root, &mut files)?;
    files.retain(|path| is_editable_path(path));
    files.sort();
    Ok(files)
}

fn collect_files(
    root: &Utf8Path,
    directory: &Utf8Path,
    files: &mut Vec<Utf8PathBuf>,
) -> Result<()> {
    for entry in fs::read_dir(directory).with_context(|| format!("failed to read {directory}"))? {
        let entry = entry?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|path| anyhow::anyhow!("non-UTF-8 site path: {}", path.display()))?;
        let relative = path
            .strip_prefix(root)
            .context("editable source escaped repository root")?;
        if entry.file_type()?.is_dir() {
            if should_descend(relative) {
                collect_files(root, &path, files)?;
            }
        } else if entry.file_type()?.is_file() {
            files.push(relative.to_owned());
        }
    }
    Ok(())
}

fn should_descend(path: &Utf8Path) -> bool {
    if path.components().count() == 1 {
        return matches!(path.as_str(), "site" | "dossiers" | "addenda");
    }
    !path.components().any(|part| {
        matches!(
            part.as_str(),
            ".git" | ".jj" | "node_modules" | "target" | "build" | "public" | "data"
        )
    })
}

fn is_editable_path(path: &Utf8Path) -> bool {
    let text = path.as_str();
    let extension = path.extension().unwrap_or_default();
    if (text.starts_with("dossiers/") || text.starts_with("addenda/"))
        && (path.file_name() == Some("spctr.toml")
            || (text.contains("/docs/") && extension == "md"))
    {
        return true;
    }
    if text.starts_with("site/templates/") && extension == "html" {
        return true;
    }
    if text.starts_with("site/blog/") {
        return (path.file_name() == Some("index.md") && extension == "md")
            || path.file_name() == Some("pandoc-template.html");
    }
    if text.starts_with("site/research-notes/") {
        return path.file_name() == Some("index.md")
            || path.file_name() == Some("pandoc-template.html");
    }
    if text.starts_with("site/updates/entries/") && extension == "json" {
        return true;
    }
    if matches!(
        text,
        "site/cabinet/cabinet-template.html" | "site/cabinet/index-template.html"
    ) {
        return true;
    }
    if text.starts_with("site/dossiers/") {
        return extension == "html" && path.file_name() == Some("showcase.html");
    }
    false
}

fn is_safe_relative_path(path: &Utf8Path) -> bool {
    !path.is_absolute()
        && !path.as_str().contains('\\')
        && path
            .as_str()
            .split('/')
            .all(|component| !component.is_empty() && component != "." && component != "..")
}

fn page_score(page: &str, source: &Utf8Path) -> u16 {
    let page = page.trim_matches('/');
    let source = source.as_str();
    if page.is_empty() && source == "site/templates/index.html" {
        return 100;
    }
    if page.is_empty() && source.ends_with("/spctr.toml") {
        return 60;
    }
    if page.is_empty() && source.starts_with("site/blog/") && source.ends_with("/index.md") {
        return 50;
    }
    if page == "dossiers" && source == "site/templates/dossiers/index.html" {
        return 100;
    }
    if page == "dossiers" && source.starts_with("dossiers/") && source.ends_with("/spctr.toml") {
        return 60;
    }
    if page == "addenda" && source == "site/templates/addenda/index.html" {
        return 100;
    }
    if page == "addenda" && source.starts_with("addenda/") && source.ends_with("/spctr.toml") {
        return 60;
    }
    if page == "blog" && source == "site/templates/blog/index.html" {
        return 100;
    }
    if page == "blog" && source.starts_with("site/blog/") && source.ends_with("/index.md") {
        return 60;
    }
    if page == "research-notes" && source == "site/templates/research-notes/index.html" {
        return 100;
    }
    if page == "research-notes"
        && source.starts_with("site/research-notes/")
        && source.ends_with("/index.md")
    {
        return 60;
    }
    if page == "sitemap" && source == "site/templates/sitemap/index.html" {
        return 100;
    }
    if page == "updates" && source.starts_with("site/updates/entries/") {
        return 60;
    }
    if let Some(slug) = page.strip_prefix("blog/") {
        if source == format!("site/blog/{slug}/index.md") {
            return 110;
        }
        if source == "site/blog/pandoc-template.html" {
            return 100;
        }
    }
    if let Some(slug) = page.strip_prefix("research-notes/") {
        if source == format!("site/research-notes/{slug}/index.md") {
            return 110;
        }
        if source == "site/research-notes/pandoc-template.html" {
            return 100;
        }
    }
    if let Some(slug) = page.strip_prefix("dossiers/") {
        if source == format!("dossiers/{slug}/spctr.toml") {
            return 110;
        }
        if source == format!("site/templates/dossiers/{slug}/index.html")
            || source == format!("site/dossiers/{slug}/showcase.html")
        {
            return 100;
        }
    }
    if let Some(slug) = page.strip_prefix("updates/") {
        if source == format!("site/updates/entries/{slug}.json") {
            return 110;
        }
    }
    if let Some(rest) = page.strip_prefix("cabinet/") {
        let mut parts = rest.split('/');
        let project = parts.next().unwrap_or_default();
        let document = parts.collect::<Vec<_>>().join("/");
        if source == format!("dossiers/{project}/docs/{document}.md")
            || source == format!("addenda/{project}/docs/{document}.md")
        {
            return 120;
        }
        if source == format!("dossiers/{project}/spctr.toml")
            || source == format!("addenda/{project}/spctr.toml")
        {
            return 100;
        }
        if source.starts_with("site/cabinet/") {
            return 90;
        }
    }
    0
}

fn projection_bonus(page: &str, source: &Utf8Path, text: &str, start: usize) -> u16 {
    if !matches!(page.trim_matches('/'), "" | "blog" | "research-notes")
        || source.extension() != Some("md")
        || !text.starts_with("---\n")
    {
        return 0;
    }
    text[4..]
        .find("\n---")
        .map_or(0, |end| u16::from(start < end + 4) * 5)
}

fn source_kind(path: &Utf8Path) -> Option<SourceKind> {
    match path.extension()? {
        "html" => Some(SourceKind::HtmlText),
        "md" => Some(SourceKind::MarkdownText),
        "toml" | "json" => Some(SourceKind::QuotedString),
        _ => None,
    }
}

fn path_supports_kind(path: &Utf8Path, kind: SourceKind) -> bool {
    matches!(
        (path.extension(), kind),
        (Some("html"), SourceKind::HtmlText)
            | (
                Some("md"),
                SourceKind::MarkdownText | SourceKind::MarkdownCode | SourceKind::MarkdownLinkText
            )
            | (Some("toml" | "json"), SourceKind::QuotedString)
    )
}

fn kind_for_candidate(
    path: &Utf8Path,
    text: &str,
    start: usize,
    end: usize,
    hint: Option<&ElementHint>,
) -> Option<SourceKind> {
    let base = source_kind(path)?;
    if base != SourceKind::MarkdownText {
        return Some(base);
    }
    let tag = hint
        .map(|value| value.tag_name.as_str())
        .unwrap_or_default();
    if tag.eq_ignore_ascii_case("code") && markdown_code_context(text, start, end) {
        return Some(SourceKind::MarkdownCode);
    }
    if tag.eq_ignore_ascii_case("a") && markdown_link_context(text, start, end) {
        return Some(SourceKind::MarkdownLinkText);
    }
    Some(SourceKind::MarkdownText)
}

fn markdown_code_context(text: &str, start: usize, end: usize) -> bool {
    let line_start = text[..start].rfind('\n').map_or(0, |index| index + 1);
    let line_end = text[end..]
        .find('\n')
        .map_or(text.len(), |index| end + index);
    let before_on_line = &text[line_start..start];
    let after_on_line = &text[end..line_end];
    let inside_inline = before_on_line.contains('`') && after_on_line.contains('`');
    let inside_fenced = text[..start].matches("```").count() % 2 == 1
        || text[..start].matches("~~~").count() % 2 == 1;
    let inside_indented = before_on_line.starts_with("    ");
    inside_inline || inside_fenced || inside_indented
}

fn markdown_link_context(text: &str, start: usize, end: usize) -> bool {
    let line_start = text[..start].rfind('\n').map_or(0, |index| index + 1);
    let line_end = text[end..]
        .find('\n')
        .map_or(text.len(), |index| end + index);
    let before = &text[line_start..start];
    let after = &text[end..line_end];
    let Some(open) = before.rfind('[') else {
        return false;
    };
    if before.rfind(']').is_some_and(|close| close > open) {
        return false;
    }
    let Some(close) = after.find("](") else {
        return false;
    };
    after.find('[').is_none_or(|next_open| close < next_open)
}

fn candidate_is_text(path: &Utf8Path, text: &str, start: usize, end: usize) -> bool {
    match source_kind(path) {
        Some(SourceKind::HtmlText) => {
            let previous_open = text[..start].rfind('<');
            let previous_close = text[..start].rfind('>');
            previous_close > previous_open && !text[start..end].contains(['<', '>'])
        }
        Some(SourceKind::QuotedString) => inside_quoted_string(text, start, end),
        Some(
            SourceKind::MarkdownText | SourceKind::MarkdownCode | SourceKind::MarkdownLinkText,
        ) => true,
        None => false,
    }
}

fn inside_quoted_string(text: &str, start: usize, end: usize) -> bool {
    let line_start = text[..start].rfind('\n').map_or(0, |index| index + 1);
    let line_end = text[end..]
        .find('\n')
        .map_or(text.len(), |index| end + index);
    let before = &text[line_start..start];
    let after = &text[end..line_end];
    let Some((_, quote)) = before.rmatch_indices('"').next() else {
        return false;
    };
    after.contains(quote)
}

fn disambiguate_with_element_hint(
    repo_root: &Utf8Path,
    candidates: &mut Vec<Candidate>,
    hint: Option<&ElementHint>,
) -> Result<()> {
    let Some(hint) = hint else {
        return Ok(());
    };
    let tag = hint.tag_name.to_ascii_lowercase();
    let mut tagged = Vec::new();
    for candidate in candidates.iter() {
        let text = fs::read_to_string(repo_root.join(&candidate.path))?;
        let matches = match source_kind(&candidate.path) {
            Some(SourceKind::HtmlText) => {
                html_tag_for_candidate(&text, candidate.start).is_some_and(|found| found == tag)
            }
            Some(SourceKind::MarkdownText) if tag.starts_with('h') => markdown_heading_matches(
                &text,
                candidate.start,
                tag.strip_prefix('h').and_then(|value| value.parse().ok()),
            ),
            Some(SourceKind::MarkdownText) if tag == "code" => {
                markdown_code_context(&text, candidate.start, candidate.end)
            }
            Some(SourceKind::MarkdownText) if tag == "a" => {
                markdown_link_context(&text, candidate.start, candidate.end)
            }
            _ => false,
        };
        if matches {
            tagged.push(candidate.clone());
        }
    }
    if !tagged.is_empty() {
        *candidates = tagged;
    }

    if candidates.len() > 1 && !hint.class_name.trim().is_empty() {
        let classes = hint.class_name.split_whitespace().collect::<Vec<_>>();
        let filtered = candidates
            .iter()
            .filter(|candidate| {
                let Ok(text) = fs::read_to_string(repo_root.join(&candidate.path)) else {
                    return false;
                };
                html_opening_tag(&text, candidate.start).is_some_and(|opening| {
                    let authored = html_class_tokens(opening);
                    classes.iter().all(|class| authored.contains(class))
                })
            })
            .cloned()
            .collect::<Vec<_>>();
        if !filtered.is_empty() {
            *candidates = filtered;
        }
    }
    if candidates.len() > 1 {
        let titled = candidates
            .iter()
            .filter(|candidate| {
                let Ok(text) = fs::read_to_string(repo_root.join(&candidate.path)) else {
                    return false;
                };
                source_kind(&candidate.path) == Some(SourceKind::QuotedString)
                    && quoted_field_name(&text, candidate.start) == Some("title")
            })
            .cloned()
            .collect::<Vec<_>>();
        if titled.len() == 1 {
            *candidates = titled;
        }
    }
    Ok(())
}

fn quoted_field_name(text: &str, start: usize) -> Option<&str> {
    let line_start = text[..start].rfind('\n').map_or(0, |index| index + 1);
    let prefix = text[line_start..start].trim_start();
    let delimiter = prefix.find(['=', ':'])?;
    Some(prefix[..delimiter].trim().trim_matches('"'))
}

fn html_opening_tag(text: &str, start: usize) -> Option<&str> {
    let close = text[..start].rfind('>')?;
    let open = text[..close].rfind('<')?;
    let opening = &text[open + 1..close];
    (!opening.starts_with('/')).then_some(opening)
}

fn html_tag_for_candidate(text: &str, start: usize) -> Option<String> {
    html_opening_tag(text, start)?
        .split_whitespace()
        .next()
        .map(|tag| tag.trim_end_matches('/').to_ascii_lowercase())
}

fn html_class_tokens(opening: &str) -> Vec<&str> {
    let Some(attribute) = opening.find("class=") else {
        return Vec::new();
    };
    let remainder = &opening[attribute + "class=".len()..];
    let Some(quote) = remainder
        .chars()
        .next()
        .filter(|value| matches!(value, '"' | '\''))
    else {
        return Vec::new();
    };
    let value = &remainder[quote.len_utf8()..];
    let Some(end) = value.find(quote) else {
        return Vec::new();
    };
    value[..end].split_whitespace().collect()
}

fn markdown_heading_matches(text: &str, start: usize, level: Option<usize>) -> bool {
    let Some(level) = level else {
        return false;
    };
    let line_start = text[..start].rfind('\n').map_or(0, |index| index + 1);
    let line = &text[line_start..start];
    line.starts_with(&"#".repeat(level)) && !line.starts_with(&"#".repeat(level + 1))
}

fn encode_replacement(kind: SourceKind, value: &str) -> Result<String> {
    Ok(match kind {
        SourceKind::HtmlText => value
            .replace('&', "&amp;")
            .replace('<', "&lt;")
            .replace('>', "&gt;"),
        SourceKind::QuotedString => {
            let encoded = serde_json::to_string(value).expect("serializing a string cannot fail");
            encoded[1..encoded.len() - 1].to_owned()
        }
        SourceKind::MarkdownText => escape_markdown_text(value),
        SourceKind::MarkdownLinkText => escape_markdown_text(value),
        SourceKind::MarkdownCode => {
            if value.contains(['`', '\n', '\r']) {
                bail!("inline code text cannot contain a backtick or newline");
            }
            value.to_owned()
        }
    })
}

fn escape_markdown_text(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        if matches!(
            character,
            '\\' | '`'
                | '*'
                | '_'
                | '['
                | ']'
                | '<'
                | '>'
                | '#'
                | '-'
                | '+'
                | '.'
                | '!'
                | '~'
                | '^'
                | '$'
                | '|'
                | ':'
                | '='
                | '('
                | ')'
        ) {
            escaped.push('\\');
        }
        escaped.push(character);
    }
    escaped
}

fn normalize_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn atomic_write(path: &Utf8Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("editable source has no parent: {path}"))?;
    let permissions = fs::metadata(path)
        .with_context(|| format!("failed to inspect editable source {path}"))?
        .permissions();
    let mut temporary = NamedTempFile::new_in(parent)
        .with_context(|| format!("failed to create temporary file beside {path}"))?;
    temporary
        .write_all(bytes)
        .with_context(|| format!("failed to write temporary source for {path}"))?;
    temporary
        .as_file()
        .set_permissions(permissions)
        .with_context(|| format!("failed to preserve permissions for {path}"))?;
    temporary
        .as_file()
        .sync_all()
        .with_context(|| format!("failed to sync temporary source for {path}"))?;
    temporary
        .persist(path)
        .map_err(|error| error.error)
        .with_context(|| format!("failed to replace editable source {path}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::fs;

    use base64::engine::general_purpose::URL_SAFE_NO_PAD;
    use base64::Engine;
    use camino::Utf8Path;
    use serde_json::json;
    use tempfile::tempdir;

    use super::{apply, resolve, restore, ElementHint};

    fn write(root: &Utf8Path, relative: &str, text: &str) {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, text).unwrap();
    }

    fn hint(tag: &str) -> ElementHint {
        ElementHint {
            tag_name: tag.to_owned(),
            class_name: String::new(),
        }
    }

    #[test]
    fn resolves_page_template_and_applies_atomic_edit() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "site/templates/index.html",
            "<p>A sentence split\nacross lines.</p>",
        );
        let resolved = resolve(
            root,
            "/",
            "A sentence split across lines.",
            Some(&hint("p")),
        )
        .unwrap();
        let edit = apply(
            root,
            &resolved.source,
            &resolved.value,
            "A clearer sentence.",
        )
        .unwrap();
        assert_eq!(
            fs::read_to_string(&edit.path).unwrap(),
            "<p>A clearer sentence.</p>"
        );
    }

    #[test]
    fn html_replacement_is_escaped() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "site/templates/index.html", "<p>Hello</p>");
        let resolved = resolve(root, "/", "Hello", Some(&hint("p"))).unwrap();
        apply(root, &resolved.source, "Hello", "A & B < C").unwrap();
        assert_eq!(
            fs::read_to_string(root.join("site/templates/index.html")).unwrap(),
            "<p>A &amp; B &lt; C</p>"
        );
    }

    #[test]
    fn quoted_replacement_is_escaped() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "dossiers/alpha/spctr.toml", "title = \"Alpha\"\n");
        let resolved = resolve(root, "/dossiers/alpha/", "Alpha", None).unwrap();
        apply(root, &resolved.source, "Alpha", "A \"quote\"").unwrap();
        assert_eq!(
            fs::read_to_string(root.join("dossiers/alpha/spctr.toml")).unwrap(),
            "title = \"A \\\"quote\\\"\"\n"
        );
    }

    #[test]
    fn manifest_title_field_wins_over_duplicate_project_identifier() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "addenda/alpha/spctr.toml",
            "title = \"alpha\"\nproject = \"alpha\"\n",
        );
        let resolved = resolve(root, "/addenda/", "alpha", Some(&hint("div"))).unwrap();
        apply(root, &resolved.source, "alpha", "Alpha Project").unwrap();
        assert_eq!(
            fs::read_to_string(root.join("addenda/alpha/spctr.toml")).unwrap(),
            "title = \"Alpha Project\"\nproject = \"alpha\"\n"
        );
    }

    #[test]
    fn stale_source_hash_is_rejected() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "dossiers/alpha/spctr.toml", "title = \"Alpha\"\n");
        let resolved = resolve(root, "/dossiers/alpha/", "Alpha", None).unwrap();
        write(root, "dossiers/alpha/spctr.toml", "title = \"Beta\"\n");
        assert!(apply(root, &resolved.source, "Alpha", "Gamma")
            .unwrap_err()
            .to_string()
            .contains("stale edit"));
    }

    #[test]
    fn element_tag_disambiguates_repeated_html_text() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "site/templates/index.html",
            "<nav><a>Blog</a></nav><h2>Blog</h2>",
        );
        let heading = resolve(root, "/", "Blog", Some(&hint("h2"))).unwrap();
        apply(root, &heading.source, "Blog", "Writing").unwrap();
        assert_eq!(
            fs::read_to_string(root.join("site/templates/index.html")).unwrap(),
            "<nav><a>Blog</a></nav><h2>Writing</h2>"
        );
    }

    #[test]
    fn repeated_html_text_without_identity_is_read_only() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "site/templates/index.html", "<p>Same</p><p>Same</p>");
        assert!(resolve(root, "/", "Same", Some(&hint("p")))
            .unwrap_err()
            .to_string()
            .contains("ambiguous"));
    }

    #[test]
    fn unrelated_computed_text_is_read_only() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "site/templates/dossiers/alpha/index.html",
            "<p>69</p>",
        );
        assert!(resolve(root, "/cabinet/", "69", Some(&hint("p"))).is_err());
    }

    #[test]
    fn formatted_container_is_read_only_but_leaf_text_resolves() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "site/templates/index.html",
            "<p>This is <a>linked</a> text</p>",
        );
        assert!(resolve(root, "/", "This is linked text", Some(&hint("p"))).is_err());
        assert!(resolve(root, "/", "linked", Some(&hint("a"))).is_ok());
    }

    #[test]
    fn nested_cabinet_route_maps_to_nested_markdown_source() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "dossiers/alpha/docs/contracts/Artifact.md",
            "# Artifact Contract\n",
        );
        let resolved = resolve(
            root,
            "/cabinet/alpha/contracts/Artifact/",
            "Artifact Contract",
            Some(&hint("h1")),
        )
        .unwrap();
        assert_eq!(resolved.label, "dossiers/alpha/docs/contracts/Artifact.md");
    }

    #[test]
    fn markdown_code_rejects_delimiter_breakout() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "site/blog/example/index.md",
            "Use `safe-command` here.\n",
        );
        let resolved =
            resolve(root, "/blog/example/", "safe-command", Some(&hint("code"))).unwrap();
        assert!(apply(root, &resolved.source, "safe-command", "bad`command").is_err());
        assert_eq!(
            fs::read_to_string(root.join("site/blog/example/index.md")).unwrap(),
            "Use `safe-command` here.\n"
        );
    }

    #[test]
    fn markdown_substrings_keep_code_and_link_context() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(
            root,
            "site/blog/example/index.md",
            "Use `safe-command` and [Diverse Intelligence](https://example.com).\n",
        );
        let code = resolve(root, "/blog/example/", "command", Some(&hint("code"))).unwrap();
        assert!(apply(root, &code.source, "command", "bad`part").is_err());

        let link = resolve(root, "/blog/example/", "Intelligence", Some(&hint("a"))).unwrap();
        apply(root, &link.source, "Intelligence", "~smart~ $label$").unwrap();
        assert_eq!(
            fs::read_to_string(root.join("site/blog/example/index.md")).unwrap(),
            "Use `safe-command` and [Diverse \\~smart\\~ \\$label\\$](https://example.com).\n"
        );
    }

    #[test]
    fn markdown_plain_text_is_escaped_against_structural_markup() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "site/blog/example/index.md", "A plain sentence.\n");
        let resolved = resolve(
            root,
            "/blog/example/",
            "A plain sentence.",
            Some(&hint("p")),
        )
        .unwrap();
        apply(
            root,
            &resolved.source,
            "A plain sentence.",
            "# Heading - not a list.",
        )
        .unwrap();
        assert_eq!(
            fs::read_to_string(root.join("site/blog/example/index.md")).unwrap(),
            "\\# Heading \\- not a list\\.\n"
        );
    }

    #[test]
    fn rollback_refuses_to_overwrite_a_concurrent_source_edit() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "site/templates/index.html", "<p>Hello</p>");
        let resolved = resolve(root, "/", "Hello", Some(&hint("p"))).unwrap();
        let edit = apply(root, &resolved.source, "Hello", "Saved").unwrap();
        write(root, "site/templates/index.html", "<p>Concurrent</p>");
        assert!(restore(&edit)
            .unwrap_err()
            .to_string()
            .contains("concurrently"));
        assert_eq!(
            fs::read_to_string(root.join("site/templates/index.html")).unwrap(),
            "<p>Concurrent</p>"
        );
    }

    #[test]
    fn traversal_token_is_rejected() {
        let temp = tempdir().unwrap();
        let root = Utf8Path::from_path(temp.path()).unwrap();
        write(root, "outside.html", "Hello");
        let token = json!({
            "version": 1,
            "path": "site/templates/../../outside.html",
            "start": 0,
            "end": 5,
            "file_sha256": "irrelevant",
            "value": "Hello",
            "kind": "html_text"
        });
        let encoded = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&token).unwrap());
        assert!(apply(root, &encoded, "Hello", "Goodbye").is_err());
        assert_eq!(
            fs::read_to_string(root.join("outside.html")).unwrap(),
            "Hello"
        );
    }
}
