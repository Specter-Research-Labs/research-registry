use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use rayon::prelude::*;
use std::fs;
use std::process::Command;

use crate::markdown;
use crate::site::{blog, discover};

pub fn build_pdf(repo_root: &Utf8Path, slug: &str) -> Result<Utf8PathBuf> {
    let md_path = discover::blog_markdown_path(repo_root, slug);
    if !md_path.is_file() {
        bail!("blog post not found: site/blog/{slug}/index.md");
    }

    let pdf_path = repo_root.join(format!("site/blog/{slug}/{slug}.pdf"));

    let text =
        fs::read_to_string(&md_path).with_context(|| format!("failed to read {}", md_path))?;
    let fm = markdown::parse_front_matter(&text);
    let title = fm
        .get("title")
        .cloned()
        .unwrap_or_else(|| markdown::extract_title(&text));
    if title.is_empty() {
        bail!("blog/{slug}/index.md: no title found");
    }

    let preprocessed = preprocess_for_pdf(&text, slug);

    let typst_content = pandoc_markdown_to_typst(repo_root, &preprocessed, slug)?;

    let wrapped = wrap_in_paper(&typst_content, &title);

    let typ_path = repo_root.join(format!("site/blog/{slug}/{slug}.typ"));

    fs::write(&typ_path, &wrapped).with_context(|| format!("failed to write {}", typ_path))?;

    let font_path = repo_root.join("addenda/typst-field-manual/assets/fonts");
    let status = Command::new("typst")
        .arg("compile")
        .arg(format!("--root={}", repo_root))
        .arg(format!("--font-path={}", font_path))
        .arg(&typ_path)
        .arg(&pdf_path)
        .status()
        .context("failed to run typst")?;

    fs::remove_file(&typ_path).ok();

    if !status.success() {
        bail!("typst compile failed for blog/{slug}");
    }

    eprintln!("built blog/{slug}/{slug}.pdf");
    Ok(pdf_path)
}

pub fn build_all_pdfs(repo_root: &Utf8Path) -> Result<()> {
    let posts = blog::load_published_posts(repo_root)?;
    build_all_pdfs_for_posts(repo_root, &posts)
}

pub(crate) fn build_all_pdfs_for_posts(
    repo_root: &Utf8Path,
    posts: &[discover::BlogPostRecord],
) -> Result<()> {
    if posts.is_empty() {
        bail!("no published blog posts found");
    }
    posts.par_iter().try_for_each(|post| -> Result<()> {
        let slug = discover::blog_slug_from_href(&post.href)?;
        build_pdf(repo_root, slug)?;
        Ok(())
    })?;
    Ok(())
}

fn preprocess_for_pdf(text: &str, slug: &str) -> String {
    let figures = regex_lite::Regex::new(r#"(?s)<figure[^>]*>\s*<img src="([^"]+)" alt="[^"]*"\s*/?>\s*<figcaption>(.*?)</figcaption>\s*</figure>"#).expect("valid figure pattern");
    let text = figures.replace_all(text, |caps: &regex_lite::Captures| {
        format!("\n![{}]({})\n", &caps[2], &caps[1])
    });
    let title = markdown::parse_front_matter(&text).get("title").cloned();
    let mut removed_title = false;
    let mut output = String::with_capacity(text.len());
    let mut in_stepper = false;
    let mut stepper_depth = 0;

    for line in text.lines() {
        let trimmed = line.trim();
        if !removed_title
            && title
                .as_ref()
                .is_some_and(|title| trimmed == format!("# {title}"))
        {
            removed_title = true;
            continue;
        }

        if in_stepper {
            if trimmed.contains("class=\"ws-stepper")
                || trimmed.starts_with("<div class=\"ws-stepper")
            {
                stepper_depth += 1;
            }
            if trimmed == "</div>" {
                stepper_depth -= 1;
                if stepper_depth == 0 {
                    in_stepper = false;
                }
            }
            continue;
        }

        if trimmed.starts_with("<div class=\"ws-stepper") {
            in_stepper = true;
            stepper_depth = 1;
            output.push_str(&format!(
                "*[Interactive element -- see web version at specterlab.org/blog/{slug}/]*\n"
            ));
            continue;
        }

        if trimmed.starts_with("<div class=\"ws-focus-grid\">") {
            continue;
        }
        if trimmed == "</div>" && !in_stepper {
            continue;
        }

        let line = if removed_title && line.starts_with("##") {
            &line[1..]
        } else {
            line
        };
        let rewritten = rewrite_image_paths(line, slug);
        output.push_str(&rewritten);
        output.push('\n');
    }

    output
}

fn rewrite_image_paths(line: &str, slug: &str) -> String {
    let old_prefix = format!("../../assets/blog/{slug}/");
    let new_prefix = format!("/site/assets/blog/{slug}/");
    line.replace(&old_prefix, &new_prefix)
}

fn pandoc_markdown_to_typst(repo_root: &Utf8Path, markdown: &str, slug: &str) -> Result<String> {
    let tmp_md = repo_root.join(format!("site/blog/{slug}/_pdf_input.md"));
    fs::write(&tmp_md, markdown)
        .with_context(|| format!("failed to write temp markdown for {slug}"))?;

    let output = Command::new("pandoc")
        .arg(&tmp_md)
        .args([
            "--from=markdown",
            "--to=typst",
            "--wrap=none",
            "--citeproc",
            "--metadata=reference-section-title:References",
        ])
        .arg(format!(
            "--resource-path={}:{}",
            tmp_md.parent().context("article has no parent")?,
            repo_root
        ))
        .current_dir(repo_root)
        .output()
        .context("failed to run pandoc")?;

    fs::remove_file(&tmp_md).ok();

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("pandoc markdown->typst failed for {slug}: {stderr}");
    }

    let typst = String::from_utf8(output.stdout).context("pandoc produced invalid UTF-8")?;
    Ok(typst)
}

fn wrap_in_paper(typst_body: &str, title: &str) -> String {
    let escaped_title = title.replace('"', "\\\"");
    format!(
        "#import \"/addenda/typst-field-manual/specter-paper.typ\": author, paper\n\
         \n\
         #paper(\n\
         \x20 title: \"{escaped_title}\",\n\
         \x20 note: \"SPECTER LABS RESEARCH BLOG\",\n\
         \x20 authors: (author(\"Specter Labs\"),),\n\
         )[\n\
         {typst_body}\n\
         ]\n"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pdf_preserves_html_figure_and_uses_the_template_title_once() {
        let md = r#"---
title: Example
---
# Example

<figure class="wide">
<img src="../../assets/blog/example/plot.svg" alt="A plot" />
<figcaption>Measured response.</figcaption>
</figure>

## Result
Some text.
"#;
        let output = preprocess_for_pdf(md, "example");
        assert!(!output.contains("# Example"));
        assert!(output.contains("![Measured response.](/site/assets/blog/example/plot.svg)"));
        assert!(output.contains("# Result"));
    }
}
