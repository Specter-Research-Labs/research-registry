use crate::site::cabinet::docs::{self, DocEntry};
use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use std::collections::HashMap;

const BACKLINKS_MARKER: &str = "<!-- BACKLINKS -->";
const DRAWERS_MARKER: &str = "<!-- DRAWERS -->";

pub fn render_doc(
    entry: &DocEntry,
    template: &Utf8Path,
    site_root: &Utf8Path,
    repo_root: &Utf8Path,
    built_at: &str,
    backlinks: &HashMap<(String, String), Vec<usize>>,
    all_entries: &[DocEntry],
) -> Result<()> {
    let out_dir = site_root
        .join("cabinet")
        .join(&entry.project_slug)
        .join(&entry.slug);
    std::fs::create_dir_all(&out_dir).with_context(|| format!("failed to create {}", out_dir))?;
    let out_file = out_dir.join("index.html");

    let slug_parts: Vec<&str> = entry.slug.split('/').collect();
    let depth = 2 + slug_parts.len();
    let root_prefix: String = "../".repeat(depth);

    let source_path = entry
        .path
        .strip_prefix(repo_root)
        .map(|p| p.as_str().replace('\\', "/"))
        .unwrap_or_else(|_| entry.path.to_string());

    let markdown = entry
        .render_markdown
        .as_deref()
        .ok_or_else(|| anyhow::anyhow!("missing transformed markdown for {}", entry.path))?;

    let temp_dir = tempfile::tempdir()?;
    let temp_md = temp_dir.path().join("doc.md");
    std::fs::write(&temp_md, markdown)?;

    let mut cmd = std::process::Command::new("pandoc");
    cmd.arg(&temp_md)
        .args([
            "--from=markdown+lists_without_preceding_blankline+autolink_bare_uris",
            "--to=html5",
        ])
        .args(["--standalone", "--wrap=none"])
        .arg(format!("--template={}", template))
        .args(["--toc", "--toc-depth=3", "--mathml"])
        .args(["--metadata", "lang=en"])
        .args([
            "--metadata",
            &format!("pagetitle={} | SPECTER Labs", entry.title),
        ])
        .args(["--metadata", &format!("slug={}", entry.slug)])
        .args(["--metadata", &format!("doc_id={}", entry.doc_id)])
        .args(["--metadata", &format!("dossier={}", entry.project_display)])
        .args(["--metadata", &format!("root_prefix={root_prefix}")])
        .args(["--metadata", &format!("source_path={source_path}")])
        .args(["--metadata", &format!("built_at={built_at}")]);

    if !entry.category.is_empty() {
        cmd.args(["--metadata", &format!("category={}", entry.category)]);
    }

    let output = cmd.output().context("failed to run pandoc")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("pandoc failed for {}: {}", entry.path, stderr.trim());
    }

    let html = String::from_utf8(output.stdout).context("pandoc produced invalid UTF-8")?;

    if !html.contains(BACKLINKS_MARKER) {
        bail!(
            "template missing backlinks marker ({BACKLINKS_MARKER}) for {}",
            entry.path
        );
    }

    let backlinks_html = render_backlinks_html(entry, backlinks, all_entries);
    let rendered = html.replace(BACKLINKS_MARKER, &backlinks_html);
    let rendered = publish_images(&rendered, entry, site_root)?;

    std::fs::write(&out_file, &rendered)
        .with_context(|| format!("failed to write {}", out_file))?;

    let rel = out_file
        .strip_prefix(site_root)
        .map(|p| p.to_string())
        .unwrap_or_else(|_| out_file.to_string());
    eprintln!("  {rel}");

    Ok(())
}

fn publish_images(html: &str, entry: &DocEntry, site_root: &Utf8Path) -> Result<String> {
    let image = regex_lite::Regex::new(r#"(<img\b[^>]*\bsrc=")([^"]+)(")"#)?;
    let content_start = html
        .find("<article class=\"doc-content\">")
        .context("cabinet template missing doc-content article")?;
    let content_end = content_start
        + html[content_start..]
            .find("</article>")
            .context("cabinet template missing closing article")?;
    let docs_root = entry.docs_root.canonicalize_utf8()?;
    let mut rendered = String::new();
    let mut end = 0;
    for cap in image.captures_iter(html) {
        let found = cap.get(0).unwrap();
        if found.start() < content_start || found.start() >= content_end {
            continue;
        }
        let src = &cap[2];
        if src.starts_with('/') || src.contains(':') {
            continue;
        }
        let source = entry
            .path
            .parent()
            .unwrap()
            .join(src)
            .canonicalize_utf8()
            .with_context(|| format!("missing image {src} in {}", entry.path))?;
        // Only publish images within the document collection, never arbitrary local paths.
        let relative = source
            .strip_prefix(&docs_root)
            .with_context(|| format!("image outside document collection: {src}"))?;
        let destination = site_root
            .join("cabinet")
            .join(&entry.project_slug)
            .join("_assets")
            .join(relative);
        std::fs::create_dir_all(destination.parent().unwrap())?;
        std::fs::copy(&source, &destination)?;
        rendered.push_str(&html[end..found.start()]);
        rendered.push_str(&format!(
            "{}/cabinet/{}/_assets/{}{}",
            &cap[1], entry.project_slug, relative, &cap[3]
        ));
        end = found.end();
    }
    rendered.push_str(&html[end..]);
    Ok(rendered)
}

fn render_backlinks_html(
    entry: &DocEntry,
    backlinks: &HashMap<(String, String), Vec<usize>>,
    all_entries: &[DocEntry],
) -> String {
    let key = (entry.project_slug.clone(), entry.slug.clone());
    let sources = backlinks.get(&key);

    let empty_section = |content: &str| -> String {
        format!(
            "<section class=\"doc-backlinks\" aria-label=\"Backlinks\">\
             <div class=\"toc-title\">Backlinks</div>\
             {content}\
             </section>"
        )
    };

    let Some(source_indices) = sources else {
        return empty_section("<p class=\"doc-backlinks-empty\">No backlinks yet.</p>");
    };
    if source_indices.is_empty() {
        return empty_section("<p class=\"doc-backlinks-empty\">No backlinks yet.</p>");
    }

    let mut items = String::new();
    for &idx in source_indices {
        let source = &all_entries[idx];
        let href = format!("{}/{}/", source.project_slug, source.slug);
        let rel_href = relative_backlink_href(entry, &href);

        let doc_id = html_escape(&source.doc_id);
        let title = html_escape(&source.title);
        let category_html = if source.category.is_empty() {
            String::new()
        } else {
            format!(
                "<span class=\"doc-backlinks-category\">{}</span>",
                html_escape(&source.category)
            )
        };

        items.push_str(&format!(
            "<li class=\"doc-backlinks-item\">\
             <a href=\"{rel_href}\" class=\"doc-backlinks-link\">\
             <span class=\"doc-backlinks-id\">{doc_id}</span>\
             <span class=\"doc-backlinks-title\">{title}</span>\
             {category_html}\
             </a>\
             </li>"
        ));
    }

    empty_section(&format!("<ul class=\"doc-backlinks-list\">{items}</ul>"))
}

fn relative_backlink_href(entry: &DocEntry, target_href: &str) -> String {
    let source_dir = format!("{}/{}", entry.project_slug, entry.slug);
    let target_dir = target_href.trim_end_matches('/');

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
        "./".to_owned()
    } else {
        rel
    }
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

pub fn build_index(entries: &[DocEntry], site_root: &Utf8Path) -> Result<()> {
    let index_template = site_root.join("cabinet/index-template.html");
    let template_text = std::fs::read_to_string(&index_template)
        .with_context(|| format!("failed to read {}", index_template))?;
    if !template_text.contains(DRAWERS_MARKER) {
        bail!("template missing drawers marker ({DRAWERS_MARKER})");
    }

    let groups = docs::group_by_project(entries);
    let mut drawers_html = String::new();

    for (project_slug, indices) in &groups {
        let display = indices
            .first()
            .map(|&idx| {
                let project_display = entries[idx].project_display.as_str();
                if project_display.is_empty() {
                    *project_slug
                } else {
                    project_display
                }
            })
            .unwrap_or(project_slug);

        let series_id = indices
            .first()
            .and_then(|&idx| entries[idx].series_id.as_deref())
            .unwrap_or("");

        let mut sorted_indices = indices.clone();
        sorted_indices.sort_by(|&a, &b| {
            let ea = &entries[a];
            let eb = &entries[b];
            category_sort_key(&ea.category)
                .cmp(&category_sort_key(&eb.category))
                .then_with(|| ea.title.to_lowercase().cmp(&eb.title.to_lowercase()))
                .then_with(|| ea.slug.cmp(&eb.slug))
        });

        let mut items_html = String::new();
        for &idx in &sorted_indices {
            let entry = &entries[idx];
            let href = format!("{}/{}/", entry.project_slug, entry.slug);
            let doc_id = html_escape(&entry.doc_id);
            let title = html_escape(&entry.title);
            let cat_span = if entry.category.is_empty() {
                String::new()
            } else {
                format!(
                    "<span class=\"drawer-item-category\">{}</span>",
                    html_escape(&entry.category)
                )
            };
            items_html.push_str(&format!(
                "<a class=\"drawer-item\" href=\"{href}\">\
                 <span class=\"drawer-item-id\">{doc_id}</span>\
                 <span class=\"drawer-item-title\">{title}</span>\
                 {cat_span}\
                 </a>"
            ));
        }

        let series_badge = if series_id.is_empty() {
            String::new()
        } else {
            format!("<span class=\"drawer-tab-series\">SPCTR {series_id}</span>")
        };

        drawers_html.push_str(&format!(
            "<div class=\"cabinet-drawer\">\
             <div class=\"drawer-tab\">\
             {}{series_badge}\
             <span class=\"drawer-tab-count\">{}</span>\
             </div>\
             <div class=\"drawer-body\">\
             {items_html}\
             </div></div>",
            html_escape(display),
            sorted_indices.len()
        ));
    }

    let index_html = template_text.replace(DRAWERS_MARKER, &drawers_html);
    let out = site_root.join("cabinet/index.html");
    std::fs::write(&out, &index_html).with_context(|| format!("failed to write {out}"))?;

    let rel = out
        .strip_prefix(site_root)
        .map(|p| p.to_string())
        .unwrap_or_else(|_| out.to_string());
    eprintln!("  {rel}");

    Ok(())
}

fn category_sort_key(category: &str) -> (u8, String) {
    if category.is_empty() {
        (1, String::new())
    } else {
        (0, category.to_lowercase())
    }
}

#[cfg(test)]
mod image_tests {
    use super::*;

    #[test]
    fn publishes_document_images_without_rewriting_the_site_logo() {
        let tmp = tempfile::tempdir().unwrap();
        let root = Utf8Path::from_path(tmp.path()).unwrap();
        let docs = root.join("docs");
        std::fs::create_dir_all(docs.join("figures")).unwrap();
        std::fs::create_dir_all(docs.join("concepts")).unwrap();
        std::fs::write(docs.join("figures/example.svg"), "<svg/>").unwrap();
        let entry = DocEntry {
            path: docs.join("concepts/example.md"),
            docs_root: docs,
            project_kind: "addenda".into(),
            project_slug: "example".into(),
            publish_docs: true,
            published: true,
            title: "Example".into(),
            slug: "concepts/example".into(),
            category: String::new(),
            doc_id: "A-001.001".into(),
            project_display: "Example".into(),
            series_id: None,
            render_markdown: None,
        };
        let html = r#"<img src="../../../assets/logo-black.svg"><article class="doc-content"><img src="../figures/example.svg"><img src="https://example.org/image.svg"></article>"#;
        let rendered = publish_images(html, &entry, &root.join("site")).unwrap();
        assert!(rendered.contains("src=\"../../../assets/logo-black.svg\""));
        assert!(rendered.contains("src=\"/cabinet/example/_assets/figures/example.svg\""));
        assert!(rendered.contains("src=\"https://example.org/image.svg\""));
        assert_eq!(
            std::fs::read_to_string(root.join("site/cabinet/example/_assets/figures/example.svg"))
                .unwrap(),
            "<svg/>"
        );
        assert!(publish_images(
            &html.replace("../figures/example.svg", "../missing.svg"),
            &entry,
            &root.join("site")
        )
        .is_err());
    }
}
