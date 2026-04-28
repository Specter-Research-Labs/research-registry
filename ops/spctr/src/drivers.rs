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

fn infer_remote_base(path: &str) -> RemoteBase {
    if path == "logs" || path.starts_with("logs/") {
        RemoteBase::Logs
    } else {
        RemoteBase::Artifacts
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
    machine: &MachineConfig,
    config: &RawRootConfig,
) -> Result<RawRoot> {
    let local_path = if config.resolve.as_deref() == Some("runtime") {
        resolve_runtime_path(project_root, machine, config)?
    } else {
        project_root.join(&config.path)
    };
    let remote_base = config
        .remote_base
        .as_deref()
        .map(|b| match b {
            "logs" => RemoteBase::Logs,
            _ => RemoteBase::Artifacts,
        })
        .unwrap_or_else(|| infer_remote_base(&config.path));
    let remote_relpath = if config.resolve.is_some() {
        String::new()
    } else {
        config.path.clone()
    };
    Ok(RawRoot {
        local_path,
        remote_base,
        remote_relpath,
        excludes: config.excludes.clone(),
    })
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
        .map(|config| resolve_raw_root(&manifest.root, machine, config))
        .collect::<Result<Vec<_>>>()?;
    let db_path = surface.local_db_path.as_ref().map(|rel| {
        if let Some(idx) = surface.db_raw_root {
            raw_roots[idx].local_path.join(rel)
        } else {
            manifest.root.join(rel)
        }
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
