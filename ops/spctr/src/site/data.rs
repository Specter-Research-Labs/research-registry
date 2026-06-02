use std::os::unix::fs as unix_fs;
use std::process::Command;

use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};

use crate::manifest;
use crate::site::publish;

pub struct ResolvedMount {
    pub name: String,
    pub project: String,
    pub site_path: String,
    pub local_abs: Utf8PathBuf,
    pub remote_path: String,
}

fn site_data_root() -> String {
    let site_root =
        publish::optional_env("SPECTER_SITE_ROOT").unwrap_or_else(|| "/srv/www/site".to_owned());
    site_data_root_for_site_root(&site_root)
}

fn site_data_root_for_site_root(site_root: &str) -> String {
    format!("{}/data", site_root.trim_end_matches('/'))
}

pub fn resolve_mounts(repo_root: &Utf8Path) -> Result<Vec<ResolvedMount>> {
    let data_root = site_data_root();
    let discoveries = manifest::discover_site_data_mounts(repo_root)?;
    let mut mounts = Vec::with_capacity(discoveries.len());
    for (manifest, config) in discoveries {
        let project = manifest
            .spctr
            .as_ref()
            .map(|s| s.project.clone())
            .unwrap_or_else(|| manifest.slug.clone());
        mounts.push(ResolvedMount {
            remote_path: format!("{}/{}/{}", data_root, project, config.name),
            local_abs: manifest.root.join(&config.local_source),
            name: config.name,
            project,
            site_path: config.site_path,
        });
    }
    Ok(mounts)
}

pub fn link_local(repo_root: &Utf8Path) -> Result<()> {
    let mounts = resolve_mounts(repo_root)?;
    for mount in &mounts {
        if !mount.local_abs.is_dir() {
            eprintln!(
                "site data: skipping {} (source not found: {})",
                mount.name, mount.local_abs
            );
            continue;
        }
        let link_path = repo_root.join("site").join(&mount.site_path);
        if let Some(parent) = link_path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("failed to create parent for {link_path}"))?;
        }
        let meta = std::fs::symlink_metadata(link_path.as_std_path());
        if let Ok(ref m) = meta {
            if m.file_type().is_symlink() {
                std::fs::remove_file(&link_path)
                    .with_context(|| format!("failed to remove existing symlink {link_path}"))?;
            } else {
                bail!("{link_path} exists and is not a symlink; remove it first");
            }
        }
        unix_fs::symlink(mount.local_abs.as_std_path(), link_path.as_std_path())
            .with_context(|| format!("failed to symlink {link_path} -> {}", mount.local_abs))?;
        eprintln!("site data: {} -> {}", link_path, mount.local_abs);
    }
    Ok(())
}

pub fn link_remote(repo_root: &Utf8Path, site_release_dir: &str) -> Result<()> {
    let mounts = resolve_mounts(repo_root)?;
    for mount in &mounts {
        let link_path = format!("{}/{}", site_release_dir, mount.site_path);
        let parent = link_path.rsplit_once('/').map(|(p, _)| p).unwrap_or(".");
        publish::run_remote_command(&format!(
            "mkdir -p {} && ln -sfn {} {}",
            publish::shell_quote(parent),
            publish::shell_quote(&mount.remote_path),
            publish::shell_quote(&link_path),
        ))?;
    }
    Ok(())
}

pub fn push_data(
    repo_root: &Utf8Path,
    project_filter: Option<&str>,
    name_filter: Option<&str>,
) -> Result<()> {
    let deploy_user = publish::required_env("SPECTER_DEPLOY_USER")?;
    let deploy_host = publish::required_env("SPECTER_DEPLOY_HOST")?;
    let mounts = resolve_mounts(repo_root)?;
    let filtered: Vec<_> = mounts
        .iter()
        .filter(|m| {
            project_filter.map_or(true, |p| m.project == p)
                && name_filter.map_or(true, |n| m.name == n)
        })
        .collect();
    if filtered.is_empty() {
        bail!("no matching site data mounts found");
    }
    for mount in &filtered {
        if !mount.local_abs.is_dir() {
            bail!("source not found: {}", mount.local_abs);
        }
        eprintln!(
            "site data: pushing {}/{} -> {}",
            mount.project, mount.name, mount.remote_path
        );
        publish::run_remote_command(&format!(
            "mkdir -p {}",
            publish::shell_quote(&mount.remote_path),
        ))?;
        let mut rsync = Command::new("rsync");
        rsync
            .arg("-az")
            .arg("--delete")
            .arg("-e")
            .arg(publish::rsync_ssh_command())
            .arg(format!("{}/", mount.local_abs))
            .arg(format!(
                "{deploy_user}@{deploy_host}:{}/",
                mount.remote_path
            ));
        publish::run_command(&mut rsync, "failed to push site data")?;
        eprintln!("site data: pushed {}/{}", mount.project, mount.name);
    }
    Ok(())
}

pub fn pull_data(
    repo_root: &Utf8Path,
    project_filter: Option<&str>,
    name_filter: Option<&str>,
    host: Option<&str>,
    user: Option<&str>,
) -> Result<()> {
    let deploy_user = match user {
        Some(value) => value.to_owned(),
        None => publish::required_env("SPECTER_DEPLOY_USER")?,
    };
    let deploy_host = match host {
        Some(value) => value.to_owned(),
        None => publish::required_env("SPECTER_DEPLOY_HOST")?,
    };
    let mounts = resolve_mounts(repo_root)?;
    let filtered: Vec<_> = mounts
        .iter()
        .filter(|m| {
            project_filter.map_or(true, |p| m.project == p)
                && name_filter.map_or(true, |n| m.name == n)
        })
        .collect();
    if filtered.is_empty() {
        bail!("no matching site data mounts found");
    }
    for mount in &filtered {
        if let Some(parent) = mount.local_abs.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("failed to create parent for {}", mount.local_abs))?;
        }
        std::fs::create_dir_all(&mount.local_abs)
            .with_context(|| format!("failed to create {}", mount.local_abs))?;
        eprintln!(
            "site data: pulling {}/{} <- {}",
            mount.project, mount.name, mount.remote_path
        );
        let mut rsync = Command::new("rsync");
        rsync
            .arg("-az")
            .arg("--delete")
            .arg("-e")
            .arg(publish::rsync_ssh_command())
            .arg(format!(
                "{deploy_user}@{deploy_host}:{}/",
                mount.remote_path
            ))
            .arg(format!("{}/", mount.local_abs));
        publish::run_command(&mut rsync, "failed to pull site data")?;
        eprintln!("site data: pulled {}/{}", mount.project, mount.name);
    }
    Ok(())
}

pub fn rsync_excludes(repo_root: &Utf8Path) -> Result<Vec<String>> {
    let discoveries = manifest::discover_site_data_mounts(repo_root)?;
    Ok(discoveries
        .into_iter()
        .map(|(_, config)| config.site_path)
        .collect())
}

#[cfg(test)]
mod tests {
    use super::site_data_root_for_site_root;

    #[test]
    fn site_data_root_is_derived_from_site_root() {
        assert_eq!(
            site_data_root_for_site_root("/srv/www/site"),
            "/srv/www/site/data"
        );
        assert_eq!(
            site_data_root_for_site_root("/srv/www/site/"),
            "/srv/www/site/data"
        );
        assert_eq!(
            site_data_root_for_site_root("/tmp/site-preview"),
            "/tmp/site-preview/data"
        );
    }
}
