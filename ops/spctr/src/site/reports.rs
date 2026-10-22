use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use std::fs;

use crate::site::discover::{self, BlogPostRecord};
use crate::site::finalize;

/// A published report as its dossier hub and the homepage present it.
pub struct Report {
    pub dossier: String,
    pub href: String,
    pub title: String,
    pub finding: String,
    pub image: String,
    pub label: String,
}

/// Reports come from two places: documents in site/publications.json, whose
/// built pages carry the title, summary and figure, and published blog posts
/// that name their dossier in front matter.
pub fn discover_reports(
    repo_root: &Utf8Path,
    blog_posts: &[BlogPostRecord],
) -> Result<Vec<Report>> {
    let mut reports = Vec::new();
    for (document, publication) in crate::doc::load_publications(repo_root)? {
        let dossier = publication
            .path
            .strip_prefix("/dossiers/")
            .and_then(|rest| rest.split('/').next())
            .filter(|slug| !slug.is_empty())
            .with_context(|| {
                format!(
                    "{document} is published at {}, outside /dossiers/<slug>/",
                    publication.path
                )
            })?;
        let relative = format!("{}index.html", &publication.path[1..]);
        let page_path = repo_root.join("site").join(&relative);
        let text = fs::read_to_string(&page_path).with_context(|| {
            format!("{document}: {page_path} is missing; run spctr doc build --target site first")
        })?;
        let page = finalize::declared_page(&relative, &text)
            .with_context(|| format!("{document}: {page_path}"))?;
        reports.push(Report {
            dossier: dossier.to_owned(),
            href: publication.path.clone(),
            title: page.title,
            finding: page.description,
            image: card_image(repo_root, &document, publication.card_image.as_ref(), page.image)?,
            label: format!("Report · revision {}", publication.revision),
        });
    }
    for post in blog_posts {
        let Some(dossier) = &post.dossier else {
            continue;
        };
        if post.release != discover::RELEASE_PUBLISHED {
            continue;
        }
        let Some(series) = &post.series else {
            bail!("{}: a dossier report needs a series ID", post.href);
        };
        let Some(cover) = &post.cover else {
            bail!("{}: a dossier report needs a cover", post.href);
        };
        reports.push(Report {
            dossier: dossier.clone(),
            href: format!("/{}", post.href),
            title: post.title.clone(),
            finding: post.summary.clone(),
            image: card_image(repo_root, &post.href, post.card_image.as_ref(), cover.src.clone())?,
            label: format!("Report · {series}"),
        });
    }
    Ok(reports)
}

fn card_image(
    repo_root: &Utf8Path,
    owner: &str,
    chosen: Option<&String>,
    default: String,
) -> Result<String> {
    let Some(chosen) = chosen else {
        return Ok(default);
    };
    let Some(relative) = chosen.strip_prefix('/') else {
        bail!("{owner}: card_image {chosen} must be a site-absolute path");
    };
    let file = repo_root.join("site").join(relative);
    if !file.is_file() {
        bail!("{owner}: card_image {chosen} does not exist at {file}");
    }
    Ok(chosen.clone())
}
