//! Content-hash cache keys for the staged site's stylesheets and scripts.
//!
//! Every local `.css`/`.js` reference in a staged page, stylesheet or module
//! gets `?v=<hash>`, where the hash covers the file after its own references
//! were rewritten, so a change in an imported file also changes every importer.

use std::collections::BTreeMap;
use std::fs;

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::{Captures, Regex};
use sha2::{Digest, Sha256};

const HASH_LEN: usize = 10;

struct Patterns {
    attr: Regex,
    script: Regex,
    js_import: Regex,
    css_import: Regex,
    css_url: Regex,
}

impl Patterns {
    fn new() -> Self {
        Self {
            attr: Regex::new(r#"(\b(?:href|src)\s*=\s*)(?:"([^"]*)"|'([^']*)')"#).unwrap(),
            script: Regex::new(r"(?s)(<script\b[^>]*>)(.*?)(</script>)").unwrap(),
            js_import: Regex::new(
                r#"(\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(?:"([^"]+\.js(?:\?[^"]*)?)"|'([^']+\.js(?:\?[^']*)?)')"#,
            )
            .unwrap(),
            css_import: Regex::new(
                r#"(@import\s+)(?:"([^"]+)"|'([^']+)')"#,
            )
            .unwrap(),
            css_url: Regex::new(r#"(url\(\s*)(?:"([^"]+)"|'([^']+)'|([^"')\s]+))(\s*\))"#).unwrap(),
        }
    }
}

pub fn fingerprint_site(stage_root: &Utf8Path) -> Result<()> {
    let patterns = Patterns::new();
    let mut files = Vec::new();
    collect(stage_root, stage_root, &mut files)?;
    files.sort();

    let mut hashes = BTreeMap::new();
    for relative in files.iter().filter(|path| is_asset(path.as_str())) {
        hash_asset(stage_root, relative, &patterns, &mut hashes, &mut Vec::new())?;
    }

    let mut errors = Vec::new();
    for relative in files.iter().filter(|path| path.extension() == Some("html")) {
        let path = stage_root.join(relative);
        let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
        match rewrite_html(stage_root, relative, &text, &patterns, &hashes) {
            Ok(rewritten) => {
                fs::write(&path, rewritten).with_context(|| format!("failed to write {path}"))?
            }
            Err(error) => errors.push(format!("{relative}: {error:#}")),
        }
    }
    if !errors.is_empty() {
        bail!(
            "asset fingerprinting rejected {} page(s):\n{}",
            errors.len(),
            errors.join("\n")
        );
    }
    Ok(())
}

fn is_asset(path: &str) -> bool {
    path.ends_with(".css") || path.ends_with(".js")
}

fn collect(root: &Utf8Path, dir: &Utf8Path, out: &mut Vec<Utf8PathBuf>) -> Result<()> {
    for entry in dir.read_dir_utf8().with_context(|| format!("failed to read {dir}"))? {
        let entry = entry?;
        let path = entry.path();
        if entry.file_type()?.is_dir() {
            collect(root, path, out)?;
        } else if matches!(path.extension(), Some("html" | "css" | "js")) {
            out.push(path.strip_prefix(root)?.to_owned());
        }
    }
    Ok(())
}

/// Rewrites the references inside one stylesheet or module, writes it back, and
/// records the hash of the rewritten text. `active` holds the import chain so
/// that a cycle fails instead of recursing forever.
fn hash_asset(
    stage_root: &Utf8Path,
    relative: &Utf8Path,
    patterns: &Patterns,
    hashes: &mut BTreeMap<Utf8PathBuf, String>,
    active: &mut Vec<Utf8PathBuf>,
) -> Result<String> {
    if let Some(hash) = hashes.get(relative) {
        return Ok(hash.clone());
    }
    if active.iter().any(|path| path == relative) {
        bail!("import cycle through {relative}");
    }
    active.push(relative.to_owned());

    let path = stage_root.join(relative);
    let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
    let mut targets = Vec::new();
    let references = if relative.extension() == Some("css") {
        css_references(&text, patterns)
    } else {
        js_references(&text, patterns)
    };
    for reference in references {
        if let Some(target) = resolve(stage_root, relative, &reference)
            .with_context(|| format!("{relative}: reference {reference}"))?
        {
            let hash = hash_asset(stage_root, &target, patterns, hashes, active)?;
            targets.push((target, hash));
        }
    }
    let local: BTreeMap<_, _> = targets.into_iter().collect();
    let rewritten = if relative.extension() == Some("css") {
        rewrite_css(stage_root, relative, &text, patterns, &local)?
    } else {
        rewrite_js(stage_root, relative, &text, patterns, &local)?
    };
    if rewritten != text {
        fs::write(&path, &rewritten).with_context(|| format!("failed to write {path}"))?;
    }

    let digest = format!("{:x}", Sha256::digest(rewritten.as_bytes()));
    let hash = digest[..HASH_LEN].to_owned();
    active.pop();
    hashes.insert(relative.to_owned(), hash.clone());
    Ok(hash)
}

fn quoted<'a>(captures: &'a Captures) -> &'a str {
    captures
        .get(2)
        .or_else(|| captures.get(3))
        .or_else(|| captures.get(4))
        .map(|value| value.as_str())
        .unwrap_or_default()
}

fn css_references(text: &str, patterns: &Patterns) -> Vec<String> {
    patterns
        .css_import
        .captures_iter(text)
        .chain(patterns.css_url.captures_iter(text))
        .map(|captures| quoted(&captures).to_owned())
        .filter(|value| is_asset(strip_query(value)))
        .collect()
}

fn js_references(text: &str, patterns: &Patterns) -> Vec<String> {
    patterns
        .js_import
        .captures_iter(text)
        .map(|captures| quoted(&captures).to_owned())
        .collect()
}

fn strip_query(reference: &str) -> &str {
    reference.split(['?', '#']).next().unwrap_or(reference)
}

/// The staged file a reference points to, or `None` for external URLs.
fn resolve(
    stage_root: &Utf8Path,
    from: &Utf8Path,
    reference: &str,
) -> Result<Option<Utf8PathBuf>> {
    if reference.contains("://") || reference.starts_with("//") || reference.starts_with("data:") {
        return Ok(None);
    }
    if reference.contains('?') {
        bail!("hand-written query string; the stage fingerprints local stylesheets and scripts");
    }
    let joined = match reference.strip_prefix('/') {
        Some(absolute) => Utf8PathBuf::from(absolute),
        None => from
            .parent()
            .with_context(|| format!("{from} has no parent directory"))?
            .join(reference),
    };
    let mut parts: Vec<&str> = Vec::new();
    for part in joined.as_str().split('/') {
        match part {
            "" | "." => {}
            ".." => {
                if parts.pop().is_none() {
                    bail!("escapes the site root");
                }
            }
            other => parts.push(other),
        }
    }
    let target = Utf8PathBuf::from(parts.join("/"));
    if !stage_root.join(&target).is_file() {
        bail!("missing from the stage");
    }
    Ok(Some(target))
}

fn keyed(
    stage_root: &Utf8Path,
    from: &Utf8Path,
    reference: &str,
    hashes: &BTreeMap<Utf8PathBuf, String>,
) -> Result<String> {
    match resolve(stage_root, from, reference)? {
        None => Ok(reference.to_owned()),
        Some(target) => {
            let hash = hashes
                .get(&target)
                .with_context(|| format!("{target} was not fingerprinted"))?;
            Ok(format!("{reference}?v={hash}"))
        }
    }
}

fn replace_quoted(
    regex: &Regex,
    text: &str,
    mut map: impl FnMut(&str) -> Result<Option<String>>,
) -> Result<String> {
    let mut error = None;
    let rewritten = regex.replace_all(text, |captures: &Captures| {
        let whole = captures[0].to_owned();
        let value = quoted(captures);
        match map(value) {
            Ok(Some(replacement)) => whole.replacen(value, &replacement, 1),
            Ok(None) => whole,
            Err(failure) => {
                error.get_or_insert_with(|| failure.context(format!("reference {value}")));
                whole
            }
        }
    });
    match error {
        Some(error) => Err(error),
        None => Ok(rewritten.into_owned()),
    }
}

fn rewrite_css(
    stage_root: &Utf8Path,
    from: &Utf8Path,
    text: &str,
    patterns: &Patterns,
    hashes: &BTreeMap<Utf8PathBuf, String>,
) -> Result<String> {
    let map = |value: &str| -> Result<Option<String>> {
        if !is_asset(strip_query(value)) {
            return Ok(None);
        }
        keyed(stage_root, from, value, hashes).map(Some)
    };
    let text = replace_quoted(&patterns.css_import, text, map)?;
    replace_quoted(&patterns.css_url, &text, map)
}

fn rewrite_js(
    stage_root: &Utf8Path,
    from: &Utf8Path,
    text: &str,
    patterns: &Patterns,
    hashes: &BTreeMap<Utf8PathBuf, String>,
) -> Result<String> {
    replace_quoted(&patterns.js_import, text, |value| {
        keyed(stage_root, from, value, hashes).map(Some)
    })
}

fn rewrite_html(
    stage_root: &Utf8Path,
    relative: &Utf8Path,
    text: &str,
    patterns: &Patterns,
    hashes: &BTreeMap<Utf8PathBuf, String>,
) -> Result<String> {
    let text = replace_quoted(&patterns.attr, text, |value| {
        if !is_asset(strip_query(value)) {
            return Ok(None);
        }
        keyed(stage_root, relative, value, hashes).map(Some)
    })?;
    let mut error = None;
    let rewritten = patterns.script.replace_all(&text, |captures: &Captures| {
        match rewrite_js(stage_root, relative, &captures[2], patterns, hashes) {
            Ok(body) => format!("{}{body}{}", &captures[1], &captures[3]),
            Err(failure) => {
                error.get_or_insert(failure);
                captures[0].to_owned()
            }
        }
    });
    match error {
        Some(error) => Err(error),
        None => Ok(rewritten.into_owned()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stage(files: &[(&str, &str)]) -> (tempfile::TempDir, Utf8PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let root = Utf8PathBuf::from_path_buf(dir.path().to_path_buf()).unwrap();
        for (path, text) in files {
            let path = root.join(path);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text).unwrap();
        }
        (dir, root)
    }

    #[test]
    fn keys_follow_imported_content() {
        let page = r#"<link rel="stylesheet" href="/a.css"><script type="module">import { f } from "/m.js";</script><img src="/x.png">"#;
        let (_dir, root) = stage(&[
            ("index.html", page),
            ("a.css", "@import url(\"./b.css\");"),
            ("b.css", "body{color:red}"),
            ("m.js", "export const f = 1;"),
        ]);
        fingerprint_site(&root).unwrap();
        let first = fs::read_to_string(root.join("index.html")).unwrap();
        assert!(first.contains("href=\"/a.css?v="));
        assert!(first.contains("from \"/m.js?v="));
        assert!(first.contains("src=\"/x.png\""));
        assert!(fs::read_to_string(root.join("a.css"))
            .unwrap()
            .contains("./b.css?v="));

        let (_dir, changed) = stage(&[
            ("index.html", page),
            ("a.css", "@import url(\"./b.css\");"),
            ("b.css", "body{color:blue}"),
            ("m.js", "export const f = 1;"),
        ]);
        fingerprint_site(&changed).unwrap();
        let second = fs::read_to_string(changed.join("index.html")).unwrap();
        let key = |html: &str| html.split("a.css?v=").nth(1).unwrap()[..HASH_LEN].to_owned();
        assert_ne!(key(&first), key(&second));
    }

    #[test]
    fn rejects_hand_written_and_missing_references() {
        let (_dir, root) = stage(&[
            ("index.html", r#"<link rel="stylesheet" href="/a.css?v=1">"#),
            ("a.css", ""),
        ]);
        assert!(fingerprint_site(&root).is_err());
        let (_dir, root) = stage(&[("index.html", r#"<script src="gone.js"></script>"#)]);
        assert!(fingerprint_site(&root).is_err());
    }
}
