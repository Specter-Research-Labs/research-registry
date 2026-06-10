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

fn license_short(license: &str) -> &str {
    match license.split_once(':') {
        Some((prefix, _)) => prefix.trim(),
        None => license.trim(),
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
            div class="project" id=(format!("project-{}", record.slug)) {
                (title_html)
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
    let scope = record.labels.get("scope").map(String::as_str);
    let markup = html! {
        header class="dossier-hub-header" id="overview" {
            h1 class="dossier-hub-title" { (record.title) }
            p class="dossier-hub-deck" { (record.summary) }
            div class="dossier-hub-metabar" {
                @if let Some(ref sid) = record.series {
                    span class="dossier-hub-metabar-item" {
                        "SPCTR " span class="dossier-hub-metabar-value" { (sid) }
                    }
                }
                span class="dossier-hub-metabar-item" {
                    "status " span class=(format!("project-status {}", record.status)) {
                        (record.status)
                    }
                }
                span class="dossier-hub-metabar-item" {
                    "activity " span class="dossier-hub-metabar-value" { (record.last_activity) }
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
    };
    markup.into_string()
}

pub fn render_dossier_hub_footer(record: &SiteRecord) -> String {
    let page_path = dossier_page_path_or_default(record);
    let cabinet_href = record.relative_cabinet_href(page_path);
    let published_surfaces = record.published_surface_links();

    let markup = html! {
        footer class="dossier-hub-footer-row" {
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
