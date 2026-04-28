use crate::config::load_machine_config;
use crate::drivers::resolve_surface;
use crate::manifest::{self, discover_surfaced_manifests, load_project_manifest, MANIFEST_NAME};
use crate::surface::{check_command, env_for_machine};
use anyhow::{bail, Context, Result};
use camino::Utf8Path;

fn discover_by_slug(repo_root: &Utf8Path, slug: &str) -> Result<manifest::ProjectManifest> {
    for parent in &["dossiers", "addenda"] {
        let path = repo_root.join(parent).join(slug).join(MANIFEST_NAME);
        if path.is_file() {
            return load_project_manifest(&path, None);
        }
    }
    bail!("no {MANIFEST_NAME} found for project '{slug}'")
}

pub fn refresh(
    project: &str,
    site_data_root: Option<&str>,
    release_id: Option<&str>,
) -> Result<()> {
    refresh_project_surface(project, None, site_data_root, release_id)
}

fn refresh_project_surface(
    project: &str,
    surface_name: Option<&str>,
    site_data_root: Option<&str>,
    release_id: Option<&str>,
) -> Result<()> {
    let repo_root = manifest::repo_root()?;
    let machine = load_machine_config()?;
    let manifest = discover_by_slug(&repo_root, project)?;

    let spctr = manifest
        .spctr
        .as_ref()
        .context("project has no spctr configuration")?;
    let surface_name = match surface_name {
        Some(surface_name) => surface_name,
        None => spctr
            .default_surface
            .as_deref()
            .context("project has no default_surface")?,
    };
    let surface_config = spctr
        .surfaces
        .get(surface_name)
        .ok_or_else(|| anyhow::anyhow!("surface '{surface_name}' not found"))?;
    let resolved = resolve_surface(&manifest, surface_config, &machine)?;

    if resolved.refresh_commands.is_empty() {
        bail!("{surface_name} has no refresh commands");
    }

    let envs = env_for_machine(&machine);

    for command in &resolved.refresh_commands {
        let program = command.first().context("empty refresh command")?;
        check_command(program, &command[1..], Some(&manifest.root), &envs, None)?;
    }
    eprintln!("{surface_name}: refresh=ok");

    if let Some(root) = site_data_root {
        let staging = format!("{root}.staging");

        let args: Vec<String> = [
            "run",
            "python",
            "wonton.py",
            "lake",
            "export-parquet",
            "--out-dir",
            staging.as_str(),
            "--profile",
            "dashboard",
        ]
        .iter()
        .map(|s| (*s).to_owned())
        .collect();
        let mut args = args;
        if let Some(release_id) = release_id {
            args.push("--release-id".to_owned());
            args.push(release_id.to_owned());
        }
        check_command("uv", &args, Some(&manifest.root), &envs, None)?;

        let validator = repo_root
            .join("site/dashboards/wonton-soup/validate_manifest.py")
            .to_string();
        let validate_args: Vec<String> = [validator.as_str(), "--root", staging.as_str()]
            .iter()
            .map(|s| (*s).to_owned())
            .collect();
        check_command("python3", &validate_args, Some(&repo_root), &envs, None)?;

        let rm_args: Vec<String> = ["-rf", root].iter().map(|s| (*s).to_owned()).collect();
        check_command("rm", &rm_args, Some(&repo_root), &envs, None)?;
        let mv_args: Vec<String> = [staging.as_str(), root]
            .iter()
            .map(|s| (*s).to_owned())
            .collect();
        check_command("mv", &mv_args, Some(&repo_root), &envs, None)?;

        eprintln!("{surface_name}: site-data=ok");
    }

    Ok(())
}

pub fn refresh_surface(
    surface: &str,
    site_data_root: Option<&str>,
    release_id: Option<&str>,
) -> Result<()> {
    let repo_root = manifest::repo_root()?;
    for manifest in discover_surfaced_manifests(&repo_root)? {
        let Some(spctr) = &manifest.spctr else {
            continue;
        };
        if spctr.surfaces.contains_key(surface) {
            return refresh_project_surface(
                &manifest.slug,
                Some(surface),
                site_data_root,
                release_id,
            );
        }
    }
    bail!("unknown surface: {surface}")
}
