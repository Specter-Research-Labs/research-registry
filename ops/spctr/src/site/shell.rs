use anyhow::{bail, Context, Result};
use camino::Utf8Path;
use std::fs;

const HEADER: &str = "site/templates/publication-header.html";
const FOOTER: &str = "site/templates/publication-footer.html";

/// The Lua filter and stylesheet that give reports, blog posts, research notes
/// and cabinet docs one table style.
pub const TABLES_FILTER: &str = "site/templates/tables.lua";
pub const TABLES_CSS: &str = "site/assets/tables.css";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Section {
    Research,
    Writing,
    Addenda,
    Cabinet,
}

impl Section {
    fn href(self) -> &'static str {
        match self {
            Section::Research => "/dossiers/",
            Section::Writing => "/blog/",
            Section::Addenda => "/addenda/",
            Section::Cabinet => "/cabinet/",
        }
    }

    pub fn card_kicker(self) -> &'static str {
        match self {
            Section::Research => "Research",
            Section::Writing => "Writing",
            Section::Addenda => "Addenda",
            Section::Cabinet => "Cabinet",
        }
    }
}

/// The navigation section a path below `site/` (for example
/// `dossiers/wonton-soup/index.html`) belongs to, if any.
pub fn nav_section(relative: &str) -> Option<Section> {
    match relative.trim_start_matches('/').split('/').next()? {
        "dossiers" => Some(Section::Research),
        "blog" | "research-notes" => Some(Section::Writing),
        "addenda" => Some(Section::Addenda),
        "cabinet" => Some(Section::Cabinet),
        _ => None,
    }
}

/// Like `nav_section`, but only the home page, sitemap and 404 may sit outside
/// the navigation, so that a new page cannot silently ship with no active section.
pub fn section_for_page(relative: &str) -> Result<Option<Section>> {
    match (nav_section(relative), relative.trim_start_matches('/')) {
        (Some(section), _) => Ok(Some(section)),
        (None, "index.html" | "sitemap/index.html" | "404.html") => Ok(None),
        (None, other) => bail!("{other}: page has no site navigation section"),
    }
}

pub fn header(repo_root: &Utf8Path, section: Option<Section>) -> Result<String> {
    let markup = read(repo_root, HEADER)?;
    let Some(section) = section else {
        return Ok(markup);
    };
    let link = format!("<a href=\"{}\">", section.href());
    if markup.matches(&link).count() != 1 {
        bail!("{HEADER}: expected exactly one navigation link {link}");
    }
    Ok(markup.replacen(
        &link,
        &format!("<a href=\"{}\" aria-current=\"page\">", section.href()),
        1,
    ))
}

pub fn footer(repo_root: &Utf8Path) -> Result<String> {
    read(repo_root, FOOTER)
}

fn read(repo_root: &Utf8Path, relative: &str) -> Result<String> {
    let path = repo_root.join(relative);
    Ok(fs::read_to_string(&path)
        .with_context(|| format!("failed to read {path}"))?
        .trim()
        .to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo() -> camino::Utf8PathBuf {
        Utf8Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
    }

    #[test]
    fn maps_pages_to_sections() {
        assert_eq!(
            section_for_page("dossiers/wonton-soup/index.html").unwrap(),
            Some(Section::Research)
        );
        assert_eq!(
            section_for_page("research-notes/x/index.html").unwrap(),
            Some(Section::Writing)
        );
        assert_eq!(section_for_page("index.html").unwrap(), None);
        assert!(section_for_page("updates/index.html").is_err());
    }

    #[test]
    fn marks_exactly_the_current_section() {
        let html = header(&repo(), Some(Section::Cabinet)).unwrap();
        assert_eq!(html.matches("aria-current").count(), 1);
        assert!(html.contains("<a href=\"/cabinet/\" aria-current=\"page\">Cabinet</a>"));
        assert!(!header(&repo(), None).unwrap().contains("aria-current"));
    }
}
