use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

use crate::markdown;

pub struct BlogPostRecord {
    pub title: String,
    pub href: String,
    pub summary: String,
    pub series: Option<String>,
    pub release: String,
}

pub struct SitePageRecord {
    pub title: String,
    pub href: String,
}

const TITLE_SUFFIX: &str = " | SPECTER Labs";
pub const RELEASE_PUBLISHED: &str = "published";
pub const RELEASE_DRAFT: &str = "draft";

pub fn blog_slug_from_href(href: &str) -> Result<&str> {
    href.strip_prefix("blog/")
        .and_then(|slug| slug.strip_suffix('/'))
        .ok_or_else(|| anyhow::anyhow!("unexpected blog href format: {href}"))
}

pub fn blog_markdown_relpath(slug: &str) -> String {
    format!("site/blog/{slug}/index.md")
}

pub fn blog_markdown_path(repo_root: &Utf8Path, slug: &str) -> Utf8PathBuf {
    repo_root.join(blog_markdown_relpath(slug))
}

pub fn article_release(front_matter: &HashMap<String, String>) -> Result<String> {
    let release = match front_matter.get("release").map(String::as_str) {
        Some(value) if !value.is_empty() => value,
        _ => RELEASE_DRAFT,
    };
    if !matches!(release, RELEASE_PUBLISHED | RELEASE_DRAFT) {
        bail!("unknown article release '{release}' (expected published or draft)");
    }
    Ok(release.to_owned())
}

pub fn discover_published_blog_posts(repo_root: &Utf8Path) -> Result<Vec<BlogPostRecord>> {
    let blog_root = repo_root.join("site/blog");
    if !blog_root.is_dir() {
        return Ok(Vec::new());
    }
    let mut posts = Vec::new();
    let mut dirs: Vec<_> = Vec::new();
    for entry in
        fs::read_dir(&blog_root).with_context(|| format!("failed to read {}", blog_root))?
    {
        let entry = entry.with_context(|| format!("failed to read entry in {}", blog_root))?;
        if entry.path().is_dir() {
            dirs.push(entry);
        }
    }
    dirs.sort_by_key(std::fs::DirEntry::file_name);

    for entry in dirs {
        let md_path = entry.path().join("index.md");
        if !md_path.is_file() {
            continue;
        }
        let text = fs::read_to_string(&md_path)
            .with_context(|| format!("failed to read {}", md_path.display()))?;
        let fm = markdown::parse_front_matter(&text);
        let release = article_release(&fm)
            .with_context(|| format!("blog/{}/index.md", entry.file_name().to_string_lossy()))?;
        if release != RELEASE_PUBLISHED {
            continue;
        }
        let slug = entry.file_name().to_string_lossy().into_owned();
        let title = match fm.get("title") {
            Some(t) if !t.is_empty() => t.clone(),
            _ => {
                let h1 = markdown::extract_title(&text);
                if h1.is_empty() {
                    bail!("blog/{slug}/index.md: published post has no title (frontmatter or H1)");
                }
                h1
            }
        };
        let series = fm.get("series").cloned();
        let summary = markdown::extract_summary(&text, &fm);
        posts.push(BlogPostRecord {
            title,
            href: format!("blog/{slug}/"),
            summary,
            series,
            release,
        });
    }
    Ok(posts)
}

pub fn site_href_from_path(site_path: &str) -> String {
    let rel = if let Some(stripped) = site_path.strip_prefix("site/") {
        stripped
    } else {
        site_path
    };
    if let Some(prefix) = rel.strip_suffix("index.html") {
        if prefix.is_empty() {
            String::new()
        } else {
            prefix.to_owned()
        }
    } else {
        rel.to_owned()
    }
}

pub fn relative_href(from_site_file: &str, target_site_href: &str) -> String {
    let from_dir = match from_site_file.rfind('/') {
        Some(i) => &from_site_file[..i],
        None => ".",
    };
    let target_bare = target_site_href.trim_end_matches('/');
    let suffix = if target_site_href.ends_with('/') {
        "/"
    } else {
        ""
    };
    let target_for_rel = if target_bare.is_empty() {
        "."
    } else {
        target_bare
    };
    let rel = posix_relpath(target_for_rel, from_dir);
    if rel == "." {
        if suffix.is_empty() {
            ".".to_owned()
        } else {
            "./".to_owned()
        }
    } else {
        format!("{rel}{suffix}")
    }
}

pub fn relative_href_with_fragment(
    from_site_file: &str,
    target_href: &str,
    fragment: &str,
) -> String {
    format!("{}#{fragment}", relative_href(from_site_file, target_href))
}

fn posix_relpath(target: &str, base: &str) -> String {
    let target_parts: Vec<&str> = target
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();
    let base_parts: Vec<&str> = base
        .split('/')
        .filter(|s| !s.is_empty() && *s != ".")
        .collect();

    let common = target_parts
        .iter()
        .zip(base_parts.iter())
        .take_while(|(a, b)| a == b)
        .count();
    let ups = base_parts.len() - common;
    let downs = &target_parts[common..];

    let mut parts: Vec<&str> = Vec::new();
    for _ in 0..ups {
        parts.push("..");
    }
    parts.extend_from_slice(downs);
    if parts.is_empty() {
        ".".to_owned()
    } else {
        parts.join("/")
    }
}

fn extract_html_title(path: &Path, fallback: &str) -> String {
    let Ok(text) = fs::read_to_string(path) else {
        return fallback.to_owned();
    };
    if let Some(start) = text.find("<title>") {
        let after = &text[start + 7..];
        if let Some(end) = after.find("</title>") {
            let raw = &after[..end];
            let title = normalize_html_title(&html_unescape(raw));
            let stripped = strip_title_suffix(&title);
            if !stripped.is_empty() {
                return stripped;
            }
        }
    }
    fallback.to_owned()
}

fn strip_title_suffix(title: &str) -> String {
    if let Some(stripped) = title.strip_suffix(TITLE_SUFFIX) {
        stripped.trim().to_owned()
    } else {
        title.trim().to_owned()
    }
}

fn normalize_html_title(title: &str) -> String {
    strip_html_comments(title)
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn strip_html_comments(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    loop {
        let Some(start) = rest.find("<!--") else {
            out.push_str(rest);
            break;
        };
        out.push_str(&rest[..start]);
        let after_start = &rest[start + 4..];
        let Some(end) = after_start.find("-->") else {
            break;
        };
        rest = &after_start[end + 3..];
    }
    out
}

fn html_unescape(s: &str) -> String {
    s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
}

pub struct SitemapGroup {
    pub section: String,
    pub index: Option<SitePageRecord>,
    pub children: Vec<SitePageRecord>,
}

const SITEMAP_SKIP: &[&str] = &["templates", "sitemap", "research-notes"];
const SITEMAP_SHALLOW: &[&str] = &["cabinet"];

pub fn discover_sitemap_pages(repo_root: &Utf8Path) -> Vec<SitemapGroup> {
    let site_root = repo_root.join("site");
    if !site_root.is_dir() {
        return Vec::new();
    }

    let root_index = site_root.join("index.html");
    let mut groups: std::collections::BTreeMap<String, SitemapGroup> =
        std::collections::BTreeMap::new();

    if root_index.is_file() {
        let title = extract_html_title(root_index.as_std_path(), "Home");
        groups.insert(
            String::new(),
            SitemapGroup {
                section: String::new(),
                index: Some(SitePageRecord {
                    title,
                    href: String::new(),
                }),
                children: Vec::new(),
            },
        );
    }

    let mut top_dirs: Vec<_> = fs::read_dir(&site_root)
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .filter(|e| e.path().is_dir())
        .collect();
    top_dirs.sort_by_key(std::fs::DirEntry::file_name);

    for dir_entry in top_dirs {
        let section = dir_entry.file_name().to_string_lossy().to_string();
        if SITEMAP_SKIP.contains(&section.as_str()) {
            continue;
        }

        let dir_path = dir_entry.path();
        let dir_index = dir_path.join("index.html");
        let index_record = if dir_index.is_file() {
            let fallback = section.replace(['-', '_'], " ");
            let title = extract_html_title(&dir_index, &fallback);
            let relative = dir_index
                .strip_prefix(&site_root)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            Some(SitePageRecord {
                title,
                href: site_href_from_path(&relative),
            })
        } else {
            None
        };

        let shallow = SITEMAP_SHALLOW.contains(&section.as_str());
        let mut children = Vec::new();
        if !shallow {
            collect_index_html_recursive_skip_root(
                &dir_path,
                site_root.as_std_path(),
                &dir_index,
                &mut children,
            );
            children.sort_by(|a, b| a.href.cmp(&b.href));
        }

        if index_record.is_some() || !children.is_empty() {
            groups.insert(
                section.clone(),
                SitemapGroup {
                    section,
                    index: index_record,
                    children,
                },
            );
        }
    }

    groups.into_values().collect()
}

fn collect_index_html_recursive_skip_root(
    dir: &Path,
    site_root: &Path,
    root_index: &Path,
    out: &mut Vec<SitePageRecord>,
) {
    let mut entries: Vec<_> = fs::read_dir(dir)
        .into_iter()
        .flatten()
        .filter_map(Result::ok)
        .collect();
    entries.sort_by_key(std::fs::DirEntry::file_name);

    for entry in entries {
        let path = entry.path();
        if path.is_dir() {
            collect_index_html_recursive_skip_root(&path, site_root, root_index, out);
        } else if path.file_name().and_then(|n| n.to_str()) == Some("index.html")
            && path != root_index
        {
            let relative = path
                .strip_prefix(site_root)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            let href = site_href_from_path(&relative);
            let fallback = path
                .parent()
                .and_then(|p| p.file_name())
                .map(|n| n.to_string_lossy().replace(['-', '_'], " "))
                .unwrap_or_default();
            let title = extract_html_title(&path, &fallback);
            out.push(SitePageRecord { title, href });
        }
    }
}

pub fn addendum_index_href(record: &crate::site::records::SiteRecord, page_path: &str) -> String {
    relative_href_with_fragment(
        page_path,
        &site_href_from_path("addenda/index.html"),
        &record.slug,
    )
}
