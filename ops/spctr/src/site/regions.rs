use crate::site::discover::{self, BlogPostRecord};
use crate::site::markup;
use crate::site::records::{self, SiteRecord};
use camino::Utf8Path;
use maud::{html, Markup, PreEscaped};
use std::collections::HashMap;

fn escape_html_text(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn inline_markdown(text: &str) -> Markup {
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

fn release_chip(record: &SiteRecord) -> Markup {
    html! {
        span class=(format!("project-chip release-chip release-{}", record.release_stage)) {
            "release:" (record.release_stage)
        }
    }
}

fn release_link_row(record: &SiteRecord) -> Markup {
    let links: Vec<Markup> = record
        .published_surface_links()
        .into_iter()
        .map(|(label, href)| markup::link(href, label))
        .collect();
    html! {
        @for link_markup in &links {
            (link_markup)
        }
    }
}

fn dossier_label_row(record: &SiteRecord, include_series: bool, include_activity: bool) -> Markup {
    html! {
        div class="project-label-row" {
            @if include_series {
                @if let Some(ref sid) = record.series {
                    span class="project-chip series-chip" { (sid) }
                }
            }
            div class=(format!("project-status {}", record.status)) {
                "status:" (record.status)
            }
            (release_chip(record))
            @if let Some(scope) = record.labels.get("scope") {
                span class="project-chip scope-chip" { "scope:" (scope) }
            }
            @if let Some(publication) = record.labels.get("publication") {
                span class="project-chip" { "publication:" (publication) }
            }
            @if include_activity {
                span class="project-chip activity-chip" { "activity:" (record.last_activity) }
            }
        }
    }
}

fn addenda_meta(record: &SiteRecord, include_activity: bool) -> Markup {
    let label_type = record.labels.get("type").map_or("", String::as_str);
    html! {
        div class="addenda-meta" {
            span class=(format!("addenda-chip class-{label_type}")) {
                "type:" (label_type)
            }
            span class=(format!("addenda-chip status-{}", record.status)) {
                "status:" (record.status)
            }
            (release_chip(record))
            @if include_activity {
                span class="addenda-chip activity-chip" { "activity:" (record.last_activity) }
            }
        }
    }
}

pub fn render_home_active_projects(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);
    let mut blocks: Vec<String> = Vec::new();
    for record in &slices.featured_dossiers {
        let title_html = if let Some(href) = record.relative_hub_href("index.html") {
            html! {
                a class="project-title project-title-link" href=(href) { (record.title) }
            }
        } else {
            html! {
                span class="project-title" { (record.title) }
            }
        };
        let block = html! {
            div class=(format!("project")) id=(format!("project-{}", record.slug)) {
                (title_html)
                (dossier_label_row(record, false, false))
                p { (record.summary) }
            }
        };
        blocks.push(block.into_string());
    }
    blocks.join("\n\n")
}

pub fn render_home_featured_addenda(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);
    let mut blocks: Vec<String> = Vec::new();
    for record in &slices.featured_addenda {
        let block = html! {
            div class="addenda-list-item" role="listitem" {
                div class="addenda-title" { (record.title) }
                (addenda_meta(record, false))
                p { (inline_markdown(&record.summary)) }
            }
        };
        blocks.push(block.into_string());
    }
    blocks.join("\n")
}

pub fn render_home_blog_posts(posts: &[BlogPostRecord]) -> String {
    let mut blocks: Vec<String> = Vec::new();
    for post in posts {
        let href = discover::relative_href("index.html", &post.href);
        let block = html! {
            div class="addenda-list-item" role="listitem" {
                div class="addenda-title" { a href=(href) { (post.title) } }
                @if !post.summary.is_empty() {
                    p { (post.summary) }
                }
            }
        };
        blocks.push(block.into_string());
    }
    blocks.join("\n")
}

fn render_dossier_links(record: &SiteRecord, page_path: &str) -> Markup {
    let mut links: Vec<Markup> = Vec::new();
    if let Some(href) = record.relative_hub_href(page_path) {
        links.push(html! { a href=(href) { "Open Dossier" } });
    }
    links.push(markup::link(&record.repo_url, "Repository"));
    for (label, href) in record.published_surface_links() {
        links.push(markup::link(href, label));
    }
    if let Some(cabinet_href) = record.relative_cabinet_href(page_path) {
        links.push(html! { a href=(cabinet_href) { "Cabinet Docs" } });
    }
    html! {
        @for link_markup in &links {
            (link_markup)
        }
    }
}

fn dossier_page_path(record: &SiteRecord) -> &str {
    record
        .hub_path
        .as_deref()
        .and_then(|hub_path| hub_path.strip_prefix("site/"))
        .expect("dossier hubs must be site-relative output paths")
}

fn related_addenda<'a>(records: &'a [SiteRecord], dossier_slug: &str) -> Vec<&'a SiteRecord> {
    let mut addenda = records
        .iter()
        .filter(|record| record.kind == "addendum" && record.visible)
        .filter(|record| record.related_dossier.as_deref() == Some(dossier_slug))
        .collect::<Vec<_>>();
    addenda.sort_by(|left, right| {
        left.title
            .to_lowercase()
            .cmp(&right.title.to_lowercase())
            .then_with(|| left.slug.cmp(&right.slug))
    });
    addenda
}

pub fn render_dossier_index_grid(records: &[SiteRecord]) -> String {
    let slices = records::slice_records(records);
    let mut blocks: Vec<String> = Vec::new();
    for record in &slices.visible_dossiers {
        let block = html! {
            article class="dossier-card" id=(record.slug) {
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
                        div class="card-meta-row" {
                            span class="card-meta-label" { "Release" }
                            span class="card-meta-value" { (record.release_stage) }
                        }
                        @if let Some(scope) = record.labels.get("scope") {
                            div class="card-meta-row" {
                                span class="card-meta-label" { "Scope" }
                                span class="card-meta-value" {
                                    span class="project-chip scope-chip" { (scope) }
                                }
                            }
                        }
                        div class="card-meta-row" {
                            span class="card-meta-label" { "Activity" }
                            span class="card-meta-value" { (record.last_activity) }
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
            links.push(html! { a href=(href) { "Linked Dossier" } });
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
    let label_type = |r: &SiteRecord| r.labels.get("type").map_or("", String::as_str).to_owned();
    let mut blocks: Vec<String> = Vec::new();
    for record in &slices.visible_addenda {
        let lt = label_type(record);
        let block = html! {
            article class="dossier-card" id=(record.slug) {
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
                            span class="card-meta-label" { "Type" }
                            span class="card-meta-value" {
                                span class=(format!("addenda-chip class-{lt}")) {
                                    (lt)
                                }
                            }
                        }
                        div class="card-meta-row" {
                            span class="card-meta-label" { "Status" }
                            span class="card-meta-value" {
                                span class=(format!("addenda-chip status-{}", record.status)) {
                                    (record.status)
                                }
                            }
                        }
                        div class="card-meta-row" {
                            span class="card-meta-label" { "Release" }
                            span class="card-meta-value" { (record.release_stage) }
                        }
                        div class="card-meta-row" {
                            span class="card-meta-label" { "Activity" }
                            span class="card-meta-value" { (record.last_activity) }
                        }
                    }
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

pub fn render_blog_index_posts(posts: &[BlogPostRecord], page_path: &str) -> String {
    let mut blocks: Vec<String> = Vec::new();
    for post in posts {
        let href = discover::relative_href(page_path, &post.href);
        let block = html! {
            article class="resource-card" {
                div class="resource-title" { (post.title) }
                @if !post.summary.is_empty() {
                    p { (post.summary) }
                }
                div class="link-row" {
                    a href=(href) { "Read Article" }
                }
            }
        };
        blocks.push(block.into_string());
    }
    blocks.join("\n")
}

pub fn render_dossier_hub_header(record: &SiteRecord) -> String {
    let markup = html! {
        section class="project-header" id="overview" {
            div class="site-page-title" { (record.title) }
            div class="hub-meta" {
                @if let Some(ref sid) = record.series {
                    div class="hub-meta-row" {
                        span class="hub-meta-label" { "Series" }
                        span class="hub-meta-value artifact-plate-id" { "SPCTR " (sid) }
                    }
                }
                div class="hub-meta-row" {
                    span class="hub-meta-label" { "Status" }
                    span class="hub-meta-value" {
                        span class=(format!("project-status {}", record.status)) {
                            (record.status)
                        }
                    }
                }
                div class="hub-meta-row" {
                    span class="hub-meta-label" { "Release" }
                    span class="hub-meta-value" { (record.release_stage) }
                }
                div class="hub-meta-row" {
                    span class="hub-meta-label" { "License" }
                    span class="hub-meta-value" { (record.license) }
                }
                @if let Some(scope) = record.labels.get("scope") {
                    div class="hub-meta-row" {
                        span class="hub-meta-label" { "Scope" }
                        span class="hub-meta-value" { (scope) }
                    }
                }
                div class="hub-meta-row" {
                    span class="hub-meta-label" { "Activity" }
                    span class="hub-meta-value" { (record.last_activity) }
                }
                div class="hub-meta-row" {
                    span class="hub-meta-label" { "Repository" }
                    span class="hub-meta-value" {
                        (markup::link(&record.repo_url, &record.repo_path))
                    }
                }
            }
            p class="section-lead" { (record.summary) }
            @if record.has_published_release_surfaces() {
                div class="link-row" {
                    (release_link_row(record))
                }
            }
        }
    };
    markup.into_string()
}

pub fn render_generated_dossier_hub(record: &SiteRecord, records: &[SiteRecord]) -> String {
    let page_path = dossier_page_path(record);
    let cabinet_href = record.relative_cabinet_href(page_path);
    let addenda_href = discover::relative_href(page_path, "addenda/");
    let published_surfaces = record.published_surface_links();
    let related_addenda = related_addenda(records, &record.slug);

    let markup = html! {
        (PreEscaped(render_dossier_hub_header(record)))

        section class="section-block section-card" id="start-here" {
            div class="site-section-title" { "Start Here" }
            ol class="quickstart-list" {
                @if let Some(ref href) = cabinet_href {
                    li {
                        a href=(href) { "Read the cabinet docs" }
                        "."
                    }
                }
                @if !published_surfaces.is_empty() {
                    li {
                        "Open the release bundle."
                    }
                }
                li {
                    (markup::link(&record.repo_url, "Inspect the project repository"))
                    "."
                }
            }
            span class="path-note" { "Repository path: " (record.repo_path) }
        }

        section class="section-block section-card" id="public-surfaces" {
            div class="site-section-title" { "Public Surfaces" }
            div class="resource-grid" {
                @if let Some(ref href) = cabinet_href {
                    article class="resource-card" {
                        div class="resource-title" { "Cabinet Docs" }
                        p { "Runbooks, contracts, and reference docs for this dossier." }
                        div class="link-row" {
                            a href=(discover::relative_href(page_path, "cabinet/")) { "Cabinet Index" }
                            a href=(href) { "Cabinet Docs" }
                        }
                    }
                }
                @for (label, href) in &published_surfaces {
                    article class="resource-card" {
                        div class="resource-title" { (label) }
                        p { "Source snapshots and published artifacts." }
                        div class="link-row" {
                            (markup::link(href, label))
                        }
                    }
                }
                article class="resource-card" {
                    div class="resource-title" { "Repository" }
                    p { "Source, manifests, run scripts, and implementation details." }
                    div class="link-row" {
                        (markup::link(&record.repo_url, "Repository Directory"))
                    }
                }
            }
        }

        @if !related_addenda.is_empty() {
            section class="section-block section-card" id="related-addenda" {
                div class="site-section-title" { "Related Addenda" }
                div class="resource-grid" {
                    @for addendum in &related_addenda {
                        article class="resource-card" {
                            div class="resource-title" { (addendum.title) }
                            p { (inline_markdown(&addendum.summary)) }
                            div class="link-row" {
                                a href=(format!("{addenda_href}#{}", addendum.slug)) { "Open in Addenda Index" }
                                (markup::link(&addendum.repo_url, "Repository"))
                            }
                        }
                    }
                }
            }
        }
    };
    markup.into_string()
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

pub fn render_sitemap_sections(repo_root: &Utf8Path) -> anyhow::Result<String> {
    let page_path = "sitemap/index.html";
    let groups = discover::discover_sitemap_pages(repo_root);

    const KNOWN_ORDER: &[&str] = &[
        "",
        "dossiers",
        "blog",
        "addenda",
        "projects",
        "updates",
        "cabinet",
        "dashboards",
    ];

    fn section_sort_key(section: &str) -> (usize, String) {
        let pos = KNOWN_ORDER.iter().position(|&s| s == section);
        (pos.unwrap_or(KNOWN_ORDER.len()), section.to_owned())
    }

    fn section_label(section: &str) -> String {
        if section.is_empty() {
            return "Home".to_owned();
        }
        let mut chars = section.chars();
        match chars.next() {
            Some(c) => c.to_uppercase().collect::<String>() + chars.as_str(),
            None => section.to_owned(),
        }
    }

    let mut sorted_groups: Vec<&discover::SitemapGroup> = groups.iter().collect();
    sorted_groups.sort_by(|a, b| section_sort_key(&a.section).cmp(&section_sort_key(&b.section)));

    let mut nodes: Vec<SitemapNode> = Vec::new();

    for group in &sorted_groups {
        let label = match &group.index {
            Some(_) if group.section.is_empty() => "Home".to_owned(),
            Some(idx) => idx.title.clone(),
            None => section_label(&group.section),
        };
        let parent_href = group
            .index
            .as_ref()
            .map(|idx| discover::relative_href(page_path, &idx.href));

        let children: Vec<SitemapNode> = group
            .children
            .iter()
            .map(|child| SitemapNode {
                label: child.title.clone(),
                href: Some(discover::relative_href(page_path, &child.href)),
                children: Vec::new(),
            })
            .collect();

        nodes.push(SitemapNode {
            label,
            href: parent_href,
            children,
        });
    }

    nodes.push(SitemapNode {
        label: "Elsewhere".to_owned(),
        href: None,
        children: vec![
            SitemapNode {
                label: "Research Registry".to_owned(),
                href: Some(
                    "https://github.com/Specter-Research-Labs/research-registry/tree/main"
                        .to_owned(),
                ),
                children: Vec::new(),
            },
            SitemapNode {
                label: "Release Archive".to_owned(),
                href: Some("https://releases.specterlab.org/".to_owned()),
                children: Vec::new(),
            },
        ],
    });

    let indent = "    ";
    Ok(render_sitemap_tree(&nodes, indent))
}

pub fn render_sitemap_registry(records: &[SiteRecord], blog_posts: &[BlogPostRecord]) -> String {
    struct Entry {
        series_id: String,
        title: String,
        href: Option<String>,
    }

    let page_path = "sitemap/index.html";
    let mut dossiers = records
        .iter()
        .filter(|record| record.kind == "dossier")
        .filter_map(|record| {
            record.series.as_ref().map(|series_id| Entry {
                series_id: series_id.clone(),
                title: record.title.clone(),
                href: record.relative_hub_href(page_path),
            })
        })
        .collect::<Vec<_>>();
    let mut addenda = records
        .iter()
        .filter(|record| record.kind == "addendum" && record.visible)
        .filter_map(|record| {
            record.series.as_ref().map(|series_id| Entry {
                series_id: series_id.clone(),
                title: record.title.clone(),
                href: Some(discover::addendum_index_href(record, page_path)),
            })
        })
        .collect::<Vec<_>>();
    let mut articles = blog_posts
        .iter()
        .filter_map(|post| {
            post.series.as_ref().map(|series_id| Entry {
                series_id: series_id.clone(),
                title: post.title.clone(),
                href: Some(discover::relative_href(page_path, &post.href)),
            })
        })
        .collect::<Vec<_>>();

    dossiers.sort_by(|left, right| left.series_id.cmp(&right.series_id));
    addenda.sort_by(|left, right| left.series_id.cmp(&right.series_id));
    articles.sort_by(|left, right| left.series_id.cmp(&right.series_id));

    fn render_group(label: &str, entries: &[Entry]) -> Markup {
        if entries.is_empty() {
            return html! {};
        }
        html! {
            (PreEscaped("                        "))
            div class="registry-group" { "\n"
                (PreEscaped("                            "))
                div class="site-kicker" { (label) } "\n"
                (PreEscaped("                            "))
                ul class="registry-list" { "\n"
                    @for entry in entries {
                        (PreEscaped("                                "))
                        li class="registry-entry" {
                            span class="registry-id" { "SPCTR " (entry.series_id) }
                            span class="registry-title" {
                                @if let Some(ref href) = entry.href {
                                    a href=(href) { (entry.title) }
                                } @else {
                                    (entry.title)
                                }
                            }
                        } "\n"
                    }
                    (PreEscaped("                            "))
                } "\n"
                (PreEscaped("                        "))
            }
        }
    }

    let indent = "                    ";
    let markup = html! {
        (PreEscaped(indent))
        section class="section-block" id="registry" { "\n"
            (PreEscaped("                        "))
            h2 { "Registry" } "\n"
            (render_group("Dossiers", &dossiers)) "\n"
            (render_group("Addenda", &addenda)) "\n"
            (render_group("Articles", &articles)) "\n"
            (PreEscaped(indent))
        }
    };
    markup.into_string()
}
