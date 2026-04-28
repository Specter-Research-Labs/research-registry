use crate::site::cabinet::docs::DocEntry;
use anyhow::{bail, Result};
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::Regex;
use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

static WIKILINK_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\[\[([^\]\n]+)\]\]").unwrap());
static MD_LINK_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[([^\]\n]+)\]\(([^)\n]+)\)").unwrap());
static FENCE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^\s*(`{3,}|~{3,})").unwrap());
static INLINE_CODE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"`[^`\n]*`").unwrap());
static EXTERNAL_HREF_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:|^//").unwrap());

pub struct DocLookup {
    by_project_slug: HashMap<String, HashMap<String, usize>>,
    by_project_basename: HashMap<String, HashMap<String, Vec<usize>>>,
    by_slug: HashMap<String, Vec<usize>>,
    by_basename: HashMap<String, Vec<usize>>,
    by_path: HashMap<Utf8PathBuf, usize>,
    docs_roots: HashMap<String, Utf8PathBuf>,
}

pub fn build_doc_lookup(entries: &[DocEntry]) -> DocLookup {
    let mut by_project_slug: HashMap<String, HashMap<String, usize>> = HashMap::new();
    let mut by_project_basename: HashMap<String, HashMap<String, Vec<usize>>> = HashMap::new();
    let mut by_slug: HashMap<String, Vec<usize>> = HashMap::new();
    let mut by_basename: HashMap<String, Vec<usize>> = HashMap::new();
    let mut by_path: HashMap<Utf8PathBuf, usize> = HashMap::new();
    let mut docs_roots: HashMap<String, Utf8PathBuf> = HashMap::new();

    for (i, entry) in entries.iter().enumerate() {
        by_project_slug
            .entry(entry.project_slug.clone())
            .or_default()
            .insert(entry.slug.clone(), i);

        let basename = Utf8Path::new(&entry.slug)
            .file_name()
            .map(ToOwned::to_owned)
            .unwrap_or_default();

        by_project_basename
            .entry(entry.project_slug.clone())
            .or_default()
            .entry(basename.clone())
            .or_default()
            .push(i);

        by_slug.entry(entry.slug.clone()).or_default().push(i);
        by_basename.entry(basename).or_default().push(i);

        if let Ok(resolved) = entry.path.canonicalize_utf8() {
            by_path.insert(resolved, i);
        }

        docs_roots
            .entry(entry.project_slug.clone())
            .or_insert_with(|| entry.docs_root.clone());
    }

    DocLookup {
        by_project_slug,
        by_project_basename,
        by_slug,
        by_basename,
        by_path,
        docs_roots,
    }
}

fn split_anchor(target: &str) -> (&str, &str) {
    match target.find('#') {
        Some(pos) => (&target[..pos], &target[pos..]),
        None => (target, ""),
    }
}

fn normalize_doc_target(raw: &str) -> String {
    let mut target = raw.trim().replace('\\', "/");
    while target.starts_with("./") {
        target = target[2..].to_owned();
    }
    if let Some(rest) = target.strip_prefix("docs/") {
        target = rest.to_owned();
    }
    target = target.trim_start_matches('/').to_owned();
    if let Some(rest) = target.strip_suffix(".md") {
        target = rest.to_owned();
    }
    target = target.trim_end_matches('/').to_owned();
    if let Some(rest) = target.strip_suffix("/index") {
        target = rest.to_owned();
    }
    target
}

fn target_candidates(target: &str, source_project: &str, lookup: &DocLookup) -> Vec<usize> {
    if target.contains('/') {
        let (first, rest) = target.split_once('/').unwrap();
        if let Some(project_map) = lookup.by_project_slug.get(first) {
            if let Some(&idx) = project_map.get(rest) {
                return vec![idx];
            }
        }
    }

    if let Some(project_map) = lookup.by_project_slug.get(source_project) {
        if let Some(&idx) = project_map.get(target) {
            return vec![idx];
        }
    }

    if let Some(project_basenames) = lookup.by_project_basename.get(source_project) {
        if let Some(indices) = project_basenames.get(target) {
            if indices.len() == 1 {
                return indices.clone();
            }
            if indices.len() > 1 {
                return indices.clone();
            }
        }
    }

    if let Some(indices) = lookup.by_slug.get(target) {
        if indices.len() == 1 {
            return indices.clone();
        }
        if indices.len() > 1 {
            return indices.clone();
        }
    }

    if let Some(indices) = lookup.by_basename.get(target) {
        return indices.clone();
    }

    Vec::new()
}

fn resolve_wikilink_target(
    raw_target: &str,
    source: &DocEntry,
    lookup: &DocLookup,
    entries: &[DocEntry],
) -> Result<usize> {
    let target = normalize_doc_target(raw_target);
    if target.is_empty() {
        bail!("{}: empty wikilink target", source.path);
    }

    let candidates = target_candidates(&target, &source.project_slug, lookup);
    match candidates.len() {
        1 => Ok(candidates[0]),
        0 => bail!(
            "{}: unresolved wikilink [[{raw_target}]] from {}",
            source.path,
            source.slug
        ),
        _ => {
            let options: Vec<String> = candidates
                .iter()
                .take(8)
                .map(|&i| format!("{}/{}", entries[i].project_slug, entries[i].slug))
                .collect();
            bail!(
                "{}: ambiguous wikilink [[{raw_target}]] from {}; candidates: {}",
                source.path,
                source.slug,
                options.join(", ")
            );
        }
    }
}

fn is_external_href(href: &str) -> bool {
    EXTERNAL_HREF_RE.is_match(href)
}

fn parse_markdown_href(raw: &str) -> &str {
    let href = raw.trim();
    let href = href
        .strip_prefix('<')
        .and_then(|h| h.strip_suffix('>'))
        .map(str::trim)
        .unwrap_or(href);
    if let Some(pos) = href.find(|c: char| c.is_whitespace()) {
        let rest = href[pos..].trim_start();
        if rest.starts_with('"') || rest.starts_with('\'') || rest.starts_with('(') {
            return &href[..pos];
        }
    }
    href
}

fn resolves_within_docs(path_part: &str, source: &DocEntry, lookup: &DocLookup) -> bool {
    let docs_root = match lookup.docs_roots.get(&source.project_slug) {
        Some(r) => r,
        None => return false,
    };
    let Ok(docs_root_canon) = docs_root.canonicalize_utf8() else {
        return false;
    };
    let source_parent = match source.path.parent() {
        Some(p) => p,
        None => return false,
    };
    let candidate = source_parent.join(path_part);
    let normalized = normalize_utf8_path_components(&candidate);
    normalized.as_str().starts_with(docs_root_canon.as_str())
}

fn normalize_utf8_path_components(path: &Utf8Path) -> Utf8PathBuf {
    let mut parts: Vec<&str> = Vec::new();
    for component in path.components() {
        match component {
            camino::Utf8Component::ParentDir => {
                parts.pop();
            }
            camino::Utf8Component::CurDir => {}
            other => parts.push(other.as_str()),
        }
    }
    parts.iter().collect()
}

fn candidate_paths(base: &Utf8Path) -> Vec<Utf8PathBuf> {
    let mut paths = vec![base.to_owned()];
    if base.extension().is_none() {
        paths.push(base.with_extension("md"));
    }
    paths
        .into_iter()
        .filter_map(|p| p.canonicalize_utf8().ok())
        .collect()
}

fn resolve_markdown_target(
    href: &str,
    source: &DocEntry,
    lookup: &DocLookup,
) -> Option<(usize, String)> {
    if href.is_empty() || href.starts_with('#') || is_external_href(href) {
        return None;
    }

    let (path_part, anchor) = split_anchor(href);
    let normalized = path_part.trim();
    if normalized.is_empty() {
        return None;
    }

    if let Some(cabinet_suffix) = normalized.strip_prefix("/cabinet/") {
        let parts: Vec<&str> = cabinet_suffix.split('/').collect();
        if parts.len() >= 2 {
            let project = parts[0];
            let mut slug = parts[1..].join("/");
            if let Some(rest) = slug.strip_suffix("/index.html") {
                slug = rest.to_owned();
            }
            slug = slug.trim_end_matches('/').to_owned();
            if let Some(project_map) = lookup.by_project_slug.get(project) {
                if let Some(&idx) = project_map.get(&slug) {
                    return Some((idx, anchor.to_owned()));
                }
            }
        }
    }

    let source_path = source.path.canonicalize_utf8().ok()?;
    let source_root = lookup.docs_roots.get(&source.project_slug)?;
    let raw_path = normalized.replace('\\', "/");

    let mut path_candidates = Vec::new();
    if let Some(rest) = raw_path.strip_prefix("docs/") {
        path_candidates.push(source_root.join(rest));
    } else if raw_path.starts_with('/') {
        path_candidates.push(Utf8PathBuf::from(&raw_path));
    } else {
        if let Some(parent) = source_path.parent() {
            path_candidates.push(parent.join(&raw_path));
        }
        path_candidates.push(source_root.join(&raw_path));
    }

    for candidate_base in &path_candidates {
        for resolved_path in candidate_paths(candidate_base) {
            if let Some(&idx) = lookup.by_path.get(&resolved_path) {
                return Some((idx, anchor.to_owned()));
            }
        }
    }

    let fallback = normalize_doc_target(&raw_path);
    if !fallback.is_empty() {
        let candidates = target_candidates(&fallback, &source.project_slug, lookup);
        if candidates.len() == 1 {
            return Some((candidates[0], anchor.to_owned()));
        }
    }

    None
}

fn relative_doc_href(source: &DocEntry, target: &DocEntry, anchor: &str) -> String {
    let source_dir = format!("{}/{}", source.project_slug, source.slug);
    let target_dir = format!("{}/{}", target.project_slug, target.slug);

    let source_parts: Vec<&str> = source_dir.split('/').collect();
    let target_parts: Vec<&str> = target_dir.split('/').collect();

    let common = source_parts
        .iter()
        .zip(target_parts.iter())
        .take_while(|(a, b)| a == b)
        .count();

    let ups = source_parts.len() - common;
    let mut rel = String::new();
    for _ in 0..ups {
        rel.push_str("../");
    }
    for part in &target_parts[common..] {
        rel.push_str(part);
        rel.push('/');
    }

    if rel.is_empty() {
        rel = "./".to_owned();
    }

    format!("{rel}{anchor}")
}

pub fn transform_markdown(
    text: &str,
    source: &DocEntry,
    lookup: &DocLookup,
    entries: &[DocEntry],
    outgoing: &mut HashSet<(String, String)>,
) -> Result<String> {
    let mut output_lines = Vec::new();
    let mut in_fence = false;

    for line in text.lines() {
        if FENCE_RE.is_match(line) {
            in_fence = !in_fence;
            output_lines.push(line.to_owned());
            continue;
        }

        if in_fence {
            output_lines.push(line.to_owned());
            continue;
        }

        let mut result = String::new();
        let mut last_end = 0;

        let code_spans: Vec<(usize, usize)> = INLINE_CODE_RE
            .find_iter(line)
            .map(|m| (m.start(), m.end()))
            .collect();

        let is_in_code = |pos: usize| -> bool {
            code_spans
                .iter()
                .any(|&(start, end)| pos >= start && pos < end)
        };

        let segments = collect_non_code_segments(line, &code_spans);

        for (seg_start, seg_end) in segments {
            let segment = &line[seg_start..seg_end];
            let rewritten = rewrite_segment(segment, source, lookup, entries, outgoing)?;
            result.push_str(&line[last_end..seg_start]);
            result.push_str(&rewritten);
            last_end = seg_end;
        }

        for &(cs, ce) in &code_spans {
            if cs >= last_end {
                result.push_str(&line[last_end..ce]);
                last_end = ce;
            }
        }
        result.push_str(&line[last_end..]);

        let _ = is_in_code;
        output_lines.push(result);
    }

    let mut output = output_lines.join("\n");
    if text.ends_with('\n') {
        output.push('\n');
    }
    Ok(output)
}

fn collect_non_code_segments(line: &str, code_spans: &[(usize, usize)]) -> Vec<(usize, usize)> {
    let mut segments = Vec::new();
    let mut pos = 0;
    for &(cs, ce) in code_spans {
        if pos < cs {
            segments.push((pos, cs));
        }
        pos = ce;
    }
    if pos < line.len() {
        segments.push((pos, line.len()));
    }
    segments
}

fn rewrite_segment(
    segment: &str,
    source: &DocEntry,
    lookup: &DocLookup,
    entries: &[DocEntry],
    outgoing: &mut HashSet<(String, String)>,
) -> Result<String> {
    let with_md = rewrite_markdown_links(segment, source, lookup, entries, outgoing)?;
    rewrite_wikilinks(&with_md, source, lookup, entries, outgoing)
}

fn rewrite_markdown_links(
    segment: &str,
    source: &DocEntry,
    lookup: &DocLookup,
    entries: &[DocEntry],
    outgoing: &mut HashSet<(String, String)>,
) -> Result<String> {
    let mut result = String::new();
    let mut last_end = 0;

    for cap in MD_LINK_RE.captures_iter(segment) {
        let full_match = cap.get(0).unwrap();
        if full_match.start() > 0 && segment.as_bytes()[full_match.start() - 1] == b'!' {
            continue;
        }
        let label = &cap[1];
        let raw_target = &cap[2];
        let href = parse_markdown_href(raw_target);

        let replacement = match resolve_markdown_target(href, source, lookup) {
            Some((idx, anchor)) => {
                let target = &entries[idx];
                outgoing.insert((target.project_slug.clone(), target.slug.clone()));
                format!("[{label}]({})", relative_doc_href(source, target, &anchor))
            }
            None => {
                let (path_part, _) = split_anchor(href);
                let is_internal_doc = !is_external_href(href)
                    && (path_part.starts_with("docs/")
                        || (path_part.ends_with(".md")
                            && resolves_within_docs(path_part, source, lookup)));
                if is_internal_doc {
                    bail!(
                        "{}: unresolved markdown doc link ({href}) in {}",
                        source.path,
                        source.slug
                    );
                }
                full_match.as_str().to_owned()
            }
        };

        result.push_str(&segment[last_end..full_match.start()]);
        result.push_str(&replacement);
        last_end = full_match.end();
    }

    result.push_str(&segment[last_end..]);
    Ok(result)
}

fn rewrite_wikilinks(
    segment: &str,
    source: &DocEntry,
    lookup: &DocLookup,
    entries: &[DocEntry],
    outgoing: &mut HashSet<(String, String)>,
) -> Result<String> {
    let mut result = String::new();
    let mut last_end = 0;

    for cap in WIKILINK_RE.captures_iter(segment) {
        let full_match = cap.get(0).unwrap();
        let inner = cap[1].trim();

        let (raw_target, link_label) = if let Some((target, label)) = inner.split_once('|') {
            (target.trim(), Some(label.trim().to_owned()))
        } else {
            (inner, None)
        };

        let (target_part, anchor) = split_anchor(raw_target);
        let idx = resolve_wikilink_target(target_part, source, lookup, entries)?;
        let target = &entries[idx];
        outgoing.insert((target.project_slug.clone(), target.slug.clone()));

        let label = link_label.unwrap_or_else(|| target.title.clone());
        let href = relative_doc_href(source, target, anchor);

        result.push_str(&segment[last_end..full_match.start()]);
        result.push_str(&format!("[{label}]({href})"));
        last_end = full_match.end();
    }

    result.push_str(&segment[last_end..]);
    Ok(result)
}

pub fn build_backlink_graph(
    entries: &mut [DocEntry],
    lookup: &DocLookup,
) -> Result<HashMap<(String, String), Vec<usize>>> {
    let entries_snapshot: Vec<DocEntry> = entries.to_vec();
    let mut backlinks: HashMap<(String, String), Vec<usize>> = HashMap::new();

    for (i, entry) in entries.iter_mut().enumerate() {
        let raw_text = std::fs::read_to_string(&entry.path)
            .map_err(|e| anyhow::anyhow!("{}: {e}", entry.path))?;
        let mut outgoing: HashSet<(String, String)> = HashSet::new();
        let transformed = transform_markdown(
            &raw_text,
            &entries_snapshot[i],
            lookup,
            &entries_snapshot,
            &mut outgoing,
        )?;
        entry.render_markdown = Some(transformed);

        let source_key = (entry.project_slug.clone(), entry.slug.clone());
        for target_key in &outgoing {
            if *target_key != source_key {
                backlinks.entry(target_key.clone()).or_default().push(i);
            }
        }
    }

    for sources in backlinks.values_mut() {
        let mut seen = HashSet::new();
        sources.retain(|idx| seen.insert(*idx));
        sources.sort_by(|&a, &b| {
            let ea = &entries[a];
            let eb = &entries[b];
            ea.project_slug
                .cmp(&eb.project_slug)
                .then_with(|| ea.doc_id.cmp(&eb.doc_id))
                .then_with(|| ea.slug.cmp(&eb.slug))
        });
    }

    Ok(backlinks)
}
