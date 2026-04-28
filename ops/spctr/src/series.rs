use anyhow::Result;
use camino::Utf8PathBuf;

use crate::markdown;
use crate::site::discover;

pub(crate) struct MissingArticleSeriesRecord {
    pub slug: String,
    pub title: String,
    pub path: Utf8PathBuf,
    pub patch_source: bool,
}

pub fn patch_frontmatter_field(text: &str, key: &str, value: &str) -> Result<String> {
    let mut lines: Vec<&str> = text.lines().collect();
    if lines.first().map(|l| l.trim()) != Some("---") {
        anyhow::bail!("file has no YAML frontmatter");
    }
    let close = lines.iter().skip(1).position(|l| l.trim() == "---");
    let close_idx = close.ok_or_else(|| anyhow::anyhow!("unclosed frontmatter"))? + 1;
    let new_line = format!("{key}: {value}");
    lines.insert(close_idx, &new_line);
    let mut result = lines.join("\n");
    if text.ends_with('\n') {
        result.push('\n');
    }
    Ok(result)
}

pub(crate) fn missing_article_series_records(
    repo_root: &camino::Utf8Path,
) -> Result<Vec<MissingArticleSeriesRecord>> {
    discover::discover_published_blog_posts(repo_root)?
        .into_iter()
        .filter(|post| post.series.is_none())
        .map(|post| {
            let slug = discover::blog_slug_from_href(&post.href)?.to_owned();
            let path = discover::blog_markdown_path(repo_root, &slug);
            let text = std::fs::read_to_string(&path)?;
            let frontmatter = markdown::parse_front_matter(&text);
            let title = frontmatter.get("title").cloned().ok_or_else(|| {
                anyhow::anyhow!("blog/{slug}/index.md: missing frontmatter title")
            })?;
            Ok(MissingArticleSeriesRecord {
                slug,
                title,
                path,
                patch_source: true,
            })
        })
        .collect()
}

pub(crate) fn missing_research_note_series_records(
    repo_root: &camino::Utf8Path,
    registry: &crate::registry::Registry,
) -> Result<Vec<MissingArticleSeriesRecord>> {
    let notes_root = repo_root.join("site/research-notes");
    if !notes_root.is_dir() {
        return Ok(Vec::new());
    }

    let mut records = Vec::new();
    for entry in std::fs::read_dir(&notes_root)? {
        let entry = entry?;
        if !entry.path().is_dir() {
            continue;
        }
        let slug = entry.file_name().to_string_lossy().into_owned();
        if crate::registry::series_for_slug(registry, "B", &slug).is_some() {
            continue;
        }
        let path = notes_root.join(&slug).join("index.md");
        if !path.is_file() {
            continue;
        }
        let text = std::fs::read_to_string(&path)?;
        let frontmatter = markdown::parse_front_matter(&text);
        let title = frontmatter
            .get("title")
            .filter(|title| !title.is_empty())
            .cloned()
            .unwrap_or_else(|| markdown::extract_title(&text));
        if title.is_empty() {
            anyhow::bail!("site/research-notes/{slug}/index.md: missing title");
        }
        records.push(MissingArticleSeriesRecord {
            slug,
            title,
            path,
            patch_source: false,
        });
    }
    records.sort_by(|left, right| left.slug.cmp(&right.slug));
    Ok(records)
}

pub fn patch_toml_series(toml_text: &str, series_id: &str) -> Result<String> {
    let line = format!("series = \"{series_id}\"");
    for existing in toml_text.lines() {
        if existing.trim().starts_with("series") && existing.contains('=') {
            anyhow::bail!("spctr.toml already contains a series line");
        }
    }
    let mut result = String::with_capacity(toml_text.len() + line.len() + 1);
    let mut inserted = false;
    for l in toml_text.lines() {
        result.push_str(l);
        result.push('\n');
        if !inserted && l.trim().starts_with("title") && l.contains('=') {
            result.push_str(&line);
            result.push('\n');
            inserted = true;
        }
    }
    if !inserted {
        result.push_str(&line);
        result.push('\n');
    }
    Ok(result)
}
