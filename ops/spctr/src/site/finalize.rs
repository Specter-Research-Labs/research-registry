use std::collections::BTreeMap;
use std::fs;
use std::io::Write;
use std::process::{Command, Stdio};

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::Regex;

pub const SITE_NAME: &str = "Specter Labs";
pub const TITLE_SUFFIX: &str = " | Specter Labs";
const NOT_FOUND_PAGE: &str = "404.html";
const ASSETS_DIR: &str = "assets/";
const CARD_META: &str = "spctr:card";
const NO_CARD: &str = "none";
const CARD_TEMPLATE: &str = include_str!("og-card.typ");

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
    let head_end = text.find("</head>").context("page has no </head>")?;
    let head = parse_head(&text[..head_end])?;
    check_internal_links(text)?;

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
        report.canonical_urls.push(canonical);
    }
    tags.push(meta_property("og:site_name", SITE_NAME));
    tags.push(meta_property("og:title", page_title));
    if !head.meta.contains_key("og:type") {
        tags.push(meta_property("og:type", "website"));
    }
    match head.meta.get("description") {
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
        (None, None) => {
            report.missing_image.push(relative.to_owned());
            head_text
        }
    };
    let card = match (declared_image, kicker) {
        (Some(_), _) => "summary_large_image",
        (None, Some(NO_CARD) | None) => "summary",
        (None, Some(_)) => "summary_large_image",
    };
    tags.push(format!(r#"<meta name="twitter:card" content="{card}">"#));

    let mut rewritten = String::with_capacity(text.len() + 512);
    rewritten.push_str(&head_text);
    rewritten.push_str(&tags.join(""));
    rewritten.push_str(&text[head_end..]);
    Ok(rewritten)
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
    if relative == NOT_FOUND_PAGE || relative.starts_with(ASSETS_DIR) {
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
            ("blog/index.html", "<html><head><title>Writing | Specter Labs</title></head><body><a href=\"/blog/x/\">x</a></body></html>"),
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
        assert!(!not_found.contains("canonical"));
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
    fn card_paths_follow_page_urls() {
        assert_eq!(
            card_path("research-notes/x/index.html").unwrap(),
            "assets/og/research-notes/x.png"
        );
        assert_eq!(card_path("404.html").unwrap(), "assets/og/404.png");
    }
}
