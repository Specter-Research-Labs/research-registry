use anyhow::{bail, Context, Result};
use base64::Engine;
use camino::{Utf8Path, Utf8PathBuf};
use regex_lite::Regex;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;
use std::fs;
use std::io::Write as _;
use std::process::Command;

use crate::site::shell;
use crate::{design_tokens, design_tokens_css};

const TEMPLATE_DIR: &str = "site/templates/report";
const PUBLICATIONS: &str = "site/publications.json";

/// Hosts of the private review app. Its revision links are allowed in report
/// sources and must be resolved to public URLs before anything reaches the site.
const REVIEW_HOSTS: &[&str] = &["lab.specterlab.org", "review.specterlab.org"];

const SITE_SHELL_CSS: &str = "site/assets/site-shell.css";

/// Site paths that must never be public.
const PRIVATE_SITE_PATHS: &[&str] = &[
    "/dossiers/lenia-swarm/causal-emergence/",
    "/home-prototype/",
];

/// Where the review app serves its own publications on the public site.
const REVIEW_APP_SITE_PATH: &str = "/experiments/";

const FONTS: &[(&str, &str, u16, &str)] = &[
    ("Berkeley Mono", "BerkeleyMono-Regular.woff2", 400, "normal"),
    ("Berkeley Mono", "BerkeleyMono-Bold.woff2", 700, "normal"),
    (
        "IBM Plex Serif",
        "IBMPlexSerif-Regular.woff2",
        400,
        "normal",
    ),
    ("IBM Plex Serif", "IBMPlexSerif-Italic.woff2", 400, "italic"),
    ("IBM Plex Serif", "IBMPlexSerif-Medium.woff2", 500, "normal"),
    ("IBM Plex Serif", "IBMPlexSerif-Bold.woff2", 700, "normal"),
];

const PRELOAD_FONTS: &[&str] = &[
    "IBMPlexSerif-Regular.woff2",
    "IBMPlexSerif-Medium.woff2",
    "BerkeleyMono-Regular.woff2",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, clap::ValueEnum)]
pub enum Target {
    /// A self-contained page for the private review app.
    Lab,
    /// A specterlab.org page, written to the document's published site path.
    Site,
}

/// The page shell a report renders into, from the `layout` front matter field.
/// Essays carry no scripts; explorer pages add explorer.css and the widget library.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Layout {
    Essay,
    Explorer,
}

#[derive(Debug, Deserialize)]
struct LayoutFrontMatter {
    layout: Option<String>,
}

#[derive(Debug, Deserialize)]
pub(crate) struct Publication {
    pub revision: String,
    pub path: String,
    /// Image for the report's card on its dossier hub; the card uses og:image when absent.
    pub card_image: Option<String>,
}

#[derive(Debug, Deserialize)]
struct SiteFrontMatter {
    document_id: String,
    revision: String,
    description: String,
    image: String,
}

struct SitePage {
    dir: Utf8PathBuf,
    document_id: String,
    path: String,
    url: String,
    description: String,
    image: String,
}

/// Renders `<dir>/report.md` for each dir and returns the paths of the written pages.
///
/// The site target builds its documents as one batch, so that documents linking
/// to each other's sections can be published together; nothing is written unless
/// every page in the batch passes its checks.
pub fn build(
    repo_root: &Utf8Path,
    dirs: &[Utf8PathBuf],
    target: Target,
    out: Option<&Utf8Path>,
) -> Result<Vec<Utf8PathBuf>> {
    match target {
        Target::Lab => {
            if out.is_some() && dirs.len() > 1 {
                bail!("--out needs exactly one report directory");
            }
            dirs.iter()
                .map(|dir| {
                    let dir = absolute(dir)?;
                    report_source(&dir)?;
                    let html = render(repo_root, &dir, Target::Lab, None)?;
                    let html = inline_widget_data(&dir, &html)?;
                    let out = match out {
                        Some(path) => absolute(path)?,
                        None => dir.join("report.html"),
                    };
                    write_page(&out, &html)?;
                    Ok(out)
                })
                .collect()
        }
        Target::Site => {
            if out.is_some() {
                bail!("the site target writes to the document's published path; drop --out");
            }
            build_site(repo_root, dirs)
        }
    }
}

fn build_site(repo_root: &Utf8Path, dirs: &[Utf8PathBuf]) -> Result<Vec<Utf8PathBuf>> {
    let publications = load_publications(repo_root)?;
    let mut rendered: Vec<(SitePage, String)> = Vec::new();
    for dir in dirs {
        let dir = absolute(dir)?;
        let page = site_page(&report_source(&dir)?, dir.clone(), &publications)?;
        if let Some((other, _)) = rendered
            .iter()
            .find(|(other, _)| other.document_id == page.document_id)
        {
            bail!(
                "{} is in the batch twice: {} and {}",
                page.document_id,
                other.dir,
                page.dir
            );
        }
        let html = render(repo_root, &dir, Target::Site, Some(&page))?;
        rendered.push((page, html));
    }
    let sections = Sections {
        site_root: repo_root.join("site"),
        batch: rendered
            .iter()
            .map(|(page, html)| (page.document_id.clone(), anchor_ids(html)))
            .collect(),
    };
    let mut pages = Vec::new();
    for (page, html) in &rendered {
        let html = resolve_review_links(html, &publications, &sections)
            .with_context(|| format!("{}", page.dir.join("report.md")))?;
        check_site_page(repo_root, &html, read_layout(&report_source(&page.dir)?)?)?;
        let assets = referenced_assets(&page.dir, &html, &page.image)?;
        let page_dir = sections.site_root.join(page.path.trim_start_matches('/'));
        check_stale_files(&page_dir, &page.path, &assets, &publications)?;
        pages.push((page, page_dir, html, assets));
    }
    let mut written = Vec::new();
    for (page, page_dir, html, assets) in pages {
        for file in assets {
            let from = page.dir.join(&file);
            let to = page_dir.join(&file);
            fs::create_dir_all(to.parent().expect("asset has a parent"))?;
            fs::copy(&from, &to).with_context(|| format!("failed to copy {from} to {to}"))?;
        }
        let out = page_dir.join("index.html");
        write_page(&out, &html)?;
        written.push(out);
    }
    Ok(written)
}

fn report_source(dir: &Utf8Path) -> Result<Utf8PathBuf> {
    let source = dir.join("report.md");
    if !source.is_file() {
        bail!("missing report source: {source}");
    }
    Ok(source)
}

fn render(
    repo_root: &Utf8Path,
    dir: &Utf8Path,
    target: Target,
    site: Option<&SitePage>,
) -> Result<String> {
    let templates = repo_root.join(TEMPLATE_DIR);
    let layout = read_layout(&report_source(dir)?)?;
    let mut header = tempfile::Builder::new().suffix(".html").tempfile()?;
    header.write_all(inline_style(repo_root, target, layout)?.as_bytes())?;
    let mut after_body = tempfile::Builder::new().suffix(".html").tempfile()?;

    let mut command = Command::new("pandoc");
    command
        .args([
            "report.md",
            "--from=markdown",
            "--to=html5",
            "--standalone",
            "--section-divs",
            "--wrap=none",
            "--citeproc",
            "--metadata=link-citations:true",
        ])
        .arg(format!(
            "--template={}",
            templates.join("pandoc-template.html")
        ))
        .arg(format!("--csl={}", templates.join("ieee.csl")))
        .arg(format!("--lua-filter={}", templates.join("report.lua")))
        .arg(format!("--include-in-header={}", header.path().display()))
        .current_dir(dir);
    if layout == Layout::Explorer {
        after_body.write_all(widget_script(repo_root)?.as_bytes())?;
        command.arg(format!(
            "--include-after-body={}",
            after_body.path().display()
        ));
    }
    for host in REVIEW_HOSTS {
        command.arg(format!("--metadata=rk-review-host:{host}"));
    }
    if let Some(page) = site {
        command
            .arg(format!("--metadata=url:{}", page.url))
            .arg("--variable=rk-site:true")
            .arg(format!(
                "--variable=rk-description:{}",
                escape(&page.description)
            ))
            .arg(format!(
                "--variable=rk-image:{}{}",
                page.path,
                escape(&page.image)
            ))
            .arg(format!(
                "--variable=rk-site-header:{}",
                shell::header(repo_root, shell::section_for_page(&page.path)?)?
            ))
            .arg(format!(
                "--variable=rk-site-footer:{}",
                shell::footer(repo_root)?
            ));
    }
    let output = command
        .output()
        .context("failed to run pandoc; install pandoc 3.7 or newer")?;
    if !output.status.success() {
        bail!(
            "pandoc failed for {}:\n{}",
            dir.join("report.md"),
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    String::from_utf8(output.stdout).context("pandoc produced invalid UTF-8")
}

fn write_page(out: &Utf8Path, html: &str) -> Result<()> {
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    fs::write(out, html).with_context(|| format!("failed to write {out}"))?;
    eprintln!("wrote {out}");
    Ok(())
}

fn site_page(
    source: &Utf8Path,
    dir: Utf8PathBuf,
    publications: &BTreeMap<String, Publication>,
) -> Result<SitePage> {
    let text = read(source)?;
    let front = gray_matter::Matter::<gray_matter::engine::YAML>::new()
        .parse(&text)
        .data
        .with_context(|| format!("{source}: missing YAML front matter"))?
        .deserialize::<SiteFrontMatter>()
        .with_context(|| {
            format!("{source}: the site target needs string fields document_id, revision, description and image")
        })?;
    if !front.image.starts_with("assets/") {
        bail!(
            "{source}: image must be a file under assets/, found {:?}",
            front.image
        );
    }
    let Some(publication) = publications.get(&front.document_id) else {
        bail!(
            "{} is not published: {PUBLICATIONS} has no entry for it",
            front.document_id
        );
    };
    if publication.revision != front.revision {
        bail!(
            "{} is published at revision {}, but report.md is revision {}",
            front.document_id,
            publication.revision,
            front.revision
        );
    }
    let path = publication.path.clone();
    let url = format!(
        "{}{path}",
        crate::site::publish::site_public_url().trim_end_matches('/')
    );
    Ok(SitePage {
        dir,
        document_id: front.document_id,
        path,
        url,
        description: front.description,
        image: front.image,
    })
}

/// Loads the publication manifest and enforces its invariants. Invariant: every
/// document has exactly one public URL. Two entries never share a path, and no
/// path lies under the review app's /experiments/ namespace; the review app in
/// turn must not serve a document that this manifest publishes.
pub(crate) fn load_publications(repo_root: &Utf8Path) -> Result<BTreeMap<String, Publication>> {
    let path = repo_root.join(PUBLICATIONS);
    let publications: BTreeMap<String, Publication> = serde_json::from_str(&read(&path)?)
        .with_context(|| format!("{path}: expected {{document_id: {{revision, path, card_image?}}}}"))?;
    let mut owners = BTreeMap::new();
    for (document, publication) in &publications {
        check_site_path(&publication.path).with_context(|| format!("{path}: entry {document}"))?;
        if let Some(other) = owners.insert(publication.path.as_str(), document) {
            bail!(
                "{path}: {other} and {document} are both published at {}",
                publication.path
            );
        }
    }
    Ok(publications)
}

/// Rejects site paths that are malformed or must stay private.
fn check_site_path(path: &str) -> Result<()> {
    let well_formed = path.starts_with('/')
        && path.ends_with('/')
        && path.len() > 1
        && path[1..path.len() - 1]
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..");
    if !well_formed {
        bail!("site path must look like /section/name/, found {path:?}");
    }
    if let Some(private) = PRIVATE_SITE_PATHS
        .iter()
        .find(|private| path.starts_with(**private))
    {
        bail!("refusing to write {path}: everything under {private} stays private");
    }
    if path.starts_with(REVIEW_APP_SITE_PATH) {
        bail!("{path} is under {REVIEW_APP_SITE_PATH}, which the review app serves");
    }
    Ok(())
}

/// Rewrites exact review revision links (`https://<review host>/#/p/DOC?revision=N[&section=ID]`)
/// to the public page of DOC, as the review app does when it publishes. The link must
/// cite the published revision, and its section must exist in DOC's page.
fn resolve_review_links(
    html: &str,
    publications: &BTreeMap<String, Publication>,
    sections: &Sections,
) -> Result<String> {
    let href = Regex::new(r##"href="(https?://([^/"#?]+)[^"]*)""##).expect("valid regex");
    let target = Regex::new(r"^https?://[^/#?]+/?#/p/([a-z0-9-]+)\?(.*)$").expect("valid regex");
    let section_id = Regex::new(r"^[A-Za-z][\w.:-]*$").expect("valid regex");
    let mut errors = BTreeSet::new();
    let rewritten = href.replace_all(html, |captures: &regex_lite::Captures<'_>| {
        let link = &captures[1];
        if !REVIEW_HOSTS.contains(&&captures[2]) {
            return captures[0].to_owned();
        }
        let resolved = (|| {
            let unescaped = link.replace("&amp;", "&");
            let Some(parts) = target.captures(&unescaped) else {
                bail!("{link}: review links must have the form https://HOST/#/p/DOCUMENT?revision=NNN[&section=ID]");
            };
            let document = &parts[1];
            let mut revision = None;
            let mut section = None;
            for pair in parts[2].split('&') {
                match pair.split_once('=') {
                    Some(("revision", value)) if revision.is_none() && !value.is_empty() => {
                        revision = Some(value);
                    }
                    Some(("section", value)) if section.is_none() && section_id.is_match(value) => {
                        section = Some(value);
                    }
                    _ => bail!("{link}: unexpected query part {pair:?}"),
                }
            }
            let Some(revision) = revision else {
                bail!("{link}: review links must name a revision");
            };
            let Some(publication) = publications.get(document) else {
                bail!("{link}: {document} is not published");
            };
            if publication.revision != revision {
                bail!(
                    "{link}: cites revision {revision}, but {document} is published at revision {}",
                    publication.revision
                );
            }
            let Some(section) = section else {
                return Ok(publication.path.clone());
            };
            if !sections.of(document, publication)?.contains(section) {
                bail!("{link}: {document} has no section {section}");
            }
            Ok(format!("{}#{section}", publication.path))
        })();
        match resolved {
            Ok(path) => format!(r#"href="{path}""#),
            Err(error) => {
                errors.insert(format!("{error:#}"));
                captures[0].to_owned()
            }
        }
    });
    if !errors.is_empty() {
        bail!(
            "unresolved review links:\n  {}",
            errors.into_iter().collect::<Vec<_>>().join("\n  ")
        );
    }
    Ok(rewritten.into_owned())
}

fn check_site_page(repo_root: &Utf8Path, html: &str, layout: Layout) -> Result<()> {
    if let Some(host) = REVIEW_HOSTS.iter().find(|host| html.contains(**host)) {
        bail!("site page still mentions the review host {host}");
    }
    let scripts = html.to_ascii_lowercase().matches("<script").count();
    let allowed = match layout {
        Layout::Essay => 0,
        Layout::Explorer => {
            if !html.contains(&widget_script(repo_root)?) {
                bail!("explorer page lacks the widget library");
            }
            1
        }
    };
    if scripts != allowed {
        bail!("site page carries a script other than the widget library");
    }
    Ok(())
}

fn read_layout(source: &Utf8Path) -> Result<Layout> {
    let text = read(source)?;
    let front = gray_matter::Matter::<gray_matter::engine::YAML>::new()
        .parse(&text)
        .data
        .with_context(|| format!("{source}: missing YAML front matter"))?
        .deserialize::<LayoutFrontMatter>()
        .with_context(|| format!("{source}: layout must be a string"))?;
    match front.layout.as_deref() {
        None | Some("essay") => Ok(Layout::Essay),
        Some("explorer") => Ok(Layout::Explorer),
        Some(other) => bail!("{source}: layout must be essay or explorer, found {other:?}"),
    }
}

/// The widget library as the one script an explorer page carries.
fn widget_script(repo_root: &Utf8Path) -> Result<String> {
    let js = read(&repo_root.join(TEMPLATE_DIR).join("widgets.js"))?;
    if js.to_ascii_lowercase().contains("</script") {
        bail!("widgets.js must not contain a closing script tag");
    }
    Ok(format!("<script type=\"module\">\n{js}</script>\n"))
}

/// Lab pages are single files, so each widget's data file is inlined into its
/// `data-src` as a data URI; the widget fetches it the same way either way.
fn inline_widget_data(dir: &Utf8Path, html: &str) -> Result<String> {
    let reference = Regex::new(r#"data-src="(assets/[^"]+\.json)""#).expect("valid regex");
    let mut error = None;
    let inlined = reference.replace_all(html, |captures: &regex_lite::Captures<'_>| {
        let path = dir.join(&captures[1]);
        match fs::read(&path) {
            Ok(bytes) => format!(
                r#"data-src="data:application/json;base64,{}""#,
                base64::engine::general_purpose::STANDARD.encode(bytes)
            ),
            Err(err) => {
                error.get_or_insert(anyhow::anyhow!("failed to read widget data {path}: {err}"));
                captures[0].to_owned()
            }
        }
    });
    if let Some(error) = error {
        return Err(error);
    }
    Ok(inlined.into_owned())
}

/// Anchor ids of the documents a link may point into. Documents in the batch
/// are checked against their new render; the others against their page as it is
/// published under site/, so the manifest stays the only record of what is public.
struct Sections {
    site_root: Utf8PathBuf,
    batch: BTreeMap<String, BTreeSet<String>>,
}

impl Sections {
    fn of(&self, document: &str, publication: &Publication) -> Result<BTreeSet<String>> {
        if let Some(ids) = self.batch.get(document) {
            return Ok(ids.clone());
        }
        let page = self
            .site_root
            .join(publication.path.trim_start_matches('/'))
            .join("index.html");
        if !page.is_file() {
            bail!("{document} has no page at {page}; build it first or in the same batch");
        }
        Ok(anchor_ids(&read(&page)?))
    }
}

fn anchor_ids(html: &str) -> BTreeSet<String> {
    Regex::new(r#"\sid="([^"]+)""#)
        .expect("valid regex")
        .captures_iter(html)
        .map(|captures| captures[1].to_owned())
        .collect()
}

/// Lists every relative `assets/` file the page references, so that the site
/// directory receives exactly what the page needs and nothing else from the
/// report directory.
fn referenced_assets(dir: &Utf8Path, html: &str, image: &str) -> Result<BTreeSet<String>> {
    let reference = Regex::new(r##"(?:src|href)="(assets/[^"#?]+)""##).expect("valid regex");
    let candidates = Regex::new(r##"srcset="([^"]*)""##).expect("valid regex");
    let single = Regex::new(r##"^assets/[^"#?\s,]+$"##).expect("valid regex");
    let mut files: BTreeSet<String> = reference
        .captures_iter(html)
        .map(|captures| captures[1].to_owned())
        .chain([image.to_owned()])
        .collect();
    // invariant: each srcset names exactly one local asset, so that the copy below
    // and the review importer, which embeds quoted asset paths, see the same file.
    for captures in candidates.captures_iter(html) {
        let value = &captures[1];
        if !single.is_match(value) {
            bail!("srcset must name one file under assets/ without descriptors: {value}");
        }
        files.insert(value.to_owned());
    }
    for file in &files {
        if file.split('/').any(|part| part == "..") {
            bail!("asset path leaves assets/: {file}");
        }
        if !dir.join(file).is_file() {
            bail!("the page references {file}, which is missing from {dir}");
        }
    }
    Ok(files)
}

/// Refuses to write a page into a directory that holds files the build would not
/// write, because those would stay public without a source. Directories of other
/// published documents nested below this one belong to those documents.
fn check_stale_files(
    page_dir: &Utf8Path,
    path: &str,
    assets: &BTreeSet<String>,
    publications: &BTreeMap<String, Publication>,
) -> Result<()> {
    let nested: BTreeSet<&str> = publications
        .values()
        .filter_map(|other| other.path.strip_prefix(path))
        .filter(|rest| !rest.is_empty())
        .collect();
    let mut stale = Vec::new();
    let mut pending = vec![Utf8PathBuf::new()];
    while let Some(rel) = pending.pop() {
        let dir = page_dir.join(&rel);
        if !dir.exists() {
            continue;
        }
        for entry in fs::read_dir(&dir).with_context(|| format!("failed to list {dir}"))? {
            let entry = entry?;
            let name = entry.file_name().into_string().map_err(|name| {
                anyhow::anyhow!("non-UTF-8 file name in {dir}: {}", name.display())
            })?;
            let rel = rel.join(name);
            if entry.file_type()?.is_dir() {
                if !nested.contains(format!("{rel}/").as_str()) {
                    pending.push(rel);
                }
            } else if rel != "index.html" && !assets.contains(rel.as_str()) {
                stale.push(rel.into_string());
            }
        }
    }
    if !stale.is_empty() {
        stale.sort();
        bail!(
            "{page_dir} holds files this build would not write; remove them or reference them from the report:\n  {}",
            stale.join("\n  ")
        );
    }
    Ok(())
}

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn read(path: &Utf8Path) -> Result<String> {
    fs::read_to_string(path).with_context(|| format!("failed to read {path}"))
}

fn absolute(path: &Utf8Path) -> Result<Utf8PathBuf> {
    if path.is_absolute() {
        return Ok(path.to_owned());
    }
    let cwd = Utf8PathBuf::try_from(std::env::current_dir()?)?;
    Ok(cwd.join(path))
}

fn inline_style(repo_root: &Utf8Path, target: Target, layout: Layout) -> Result<String> {
    let mut head = String::new();
    if target == Target::Site {
        for file in PRELOAD_FONTS {
            writeln!(
                head,
                "<link rel=\"preload\" href=\"/fonts/{file}\" as=\"font\" type=\"font/woff2\" crossorigin>"
            )?;
        }
    }
    let mut css = String::new();
    for (family, file, weight, style) in FONTS {
        // Lab pages are single files, so their fonts are inlined; site pages share
        // the site's font files.
        let src = match target {
            Target::Lab => {
                let path = repo_root.join("site/fonts").join(file);
                let bytes =
                    fs::read(&path).with_context(|| format!("failed to read font {path}"))?;
                let data = base64::engine::general_purpose::STANDARD.encode(bytes);
                format!("data:font/woff2;base64,{data}")
            }
            Target::Site => format!("/fonts/{file}"),
        };
        writeln!(
            css,
            "@font-face{{font-family:\"{family}\";src:url({src}) format(\"woff2\");font-weight:{weight};font-style:{style};font-display:swap}}"
        )?;
    }
    let tokens = design_tokens::load_spec(&design_tokens::spec_dir(repo_root), "web")?;
    css.push_str(&design_tokens_css::generate_css(&tokens)?);
    css.push_str(&read(&repo_root.join(TEMPLATE_DIR).join("report.css"))?);
    if target == Target::Site {
        css.push_str(&read(&repo_root.join(SITE_SHELL_CSS))?);
    }
    if layout == Layout::Explorer {
        css.push_str(&read(&repo_root.join(TEMPLATE_DIR).join("explorer.css"))?);
    }
    Ok(format!("{head}<style>\n{css}</style>\n"))
}
