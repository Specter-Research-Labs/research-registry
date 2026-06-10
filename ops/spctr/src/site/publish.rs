use std::ffi::OsStr;
use std::fs;
use std::path::Path;
use std::process::{Command, Output, Stdio};

use anyhow::{anyhow, bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use serde::Serialize;
use tempfile::Builder;

use crate::site::{archive, blog, cabinet, pdf};
use crate::{lake, registry_sync, report, site, tokens};

const REMOTE_PORTAL_BIN: &str = "/tmp/spctr-portal";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PublishArtifact {
    label: String,
    url: String,
    path: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct PublishResult {
    release_id: String,
    surface: String,
    public_url: String,
    current_url: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    artifacts: Vec<PublishArtifact>,
    #[serde(skip_serializing_if = "Option::is_none")]
    manifest_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    site_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    provenance: Option<String>,
}

impl PublishResult {
    fn archived(
        release_id: &str,
        surface: &str,
        archive: &ArchivedRelease,
        current_url: String,
    ) -> Self {
        Self {
            release_id: release_id.to_owned(),
            surface: surface.to_owned(),
            public_url: archive.public_url.clone(),
            current_url,
            artifacts: Vec::new(),
            manifest_path: None,
            site_path: None,
            provenance: None,
        }
    }
}

struct SitePublishPlan {
    excludes: Vec<String>,
    remote_prunes: Vec<String>,
}

fn publish_artifact(label: &str, url: String, path: String) -> PublishArtifact {
    PublishArtifact {
        label: label.to_owned(),
        url,
        path,
    }
}

fn emit_archived_publish_result(
    label: &str,
    release_id: &str,
    current_url: &str,
    archive_url: &str,
    result: &PublishResult,
) -> Result<()> {
    emit_publish_result(
        &format!(
            "{label}: release={} current={} archive={}",
            release_id, current_url, archive_url
        ),
        result,
    )
}

pub fn publish_site(repo_root: &Utf8Path, release_id: Option<&str>) -> Result<()> {
    let release_id = resolve_release_id(repo_root, release_id)?;
    let site_root = repo_root.join("site");

    registry_sync::ensure_clean(repo_root)?;
    tokens::dispatch(
        repo_root,
        crate::cli::TokensCommand::Generate { target: None },
    )?;
    let blog_posts = site::build_with_blog_posts(repo_root, true)?;
    blog::build_blog_for_posts(repo_root, &blog_posts, true)?;
    pdf::build_all_pdfs_for_posts(repo_root, &blog_posts)?;
    cabinet::build_cabinet(repo_root, true)?;
    build_wonton_dashboard(repo_root)?;
    minify_site_tree(&site_root)?;
    render_status_page(&site_root)?;

    let site_publish_plan = site_publish_plan(repo_root)?;
    publish_current_site(
        repo_root,
        &site_root,
        &release_id,
        &site_publish_plan.excludes,
        &site_publish_plan.remote_prunes,
    )?;
    let archive = archive_public_release(
        "site",
        "root",
        &release_id,
        &site_root,
        true,
        &site_publish_plan.excludes,
    )?;

    let current_url = format!("{}/", site_public_url().trim_end_matches('/'));
    let mut result = PublishResult::archived(&release_id, "site", &archive, current_url.clone());
    result.site_path = Some("site".to_owned());

    emit_archived_publish_result(
        "Site publish",
        &release_id,
        &current_url,
        &result.public_url,
        &result,
    )
}

fn site_publish_plan(repo_root: &Utf8Path) -> Result<SitePublishPlan> {
    let mut excludes = crate::site::data::rsync_excludes(repo_root)?;
    let research_notes = research_note_publish_plan(repo_root)?;
    excludes.extend(research_notes.excludes);
    Ok(SitePublishPlan {
        excludes,
        remote_prunes: research_notes.remote_prunes,
    })
}

fn research_note_publish_plan(repo_root: &Utf8Path) -> Result<SitePublishPlan> {
    let notes_root = repo_root.join("site/research-notes");
    if !notes_root.is_dir() {
        return Ok(SitePublishPlan {
            excludes: Vec::new(),
            remote_prunes: Vec::new(),
        });
    }

    let mut draft_slugs = Vec::new();
    let mut has_published = false;
    for entry in
        fs::read_dir(&notes_root).with_context(|| format!("failed to read {notes_root}"))?
    {
        let entry = entry?;
        if !entry.path().is_dir() {
            continue;
        }
        let slug = entry.file_name().to_string_lossy().to_string();
        let md_path = notes_root.join(&slug).join("index.md");
        if !md_path.is_file() {
            continue;
        }
        let text =
            fs::read_to_string(&md_path).with_context(|| format!("failed to read {md_path}"))?;
        let front_matter = crate::markdown::parse_front_matter(&text);
        match crate::site::discover::article_release(&front_matter)
            .with_context(|| format!("research-notes/{slug}/index.md"))?
            .as_str()
        {
            crate::site::discover::RELEASE_PUBLISHED => has_published = true,
            _ => draft_slugs.push(slug),
        }
    }

    if !has_published {
        return Ok(SitePublishPlan {
            excludes: vec!["research-notes/".to_owned()],
            remote_prunes: vec!["research-notes/".to_owned()],
        });
    }

    let mut excludes = vec![
        "research-notes/index.html".to_owned(),
        "research-notes/pandoc-template.html".to_owned(),
    ];
    let mut remote_prunes = Vec::new();
    for slug in draft_slugs {
        let relative = format!("research-notes/{slug}/");
        excludes.push(relative.clone());
        remote_prunes.push(relative);
    }
    excludes.sort();
    remote_prunes.sort();
    Ok(SitePublishPlan {
        excludes,
        remote_prunes,
    })
}

fn build_wonton_dashboard(repo_root: &Utf8Path) -> Result<()> {
    let dashboard_root = repo_root.join("site/dashboards/wonton-soup");
    if !dashboard_root.join("package-lock.json").is_file() {
        bail!("Wonton dashboard package-lock.json not found at {dashboard_root}");
    }
    run_command(
        Command::new("npm").arg("ci").current_dir(&dashboard_root),
        "failed to install Wonton dashboard dependencies",
    )?;
    run_command(
        Command::new("npm")
            .arg("run")
            .arg("build")
            .current_dir(&dashboard_root),
        "failed to build Wonton dashboard",
    )?;
    Ok(())
}

pub fn publish_lenia_compendium(
    repo_root: &Utf8Path,
    release_id: &str,
    output: Option<&Utf8Path>,
    passthrough: &[String],
) -> Result<()> {
    let release_id = crate::release::validate_release_id(release_id)?;
    let dossier_root = repo_root.join("dossiers/lenia-swarm");
    let output_root = resolve_repo_path(
        repo_root,
        output.unwrap_or_else(|| Utf8Path::new("dossiers/lenia-swarm/artifacts/compendium")),
    );

    let runtime_root = runtime_root(repo_root)?;
    fs::create_dir_all(&runtime_root)
        .with_context(|| format!("failed to create runtime root {runtime_root}"))?;
    let derived_data = Builder::new()
        .prefix(&format!("lenia-compendium-{release_id}."))
        .tempdir_in(runtime_root.as_std_path())
        .context("failed to allocate temporary LeniaCLI derived data directory")?;
    let derived_data_path = Utf8PathBuf::from_path_buf(derived_data.path().to_path_buf())
        .map_err(|_| anyhow!("temporary LeniaCLI derived data path must be valid UTF-8"))?;

    run_command(
        Command::new("/usr/bin/xcrun")
            .arg("xcodebuild")
            .arg("build")
            .arg("-scheme")
            .arg("LeniaCLI")
            .arg("-destination")
            .arg("platform=OS X")
            .arg("-configuration")
            .arg("Release")
            .arg("-derivedDataPath")
            .arg(&derived_data_path)
            .arg("-quiet")
            .current_dir(&dossier_root),
        "failed to build LeniaCLI for compendium publish",
    )?;

    let cli_bin = derived_data_path.join("Build/Products/Release/LeniaCLI");
    if !cli_bin.is_file() {
        bail!("LeniaCLI build did not produce a CLI binary at {cli_bin}");
    }

    let mut publish_command = Command::new(cli_bin.as_std_path());
    publish_command
        .arg("compendium")
        .arg("publish")
        .arg("--release-id")
        .arg(&release_id)
        .arg("--output")
        .arg(&output_root)
        .args(passthrough)
        .current_dir(&dossier_root);
    run_command(
        &mut publish_command,
        "failed to materialize Lenia compendium release",
    )?;

    let manifest_path = output_root.join("manifest.json");
    if !manifest_path.is_file() {
        bail!("Lenia compendium manifest not found at {manifest_path}");
    }
    let release_root = output_root.join("releases").join(&release_id);
    if !release_root.is_dir() {
        bail!("Lenia compendium release directory not found at {release_root}");
    }

    let release_bundle = Builder::new()
        .prefix(&format!("lenia-bundle-{release_id}."))
        .tempdir_in(runtime_root.as_std_path())
        .context("failed to allocate temporary Lenia release bundle directory")?;
    let release_bundle_path = Utf8PathBuf::from_path_buf(release_bundle.path().to_path_buf())
        .map_err(|_| anyhow!("temporary Lenia release bundle path must be valid UTF-8"))?;
    fs::create_dir_all(release_bundle_path.join("releases")).with_context(|| {
        format!("failed to create Lenia release staging root {release_bundle_path}")
    })?;
    fs::copy(&manifest_path, release_bundle_path.join("manifest.json"))
        .with_context(|| format!("failed to stage Lenia manifest {manifest_path}"))?;
    copy_dir_all(
        &release_root,
        &release_bundle_path.join("releases").join(&release_id),
    )?;

    let archive = archive_public_release(
        "lenia-swarm",
        "compendium",
        &release_id,
        &release_bundle_path,
        true,
        &[],
    )?;
    crate::site::data::push_data(repo_root, Some("lenia-swarm"), Some("compendium"))?;

    let current_url = "https://specterlab.org/dossiers/lenia-swarm/compendium/".to_owned();
    let manifest_path_string = manifest_path.to_string();
    let release_index_path = release_root.join("index.json").to_string();
    let mut result =
        PublishResult::archived(&release_id, "compendium", &archive, current_url.clone());
    result.artifacts = vec![
        publish_artifact(
            "manifest",
            format!("{}manifest.json", archive.public_url),
            manifest_path_string.clone(),
        ),
        publish_artifact(
            "release index",
            format!("{}index.json", archive.public_url),
            release_index_path,
        ),
    ];
    result.manifest_path = Some(manifest_path_string.clone());
    result.site_path = Some("site/dossiers/lenia-swarm/compendium".to_owned());
    result.provenance = Some(format!("manifest={manifest_path_string}"));

    emit_archived_publish_result(
        "Lenia compendium publish",
        &release_id,
        &current_url,
        &result.public_url,
        &result,
    )
}

pub fn publish_wonton_dashboard(
    repo_root: &Utf8Path,
    release_id: Option<&str>,
    site_data_root: Option<&Utf8Path>,
) -> Result<()> {
    let release_id = resolve_release_id(repo_root, release_id)?;
    let site_data_root = resolve_repo_path(
        repo_root,
        site_data_root.unwrap_or_else(|| Utf8Path::new("site/dashboards/wonton-soup/data")),
    );

    lake::refresh(
        "wonton-soup",
        Some(site_data_root.as_str()),
        Some(&release_id),
    )?;

    let manifest_path = site_data_root.join("manifest.json");
    if !manifest_path.is_file() {
        bail!("Wonton dashboard manifest not found at {manifest_path}");
    }
    let manifest = read_json_map(&manifest_path)?;
    let selected_runs = manifest
        .get("selected_runs")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or(0);

    let archive = archive_public_release(
        "wonton-soup",
        "site-dashboard",
        &release_id,
        &site_data_root,
        true,
        &[],
    )?;
    let canonical_site_data = repo_root.join("site/dashboards/wonton-soup/data");
    let current_url = if same_path(&site_data_root, &canonical_site_data)? {
        "https://specterlab.org/dashboards/wonton-soup/".to_owned()
    } else {
        archive.current_url.clone()
    };

    let manifest_path_string = manifest_path.to_string();
    let mut result =
        PublishResult::archived(&release_id, "site-dashboard", &archive, current_url.clone());
    result.artifacts = vec![publish_artifact(
        "release manifest",
        format!("{}manifest.json", archive.public_url),
        manifest_path_string.clone(),
    )];
    result.manifest_path = Some(manifest_path_string);
    result.site_path = (current_url == "https://specterlab.org/dashboards/wonton-soup/")
        .then(|| "site/dashboards/wonton-soup".to_owned());
    result.provenance = Some(format!("selected_runs={selected_runs} profile=dashboard"));

    emit_archived_publish_result(
        "Wonton site dashboard publish",
        &release_id,
        &current_url,
        &result.public_url,
        &result,
    )
}

pub fn publish_typst_release(
    repo_root: &Utf8Path,
    input: &Utf8Path,
    release_id: &str,
    overwrite_release: bool,
) -> Result<()> {
    let release_id = crate::release::validate_release_id(release_id)?;
    let input_path = resolve_repo_path(repo_root, input);
    if !input_path.is_file() {
        bail!("Typst input does not exist: {input_path}");
    }

    let build_script = repo_root.join("addenda/typst-field-manual/tools/build.py");
    let output = command_output(
        Command::new("python3")
            .arg(&build_script)
            .arg(&input_path)
            .current_dir(repo_root)
            .env_remove("SPECTER_ARTIFACT_ROOT"),
        "failed to build Typst field manual PDF",
    )?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        if stderr.is_empty() {
            bail!("failed to build Typst field manual PDF");
        }
        bail!("failed to build Typst field manual PDF: {stderr}");
    }
    let pdf_path = Utf8PathBuf::from(String::from_utf8_lossy(&output.stdout).trim());
    if !pdf_path.is_file() {
        bail!("Typst build did not produce a PDF at {pdf_path}");
    }
    let pdf_name = pdf_path
        .file_name()
        .context("Typst PDF path must have a filename")?
        .to_owned();

    let archive = archive_public_release(
        "typst-field-manual",
        "root",
        &release_id,
        &pdf_path,
        overwrite_release,
        &[],
    )?;
    let immutable_pdf_url = format!("{}{}", archive.public_url, pdf_name);
    let current_pdf_url = format!("{}{}", archive.current_url, pdf_name);
    let mut result =
        PublishResult::archived(&release_id, "release", &archive, current_pdf_url.clone());
    result.artifacts = vec![publish_artifact(
        "pdf",
        immutable_pdf_url.clone(),
        pdf_path.to_string(),
    )];
    result.provenance = Some(format!("input={input_path}"));

    emit_archived_publish_result(
        "Typst release",
        &release_id,
        &current_pdf_url,
        &immutable_pdf_url,
        &result,
    )
}

fn emit_publish_result(summary: &str, result: &PublishResult) -> Result<()> {
    println!("{summary}");
    println!(
        "SPECTER_RESULT_JSON={}",
        serde_json::to_string(result).context("failed to serialize publish result")?
    );
    Ok(())
}

#[derive(Clone, Debug)]
pub(crate) struct ArchivedRelease {
    pub public_url: String,
    pub current_url: String,
}

pub(crate) fn resolve_release_id(repo_root: &Utf8Path, explicit: Option<&str>) -> Result<String> {
    if let Some(id) = explicit.map(str::trim).filter(|id| !id.is_empty()) {
        return crate::release::validate_release_id(id);
    }

    let output = command_output(
        Command::new("git")
            .arg("-C")
            .arg(repo_root.as_str())
            .arg("rev-parse")
            .arg("HEAD"),
        "failed to resolve git HEAD",
    )?;
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

pub fn push_records(source: &Path) -> Result<()> {
    let source = Utf8PathBuf::from_path_buf(
        source
            .canonicalize()
            .with_context(|| format!("failed to resolve records source {}", source.display()))?,
    )
    .map_err(|_| anyhow!("records source path must be valid UTF-8"))?;
    if !source.is_dir() {
        bail!("records source directory does not exist: {source}");
    }

    let deploy_user = required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = required_env("SPECTER_DEPLOY_HOST")?;
    let release_root =
        optional_env("SPECTER_RELEASE_ROOT").unwrap_or_else(|| "/srv/www/releases".to_owned());
    let public_base = optional_env("SPECTER_RELEASES_PUBLIC_URL")
        .unwrap_or_else(|| "https://releases.specterlab.org".to_owned());
    let remote_records_dir = format!("{}/records", release_root.trim_end_matches('/'));

    run_remote_command(&format!("mkdir -p {}", shell_quote(&remote_records_dir)))?;

    let mut rsync = Command::new("rsync");
    rsync
        .arg("-az")
        .arg("--delete")
        .arg("-e")
        .arg(rsync_ssh_command())
        .arg(format!("{}/", source))
        .arg(format!("{deploy_user}@{deploy_host}:{remote_records_dir}/"));
    run_command(&mut rsync, "failed to sync records archive")?;

    run_remote_command(&format!(
        "find {dir} -type d -exec chmod 755 {{}} + && find {dir} -type f -exec chmod 644 {{}} +",
        dir = shell_quote(&remote_records_dir),
    ))?;

    #[derive(Debug, Serialize)]
    #[serde(rename_all = "camelCase")]
    struct RecordsPushResult {
        public_url: String,
        remote_records_dir: String,
        source_path: String,
    }

    let result = RecordsPushResult {
        public_url: format!("{}/records/", public_base.trim_end_matches('/')),
        remote_records_dir,
        source_path: source.to_string(),
    };

    println!(
        "Records push: public={} remote={} source={}",
        result.public_url, result.remote_records_dir, result.source_path
    );
    println!(
        "SPECTER_RESULT_JSON={}",
        serde_json::to_string(&result).context("failed to serialize records push result")?
    );

    Ok(())
}

fn render_status_page(site_root: &Utf8Path) -> Result<()> {
    let status_dir = site_root.join("status");
    fs::create_dir_all(&status_dir).with_context(|| format!("failed to create {status_dir}"))?;
    let path = status_dir.join("index.html");

    let config = crate::config::load_report_config()
        .context("failed to load status report config for site/status/index.html")?;
    let data = report::collect(&config)
        .context("failed to collect status report for site/status/index.html")?;
    fs::write(&path, report::format_html(&data))
        .with_context(|| format!("failed to write {path}"))?;

    Ok(())
}

fn minify_site_tree(site_root: &Utf8Path) -> Result<()> {
    let has_lightningcss = command_succeeds(Command::new("lightningcss").arg("--version"));
    let has_minhtml = command_succeeds(Command::new("minhtml").arg("--version"));
    if !has_lightningcss || !has_minhtml {
        eprintln!("warning: lightningcss / minhtml not found, skipping minification");
        return Ok(());
    }

    let mut stack = vec![site_root.as_std_path().to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in
            fs::read_dir(&dir).with_context(|| format!("failed to read {}", dir.display()))?
        {
            let entry = entry?;
            let path = entry.path();
            if entry.file_type()?.is_dir() {
                if should_prune_dir(&path) {
                    continue;
                }
                stack.push(path);
                continue;
            }
            if should_minify_css(&path) {
                run_command(
                    Command::new("lightningcss")
                        .arg("--minify")
                        .arg("--targets")
                        .arg(">= 0.25%")
                        .arg(&path)
                        .arg("-o")
                        .arg(&path),
                    &format!("failed to minify CSS {}", path.display()),
                )?;
            } else if should_minify_html(&path) {
                run_command(
                    Command::new("minhtml")
                        .arg("--keep-closing-tags")
                        .arg("--keep-html-and-head-opening-tags")
                        .arg("--minify-css")
                        .arg("--minify-js")
                        .arg("--output")
                        .arg(&path)
                        .arg(&path),
                    &format!("failed to minify HTML {}", path.display()),
                )?;
            }
        }
    }

    Ok(())
}

fn should_prune_dir(path: &Path) -> bool {
    matches!(
        path.file_name().and_then(OsStr::to_str),
        Some("atlas" | "templates" | "node_modules")
    )
}

fn should_minify_css(path: &Path) -> bool {
    path.extension().and_then(OsStr::to_str) == Some("css")
}

fn should_minify_html(path: &Path) -> bool {
    path.extension().and_then(OsStr::to_str) == Some("html")
        && !path
            .file_name()
            .and_then(OsStr::to_str)
            .is_some_and(|name| name.ends_with("-template.html"))
}

fn publish_current_site(
    repo_root: &Utf8Path,
    site_root: &Utf8Path,
    release_id: &str,
    mount_excludes: &[String],
    remote_prunes: &[String],
) -> Result<()> {
    let deploy_user = required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = required_env("SPECTER_DEPLOY_HOST")?;
    let site_release_root =
        optional_env("SPECTER_SITE_ROOT").unwrap_or_else(|| "/srv/www/site".to_owned());
    let site_release_dir = format!("{site_release_root}/releases/{release_id}");

    run_remote_command(&format!("mkdir -p {}", shell_quote(&site_release_dir)))?;
    prune_remote_site_paths(&site_release_dir, remote_prunes)?;

    let mut rsync = Command::new("rsync");
    rsync
        .arg("-az")
        .arg("--delete")
        .arg("-e")
        .arg(rsync_ssh_command());
    for exclude in mount_excludes {
        rsync.arg("--exclude").arg(exclude);
    }
    rsync
        .arg(format!("{}/", site_root))
        .arg(format!("{deploy_user}@{deploy_host}:{site_release_dir}/"))
        .current_dir(repo_root);
    run_command(&mut rsync, "failed to rsync current site release")?;

    crate::site::data::link_remote(repo_root, &site_release_dir)?;

    run_remote_command(&format!(
        "find {dir} -type d -exec chmod 755 {{}} + && find {dir} -type f -exec chmod 644 {{}} + && ln -sfn {dir} {current}",
        dir = shell_quote(&site_release_dir),
        current = shell_quote(&format!("{site_release_root}/current"))
    ))?;

    Ok(())
}

fn prune_remote_site_paths(site_release_dir: &str, relative_paths: &[String]) -> Result<()> {
    if relative_paths.is_empty() {
        return Ok(());
    }
    let mut command = String::from("rm -rf --");
    for relative in relative_paths {
        let trimmed = relative.trim_start_matches('/').trim_end_matches('/');
        if trimmed.is_empty() {
            continue;
        }
        command.push(' ');
        command.push_str(&shell_quote(&format!("{site_release_dir}/{trimmed}")));
    }
    if command != "rm -rf --" {
        run_remote_command(&command)?;
    }
    Ok(())
}

pub(crate) fn archive_public_release(
    project: &str,
    surface: &str,
    release_id: &str,
    source: &Utf8Path,
    overwrite: bool,
    excludes: &[String],
) -> Result<ArchivedRelease> {
    let deploy_user = required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = required_env("SPECTER_DEPLOY_HOST")?;
    let release_root =
        optional_env("SPECTER_RELEASE_ROOT").unwrap_or_else(|| "/srv/www/releases".to_owned());
    let public_base = optional_env("SPECTER_RELEASES_PUBLIC_URL")
        .unwrap_or_else(|| "https://releases.specterlab.org".to_owned());
    let namespace = namespace_parts(project, surface);
    let namespace_root = join_remote_path(&release_root, &namespace);
    let release_dir = format!("{namespace_root}/releases/{release_id}");
    let current_link = format!("{namespace_root}/current");

    if overwrite {
        run_remote_command(&format!("rm -rf {}", shell_quote(&release_dir)))?;
    } else {
        let status = remote_command_status(&format!("test ! -e {}", shell_quote(&release_dir)))?;
        if !status.success() {
            bail!("public release already exists: {release_dir}");
        }
    }

    run_remote_command(&format!(
        "mkdir -p {} {}",
        shell_quote(&format!("{namespace_root}/releases")),
        shell_quote(&release_dir)
    ))?;

    let mut rsync = Command::new("rsync");
    rsync.arg("-az").arg("-e").arg(rsync_ssh_command());
    for exclude in excludes {
        rsync.arg("--exclude").arg(exclude);
    }
    let source_arg = rsync_source_arg(source)?;
    rsync
        .arg(source_arg)
        .arg(format!("{deploy_user}@{deploy_host}:{release_dir}/"));
    run_command(&mut rsync, "failed to archive public release")?;

    run_remote_command(&format!(
        "find {dir} -type d -exec chmod 755 {{}} + && find {dir} -type f -exec chmod 644 {{}} + && ln -sfn {dir} {current}",
        dir = shell_quote(&release_dir),
        current = shell_quote(&current_link)
    ))?;

    refresh_remote_portal(&release_root)?;

    let namespace_relative = namespace.join("/");
    Ok(ArchivedRelease {
        public_url: format!(
            "{}/{}/releases/{}/",
            public_base.trim_end_matches('/'),
            namespace_relative,
            release_id
        ),
        current_url: format!(
            "{}/{}/current/",
            public_base.trim_end_matches('/'),
            namespace_relative
        ),
    })
}

fn refresh_remote_portal(release_root: &str) -> Result<()> {
    if let Err(err) = sync_remote_portal_manifest(release_root) {
        eprintln!("warning: failed to sync remote portal surface manifest: {err:#}");
    }

    let remote_bin = if remote_has_system_spctr() {
        "spctr".to_owned()
    } else {
        match upload_local_spctr() {
            Ok(()) => REMOTE_PORTAL_BIN.to_owned(),
            Err(err) => {
                eprintln!("warning: {err:#}");
                eprintln!("warning: no usable spctr on remote, skipping portal refresh");
                return Ok(());
            }
        }
    };

    let cmd = format!(
        "{} site portal --release-root {}",
        shell_quote(&remote_bin),
        shell_quote(release_root)
    );
    let output = remote_command_output(&cmd)?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        if detail.is_empty() {
            eprintln!("warning: failed to refresh remote release portal");
        } else {
            eprintln!("warning: failed to refresh remote release portal: {detail}");
        }
    }

    Ok(())
}

fn sync_remote_portal_manifest(release_root: &str) -> Result<()> {
    let local_manifest_root = Builder::new()
        .prefix("spctr-portal-manifest.")
        .tempdir()
        .context("failed to allocate temporary portal manifest directory")?;
    let local_manifest_path = local_manifest_root
        .path()
        .join(archive::PORTAL_MANIFEST_RELATIVE_PATH);
    archive::write_portal_manifest_file(&local_manifest_path)?;

    let deploy_user = required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = required_env("SPECTER_DEPLOY_HOST")?;
    let remote_manifest_dir = format!(
        "{}/{}",
        release_root.trim_end_matches('/'),
        archive::PORTAL_MANIFEST_DIR
    );
    run_remote_command(&format!("mkdir -p {}", shell_quote(&remote_manifest_dir)))?;

    let mut rsync = Command::new("rsync");
    rsync
        .arg("-az")
        .arg("-e")
        .arg(rsync_ssh_command())
        .arg(local_manifest_path.as_os_str())
        .arg(format!(
            "{deploy_user}@{deploy_host}:{}/{}",
            remote_manifest_dir,
            archive::PORTAL_MANIFEST_FILE
        ));
    run_command(&mut rsync, "failed to sync portal surface manifest")
}

fn remote_has_system_spctr() -> bool {
    remote_command_status("command -v spctr")
        .map(|s| s.success())
        .unwrap_or(false)
}

fn upload_local_spctr() -> Result<()> {
    let current_exe = std::env::current_exe().context("failed to resolve current spctr binary")?;
    if !current_exe.is_file() {
        bail!("local spctr binary not found");
    }
    let deploy_user = required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = required_env("SPECTER_DEPLOY_HOST")?;
    let mut rsync = Command::new("rsync");
    rsync
        .arg("-az")
        .arg("-e")
        .arg(rsync_ssh_command())
        .arg(&current_exe)
        .arg(format!("{deploy_user}@{deploy_host}:{REMOTE_PORTAL_BIN}"));
    run_command(
        &mut rsync,
        "failed to copy spctr binary for remote portal refresh",
    )?;
    run_remote_command(&format!("chmod +x {}", shell_quote(REMOTE_PORTAL_BIN)))?;
    Ok(())
}

fn namespace_parts(project: &str, surface: &str) -> Vec<String> {
    let mut parts = vec![project.to_owned()];
    if !matches!(surface, "" | "." | "_" | "default" | "root") {
        parts.push(surface.to_owned());
    }
    parts
}

fn join_remote_path(base: &str, parts: &[String]) -> String {
    let mut path = base.trim_end_matches('/').to_owned();
    for part in parts {
        path.push('/');
        path.push_str(part.trim_matches('/'));
    }
    path
}

fn site_public_url() -> String {
    optional_env("SPECTER_SITE_PUBLIC_URL").unwrap_or_else(|| "https://specterlab.org".to_owned())
}

pub(crate) fn optional_env(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

pub(crate) fn required_env(name: &str) -> Result<String> {
    optional_env(name)
        .ok_or_else(|| anyhow::anyhow!("missing required environment variable: {name}"))
}

pub(crate) fn ssh_base_args() -> Result<Vec<String>> {
    let mut args = vec![
        "ssh".to_owned(),
        "-o".to_owned(),
        "BatchMode=yes".to_owned(),
        "-o".to_owned(),
        "ConnectTimeout=10".to_owned(),
    ];
    if let Some(key) = optional_env("SPECTER_DEPLOY_SSH_KEY") {
        args.extend([
            "-i".to_owned(),
            key,
            "-o".to_owned(),
            "IdentitiesOnly=yes".to_owned(),
        ]);
    }
    Ok(args)
}

pub(crate) fn rsync_ssh_command() -> String {
    ssh_base_args()
        .expect("ssh args should be infallible")
        .into_iter()
        .map(|arg| shell_quote(&arg))
        .collect::<Vec<_>>()
        .join(" ")
}

fn remote_command_status(command: &str) -> Result<std::process::ExitStatus> {
    let output = remote_command_output(command)?;
    Ok(output.status)
}

fn remote_command_output(command: &str) -> Result<Output> {
    let deploy_user = required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = required_env("SPECTER_DEPLOY_HOST")?;
    let mut ssh = Command::new("ssh");
    for arg in ssh_base_args()?.into_iter().skip(1) {
        ssh.arg(arg);
    }
    ssh.arg(format!("{deploy_user}@{deploy_host}"))
        .arg(command)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    ssh.output()
        .with_context(|| format!("failed to run remote ssh command: {command}"))
}

pub(crate) fn run_remote_command(command: &str) -> Result<()> {
    let output = remote_command_output(command)?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        bail!("remote command failed: {command}\n{stderr}");
    }
    Ok(())
}

pub(crate) fn run_command(command: &mut Command, context: &str) -> Result<()> {
    let output = command_output(command, context)?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        bail!("{context}: {stderr}");
    }
    Ok(())
}

fn command_output(command: &mut Command, context: &str) -> Result<Output> {
    command.output().with_context(|| context.to_owned())
}

fn resolve_repo_path(repo_root: &Utf8Path, path: &Utf8Path) -> Utf8PathBuf {
    if path.is_absolute() {
        path.to_owned()
    } else {
        repo_root.join(path)
    }
}

fn runtime_root(repo_root: &Utf8Path) -> Result<Utf8PathBuf> {
    let root = optional_env("SPECTER_RUNTIME_ROOT")
        .map(Utf8PathBuf::from)
        .unwrap_or_else(|| repo_root.join("tmp"));
    if root.exists() && !root.is_dir() {
        bail!("runtime root exists and is not a directory: {root}");
    }
    Ok(root)
}

fn rsync_source_arg(source: &Utf8Path) -> Result<String> {
    if source.is_dir() {
        return Ok(format!("{}/", source));
    }
    if source.is_file() {
        return Ok(source.to_string());
    }
    bail!("release source does not exist: {source}");
}

fn same_path(left: &Utf8Path, right: &Utf8Path) -> Result<bool> {
    if !left.exists() || !right.exists() {
        return Ok(left == right);
    }
    Ok(left.canonicalize_utf8()? == right.canonicalize_utf8()?)
}

fn read_json_map(path: &Utf8Path) -> Result<serde_json::Map<String, serde_json::Value>> {
    let text = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let value: serde_json::Value =
        serde_json::from_str(&text).with_context(|| format!("failed to parse JSON in {path}"))?;
    let object = value
        .as_object()
        .cloned()
        .ok_or_else(|| anyhow!("expected a JSON object in {path}"))?;
    Ok(object)
}

fn copy_dir_all(source: &Utf8Path, destination: &Utf8Path) -> Result<()> {
    fs::create_dir_all(destination)
        .with_context(|| format!("failed to create directory {destination}"))?;
    for entry in fs::read_dir(source).with_context(|| format!("failed to read {source}"))? {
        let entry = entry?;
        let entry_path = Utf8PathBuf::from_path_buf(entry.path())
            .map_err(|_| anyhow!("copied directory path must be valid UTF-8"))?;
        let target_path = destination.join(entry.file_name().to_string_lossy().as_ref());
        if entry.file_type()?.is_dir() {
            copy_dir_all(&entry_path, &target_path)?;
        } else {
            fs::copy(&entry_path, &target_path)
                .with_context(|| format!("failed to copy {entry_path} -> {target_path}"))?;
        }
    }
    Ok(())
}

fn command_succeeds(command: &mut Command) -> bool {
    command.status().is_ok_and(|status| status.success())
}

pub(crate) fn shell_quote(value: &str) -> String {
    if value.is_empty() {
        return "''".to_owned();
    }
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

#[cfg(test)]
mod tests {
    use super::{
        join_remote_path, namespace_parts, research_note_publish_plan, rsync_source_arg,
        should_minify_css, should_minify_html, should_prune_dir,
    };
    use camino::Utf8Path;
    use std::path::Path;
    use tempfile::tempdir;

    fn write(root: &Utf8Path, rel: &str, content: &str) {
        let path = root.join(rel);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, content).unwrap();
    }

    #[test]
    fn minify_filters_skip_templates_and_atlas_inputs() {
        assert!(should_prune_dir(Path::new("site/templates")));
        assert!(should_prune_dir(Path::new("site/atlas")));
        assert!(should_prune_dir(Path::new(
            "site/dashboards/wonton-soup/node_modules"
        )));
        assert!(should_minify_css(Path::new("site/style.css")));
        assert!(should_minify_html(Path::new("site/index.html")));
        assert!(!should_minify_html(Path::new(
            "site/cabinet/index-template.html"
        )));
    }

    #[test]
    fn namespace_root_omits_root_surface_segment() {
        assert_eq!(namespace_parts("site", "root"), vec!["site".to_owned()]);
        assert_eq!(
            namespace_parts("lenia-swarm", "compendium"),
            vec!["lenia-swarm".to_owned(), "compendium".to_owned()]
        );
        assert_eq!(
            join_remote_path("/srv/www/releases", &["site".to_owned()]),
            "/srv/www/releases/site"
        );
    }

    #[test]
    fn rsync_source_arg_preserves_files_and_slashes_directories() {
        let root = tempdir().unwrap();
        let dir = root.path().join("site");
        let file = root.path().join("site.pdf");
        std::fs::create_dir(&dir).unwrap();
        std::fs::write(&file, b"pdf").unwrap();
        let dir = Utf8Path::from_path(dir.as_path()).unwrap();
        let file = Utf8Path::from_path(file.as_path()).unwrap();
        assert_eq!(rsync_source_arg(dir).unwrap(), format!("{dir}/"));
        assert_eq!(rsync_source_arg(file).unwrap(), file.to_string());
    }

    #[test]
    fn draft_research_notes_are_excluded_from_site_publish() {
        let root = tempdir().unwrap();
        let root = Utf8Path::from_path(root.path()).unwrap();
        write(
            root,
            "site/research-notes/draft-note/index.md",
            r#"---
title: "Draft Note"
release: "draft"
---

# Draft Note
"#,
        );

        let plan = research_note_publish_plan(root).unwrap();
        assert_eq!(plan.excludes, vec!["research-notes/".to_owned()]);
        assert_eq!(plan.remote_prunes, vec!["research-notes/".to_owned()]);
    }

    #[test]
    fn mixed_research_notes_exclude_only_drafts_and_staging_files() {
        let root = tempdir().unwrap();
        let root = Utf8Path::from_path(root.path()).unwrap();
        write(
            root,
            "site/research-notes/draft-note/index.md",
            r#"---
title: "Draft Note"
release: "draft"
---

# Draft Note
"#,
        );
        write(
            root,
            "site/research-notes/public-note/index.md",
            r#"---
title: "Public Note"
release: "published"
---

# Public Note
"#,
        );

        let plan = research_note_publish_plan(root).unwrap();
        assert_eq!(
            plan.excludes,
            vec![
                "research-notes/draft-note/".to_owned(),
                "research-notes/index.html".to_owned(),
                "research-notes/pandoc-template.html".to_owned(),
            ]
        );
        assert_eq!(
            plan.remote_prunes,
            vec!["research-notes/draft-note/".to_owned()]
        );
    }
}
