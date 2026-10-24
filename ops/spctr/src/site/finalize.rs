use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::process::{Command, Stdio};

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::Regex;
use url::Url;

use super::shell;

pub const SITE_NAME: &str = "Specter Labs";
pub const TITLE_SUFFIX: &str = " | Specter Labs";
const NOT_FOUND_PAGE: &str = "404.html";
const ASSETS_DIR: &str = "assets/";
const CARD_META: &str = "spctr:card";
const MAX_DESCRIPTION: usize = 160;
const NO_CARD: &str = "none";
const CARD_TEMPLATE: &str = include_str!("og-card.typ");
const TOKENS_STYLESHEET: &str = "/tokens.css";
const SITE_SHELL_STYLESHEET: &str = "/assets/site-shell.css";

// Keys finalize derives from the page title, description, and path. A page that
// declares one itself would ship a second, possibly conflicting, value.
const DERIVED_META: &[&str] = &[
    "og:title",
    "og:description",
    "og:url",
    "og:site_name",
    "twitter:card",
    "twitter:title",
    "twitter:description",
    "twitter:image",
];

#[derive(Debug, Default)]
pub struct FinalizeReport {
    pub canonical_urls: Vec<String>,
    pub missing_description: Vec<String>,
    pub missing_image: Vec<String>,
}

struct PageHead {
    title: String,
    meta: BTreeMap<String, String>,
    has_canonical: bool,
}

pub fn finalize_site(
    stage_root: &Utf8Path,
    font_path: &Utf8Path,
    public_url: &str,
) -> Result<FinalizeReport> {
    let public_url = public_url.trim_end_matches('/');
    let mut pages = Vec::new();
    collect_html(stage_root, stage_root, &mut pages)?;
    pages.sort();

    let mut report = FinalizeReport::default();
    let mut errors = Vec::new();
    for relative in &pages {
        let path = stage_root.join(relative);
        let text = fs::read_to_string(&path).with_context(|| format!("failed to read {path}"))?;
        match finalize_page(
            stage_root,
            font_path,
            relative.as_str(),
            &text,
            public_url,
            &mut report,
        ) {
            Ok(rewritten) => {
                fs::write(&path, rewritten).with_context(|| format!("failed to write {path}"))?;
            }
            Err(error) => errors.push(format!("{relative}: {error:#}")),
        }
    }
    if !errors.is_empty() {
        bail!(
            "site finalize rejected {} page(s):\n{}",
            errors.len(),
            errors.join("\n")
        );
    }

    report.canonical_urls.sort();
    let sitemap_path = stage_root.join("sitemap.xml");
    fs::write(&sitemap_path, render_sitemap(&report.canonical_urls))
        .with_context(|| format!("failed to write {sitemap_path}"))?;
    Ok(report)
}

fn collect_html(root: &Utf8Path, dir: &Utf8Path, out: &mut Vec<Utf8PathBuf>) -> Result<()> {
    for entry in fs::read_dir(dir).with_context(|| format!("failed to read {dir}"))? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|path| anyhow::anyhow!("non-UTF-8 path {}", path.display()))?;
        if file_type.is_dir() {
            collect_html(root, &path, out)?;
        } else if file_type.is_file() && path.extension() == Some("html") {
            out.push(path.strip_prefix(root)?.to_owned());
        }
    }
    Ok(())
}

fn finalize_page(
    stage_root: &Utf8Path,
    font_path: &Utf8Path,
    relative: &str,
    text: &str,
    public_url: &str,
    report: &mut FinalizeReport,
) -> Result<String> {
    let text = ensure_current_site_shell(text);
    let head_end = text.find("</head>").context("page has no </head>")?;
    let head = parse_head(&text[..head_end])?;
    check_internal_links(&text)?;

    let page_title = page_title(relative, &head.title)?;
    for key in DERIVED_META {
        if head.meta.contains_key(*key) {
            bail!("page declares {key}; finalize derives it");
        }
    }
    if head.has_canonical {
        bail!("page declares rel=canonical; finalize derives it");
    }

    let url_path = url_path(relative);
    let mut tags = Vec::new();
    if let Some(url_path) = &url_path {
        let canonical = format!("{public_url}{url_path}");
        tags.push(format!(r#"<link rel="canonical" href="{canonical}">"#));
        tags.push(meta_property("og:url", &canonical));
        if relative != NOT_FOUND_PAGE {
            report.canonical_urls.push(canonical);
        }
    }
    tags.push(meta_property("og:site_name", SITE_NAME));
    tags.push(meta_property("og:title", page_title));
    if !head.meta.contains_key("og:type") {
        tags.push(meta_property("og:type", "website"));
    }
    match head.meta.get("description") {
        Some(description) if description.chars().count() > MAX_DESCRIPTION => bail!(
            "meta description has {} characters; search results cut it after {MAX_DESCRIPTION}",
            description.chars().count()
        ),
        Some(description) => tags.push(meta_property("og:description", description)),
        None => report.missing_description.push(relative.to_owned()),
    }
    let declared_image = head.meta.get("og:image");
    let kicker = head.meta.get(CARD_META).map(String::as_str);
    let head_text = strip_card_meta(&text[..head_end]);
    let head_text = match (declared_image, kicker) {
        (Some(_), Some(kicker)) => {
            bail!("page declares both og:image and {CARD_META} {kicker:?}")
        }
        (Some(image), None) => {
            check_image(stage_root, image)?;
            replace_og_image(&head_text, image, &format!("{public_url}{image}"))?
        }
        (None, Some(NO_CARD)) => head_text,
        (None, Some(kicker)) => {
            let image = card_path(relative)?;
            render_card(stage_root, font_path, &image, page_title, kicker)?;
            tags.push(meta_property("og:image", &format!("{public_url}/{image}")));
            head_text
        }
        (None, None) => match shell::nav_section(relative) {
            Some(section) => {
                let image = card_path(relative)?;
                render_card(stage_root, font_path, &image, page_title, section.card_kicker())?;
                tags.push(meta_property("og:image", &format!("{public_url}/{image}")));
                head_text
            }
            None => {
                report.missing_image.push(relative.to_owned());
                head_text
            }
        },
    };
    let card = if tags.iter().any(|tag| tag.contains("og:image")) || declared_image.is_some() {
        "summary_large_image"
    } else {
        "summary"
    };
    tags.push(format!(r#"<meta name="twitter:card" content="{card}">"#));

    let mut rewritten = String::with_capacity(text.len() + 512);
    rewritten.push_str(&head_text);
    rewritten.push_str(&tags.join(""));
    rewritten.push_str(&text[head_end..]);
    rewrite_external_links(&rewritten, public_url)
}

/// What a built page declares about itself, read the same way finalize reads
/// it, so that cards linking to the page repeat its own title and summary.
pub(crate) struct DeclaredPage {
    pub title: String,
    pub description: String,
    pub image: String,
}

pub(crate) fn declared_page(relative: &str, text: &str) -> Result<DeclaredPage> {
    let head_end = text.find("</head>").context("page has no </head>")?;
    let head = parse_head(&text[..head_end])?;
    let field = |key: &str| {
        head.meta
            .get(key)
            .map(|value| decode_entities(value))
            .with_context(|| format!("{relative} declares no {key}"))
    };
    Ok(DeclaredPage {
        title: decode_entities(page_title(relative, &head.title)?),
        description: field("description")?,
        image: field("og:image")?,
    })
}

fn parse_head(head: &str) -> Result<PageHead> {
    let title_re = Regex::new(r"(?is)<title[^>]*>(.*?)</title>").expect("valid regex");
    let titles: Vec<String> = title_re
        .captures_iter(head)
        .map(|captures| captures[1].trim().to_owned())
        .collect();
    let title = match titles.as_slice() {
        [title] => title.clone(),
        [] => bail!("page has no <title>"),
        _ => bail!("page has {} <title> elements", titles.len()),
    };

    let tag_re = Regex::new(r"(?is)<(meta|link)\s[^>]*>").expect("valid regex");
    let mut meta = BTreeMap::new();
    let mut has_canonical = false;
    for tag in tag_re.find_iter(head) {
        let attrs = parse_attrs(tag.as_str());
        if tag.as_str()[1..].to_ascii_lowercase().starts_with("link") {
            has_canonical |= attrs.get("rel").is_some_and(|rel| rel == "canonical");
            continue;
        }
        let Some(key) = attrs.get("property").or_else(|| attrs.get("name")) else {
            continue;
        };
        let Some(content) = attrs.get("content") else {
            continue;
        };
        if meta.insert(key.clone(), content.clone()).is_some() {
            bail!("page declares meta {key} more than once");
        }
    }
    Ok(PageHead {
        title,
        meta,
        has_canonical,
    })
}

fn parse_attrs(tag: &str) -> BTreeMap<String, String> {
    let attr_re = Regex::new(r#"([A-Za-z:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))"#)
        .expect("valid regex");
    attr_re
        .captures_iter(tag)
        .map(|captures| {
            let value = captures
                .get(2)
                .or_else(|| captures.get(3))
                .or_else(|| captures.get(4))
                .map_or("", |m| m.as_str());
            (captures[1].to_ascii_lowercase(), value.to_owned())
        })
        .collect()
}

fn page_title<'a>(relative: &str, title: &'a str) -> Result<&'a str> {
    if relative == "index.html" {
        if title != SITE_NAME {
            bail!("home page title must be {SITE_NAME:?}, found {title:?}");
        }
        return Ok(title);
    }
    match title.strip_suffix(TITLE_SUFFIX) {
        Some(page) if !page.trim().is_empty() => Ok(page),
        _ => bail!("title must end with {TITLE_SUFFIX:?}, found {title:?}"),
    }
}

fn url_path(relative: &str) -> Option<String> {
    // HTML under assets/ is embedded in other pages (interactive figures), so it
    // gets no canonical URL and stays out of sitemap.xml.
    if relative.starts_with(ASSETS_DIR) {
        return None;
    }
    if relative == "index.html" {
        return Some("/".to_owned());
    }
    Some(match relative.strip_suffix("/index.html") {
        Some(dir) => format!("/{dir}/"),
        None => format!("/{relative}"),
    })
}

fn check_internal_links(text: &str) -> Result<()> {
    let href_re = Regex::new(r#"(?i)\shref\s*=\s*["']([^"']*)["']"#).expect("valid regex");
    let offenders: Vec<&str> = href_re
        .captures_iter(text)
        .map(|captures| captures.get(1).expect("group").as_str())
        .filter(|href| !href.contains("://") && !href.starts_with("//"))
        .filter(|href| {
            let path = href.split(['?', '#']).next().unwrap_or_default();
            path == "index.html" || path.ends_with("/index.html")
        })
        .collect();
    if !offenders.is_empty() {
        bail!(
            "internal links must use the directory URL, not index.html: {}",
            offenders.join(", ")
        );
    }
    Ok(())
}

fn ensure_current_site_shell(text: &str) -> String {
    let header_re = Regex::new(
        r#"(?is)<header\s[^>]*class\s*=\s*["'][^"']*\bpublication-header\b[^"']*["'][^>]*>"#,
    )
    .expect("valid regex");
    if !header_re.is_match(text) || text.contains(SITE_SHELL_STYLESHEET) {
        return text.to_owned();
    }
    let Some(head_end) = text.find("</head>") else {
        return text.to_owned();
    };
    let injection = format!(
        r#"<link rel="stylesheet" href="{TOKENS_STYLESHEET}"><link rel="stylesheet" href="{SITE_SHELL_STYLESHEET}">"#
    );
    let mut rewritten = String::with_capacity(text.len() + injection.len());
    rewritten.push_str(&text[..head_end]);
    rewritten.push_str(&injection);
    rewritten.push_str(&text[head_end..]);
    rewritten
}

fn rewrite_external_links(text: &str, public_url: &str) -> Result<String> {
    let site = Url::parse(public_url).context("site public URL is invalid")?;
    let anchor_re = Regex::new(r"(?is)<a\b[^>]*>").expect("valid regex");
    Ok(anchor_re
        .replace_all(text, |captures: &regex_lite::Captures<'_>| {
            rewrite_external_anchor(&captures[0], &site)
        })
        .into_owned())
}

fn rewrite_external_anchor(tag: &str, site: &Url) -> String {
    let attrs = parse_attrs(tag);
    let Some(href) = attrs.get("href") else {
        return tag.to_owned();
    };
    let Ok(url) = site.join(href) else {
        return tag.to_owned();
    };
    if !matches!(url.scheme(), "http" | "https") || url.host_str() == site.host_str() {
        return tag.to_owned();
    }

    let mut rel: Vec<&str> = attrs
        .get("rel")
        .map(|value| value.split_whitespace().collect())
        .unwrap_or_default();
    if !rel
        .iter()
        .any(|value| value.eq_ignore_ascii_case("noopener"))
    {
        rel.push("noopener");
    }
    let rewritten = set_tag_attribute(tag, "target", "_blank");
    set_tag_attribute(&rewritten, "rel", &rel.join(" "))
}

fn set_tag_attribute(tag: &str, name: &str, value: &str) -> String {
    let pattern = format!(r#"(?i)(\s{name}\s*=\s*)(?:"[^"]*"|'[^']*'|[^\s>]+)"#);
    let attr_re = Regex::new(&pattern).expect("valid attribute regex");
    if attr_re.is_match(tag) {
        return attr_re
            .replace(tag, |captures: &regex_lite::Captures<'_>| {
                format!(r#"{}"{value}""#, &captures[1])
            })
            .into_owned();
    }
    let Some(end) = tag.rfind('>') else {
        return tag.to_owned();
    };
    let mut insertion = end;
    if tag[..end].trim_end().ends_with('/') {
        insertion = tag[..end].rfind('/').unwrap_or(end);
    }
    let mut rewritten = String::with_capacity(tag.len() + name.len() + value.len() + 4);
    rewritten.push_str(&tag[..insertion]);
    rewritten.push_str(&format!(r#" {name}="{value}""#));
    rewritten.push_str(&tag[insertion..]);
    rewritten
}

fn check_image(stage_root: &Utf8Path, image: &str) -> Result<()> {
    let Some(relative) = image.strip_prefix('/') else {
        bail!("og:image must be a root-relative path, found {image:?}");
    };
    let relative = relative.split(['?', '#']).next().unwrap_or_default();
    if !stage_root.join(relative).is_file() {
        bail!("og:image {image:?} is not part of the published site");
    }
    Ok(())
}

fn replace_og_image(head: &str, image: &str, absolute: &str) -> Result<String> {
    let tag_re = Regex::new(r"(?is)<meta\s[^>]*>").expect("valid regex");
    let mut replaced = 0;
    let rewritten = tag_re.replace_all(head, |captures: &regex_lite::Captures<'_>| {
        let tag = &captures[0];
        let attrs = parse_attrs(tag);
        if attrs.get("property").is_some_and(|key| key == "og:image") {
            replaced += 1;
            meta_property("og:image", absolute)
        } else {
            tag.to_owned()
        }
    });
    if replaced != 1 {
        bail!("expected one og:image tag for {image:?}, found {replaced}");
    }
    Ok(rewritten.into_owned())
}

fn strip_card_meta(head: &str) -> String {
    let tag_re = Regex::new(r"(?is)<meta\s[^>]*>\s*").expect("valid regex");
    tag_re
        .replace_all(head, |captures: &regex_lite::Captures<'_>| {
            let attrs = parse_attrs(&captures[0]);
            if attrs.get("name").is_some_and(|key| key == CARD_META) {
                String::new()
            } else {
                captures[0].to_owned()
            }
        })
        .into_owned()
}

fn card_path(relative: &str) -> Result<String> {
    let page = match relative.strip_suffix("/index.html") {
        Some(dir) => dir,
        None => relative
            .strip_suffix(".html")
            .with_context(|| format!("{relative} is not an html page"))?,
    };
    Ok(format!("assets/og/{page}.png"))
}

fn render_card(
    stage_root: &Utf8Path,
    font_path: &Utf8Path,
    image: &str,
    title: &str,
    kicker: &str,
) -> Result<()> {
    let output = stage_root.join(image);
    if let Some(parent) = output.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    let mut child = Command::new("typst")
        .arg("compile")
        .arg(format!("--root={stage_root}"))
        .arg(format!("--font-path={font_path}"))
        .args(["--format", "png", "--ppi", "144"])
        .arg("--input")
        .arg(format!("title={}", decode_entities(title)))
        .arg("--input")
        .arg(format!("kicker={kicker}"))
        .arg("-")
        .arg(&output)
        .stdin(Stdio::piped())
        .spawn()
        .context("failed to run typst")?;
    child
        .stdin
        .take()
        .context("typst stdin unavailable")?
        .write_all(CARD_TEMPLATE.as_bytes())
        .context("failed to send card template to typst")?;
    let status = child.wait().context("failed to wait for typst")?;
    if !status.success() {
        bail!("typst failed to render the {image} card");
    }
    Ok(())
}

fn decode_entities(text: &str) -> String {
    text.replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
}

fn meta_property(property: &str, content: &str) -> String {
    format!(
        r#"<meta property="{property}" content="{}">"#,
        content.replace('"', "&quot;")
    )
}

fn render_sitemap(urls: &[String]) -> String {
    let mut xml = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n",
    );
    for url in urls {
        xml.push_str("  <url><loc>");
        xml.push_str(&url.replace('&', "&amp;").replace('<', "&lt;"));
        xml.push_str("</loc></url>\n");
    }
    xml.push_str("</urlset>\n");
    xml
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stage_with(pages: &[(&str, &str)]) -> tempfile::TempDir {
        let temp = tempfile::tempdir().unwrap();
        for (relative, content) in pages {
            let path = temp.path().join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, content).unwrap();
        }
        temp
    }

    fn root(temp: &tempfile::TempDir) -> &Utf8Path {
        Utf8Path::from_path(temp.path()).unwrap()
    }

    #[test]
    fn injects_canonical_and_open_graph_from_title_and_description() {
        let temp = stage_with(&[
            ("index.html", "<html><head><title>Specter Labs</title><meta name=\"description\" content=\"Home\"><meta property=\"og:image\" content=\"/a.webp\"></head><body></body></html>"),
            ("a.webp", ""),
            ("blog/index.html", "<html><head><title>Writing | Specter Labs</title><meta name=\"spctr:card\" content=\"none\"></head><body><a href=\"/blog/x/\">x</a></body></html>"),
            ("404.html", "<html><head><title>Page not found | Specter Labs</title></head><body></body></html>"),
            ("assets/blog/fig.html", "<html><head><title>Figure | Specter Labs</title></head><body></body></html>"),
        ]);
        let report =
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org/").unwrap();

        let home = fs::read_to_string(temp.path().join("index.html")).unwrap();
        assert!(home.contains(r#"<link rel="canonical" href="https://example.org/">"#));
        assert!(home.contains(r#"<meta property="og:title" content="Specter Labs">"#));
        assert!(home.contains(r#"<meta property="og:description" content="Home">"#));
        assert!(home.contains(r#"<meta property="og:image" content="https://example.org/a.webp">"#));
        assert!(home.contains(r#"<meta name="twitter:card" content="summary_large_image">"#));

        let blog = fs::read_to_string(temp.path().join("blog/index.html")).unwrap();
        assert!(blog.contains(r#"<meta property="og:title" content="Writing">"#));
        assert!(blog.contains(r#"<meta property="og:url" content="https://example.org/blog/">"#));
        assert!(blog.contains(r#"<meta name="twitter:card" content="summary">"#));

        let not_found = fs::read_to_string(temp.path().join("404.html")).unwrap();
        assert!(not_found.contains(r#"<link rel="canonical" href="https://example.org/404.html">"#));
        assert!(not_found.contains(r#"<meta property="og:url" content="https://example.org/404.html">"#));
        let figure = fs::read_to_string(temp.path().join("assets/blog/fig.html")).unwrap();
        assert!(!figure.contains("canonical"));

        assert_eq!(
            report.canonical_urls,
            vec!["https://example.org/", "https://example.org/blog/"]
        );
        assert_eq!(
            report.missing_description,
            vec!["404.html", "assets/blog/fig.html", "blog/index.html"]
        );
        let sitemap = fs::read_to_string(temp.path().join("sitemap.xml")).unwrap();
        assert!(sitemap.contains("<loc>https://example.org/blog/</loc>"));
        assert!(!sitemap.contains("404"));
        assert!(!sitemap.contains("assets"));
    }

    #[test]
    fn rejects_long_descriptions() {
        let description = "a".repeat(MAX_DESCRIPTION + 1);
        let temp = stage_with(&[(
            "blog/index.html",
            &format!("<html><head><title>Writing | Specter Labs</title><meta name=\"description\" content=\"{description}\"></head></html>"),
        )]);
        let error =
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org/").unwrap_err();
        assert!(format!("{error:#}").contains("meta description has 161 characters"));
    }

    #[test]
    fn rejects_titles_without_site_suffix() {
        let temp = stage_with(&[(
            "blog/index.html",
            "<html><head><title>Writing | SPECTER Labs</title></head></html>",
        )]);
        let error =
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org").unwrap_err();
        assert!(format!("{error:#}").contains("blog/index.html: title must end with"));
    }

    #[test]
    fn rejects_page_declared_canonical_and_index_html_links() {
        let temp = stage_with(&[
            (
                "a/index.html",
                "<html><head><title>A | Specter Labs</title><link rel=\"canonical\" href=\"/a/\"></head></html>",
            ),
            (
                "b/index.html",
                "<html><head><title>B | Specter Labs</title></head><body><a href=\"../a/index.html#x\">a</a></body></html>",
            ),
        ]);
        let message = format!(
            "{:#}",
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org").unwrap_err()
        );
        assert!(message.contains("a/index.html: page declares rel=canonical"));
        assert!(message.contains("b/index.html: internal links must use the directory URL"));
    }

    #[test]
    fn rejects_og_image_outside_published_site() {
        let temp = stage_with(&[(
            "a/index.html",
            "<html><head><title>A | Specter Labs</title><meta property=\"og:image\" content=\"/missing.png\"></head></html>",
        )]);
        let message = format!(
            "{:#}",
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org").unwrap_err()
        );
        assert!(message.contains("is not part of the published site"));
    }

    #[test]
    fn strips_no_card_marker_and_reports_only_undeclared_pages() {
        let temp = stage_with(&[
            (
                "a/index.html",
                "<html><head><title>A | Specter Labs</title><meta name=\"spctr:card\" content=\"none\"></head></html>",
            ),
            ("b/index.html", "<html><head><title>B | Specter Labs</title></head></html>"),
        ]);
        let report =
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org").unwrap();

        let a = fs::read_to_string(temp.path().join("a/index.html")).unwrap();
        assert!(!a.contains("spctr:card"));
        assert!(!a.contains("og:image"));
        assert!(a.contains(r#"<meta name="twitter:card" content="summary">"#));
        assert_eq!(report.missing_image, vec!["b/index.html"]);
    }

    #[test]
    fn rejects_og_image_together_with_card() {
        let temp = stage_with(&[
            (
                "a/index.html",
                "<html><head><title>A | Specter Labs</title><meta property=\"og:image\" content=\"/a.png\"><meta name=\"spctr:card\" content=\"Dossier\"></head></html>",
            ),
            ("a.png", ""),
        ]);
        let message = format!(
            "{:#}",
            finalize_site(root(&temp), Utf8Path::new("fonts"), "https://example.org").unwrap_err()
        );
        assert!(message.contains("page declares both og:image and spctr:card"));
    }

    #[test]
    fn loads_the_current_shell_after_embedded_report_styles() {
        let report = r#"<html><head><style>:root{--sl-layout-brand-size:51px}</style></head><body><header class="publication-header"></header></body></html>"#;
        let rewritten = ensure_current_site_shell(report);
        assert!(rewritten.contains(r#"href="/tokens.css""#));
        assert!(rewritten.contains(r#"href="/assets/site-shell.css""#));
        assert!(
            rewritten.find(SITE_SHELL_STYLESHEET).unwrap()
                > rewritten.find("--sl-layout-brand-size:51px").unwrap()
        );

        let already_current = format!(
            r#"<html><head><link rel="stylesheet" href="{SITE_SHELL_STYLESHEET}"></head><body><header class="publication-header"></header></body></html>"#
        );
        assert_eq!(ensure_current_site_shell(&already_current), already_current);
        assert_eq!(
            ensure_current_site_shell("<html><head></head><body></body></html>"),
            "<html><head></head><body></body></html>"
        );
    }

    #[test]
    fn external_links_open_in_a_new_tab_without_changing_site_links() {
        let input = r#"<a href="https://outside.example/a">outside</a><a href='//outside.example/b' target='_self' rel='nofollow'>protocol relative</a><a href="https://outside.example/c" target="_blank" rel="noopener noreferrer">ready</a><a href="https://specterlab.org/dossiers/">absolute site</a><a href="/blog/">relative site</a><a href="mailto:contact@specterlab.org">mail</a>"#;
        let rewritten = rewrite_external_links(input, "https://specterlab.org").unwrap();

        assert!(rewritten
            .contains(r#"href="https://outside.example/a" target="_blank" rel="noopener""#));
        assert!(rewritten
            .contains(r#"href='//outside.example/b' target="_blank" rel="nofollow noopener""#));
        assert!(rewritten.contains(
            r#"href="https://outside.example/c" target="_blank" rel="noopener noreferrer""#
        ));
        assert!(
            rewritten.contains(r#"<a href="https://specterlab.org/dossiers/">absolute site</a>"#)
        );
        assert!(rewritten.contains(r#"<a href="/blog/">relative site</a>"#));
        assert!(rewritten.contains(r#"<a href="mailto:contact@specterlab.org">mail</a>"#));
    }

    #[test]
    fn card_paths_follow_page_urls() {
        assert_eq!(
            card_path("research-notes/x/index.html").unwrap(),
            "assets/og/research-notes/x.png"
        );
        assert_eq!(card_path("404.html").unwrap(), "assets/og/404.png");
    }
}
