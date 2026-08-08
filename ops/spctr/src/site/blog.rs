use anyhow::{anyhow, bail, Context, Result};
use camino::Utf8Path;
use rayon::prelude::*;
use std::collections::HashSet;
use std::fs;
use std::process::Command;

use crate::graph::{self, RegistryGraph};
use crate::markdown;
use crate::registry;
use crate::site::discover;

struct FigureSource {
    slug: &'static str,
    pdf_dir: &'static str,
    required: bool,
}

const FIGURE_SOURCES: &[FigureSource] = &[
    FigureSource {
        slug: "wonton-soup",
        pdf_dir: "dossiers/wonton-soup/docs/figures/out",
        required: true,
    },
    FigureSource {
        slug: "wonton-soup-follow-up",
        pdf_dir: "dossiers/wonton-soup/docs/figures/out",
        required: false,
    },
];

pub(crate) fn figure_source_patterns(slug: &str) -> Vec<String> {
    FIGURE_SOURCES
        .iter()
        .filter(|source| source.slug == slug)
        .map(|source| format!("{}/**/*.pdf", source.pdf_dir))
        .collect()
}

pub fn build_blog(repo_root: &Utf8Path, write: bool) -> Result<()> {
    let posts = discover::discover_all_blog_posts(repo_root)?;
    let has_published = posts.iter().any(is_published_post);
    build_blog_for_posts_inner(repo_root, &posts, write, true)?;
    if !has_published {
        bail!("no published blog posts found (set 'release: published' in YAML front matter)");
    }
    Ok(())
}

pub(crate) fn build_blog_preview(repo_root: &Utf8Path, write: bool) -> Result<()> {
    let posts = discover::discover_all_blog_posts(repo_root)?;
    build_blog_for_posts_inner(repo_root, &posts, write, false)
}

struct ResearchNoteRecord {
    slug: String,
    title: String,
    spctr_id: Option<String>,
    release_label: String,
    provenance: Option<String>,
    source_id: Option<String>,
    source_href: Option<String>,
}

pub(crate) fn build_research_notes(repo_root: &Utf8Path, write: bool) -> Result<usize> {
    let site_root = repo_root.join("site");
    let notes_root = site_root.join("research-notes");
    if !notes_root.is_dir() {
        return Ok(0);
    }

    let notes = load_research_notes(repo_root, &notes_root)?;
    if notes.is_empty() {
        return Ok(0);
    }

    let template = notes_root.join("pandoc-template.html");
    if !template.is_file() {
        bail!("missing pandoc template: site/research-notes/pandoc-template.html");
    }

    notes.par_iter().try_for_each(|note| -> Result<()> {
        let md_path = notes_root.join(&note.slug).join("index.md");
        let out_path = notes_root.join(&note.slug).join("index.html");
        let dest = if write {
            out_path.to_string()
        } else {
            "/dev/null".into()
        };

        let pagetitle = format!("{} | SPECTER Labs", note.title);
        let mut command = Command::new("pandoc");
        command
            .arg(&md_path)
            .args([
                "--from=markdown+autolink_bare_uris",
                "--to=html5",
                "--standalone",
                "--wrap=none",
            ])
            .arg(format!("--template={}", template))
            .args(["--toc", "--toc-depth=2", "--mathml"])
            .arg("--metadata")
            .arg("lang=en")
            .arg("--metadata")
            .arg(format!("pagetitle={pagetitle}"))
            .arg("--metadata")
            .arg(format!("slug={}", note.slug));

        if let Some(spctr_id) = &note.spctr_id {
            command
                .arg("--metadata")
                .arg(format!("spctr_id={spctr_id}"));
        }
        command
            .arg("--metadata")
            .arg(format!("release={}", note.release_label));
        if let Some(provenance) = &note.provenance {
            command
                .arg("--metadata")
                .arg(format!("provenance={provenance}"));
        }
        if let Some(source_id) = &note.source_id {
            command
                .arg("--metadata")
                .arg(format!("source_id={source_id}"));
        }
        if let Some(source_href) = &note.source_href {
            command
                .arg("--metadata")
                .arg(format!("source_href={source_href}"));
        }
        let status = command
            .arg(format!("--output={dest}"))
            .current_dir(&site_root)
            .status()
            .context("failed to run pandoc")?;

        if !status.success() {
            bail!("pandoc failed for research-notes/{}/index.md", note.slug);
        }

        if write {
            eprintln!("built research-notes/{}/index.html", note.slug);
        } else {
            eprintln!("validated research-notes/{}/index.md", note.slug);
        }
        Ok(())
    })?;

    Ok(notes.len())
}

pub(crate) fn build_blog_for_posts(
    repo_root: &Utf8Path,
    posts: &[discover::BlogPostRecord],
    write: bool,
) -> Result<()> {
    build_blog_for_posts_inner(repo_root, posts, write, true)
}

fn build_blog_for_posts_inner(
    repo_root: &Utf8Path,
    posts: &[discover::BlogPostRecord],
    write: bool,
    sync_assets: bool,
) -> Result<()> {
    let site_root = repo_root.join("site");

    let template = site_root.join("blog/pandoc-template.html");
    if !template.is_file() {
        bail!("missing pandoc template: blog/pandoc-template.html");
    }

    let blog_root = site_root.join("blog");
    let mut dirs: Vec<_> = Vec::new();
    for entry in
        fs::read_dir(&blog_root).with_context(|| format!("failed to read {}", blog_root))?
    {
        let entry = entry?;
        if entry.path().is_dir() {
            dirs.push(entry);
        }
    }

    let published_slugs: HashSet<String> = posts
        .iter()
        .filter(|post| is_published_post(post))
        .map(|p| {
            p.href
                .trim_start_matches("blog/")
                .trim_end_matches('/')
                .to_owned()
        })
        .collect();

    if write && sync_assets {
        sync_figures_for_slugs(repo_root, &published_slugs)?;
    }

    for entry in &dirs {
        let slug = entry.file_name().to_string_lossy().to_string();
        let output = entry.path().join("index.html");
        if !published_slugs.contains(&slug) && output.is_file() && write {
            fs::remove_file(&output).with_context(|| {
                format!("failed to remove stale draft output {}", output.display())
            })?;
            eprintln!("removed stale output blog/{slug}/index.html");
        }
    }

    posts.par_iter().try_for_each(|post| -> Result<()> {
        if !is_published_post(post) {
            return Ok(());
        }
        let slug = discover::blog_slug_from_href(&post.href)?;
        let md_path = discover::blog_markdown_path(repo_root, slug);
        let out_path = site_root.join(format!("blog/{slug}/index.html"));

        let dest = if write {
            out_path.to_string()
        } else {
            "/dev/null".into()
        };

        let pagetitle = format!("{} | SPECTER Labs", post.title);
        let status = Command::new("pandoc")
            .arg(&md_path)
            .args([
                "--from=markdown+autolink_bare_uris",
                "--to=html5",
                "--standalone",
                "--wrap=none",
            ])
            .arg(format!("--template={}", template))
            .args(["--toc", "--toc-depth=2", "--mathml"])
            .arg("--metadata")
            .arg("lang=en")
            .arg("--metadata")
            .arg(format!("pagetitle={pagetitle}"))
            .arg("--metadata")
            .arg(format!("slug={slug}"))
            .arg("--metadata")
            .arg(format!("status={}", post.release))
            .arg(format!("--output={dest}"))
            .current_dir(&site_root)
            .status()
            .context("failed to run pandoc")?;

        if !status.success() {
            bail!("pandoc failed for blog/{slug}/index.md");
        }

        if write {
            eprintln!("built blog/{slug}/index.html");
        } else {
            eprintln!("validated blog/{slug}/index.md");
        }
        Ok(())
    })?;

    Ok(())
}

fn is_published_post(post: &discover::BlogPostRecord) -> bool {
    post.release == discover::RELEASE_PUBLISHED
}

pub(crate) fn load_published_posts(repo_root: &Utf8Path) -> Result<Vec<discover::BlogPostRecord>> {
    let graph =
        graph::build_with_options(repo_root, None, graph::GraphBuildOptions::site_records())?;
    load_published_posts_from_graph(&graph)
}

pub(crate) fn load_published_posts_from_graph(
    graph: &RegistryGraph,
) -> Result<Vec<discover::BlogPostRecord>> {
    let mut posts = graph
        .nodes_of_kind("article")
        .map(|node| {
            Ok(discover::BlogPostRecord {
                title: required_attr(node, "title")?,
                href: required_attr(node, "href")?,
                summary: required_attr(node, "summary")?,
                series: graph::attr_str(node, "series_id").map(str::to_owned),
                release: graph::attr_str(node, "release")
                    .unwrap_or(discover::RELEASE_PUBLISHED)
                    .to_owned(),
            })
        })
        .collect::<Result<Vec<_>>>()?;
    posts.sort_by(|left, right| left.href.cmp(&right.href));
    Ok(posts)
}

fn load_research_notes(
    repo_root: &Utf8Path,
    notes_root: &Utf8Path,
) -> Result<Vec<ResearchNoteRecord>> {
    let mut notes = Vec::new();
    let mut loaded_registry: Option<registry::Registry> = None;
    for entry in
        fs::read_dir(notes_root).with_context(|| format!("failed to read {}", notes_root))?
    {
        let entry = entry?;
        if !entry.path().is_dir() {
            continue;
        }
        let slug = entry.file_name().to_string_lossy().to_string();
        let md_path = notes_root.join(&slug).join("index.md");
        if !md_path.is_file() {
            continue;
        }

        let text =
            fs::read_to_string(&md_path).with_context(|| format!("failed to read {}", md_path))?;
        let front_matter = markdown::parse_front_matter(&text);

        let title = front_matter
            .get("title")
            .filter(|title| !title.is_empty())
            .cloned()
            .unwrap_or_else(|| markdown::extract_title(&text));
        if title.is_empty() {
            bail!("research-notes/{slug}/index.md: missing title");
        }

        let release_label = discover::article_release(&front_matter)
            .with_context(|| format!("research-notes/{slug}/index.md"))?;
        let provenance = research_note_provenance(&front_matter)
            .with_context(|| format!("research-notes/{slug}/index.md"))?;
        if loaded_registry.is_none() {
            loaded_registry = Some(registry::load_registry(repo_root)?);
        }
        let registry = loaded_registry.as_ref().expect("registry loaded");
        let spctr_id = registry::series_for_slug(registry, "N", &slug)
            .map(|series_id| format!("SPCTR {series_id}"))
            .with_context(|| {
                format!("research-notes/{slug}/index.md: missing registry N-series assignment")
            })?;
        let source_id = research_note_source_id(&front_matter, registry)
            .with_context(|| format!("research-notes/{slug}/index.md"))?;
        let source_href = source_id
            .as_deref()
            .and_then(|source_id| research_note_source_href(notes_root, registry, source_id));
        notes.push(ResearchNoteRecord {
            slug,
            title,
            spctr_id: Some(spctr_id),
            release_label,
            provenance,
            source_id,
            source_href,
        });
    }
    notes.sort_by(|left, right| left.slug.cmp(&right.slug));
    Ok(notes)
}

fn optional_front_matter(
    front_matter: &std::collections::HashMap<String, String>,
    key: &str,
) -> Option<String> {
    front_matter
        .get(key)
        .filter(|value| !value.is_empty())
        .cloned()
}

fn research_note_provenance(
    front_matter: &std::collections::HashMap<String, String>,
) -> Result<Option<String>> {
    let Some(provenance) = optional_front_matter(front_matter, "provenance") else {
        return Ok(None);
    };
    if !matches!(
        provenance.as_str(),
        "human-written" | "assistant-drafted" | "generated-analysis" | "human-reviewed"
    ) {
        bail!(
            "unknown research note provenance '{provenance}' (expected human-written, assistant-drafted, generated-analysis, or human-reviewed)"
        );
    }
    Ok(Some(provenance))
}

fn research_note_source_id(
    front_matter: &std::collections::HashMap<String, String>,
    registry: &registry::Registry,
) -> Result<Option<String>> {
    let Some(source_id) = optional_front_matter(front_matter, "source_id") else {
        return Ok(None);
    };
    if !registry.series.contains_key(&source_id) {
        bail!("unknown source_id '{source_id}'");
    }
    Ok(Some(source_id))
}

fn research_note_source_href(
    notes_root: &Utf8Path,
    registry: &registry::Registry,
    source_id: &str,
) -> Option<String> {
    let slug = &registry.series.get(source_id)?.slug;
    let site_root = notes_root.parent()?;
    match source_id.split_once('-')?.0 {
        "D" if site_root
            .join("dossiers")
            .join(slug)
            .join("index.html")
            .is_file() =>
        {
            Some(format!("../../dossiers/{slug}/"))
        }
        "B" if is_published_md(&notes_root.join(slug).join("index.md")) => {
            Some(format!("../{slug}/"))
        }
        "B" if is_published_md(&site_root.join("blog").join(slug).join("index.md")) => {
            Some(format!("../../blog/{slug}/"))
        }
        "N" if notes_root.join(slug).join("index.md").is_file() => Some(format!("../{slug}/")),
        _ => None,
    }
}

fn is_published_md(path: &Utf8Path) -> bool {
    path.is_file()
        && fs::read_to_string(path)
            .ok()
            .as_deref()
            .map(markdown::parse_front_matter)
            .and_then(|fm| fm.get("release").map(|v| v == "published"))
            .unwrap_or(false)
}

fn required_attr(node: &graph::GraphNode, key: &str) -> Result<String> {
    graph::attr_str(node, key)
        .map(str::to_owned)
        .ok_or_else(|| anyhow!("{}: missing article attr '{key}'", node.id))
}

fn sync_figures_for_slugs(repo_root: &Utf8Path, published_slugs: &HashSet<String>) -> Result<()> {
    for source in FIGURE_SOURCES {
        if !published_slugs.contains(source.slug) {
            continue;
        }
        let md_path = discover::blog_markdown_path(repo_root, source.slug);
        if !md_path.is_file() {
            if source.required {
                bail!("missing blog markdown: site/blog/{}/index.md", source.slug);
            }
            continue;
        }
        let pdf_dir = repo_root.join(source.pdf_dir);
        if !pdf_dir.is_dir() {
            if source.required {
                bail!("missing figure PDF directory: {}", source.pdf_dir);
            }
            continue;
        }
        sync_figures(repo_root, source.slug, &pdf_dir)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(root: &Utf8Path, rel: &str, content: &str) {
        let path = root.join(rel);
        fs::create_dir_all(path.parent().expect("test path has parent")).unwrap();
        fs::write(path, content).unwrap();
    }

    #[test]
    fn build_blog_write_removes_stale_draft_outputs() {
        let tmp = tempfile::tempdir().unwrap();
        let root = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");
        write(root, "site/blog/pandoc-template.html", "$body$");
        write(
            root,
            "site/blog/draft-note/index.md",
            r#"---
title: Draft Note
release: draft
summary: Not public yet.
---

# Draft Note
"#,
        );
        write(
            root,
            "site/blog/draft-note/index.html",
            "stale draft output",
        );

        let error = build_blog(root, true).unwrap_err();
        let message = format!("{error:#}");

        assert!(
            message.contains("no published blog posts found"),
            "got: {message}"
        );
        assert!(
            !root.join("site/blog/draft-note/index.html").exists(),
            "draft output should be removed, not retained or regenerated"
        );
    }
}

fn sync_figures(repo_root: &Utf8Path, slug: &str, pdf_dir: &Utf8Path) -> Result<()> {
    let md_path = discover::blog_markdown_path(repo_root, slug);
    let assets_dir = repo_root.join(format!("site/assets/blog/{slug}"));
    fs::create_dir_all(&assets_dir).with_context(|| format!("failed to create {}", assets_dir))?;

    let text =
        fs::read_to_string(&md_path).with_context(|| format!("failed to read {}", md_path))?;

    let pattern = format!("assets/blog/{slug}/");
    let png_names: Vec<String> = text
        .lines()
        .flat_map(|line| extract_png_refs(line, &pattern))
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();

    if png_names.is_empty() {
        return Ok(());
    }

    remove_stale_pngs(&assets_dir, &png_names)?;

    let converter = detect_pdf_converter()?;

    for png_name in &png_names {
        let pdf_name = png_name.replace(".png", ".pdf");
        let pdf_path = pdf_dir.join(&pdf_name);
        let png_path = assets_dir.join(png_name);

        if !pdf_path.is_file() {
            bail!("missing required figure PDF: {}", pdf_path);
        }

        convert_pdf_to_png(&converter, &pdf_path, &png_path)?;
        eprintln!(
            "synced {}",
            png_path.strip_prefix(repo_root).unwrap_or(&png_path)
        );
    }

    Ok(())
}

#[allow(clippy::case_sensitive_file_extension_comparisons)]
fn extract_png_refs(line: &str, prefix: &str) -> Vec<String> {
    let mut refs = Vec::new();
    let mut start = 0;
    while let Some(idx) = line[start..].find(prefix) {
        let abs = start + idx + prefix.len();
        let rest = &line[abs..];
        if let Some(end) =
            rest.find(|c: char| !c.is_alphanumeric() && c != '.' && c != '-' && c != '_')
        {
            let name = &rest[..end];
            if name.ends_with(".png") {
                refs.push(name.to_owned());
            }
        } else if rest.ends_with(".png") {
            refs.push(rest.to_owned());
        }
        start = abs;
    }
    refs
}

fn remove_stale_pngs(assets_dir: &Utf8Path, wanted: &[String]) -> Result<()> {
    let wanted_set: HashSet<&str> = wanted.iter().map(String::as_str).collect();
    for entry in
        fs::read_dir(assets_dir).with_context(|| format!("failed to read {}", assets_dir))?
    {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_string();
        if Utf8Path::new(&name)
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("png"))
            && !wanted_set.contains(name.as_str())
        {
            fs::remove_file(entry.path())
                .with_context(|| format!("failed to remove {}", entry.path().display()))?;
            eprintln!("removed stale {}", entry.path().display());
        }
    }
    Ok(())
}

enum PdfConverter {
    Sips,
    Pdftoppm,
}

fn detect_pdf_converter() -> Result<PdfConverter> {
    if Command::new("sips").arg("--help").output().is_ok() {
        return Ok(PdfConverter::Sips);
    }
    if Command::new("pdftoppm").arg("-h").output().is_ok() {
        return Ok(PdfConverter::Pdftoppm);
    }
    bail!("no PDF->PNG tool found; install sips (macOS) or pdftoppm (poppler)")
}

fn convert_pdf_to_png(converter: &PdfConverter, pdf: &Utf8Path, png: &Utf8Path) -> Result<()> {
    let status = match converter {
        PdfConverter::Sips => Command::new("sips")
            .args(["-s", "format", "png", "--resampleHeightWidthMax", "2200"])
            .arg(pdf)
            .args(["--out"])
            .arg(png)
            .stdout(std::process::Stdio::null())
            .status()
            .context("failed to run sips")?,
        PdfConverter::Pdftoppm => {
            let stem = png.with_extension("");
            Command::new("pdftoppm")
                .args(["-png", "-r", "300", "-singlefile"])
                .arg(pdf)
                .arg(&stem)
                .stdout(std::process::Stdio::null())
                .status()
                .context("failed to run pdftoppm")?
        }
    };
    if !status.success() {
        bail!("PDF->PNG conversion failed for {pdf}");
    }
    Ok(())
}
