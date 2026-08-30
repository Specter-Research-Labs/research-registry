pub mod archive;
pub mod artifacts;
pub mod blog;
pub mod cabinet;
pub mod catalog;
pub mod causal_emergence;
pub mod causal_emergence_release;
pub mod data;
pub mod discover;
pub mod health;
pub mod inject;
pub mod markup;
pub mod pdf;
pub mod portal;
pub mod provenance;
pub mod publish;
pub mod records;
pub mod regions;
pub mod tokens;

use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use rayon::prelude::*;
use std::fs;

use self::inject::replace_region;

struct PageRegion {
    template_path: String,
    output_path: String,
    regions: Vec<(&'static str, String)>,
}

struct ProjectFeeds {
    artifacts_report: artifacts::ProjectArtifactReport,
    health_report: health::ProjectHealthReport,
}

struct SiteProjection {
    blog_posts: Vec<discover::BlogPostRecord>,
    records: Vec<records::SiteRecord>,
    project_feeds: ProjectFeeds,
}

pub fn build(repo_root: &Utf8Path, write: bool) -> Result<()> {
    build_with_blog_posts(repo_root, write).map(|_| ())
}

pub(crate) fn build_with_blog_posts(
    repo_root: &Utf8Path,
    write: bool,
) -> Result<Vec<discover::BlogPostRecord>> {
    let projection = load_site_projection(repo_root)?;
    build_from_projection(repo_root, projection, write)
}

fn build_from_projection(
    repo_root: &Utf8Path,
    projection: SiteProjection,
    write: bool,
) -> Result<Vec<discover::BlogPostRecord>> {
    let SiteProjection {
        blog_posts,
        records,
        project_feeds,
    } = projection;
    let record_slices = records::slice_records(&records);
    let causal_emergence_catalog = causal_emergence::load_catalog(repo_root)?;
    let causal_emergence_sitemap_pages = causal_emergence_catalog
        .as_ref()
        .map(|_| causal_emergence::sitemap_pages())
        .unwrap_or_default();

    let mut pages: Vec<PageRegion> = vec![
        PageRegion {
            template_path: "site/templates/index.html".into(),
            output_path: "site/index.html".into(),
            regions: vec![
                (
                    "HOME_ACTIVE_PROJECTS",
                    regions::render_home_active_projects(&records),
                ),
                (
                    "HOME_FEATURED_ADDENDA",
                    regions::render_home_featured_addenda(&records),
                ),
                (
                    "HOME_BLOG_POSTS",
                    regions::render_home_blog_posts(&blog_posts),
                ),
            ],
        },
        PageRegion {
            template_path: "site/templates/dossiers/index.html".into(),
            output_path: "site/dossiers/index.html".into(),
            regions: vec![(
                "DOSSIER_INDEX_GRID",
                regions::render_dossier_index_grid(&records),
            )],
        },
        PageRegion {
            template_path: "site/templates/addenda/index.html".into(),
            output_path: "site/addenda/index.html".into(),
            regions: vec![(
                "ADDENDA_INDEX_GRID",
                regions::render_addenda_index_grid(&records),
            )],
        },
        PageRegion {
            template_path: "site/templates/blog/index.html".into(),
            output_path: "site/blog/index.html".into(),
            regions: vec![(
                "BLOG_INDEX_POSTS",
                regions::render_blog_index_posts(&blog_posts, "blog/index.html"),
            )],
        },
        PageRegion {
            template_path: "site/templates/research-notes/index.html".into(),
            output_path: "site/research-notes/index.html".into(),
            regions: vec![],
        },
        PageRegion {
            template_path: "site/templates/sitemap/index.html".into(),
            output_path: "site/sitemap/index.html".into(),
            regions: vec![
                (
                    "SITEMAP_SECTIONS",
                    regions::render_sitemap_sections(repo_root, &causal_emergence_sitemap_pages)?,
                ),
                (
                    "SITEMAP_REGISTRY",
                    regions::render_sitemap_registry(&records, &blog_posts),
                ),
            ],
        },
        PageRegion {
            template_path: "site/templates/projects/health/index.html".into(),
            output_path: "site/projects/health/index.html".into(),
            regions: vec![(
                "PROJECT_HEALTH_CONTENT",
                health::render_html(&project_feeds.health_report),
            )],
        },
    ];

    for record in &record_slices.visible_dossiers {
        let Some(ref hub_path) = record.hub_path else {
            continue;
        };
        if record.hub_generated {
            pages.push(PageRegion {
                template_path: "site/templates/dossiers/default-hub.html".into(),
                output_path: hub_path.clone(),
                regions: vec![
                    ("DOSSIER_HUB_TITLE", record.title.clone()),
                    (
                        "DOSSIER_HUB_CONTENT",
                        regions::render_generated_dossier_hub(record, &records),
                    ),
                ],
            });
        } else {
            let template = format!(
                "site/templates/{}",
                hub_path
                    .strip_prefix("site/")
                    .expect("hub_path validated to start with site/")
            );
            pages.push(PageRegion {
                template_path: template,
                output_path: hub_path.clone(),
                regions: vec![
                    (
                        "DOSSIER_HUB_HEADER",
                        regions::render_dossier_hub_header(record),
                    ),
                    (
                        "DOSSIER_HUB_FOOTER",
                        regions::render_dossier_hub_footer(record),
                    ),
                ],
            });
        }
    }

    if let Some(catalog) = causal_emergence_catalog.as_ref() {
        let template_path = "site/templates/dossiers/lenia-swarm/causal-emergence/page.html";
        for (output_path, title, description, canonical_path, content) in [
            (
                causal_emergence::LANDING_OUTPUT,
                "Causal Emergence in Flow Lenia",
                "A guided path through the experiments that follow when a developing Flow Lenia system becomes harder to redirect and more specific in its response.",
                "/dossiers/lenia-swarm/causal-emergence/",
                causal_emergence::render_landing(catalog),
            ),
            (
                causal_emergence::LIBRARY_OUTPUT,
                "Flow Lenia Causal Emergence Report Library",
                "The complete public library of current Flow Lenia causal-emergence reports, ordered as the experimental questions developed.",
                "/dossiers/lenia-swarm/causal-emergence/library/",
                causal_emergence::render_library(catalog),
            ),
            (
                causal_emergence::ARCHIVE_OUTPUT,
                "Flow Lenia Causal Emergence Archive",
                "Pilots and superseded Flow Lenia causal-emergence reports retained as part of the experimental record.",
                "/dossiers/lenia-swarm/causal-emergence/archive/",
                causal_emergence::render_archive(catalog),
            ),
        ] {
            pages.push(PageRegion {
                template_path: template_path.into(),
                output_path: output_path.into(),
                regions: vec![
                    (
                        "CAUSAL_EMERGENCE_PAGE_TITLE",
                        causal_emergence::render_page_title(title),
                    ),
                    (
                        "CAUSAL_EMERGENCE_PAGE_META",
                        causal_emergence::render_page_meta(title, description, canonical_path),
                    ),
                    ("CAUSAL_EMERGENCE_PAGE_CONTENT", content),
                ],
            });
        }
    }

    pages.par_iter().try_for_each(|page| -> Result<()> {
        let template_abs = repo_root.join(&page.template_path);
        if !template_abs.is_file() {
            bail!("template not found: {}", page.template_path);
        }
        let mut text = fs::read_to_string(&template_abs)
            .with_context(|| format!("failed to read {}", page.template_path))?;
        for (name, content) in &page.regions {
            text = replace_region(&text, name, content, &page.template_path)?;
        }
        if write {
            let output_abs = repo_root.join(&page.output_path);
            if let Some(parent) = output_abs.parent() {
                fs::create_dir_all(parent)
                    .with_context(|| format!("failed to create {}", parent))?;
            }
            fs::write(&output_abs, &text)
                .with_context(|| format!("failed to write {}", page.output_path))?;
        }
        Ok(())
    })?;

    if write {
        write_project_feeds(repo_root, &records, &project_feeds)?;
        data::link_local(repo_root)?;
        let research_notes = blog::build_research_notes(repo_root, write)?;
        build_updates_archive_if_present(repo_root, write)?;
        eprintln!(
            "site build: wrote {} files",
            pages.len() + 3 + research_notes
        );
    } else {
        let research_notes = blog::build_research_notes(repo_root, write)?;
        build_updates_archive_if_present(repo_root, write)?;
        eprintln!(
            "site build: validated {} pages",
            pages.len() + research_notes
        );
    }

    Ok(blog_posts)
}

fn build_updates_archive_if_present(repo_root: &Utf8Path, write: bool) -> Result<()> {
    if repo_root.join("site/updates/entries").is_dir() {
        let _ = crate::updates_archive::apply_or_check(repo_root, write, false)?;
    }
    Ok(())
}

pub fn export_project_feeds(repo_root: &Utf8Path, write: bool) -> Result<()> {
    let projection = load_site_projection(repo_root)?;
    if write {
        write_project_feeds(repo_root, &projection.records, &projection.project_feeds)?;
        eprintln!("site project-feeds: wrote 3 files");
    } else {
        eprintln!("site project-feeds: validated 3 feeds");
    }
    Ok(())
}

fn build_project_feeds(
    graph: &crate::graph::RegistryGraph,
    records: &[records::SiteRecord],
) -> Result<ProjectFeeds> {
    let _ = catalog::build_catalog_json(records);
    let artifacts_report = artifacts::build_report_from_graph(graph, records)?;
    let _ = artifacts::render_json(&artifacts_report)?;
    let health_report = health::build_report_from_graph(graph, records)?;
    let _ = health::render_json(&health_report)?;
    Ok(ProjectFeeds {
        artifacts_report,
        health_report,
    })
}

fn load_site_projection(repo_root: &Utf8Path) -> Result<SiteProjection> {
    let graph = crate::graph::build_with_options(
        repo_root,
        None,
        crate::graph::GraphBuildOptions::site_projection(),
    )?;
    let blog_posts = blog::load_published_posts_from_graph(&graph)?;
    let records = records::load_site_records_from_graph(repo_root, &graph)?;
    let project_feeds = build_project_feeds(&graph, &records)?;
    Ok(SiteProjection {
        blog_posts,
        records,
        project_feeds,
    })
}

fn write_project_feeds(
    repo_root: &Utf8Path,
    records: &[records::SiteRecord],
    project_feeds: &ProjectFeeds,
) -> Result<()> {
    let catalog_path = repo_root.join("site/projects/catalog.json");
    if let Some(parent) = catalog_path.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {}", parent))?;
    }
    fs::write(&catalog_path, catalog::build_catalog_json(records))
        .with_context(|| format!("failed to write {catalog_path}"))?;

    let artifacts_path = repo_root.join("site/projects/artifacts.json");
    if let Some(parent) = artifacts_path.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {}", parent))?;
    }
    fs::write(
        &artifacts_path,
        artifacts::render_json(&project_feeds.artifacts_report)?,
    )
    .with_context(|| format!("failed to write {artifacts_path}"))?;

    let health_path = repo_root.join("site/projects/health.json");
    if let Some(parent) = health_path.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {}", parent))?;
    }
    fs::write(
        &health_path,
        health::render_json(&project_feeds.health_report)?,
    )
    .with_context(|| format!("failed to write {health_path}"))?;

    Ok(())
}
