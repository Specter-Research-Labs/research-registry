use crate::config::MachineConfig;
use crate::manifest::{ProjectManifest, RawRootConfig, SurfaceConfig};
use anyhow::Result;
use camino::{Utf8Path, Utf8PathBuf};

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RemoteBase {
    Logs,
    Artifacts,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RawRoot {
    pub local_path: Utf8PathBuf,
    pub remote_base: RemoteBase,
    pub remote_relpath: String,
    pub excludes: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ResolvedSurface {
    pub project_name: String,
    pub surface_name: String,
    pub kind: String,
    pub raw_roots: Vec<RawRoot>,
    pub db_path: Option<Utf8PathBuf>,
    pub refresh_commands: Vec<Vec<String>>,
    pub remote_raw_namespace: String,
    pub remote_snapshot_namespace: String,
    pub db_filename: Option<String>,
}

fn runtime_root(machine: &MachineConfig, slug: &str) -> Option<Utf8PathBuf> {
    machine
        .runtime_root
        .as_ref()
        .map(|root| Utf8PathBuf::from(root).join(slug))
}

fn repo_root(project_root: &Utf8Path) -> Result<Utf8PathBuf> {
    project_root
        .parent()
        .and_then(Utf8Path::parent)
        .map(Utf8Path::to_owned)
        .ok_or_else(|| {
            anyhow::anyhow!("{project_root}: project root is not under dossiers/ or addenda/")
        })
}

fn default_local_project_root(project_root: &Utf8Path, project_name: &str) -> Utf8PathBuf {
    let Some(repo) = project_root.parent().and_then(Utf8Path::parent) else {
        return project_root.to_owned();
    };
    let Some(workspace_parent) = repo.parent() else {
        return project_root.to_owned();
    };
    if workspace_parent.file_name() != Some("research-registry-workspaces") {
        return project_root.to_owned();
    }
    let Some(specter_root) = workspace_parent.parent() else {
        return project_root.to_owned();
    };
    let shared_project_root = specter_root
        .join("research-registry/dossiers")
        .join(project_name);
    if shared_project_root.exists() {
        return shared_project_root;
    }
    project_root.to_owned()
}

fn infer_remote_base(path: &str) -> RemoteBase {
    if path == "logs" || path.starts_with("logs/") {
        RemoteBase::Logs
    } else {
        RemoteBase::Artifacts
    }
}

fn resolve_local_root(
    project_root: &Utf8Path,
    machine: &MachineConfig,
    project_name: &str,
    path: &str,
    remote_base: &RemoteBase,
) -> Utf8PathBuf {
    let configured_root = match remote_base {
        RemoteBase::Logs => machine.local_log_root.as_ref(),
        RemoteBase::Artifacts => machine.local_artifact_root.as_ref(),
    };
    match configured_root {
        Some(root) => Utf8PathBuf::from(root).join(project_name).join(path),
        None => default_local_project_root(project_root, project_name).join(path),
    }
}

fn resolve_runtime_path(
    project_root: &Utf8Path,
    machine: &MachineConfig,
    config: &RawRootConfig,
) -> Result<Utf8PathBuf> {
    let slug = config.runtime_slug.as_deref().unwrap();
    let subpath = &config.path;
    if let Some(rt) = runtime_root(machine, slug) {
        return Ok(rt.join(subpath));
    }
    let category = config.remote_base.as_deref().unwrap_or_else(|| {
        if subpath == "logs" || subpath.starts_with("logs/") {
            "logs"
        } else {
            "artifacts"
        }
    });
    let has_durable = match category {
        "logs" => !machine.durable_log_root.is_empty(),
        _ => !machine.durable_artifact_root.is_empty(),
    };
    if has_durable {
        return Ok(
            repo_root(project_root)?.join(format!("tmp/runtime-{category}/{slug}/{subpath}"))
        );
    }
    Ok(project_root.join(config.project_fallback.as_deref().unwrap()))
}

fn resolve_raw_root(
    project_root: &Utf8Path,
    project_name: &str,
    machine: &MachineConfig,
    config: &RawRootConfig,
) -> Result<RawRoot> {
    let remote_base = config
        .remote_base
        .as_deref()
        .map(|b| match b {
            "logs" => RemoteBase::Logs,
            _ => RemoteBase::Artifacts,
        })
        .unwrap_or_else(|| infer_remote_base(&config.path));
    let local_path = if config.resolve.as_deref() == Some("runtime") {
        resolve_runtime_path(project_root, machine, config)?
    } else {
        resolve_local_root(
            project_root,
            machine,
            project_name,
            &config.path,
            &remote_base,
        )
    };
    let remote_relpath = if config.resolve.is_some() {
        String::new()
    } else {
        remote_relpath(&remote_base, &config.path)
    };
    Ok(RawRoot {
        local_path,
        remote_base,
        remote_relpath,
        excludes: config.excludes.clone(),
    })
}

fn strip_category_prefix<'a>(path: &'a str, category: &str) -> &'a str {
    if path == category {
        ""
    } else {
        path.strip_prefix(&format!("{category}/")).unwrap_or(path)
    }
}

fn remote_relpath(remote_base: &RemoteBase, path: &str) -> String {
    match remote_base {
        RemoteBase::Logs => strip_category_prefix(path, "logs").to_owned(),
        RemoteBase::Artifacts => strip_category_prefix(path, "artifacts").to_owned(),
    }
}

fn resolve_db_path(
    project_root: &Utf8Path,
    project_name: &str,
    machine: &MachineConfig,
    raw_roots: &[RawRoot],
    db_raw_root: Option<usize>,
    rel: &str,
) -> Utf8PathBuf {
    if let Some(idx) = db_raw_root {
        return raw_roots[idx].local_path.join(rel);
    }
    let remote_base = infer_remote_base(rel);
    resolve_local_root(project_root, machine, project_name, rel, &remote_base)
}

pub fn resolve_surface(
    manifest: &ProjectManifest,
    surface: &SurfaceConfig,
    machine: &MachineConfig,
) -> Result<ResolvedSurface> {
    let project_name = manifest
        .spctr
        .as_ref()
        .map_or_else(|| manifest.slug.clone(), |spctr| spctr.project.clone());
    let raw_roots = surface
        .raw_roots
        .iter()
        .map(|config| resolve_raw_root(&manifest.root, &project_name, machine, config))
        .collect::<Result<Vec<_>>>()?;
    let db_path = surface.local_db_path.as_ref().map(|rel| {
        resolve_db_path(
            &manifest.root,
            &project_name,
            machine,
            &raw_roots,
            surface.db_raw_root,
            rel,
        )
    });
    let db_filename = db_path
        .as_ref()
        .and_then(|path| path.file_name())
        .map(ToOwned::to_owned);
    let refresh_commands = if let Some(ref cmds) = surface.refresh_commands {
        cmds.clone()
    } else if let Some(ref cmd) = surface.refresh_command {
        vec![cmd.clone()]
    } else {
        Vec::new()
    };
    let remote_raw_namespace = surface
        .remote_raw_namespace
        .clone()
        .unwrap_or_else(|| project_name.clone());
    let remote_snapshot_namespace = surface
        .remote_snapshot_namespace
        .clone()
        .unwrap_or_else(|| surface.name.clone());
    Ok(ResolvedSurface {
        project_name,
        surface_name: surface.name.clone(),
        kind: surface.kind.clone(),
        raw_roots,
        db_path,
        refresh_commands,
        remote_raw_namespace,
        remote_snapshot_namespace,
        db_filename,
    })
}
