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

use crate::{design_tokens, design_tokens_css};

const TEMPLATE_DIR: &str = "site/templates/report";
const PUBLICATIONS: &str = "site/publications.json";
const SITE_HEADER: &str = "site/templates/publication-header.html";
const SITE_FOOTER: &str = "site/templates/publication-footer.html";

/// Hosts of the private review app. Its revision links are allowed in report
/// sources and must be resolved to public URLs before anything reaches the site.
const REVIEW_HOSTS: &[&str] = &["lab.specterlab.org", "review.specterlab.org"];

/// Site paths that must never be public.
const PRIVATE_SITE_PATHS: &[&str] = &[
    "/dossiers/lenia-swarm/causal-emergence/",
    "/home-prototype/",
];

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
    ("IBM Plex Serif", "IBMPlexSerif-Bold.woff2", 700, "normal"),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, clap::ValueEnum)]
pub enum Target {
    /// A self-contained page for the private review app.
    Lab,
    /// A specterlab.org page, written to the document's published site path.
    Site,
}

#[derive(Debug, Deserialize)]
struct Publication {
    revision: String,
    path: String,
}

#[derive(Debug, Deserialize)]
struct SiteFrontMatter {
    document_id: String,
    revision: String,
    description: String,
    image: String,
}

struct SitePage {
    path: String,
    url: String,
    description: String,
    image: String,
    publications: BTreeMap<String, Publication>,
}

/// Renders `<dir>/report.md` and returns the path of the written page.
pub fn build(
    repo_root: &Utf8Path,
    dir: &Utf8Path,
    target: Target,
    out: Option<&Utf8Path>,
) -> Result<Utf8PathBuf> {
    let dir = absolute(dir)?;
    let source = dir.join("report.md");
    if !source.is_file() {
        bail!("missing report source: {source}");
    }
    let site = match target {
        Target::Lab => None,
        Target::Site => {
            if out.is_some() {
                bail!("the site target writes to the document's published path; drop --out");
            }
            Some(site_page(repo_root, &source)?)
        }
    };
    let out = match (out, &site) {
        (Some(path), _) => absolute(path)?,
        (None, Some(page)) => repo_root
            .join("site")
            .join(page.path.trim_start_matches('/'))
            .join("index.html"),
        (None, None) => dir.join("report.html"),
    };
    let templates = repo_root.join(TEMPLATE_DIR);

    let mut header = tempfile::Builder::new().suffix(".html").tempfile()?;
    header.write_all(inline_style(repo_root, target)?.as_bytes())?;

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
        .current_dir(&dir);
    for host in REVIEW_HOSTS {
        command.arg(format!("--metadata=rk-review-host:{host}"));
    }
    if let Some(page) = &site {
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
                read(&repo_root.join(SITE_HEADER))?.trim()
            ))
            .arg(format!(
                "--variable=rk-site-footer:{}",
                read(&repo_root.join(SITE_FOOTER))?.trim()
            ));
    }
    let output = command
        .output()
        .context("failed to run pandoc; install pandoc 3.7 or newer")?;
    if !output.status.success() {
        bail!(
            "pandoc failed for {source}:\n{}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let mut html = String::from_utf8(output.stdout).context("pandoc produced invalid UTF-8")?;
    if let Some(page) = &site {
        html = resolve_review_links(&html, &page.publications)?;
        check_site_page(&html)?;
        let site_dir = out.parent().context("site page has no parent")?;
        copy_assets(&dir, site_dir, &html, &page.image)?;
    }
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    fs::write(&out, html).with_context(|| format!("failed to write {out}"))?;
    eprintln!("wrote {out}");
    Ok(out)
}

fn site_page(repo_root: &Utf8Path, source: &Utf8Path) -> Result<SitePage> {
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
    let publications = load_publications(repo_root)?;
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
        path,
        url,
        description: front.description,
        image: front.image,
        publications,
    })
}

fn load_publications(repo_root: &Utf8Path) -> Result<BTreeMap<String, Publication>> {
    let path = repo_root.join(PUBLICATIONS);
    let publications: BTreeMap<String, Publication> = serde_json::from_str(&read(&path)?)
        .with_context(|| format!("{path}: expected {{document_id: {{revision, path}}}}"))?;
    for (document, publication) in &publications {
        check_site_path(&publication.path).with_context(|| format!("{path}: entry {document}"))?;
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
    Ok(())
}

/// Rewrites exact review revision links (`https://<review host>/#/p/DOC?revision=N[&section=ID]`)
/// to the public page of DOC, as the review app does when it publishes. The link must
/// cite the published revision.
fn resolve_review_links(
    html: &str,
    publications: &BTreeMap<String, Publication>,
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
            Ok(match section {
                Some(section) => format!("{}#{section}", publication.path),
                None => publication.path.clone(),
            })
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

fn check_site_page(html: &str) -> Result<()> {
    if let Some(host) = REVIEW_HOSTS.iter().find(|host| html.contains(**host)) {
        bail!("site page still mentions the review host {host}");
    }
    if html.to_ascii_lowercase().contains("<script") {
        bail!("site page carries a script");
    }
    Ok(())
}

/// Copies every relative `assets/` file the page references next to it, so that
/// the site directory holds exactly what the page needs and nothing else from the
/// report directory.
fn copy_assets(dir: &Utf8Path, site_dir: &Utf8Path, html: &str, image: &str) -> Result<()> {
    let reference = Regex::new(r##"(?:src|href)="(assets/[^"#?]+)""##).expect("valid regex");
    let files: BTreeSet<&str> = reference
        .captures_iter(html)
        .map(|captures| captures.get(1).expect("group").as_str())
        .chain([image])
        .collect();
    for file in files {
        if file.split('/').any(|part| part == "..") {
            bail!("asset path leaves assets/: {file}");
        }
        let from = dir.join(file);
        let to = site_dir.join(file);
        if !from.is_file() {
            bail!("the page references {file}, which is missing from {dir}");
        }
        fs::create_dir_all(to.parent().expect("asset has a parent"))?;
        fs::copy(&from, &to).with_context(|| format!("failed to copy {from} to {to}"))?;
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

fn inline_style(repo_root: &Utf8Path, target: Target) -> Result<String> {
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
    Ok(format!("<style>\n{css}</style>\n"))
}
