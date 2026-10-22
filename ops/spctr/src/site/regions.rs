use crate::site::discover::{self, BlogPostRecord};
use crate::site::markup;
use crate::site::records::{self, SiteRecord};
use anyhow::Result;
use camino::Utf8Path;
use maud::{html, Markup, PreEscaped};
use std::collections::HashMap;

fn escape_html_text(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

pub(crate) fn inline_markdown(text: &str) -> Markup {
    let mut html = String::new();
    let mut parts = text.split('`');
    if let Some(first) = parts.next() {
        html.push_str(&escape_html_text(first));
    }
    let mut is_code = true;
    for part in parts {
        if is_code {
            html.push_str("<code>");
            html.push_str(&escape_html_text(part));
            html.push_str("</code>");
        } else {
            html.push_str(&escape_html_text(part));
        }
        is_code = !is_code;
    }
    if !is_code {
        html.push('`');
    }
    PreEscaped(html)
}

fn license_short(license: &str) -> &str {
    match license.split_once(':') {
        Some((prefix, _)) => prefix.trim(),
        None => license.trim(),
    }
}

fn render_dossier_links(record: &SiteRecord, page_path: &str) -> Markup {
    let mut links: Vec<Markup> = Vec::new();
    if let Some(href) = record.relative_hub_href(page_path) {
        links.push(html! { a href=(href) { "Open dossier" } });
    }
    links.push(markup::link(&record.repo_url, "Repository"));
    for (label, href) in record.published_surface_links() {
        links.push(markup::link(href, label));
    }
    if let Some(cabinet_href) = record.relative_cabinet_href(page_path) {
        links.push(html! { a href=(cabinet_href) { "Cabinet docs" } });
    }
    html! {
        @for link_markup in &links {
            (link_markup)
        }
    }
}

pub fn render_dossier_index_grid(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);
    let mut blocks: Vec<String> = Vec::new();
    for record in &slices.visible_dossiers {
        let block = html! {
            article class="dossier-card" id=(record.slug) {
                @if let Some(href) = record.relative_hub_href("dossiers/index.html") {
                    @match record.slug.as_str() {
                        "lenia-swarm" => { a class="dossier-preview" href=(href) { img src="/assets/home/quadrium-poster.webp?v=2" alt="A Quadrium-derived Lenia pattern." loading="lazy"; } }
                        "wonton-soup" => { a class="dossier-preview" href=(href) { img src="/assets/research-proof.svg?v=20261017" alt="Recorded Lean proof-search trees before and after removing exact; winning routes in teal and blocked tactics in rust." loading="lazy"; } }
                        "zhang-levin-playground" => { a class="dossier-preview" href=(href) { img src="/assets/research-sorting.svg?v=20261017" alt="Fifty colored sorting-cell trajectories braid from a shuffled arrangement into order in the dossier’s Bubble–Insertion replay." loading="lazy"; } }
                        _ => {}
                    }
                }
                div class="dossier-card-header" {
                    div class="dossier-card-tab" {
                        @if let Some(ref sid) = record.series {
                            span class="series-badge" { (sid) }
                        }
                        (record.title)
                    }
                }
                div class="dossier-card-body" {
                    div class="card-meta" {
                        div class="card-meta-row" {
                            span class="card-meta-label" { "Status" }
                            span class="card-meta-value" {
                                span class=(format!("project-status {}", record.status)) {
                                    (record.status)
                                }
                            }
                        }
                        @if let Some(scope) = record.labels.get("scope") {
                            div class="card-meta-row" {
                                span class="card-meta-label" { "Scope" }
                                span class="card-meta-value" {
                                    span class="project-chip scope-chip" { (scope) }
                                }
                            }
                        }
                        @if record.last_activity != "unknown" {
                            div class="card-meta-row" {
                                span class="card-meta-label" { "Activity" }
                                span class="card-meta-value" { (record.last_activity) }
                            }
                        }
                    }
                    p { (record.summary) }
                    div class="link-row" {
                        (render_dossier_links(record, "dossiers/index.html"))
                    }
                }
            }
        };
        blocks.push(block.into_string());
    }
    blocks.join("\n")
}

fn render_addenda_links(
    record: &SiteRecord,
    dossiers_by_slug: &HashMap<&str, &SiteRecord>,
    page_path: &str,
) -> Markup {
    let mut links: Vec<Markup> = Vec::new();
    links.push(markup::link(&record.repo_url, "Repository"));
    for (label, href) in record.published_surface_links() {
        links.push(markup::link(href, label));
    }
    if let Some(dossier) = records::related_visible_dossier(record, dossiers_by_slug) {
        if let Some(href) = dossier.relative_hub_href(page_path) {
            links.push(html! { a href=(href) { "Linked dossier" } });
        }
    }
    html! {
        @for link_markup in &links {
            (link_markup)
        }
    }
}

pub fn render_addenda_index_grid(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);
    let specimens: serde_json::Value = serde_json::from_str(include_str!(
        "../../../../site/assets/addenda-specimens/manifest.json"
    ))
    .expect("addenda specimen manifest must be valid JSON");
    let mut blocks: Vec<String> = Vec::new();
    for record in &slices.visible_addenda {
        if matches!(
            record.slug.as_str(),
            "poly-morphogenesis" | "k-semantics-reference" | "equational-theories-distillation"
        ) {
            continue;
        }
        let block = html! {
            article class="dossier-card addendum-specimen-card" id=(record.slug) {
                @if let Some(specimen) = specimens.get(&record.slug) {
                    figure class="addendum-specimen" {
                        a href=(specimen["dataHref"].as_str().or_else(|| specimen["sourceHref"].as_str()).expect("specimen destination")) {
                            img src=(specimen["src"].as_str().expect("specimen image")) alt=(specimen["alt"].as_str().expect("specimen alternative text")) width="1000" height="600" loading="lazy";
                        }
                    }
                }
                div class="dossier-card-header" {
                    div class="dossier-card-tab" {
                        @if let Some(ref sid) = record.series {
                            span class="series-badge" { (sid) }
                        }
                        (record.title)
                    }
                }
                div class="dossier-card-body" {
                    p { (inline_markdown(&record.summary)) }
                    div class="link-row" {
                        (render_addenda_links(record, &slices.dossier_by_slug, "addenda/index.html"))
                    }
                }
            }
        };
        blocks.push(block.into_string());
    }
    blocks.join("\n")
}

pub fn render_home_site_tree(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);
    html! {
        ul class="lab-tree" {
            li {
                a class="tree-root" href="/dossiers/" { "Research" }
                ul {
                    @for record in &slices.visible_dossiers {
                        @if let Some(href) = record.relative_hub_href("index.html") {
                            li { a href=(href) { (record.title) } }
                        }
                    }
                }
            }
            li {
                a class="tree-root" href="/blog/" { "Writing" }
                ul {
                    li { a href="/blog/#published-writing" { "Articles & reports" } }
                    li { a href="/blog/#lab-notes" { "Lab notes" } }
                }
            }
            li { a class="tree-root" href="/addenda/" { "Addenda" } }
            li { a class="tree-root" href="/cabinet/" { "Cabinet" } }
        }
    }
    .into_string()
}

pub fn render_blog_index_posts(posts: &[BlogPostRecord], page_path: &str) -> Result<String> {
    let mut blocks: Vec<String> = Vec::new();
    for post in posts {
        let href = discover::relative_href(page_path, &post.href);
        let cover = post
            .cover
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("{}: published post has no cover", post.href))?;
        let block = html! {
            article class="editorial-entry" {
                a class="entry-link" href=(href) aria-label=(format!("Read {}", post.title)) {
                    div class="entry-copy" {
                        h2 { (post.title) }
                        p { (post.summary) }
                    }
                    // Keep the annotated proof tree in the article, where its labels remain readable.
                    @if post.href != "blog/wonton-soup/" {
                        img class="entry-art" src=(cover.src) alt=(cover.alt) loading="lazy";
                    }
                }
            }
        };
        blocks.push(block.into_string());
    }
    Ok(blocks.join("\n"))
}

pub(crate) fn render_blog_index_notes(notes: &[super::blog::ResearchNoteRecord]) -> Result<String> {
    if notes.is_empty() {
        return Ok(String::new());
    }
    let mut items = Vec::new();
    for note in notes {
        let summary = note.summary.as_ref().ok_or_else(|| {
            anyhow::anyhow!("research-notes/{}/index.md: published note has no summary", note.slug)
        })?;
        items.push(html! {
            li class="research-note-card" {
                h3 class="research-note-title" {
                    a href=(format!("/research-notes/{}/", note.slug)) { (note.title) }
                }
                p { (summary) }
            }
        });
    }
    Ok(html! {
        section class="section-block" id="lab-notes" aria-labelledby="lab-notes-title" {
            h2 class="site-section-title" id="lab-notes-title" { "Lab notes" }
            ol class="research-note-list" {
                @for item in &items { (item) }
            }
        }
    }
    .into_string())
}

pub fn render_dossier_hub_header(record: &SiteRecord) -> String {
    let markup = html! {
        header class="dossier-hub-header" id="overview" {
            h1 class="dossier-hub-title" { (record.title) }
            p class="dossier-hub-deck" { (record.summary) }
            (render_dossier_hub_metabar(record))
        }
    };
    markup.into_string()
}

/// The series, status, activity, license and scope strip every hub carries,
/// including hubs whose cover comes from a hand-written header.html.
pub fn render_dossier_hub_metabar(record: &SiteRecord) -> maud::Markup {
    let scope = record.labels.get("scope").map(String::as_str);
    html! {
            div class="dossier-hub-metabar" {
                @if let Some(ref sid) = record.series {
                    span class="dossier-hub-metabar-item" {
                        span class="dossier-hub-metabar-value" { (sid) }
                    }
                }
                span class="dossier-hub-metabar-item" {
                    "status " span class=(format!("project-status {}", record.status)) {
                        (record.status)
                    }
                }
                @if record.last_activity != "unknown" {
                    span class="dossier-hub-metabar-item" {
                        "activity " span class="dossier-hub-metabar-value" { (record.last_activity) }
                    }
                }
                span class="dossier-hub-metabar-item" {
                    "license " span class="dossier-hub-metabar-value" { (license_short(&record.license)) }
                }
                @if let Some(scope_label) = scope {
                    span class="dossier-hub-metabar-item" {
                        "scope " span class="dossier-hub-metabar-value" { (scope_label) }
                    }
                }
            }
    }
}

pub fn render_dossier_hub_meta(record: &SiteRecord) -> String {
    html! {
        meta name="description" content=(record.summary);
        meta name="spctr:card" content="Dossier";
    }
    .into_string()
}

pub fn render_dossier_hub_footer(record: &SiteRecord) -> String {
    let page_path = dossier_page_path_or_default(record);
    let cabinet_href = record.relative_cabinet_href(page_path);
    let published_surfaces = record.published_surface_links();

    let markup = html! {
        nav class="dossier-hub-links" aria-label="Dossier links" {
            @if let Some(ref href) = cabinet_href {
                a href=(href) { "Cabinet docs" }
            }
            (markup::link(&record.repo_url, "Repository"))
            @for (label, href) in &published_surfaces {
                (markup::link(href, label))
            }
        }
    };
    markup.into_string()
}

fn dossier_page_path_or_default(record: &SiteRecord) -> &str {
    record
        .hub_path
        .as_deref()
        .and_then(|hub_path| hub_path.strip_prefix("site/"))
        .unwrap_or("dossiers/index.html")
}

pub fn render_generated_dossier_hub(record: &SiteRecord, _records: &[SiteRecord]) -> String {
    let mut output = String::new();
    output.push_str(&render_dossier_hub_header(record));
    output.push('\n');
    output.push_str(&render_dossier_hub_footer(record));
    output
}

struct SitemapNode {
    label: String,
    href: Option<String>,
    children: Vec<SitemapNode>,
}

fn render_sitemap_node(node: &SitemapNode, indent: &str) -> String {
    let label_html = match &node.href {
        Some(href) => markup::link(href, &node.label).into_string(),
        None => html! { span class="sitemap-tree-label" { (node.label) } }.into_string(),
    };
    let child_indent = format!("{indent}    ");
    let mut lines = vec![
        format!("{indent}<li>"),
        format!("{child_indent}{label_html}"),
    ];
    if !node.children.is_empty() {
        lines.push(format!("{child_indent}<ul class=\"sitemap-tree nested\">"));
        let nested_indent = format!("{child_indent}    ");
        for child in &node.children {
            lines.push(render_sitemap_node(child, &nested_indent));
        }
        lines.push(format!("{child_indent}</ul>"));
    }
    lines.push(format!("{indent}</li>"));
    lines.join("\n")
}

fn render_sitemap_tree(nodes: &[SitemapNode], indent: &str) -> String {
    let child_indent = format!("{indent}    ");
    let mut lines = vec![format!(
        "{indent}<ul class=\"sitemap-tree sitemap-tree-root\">"
    )];
    for node in nodes {
        lines.push(render_sitemap_node(node, &child_indent));
    }
    lines.push(format!("{indent}</ul>"));
    lines.join("\n")
}

fn series_label(series: Option<&String>, title: &str) -> String {
    match series {
        Some(series_id) => format!("{series_id} {title}"),
        None => title.to_owned(),
    }
}

fn leaf(label: String, href: String) -> SitemapNode {
    SitemapNode {
        label,
        href: Some(href),
        children: Vec::new(),
    }
}

pub fn render_sitemap_sections(
    repo_root: &Utf8Path,
    records: &[SiteRecord],
    blog_posts: &[BlogPostRecord],
) -> anyhow::Result<String> {
    let page_path = "sitemap/index.html";
    let href = |target: &str| discover::relative_href(page_path, target);
    let slices = records::slice_records(records);

    let dossier_pages: Vec<discover::SitePageRecord> = discover::discover_sitemap_pages(repo_root)
        .into_iter()
        .filter(|group| group.section == "dossiers")
        .flat_map(|group| group.children)
        .collect();

    let mut dossiers: Vec<&SiteRecord> = slices.visible_dossiers.clone();
    dossiers.sort_by(|a, b| a.series.cmp(&b.series));
    let dossier_nodes: Vec<SitemapNode> = dossiers
        .iter()
        .filter_map(|record| {
            let hub = record.hub_href()?;
            let reports = dossier_pages
                .iter()
                .filter(|page| page.href != hub && page.href.starts_with(&hub))
                .map(|page| leaf(page.title.clone(), href(&page.href)))
                .collect();
            Some(SitemapNode {
                label: series_label(record.series.as_ref(), &record.title),
                href: Some(href(&hub)),
                children: reports,
            })
        })
        .collect();

    let mut posts: Vec<&BlogPostRecord> = blog_posts
        .iter()
        .filter(|post| post.release == discover::RELEASE_PUBLISHED)
        .collect();
    posts.sort_by(|a, b| a.series.cmp(&b.series));
    let mut writing_nodes: Vec<SitemapNode> = posts
        .iter()
        .map(|post| leaf(series_label(post.series.as_ref(), &post.title), href(&post.href)))
        .collect();
    writing_nodes.push(leaf("Lab notes".to_owned(), href("research-notes/")));

    let mut addenda: Vec<&SiteRecord> = slices.visible_addenda.clone();
    addenda.sort_by(|a, b| a.series.cmp(&b.series));
    let addenda_nodes: Vec<SitemapNode> = addenda
        .iter()
        .map(|record| {
            leaf(
                series_label(record.series.as_ref(), &record.title),
                discover::addendum_index_href(record, page_path),
            )
        })
        .collect();

    let nodes = vec![
        leaf("Home".to_owned(), href("")),
        SitemapNode {
            label: "Research".to_owned(),
            href: Some(href("dossiers/")),
            children: dossier_nodes,
        },
        SitemapNode {
            label: "Writing".to_owned(),
            href: Some(href("blog/")),
            children: writing_nodes,
        },
        SitemapNode {
            label: "Addenda".to_owned(),
            href: Some(href("addenda/")),
            children: addenda_nodes,
        },
        leaf("Cabinet".to_owned(), href("cabinet/")),
        SitemapNode {
            label: "Dashboards".to_owned(),
            href: None,
            children: vec![leaf(
                "Wonton Soup dashboard".to_owned(),
                href("dashboards/wonton-soup/"),
            )],
        },
        SitemapNode {
            label: "Elsewhere".to_owned(),
            href: None,
            children: vec![
                leaf(
                    "Research registry".to_owned(),
                    "https://github.com/Specter-Research-Labs/research-registry/tree/main"
                        .to_owned(),
                ),
                leaf(
                    "Release archive".to_owned(),
                    "https://releases.specterlab.org/".to_owned(),
                ),
            ],
        },
    ];

    Ok(render_sitemap_tree(&nodes, "    "))
}

#[cfg(test)]
mod license_short_tests {
    use super::license_short;

    #[test]
    fn returns_prefix_before_colon() {
        assert_eq!(
            license_short("Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"),
            "Mixed"
        );
    }

    #[test]
    fn returns_full_string_when_no_colon() {
        assert_eq!(license_short("MIT"), "MIT");
    }

    #[test]
    fn trims_whitespace_around_prefix() {
        assert_eq!(license_short("  Apache-2.0  : extra"), "Apache-2.0");
    }
}
