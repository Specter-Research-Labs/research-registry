use anyhow::{bail, Context, Result};
use base64::Engine;
use camino::{Utf8Path, Utf8PathBuf};
use std::fmt::Write as _;
use std::fs;
use std::io::Write as _;
use std::process::Command;

use crate::{design_tokens, design_tokens_css};

const TEMPLATE_DIR: &str = "site/templates/report";

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

pub fn build(repo_root: &Utf8Path, dir: &Utf8Path, out: Option<&Utf8Path>) -> Result<()> {
    let dir = absolute(dir)?;
    let source = dir.join("report.md");
    if !source.is_file() {
        bail!("missing report source: {source}");
    }
    let out = match out {
        Some(path) => absolute(path)?,
        None => dir.join("report.html"),
    };
    let templates = repo_root.join(TEMPLATE_DIR);

    let mut header = tempfile::Builder::new().suffix(".html").tempfile()?;
    header.write_all(inline_style(repo_root)?.as_bytes())?;

    let output = Command::new("pandoc")
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
        .arg(format!("--output={out}"))
        .current_dir(&dir)
        .output()
        .context("failed to run pandoc; install pandoc 3.7 or newer")?;
    if !output.status.success() {
        bail!(
            "pandoc failed for {source}:\n{}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    eprintln!("wrote {out}");
    Ok(())
}

fn absolute(path: &Utf8Path) -> Result<Utf8PathBuf> {
    if path.is_absolute() {
        return Ok(path.to_owned());
    }
    let cwd = Utf8PathBuf::try_from(std::env::current_dir()?)?;
    Ok(cwd.join(path))
}

fn inline_style(repo_root: &Utf8Path) -> Result<String> {
    let mut css = String::new();
    for (family, file, weight, style) in FONTS {
        let path = repo_root.join("site/fonts").join(file);
        let bytes = fs::read(&path).with_context(|| format!("failed to read font {path}"))?;
        let data = base64::engine::general_purpose::STANDARD.encode(bytes);
        writeln!(
            css,
            "@font-face{{font-family:\"{family}\";src:url(data:font/woff2;base64,{data}) format(\"woff2\");font-weight:{weight};font-style:{style};font-display:swap}}"
        )?;
    }
    let tokens = design_tokens::load_spec(&design_tokens::spec_dir(repo_root), "web")?;
    css.push_str(&design_tokens_css::generate_css(&tokens)?);
    let report_css = repo_root.join(TEMPLATE_DIR).join("report.css");
    css.push_str(
        &fs::read_to_string(&report_css).with_context(|| format!("failed to read {report_css}"))?,
    );
    Ok(format!("<style>\n{css}</style>\n"))
}
