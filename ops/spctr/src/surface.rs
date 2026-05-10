use crate::config::{load_machine_config, MachineConfig, SshConfig};
use crate::drivers::{resolve_surface, RawRoot, RemoteBase, ResolvedSurface};
use crate::manifest::{
    discover_manifest, discover_surfaced_manifests, repo_root, ProjectManifest, SurfaceConfig,
};
use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use chrono::Utc;
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::process::{Command, Output, Stdio};

trait RemoteFs {
    fn read_text(&self, path: &str) -> Result<Option<String>>;
    fn write_text(&self, path: &str, content: &str) -> Result<()>;
    fn ensure_dir(&self, path: &str) -> Result<()>;
    fn checksum(&self, path: &str) -> Result<String>;
    fn list_json_stems(&self, dir: &str) -> Result<Vec<String>>;
    fn rsync_target(&self, path: &str) -> String;
    fn rsync_transport_args(&self) -> Vec<String>;
    fn copy_to_local(&self, source: &str, local_target: &Utf8Path) -> Result<()>;
    fn copy_remote_file(&self, source: &str, target: &str) -> Result<()>;
    fn cas_write_text(
        &self,
        path: &str,
        content: &str,
        expected_snapshot_id: Option<&str>,
    ) -> Result<()>;
}

fn read_json<T: DeserializeOwned>(fs: &dyn RemoteFs, path: &str) -> Result<Option<T>> {
    let Some(text) = fs.read_text(path)? else {
        return Ok(None);
    };
    serde_json::from_str::<T>(&text)
        .with_context(|| format!("invalid JSON in {path}"))
        .map(Some)
}

fn write_json(fs: &dyn RemoteFs, path: &str, payload: &impl Serialize) -> Result<()> {
    let encoded = serde_json::to_string_pretty(payload).context("failed to encode JSON")?;
    fs.write_text(path, &(encoded + "\n"))
}

struct LocalFs;

impl RemoteFs for LocalFs {
    fn read_text(&self, path: &str) -> Result<Option<String>> {
        let local = Utf8Path::new(path);
        if !local.exists() {
            return Ok(None);
        }
        fs::read_to_string(local)
            .with_context(|| format!("failed to read {local}"))
            .map(Some)
    }

    fn write_text(&self, path: &str, content: &str) -> Result<()> {
        atomic_write_bytes(Utf8Path::new(path), content.as_bytes())
    }

    fn ensure_dir(&self, path: &str) -> Result<()> {
        fs::create_dir_all(path).with_context(|| format!("failed to create {path}"))
    }

    fn checksum(&self, path: &str) -> Result<String> {
        sha256_file(Utf8Path::new(path))
    }

    fn list_json_stems(&self, dir: &str) -> Result<Vec<String>> {
        let local = Utf8Path::new(dir);
        if !local.exists() {
            return Ok(Vec::new());
        }
        let mut items = local
            .read_dir()
            .with_context(|| format!("failed to read {local}"))?
            .filter_map(|entry| entry.ok())
            .filter_map(|entry| {
                let path = entry.path();
                (path.extension().and_then(|ext| ext.to_str()) == Some("json")).then(|| {
                    path.file_stem()
                        .and_then(|stem| stem.to_str())
                        .map(ToOwned::to_owned)
                })?
            })
            .collect::<Vec<_>>();
        items.sort();
        Ok(items)
    }

    fn rsync_target(&self, path: &str) -> String {
        path.to_owned()
    }

    fn rsync_transport_args(&self) -> Vec<String> {
        Vec::new()
    }

    fn copy_to_local(&self, source: &str, local_target: &Utf8Path) -> Result<()> {
        fs::copy(source, local_target)
            .with_context(|| format!("failed to copy {source} to {local_target}"))?;
        Ok(())
    }

    fn copy_remote_file(&self, source: &str, target: &str) -> Result<()> {
        let source = Utf8Path::new(source);
        let target = Utf8Path::new(target);
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
        }
        if fs::hard_link(source, target).is_err() {
            fs::copy(source, target)
                .with_context(|| format!("failed to copy {source} to {target}"))?;
        }
        Ok(())
    }

    fn cas_write_text(
        &self,
        path: &str,
        content: &str,
        expected_snapshot_id: Option<&str>,
    ) -> Result<()> {
        let current_snapshot: Option<String> =
            read_json::<CurrentSnapshot>(self, path)?.and_then(|c| c.snapshot_id);
        if current_snapshot.as_deref() != expected_snapshot_id {
            bail!(
                "remote current changed during promote: expected={:?} actual={:?}",
                expected_snapshot_id,
                current_snapshot
            );
        }
        self.write_text(path, content)
    }
}

struct SshFs {
    ssh: SshConfig,
}

fn shell_quote(value: &str) -> String {
    if value.is_empty() {
        return "''".to_owned();
    }
    let mut quoted = String::from("'");
    for ch in value.chars() {
        if ch == '\'' {
            quoted.push_str("'\"'\"'");
        } else {
            quoted.push(ch);
        }
    }
    quoted.push('\'');
    quoted
}

impl SshFs {
    fn remote_command_args(&self, parts: &[String]) -> Vec<String> {
        let mut args = self.ssh.ssh_args();
        args.push(
            parts
                .iter()
                .map(|part| shell_quote(part))
                .collect::<Vec<_>>()
                .join(" "),
        );
        args
    }

    fn python_args(&self, snippet: &str, target: &str) -> Vec<String> {
        self.remote_command_args(&[
            "python3".to_owned(),
            "-c".to_owned(),
            snippet.to_owned(),
            target.to_owned(),
        ])
    }
}

impl RemoteFs for SshFs {
    fn read_text(&self, path: &str) -> Result<Option<String>> {
        let args = self.python_args(
            "import pathlib,sys\np=pathlib.Path(sys.argv[1])\nif not p.exists():\n    raise SystemExit(1)\nprint(p.read_text(encoding='utf-8'), end='')",
            path,
        );
        let output = run_command("ssh", &args, None, &BTreeMap::new(), None)?;
        match output.status.code() {
            Some(0) => Ok(Some(String::from_utf8_lossy(&output.stdout).into_owned())),
            Some(1) => Ok(None),
            _ => bail!(
                "failed to read remote file: {path}\nstderr:\n{}",
                String::from_utf8_lossy(&output.stderr)
            ),
        }
    }

    fn write_text(&self, path: &str, content: &str) -> Result<()> {
        let args = self.remote_command_args(&[
            "python3".to_owned(),
            "-c".to_owned(),
            "import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True, exist_ok=True); tmp=p.with_suffix(p.suffix + '.tmp'); tmp.write_text(sys.stdin.read(), encoding='utf-8'); tmp.replace(p)".to_owned(),
            path.to_owned(),
        ]);
        check_command("ssh", &args, None, &BTreeMap::new(), Some(content))?;
        Ok(())
    }

    fn ensure_dir(&self, path: &str) -> Result<()> {
        let args = self.python_args(
            "import pathlib,sys; pathlib.Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)",
            path,
        );
        check_command("ssh", &args, None, &BTreeMap::new(), None)?;
        Ok(())
    }

    fn checksum(&self, path: &str) -> Result<String> {
        let args = self.python_args(
            "import hashlib,pathlib,sys\np=pathlib.Path(sys.argv[1])\nh=hashlib.sha256()\nwith p.open('rb') as handle:\n    for chunk in iter(lambda: handle.read(1048576), b''):\n        h.update(chunk)\nprint(h.hexdigest())",
            path,
        );
        let output = check_command("ssh", &args, None, &BTreeMap::new(), None)?;
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
    }

    fn list_json_stems(&self, dir: &str) -> Result<Vec<String>> {
        let args = self.python_args(
            "import json,pathlib,sys; root=pathlib.Path(sys.argv[1]); items=[] if not root.exists() else sorted(p.stem for p in root.glob('*.json') if p.is_file()); print(json.dumps(items))",
            dir,
        );
        let output = check_command("ssh", &args, None, &BTreeMap::new(), None)?;
        let items = serde_json::from_slice::<Vec<String>>(&output.stdout)
            .context("remote checkpoint listing was not a JSON array")?;
        Ok(items)
    }

    fn rsync_target(&self, path: &str) -> String {
        format!("{}@{}:{path}", self.ssh.user, self.ssh.host)
    }

    fn rsync_transport_args(&self) -> Vec<String> {
        vec!["-e".to_owned(), format!("ssh -p {}", self.ssh.port)]
    }

    fn copy_to_local(&self, source: &str, local_target: &Utf8Path) -> Result<()> {
        let mut args = vec!["-a".to_owned(), "--delete".to_owned()];
        args.extend(self.rsync_transport_args());
        args.push(self.rsync_target(source));
        args.push(local_target.to_string());
        check_command("rsync", &args, None, &BTreeMap::new(), None)?;
        Ok(())
    }

    fn copy_remote_file(&self, source: &str, target: &str) -> Result<()> {
        let args = self.remote_command_args(&[
            "python3".to_owned(),
            "-c".to_owned(),
            "import os,pathlib,shutil,sys\nsrc=pathlib.Path(sys.argv[1])\ndst=pathlib.Path(sys.argv[2])\ndst.parent.mkdir(parents=True, exist_ok=True)\ntry:\n    os.link(src, dst)\nexcept OSError:\n    shutil.copy2(src, dst)".to_owned(),
            source.to_owned(),
            target.to_owned(),
        ]);
        check_command("ssh", &args, None, &BTreeMap::new(), None)?;
        Ok(())
    }

    fn cas_write_text(
        &self,
        path: &str,
        content: &str,
        expected_snapshot_id: Option<&str>,
    ) -> Result<()> {
        let args = self.remote_command_args(&[
            "python3".to_owned(),
            "-c".to_owned(),
            "import json,pathlib,sys\npath=pathlib.Path(sys.argv[1])\nexpected=sys.argv[2]\nraw=sys.stdin.read()\ncurrent_snapshot=None\nif path.exists():\n    current=json.loads(path.read_text(encoding='utf-8'))\n    current_snapshot=current.get('snapshot_id')\nexpected_snapshot=None if expected == '__NONE__' else expected\nif current_snapshot != expected_snapshot:\n    raise SystemExit(17)\npath.parent.mkdir(parents=True, exist_ok=True)\ntmp=path.with_suffix(path.suffix + '.tmp')\ntmp.write_text(raw, encoding='utf-8')\ntmp.replace(path)".to_owned(),
            path.to_owned(),
            expected_snapshot_id.unwrap_or("__NONE__").to_owned(),
        ]);
        let output = run_command("ssh", &args, None, &BTreeMap::new(), Some(content))?;
        match output.status.code() {
            Some(0) => Ok(()),
            Some(17) => bail!(
                "remote current changed during promote: expected={:?}",
                expected_snapshot_id
            ),
            _ => bail!(
                "failed to update current snapshot: {path}\nstderr:\n{}",
                String::from_utf8_lossy(&output.stderr)
            ),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::shell_quote;

    #[test]
    fn shell_quote_preserves_remote_argument_boundaries() {
        assert_eq!(shell_quote(""), "''");
        assert_eq!(shell_quote("plain"), "'plain'");
        assert_eq!(
            shell_quote("root.glob('*.json')"),
            "'root.glob('\"'\"'*.json'\"'\"')'"
        );
    }
}

fn fs_for(machine: &MachineConfig) -> Box<dyn RemoteFs> {
    match &machine.ssh {
        None => Box::new(LocalFs),
        Some(ssh) => Box::new(SshFs { ssh: ssh.clone() }),
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct CheckpointResult {
    pub(crate) surface: String,
    pub(crate) checkpoint_id: Option<String>,
    pub(crate) changed_roots: Vec<String>,
}

#[derive(Debug, Serialize)]
struct CheckpointPayload {
    schema_version: u8,
    checkpoint_id: String,
    project: String,
    surface: String,
    machine_id: String,
    created_at: String,
    commit: String,
    changed_roots: Vec<String>,
}

#[derive(Debug, Serialize)]
struct RefreshResult {
    surface: String,
    status: String,
}

#[derive(Debug, Serialize)]
pub(crate) struct PromoteResult {
    pub(crate) surface: String,
    pub(crate) snapshot_id: String,
    pub(crate) changed: bool,
}

#[derive(Debug, Serialize)]
pub(crate) struct SurfaceSyncResult {
    pub(crate) surface: String,
    pub(crate) checkpoint_id: Option<String>,
    pub(crate) changed_roots: Vec<String>,
    pub(crate) promoted_snapshot_id: Option<String>,
    pub(crate) promoted: bool,
}

#[derive(Debug, Serialize)]
struct PullResult {
    surface: String,
    snapshot_id: String,
}

#[derive(Debug, Serialize)]
struct StatusPayload {
    surface: String,
    latest_checkpoint_id: Option<String>,
    current_snapshot_id: Option<String>,
    state: String,
    included_raw_checkpoint_ids: Vec<String>,
}

#[derive(Debug, Serialize)]
struct SurfaceListItem {
    name: String,
    project: String,
    kind: String,
    default: bool,
    raw_roots: usize,
    db_path: Option<String>,
}

#[derive(Debug, Serialize)]
struct SnapshotPayload {
    schema_version: u8,
    surface: String,
    snapshot_id: String,
    created_at: String,
    project: String,
    source_machine: String,
    source_commit: String,
    based_on_snapshot_id: Option<String>,
    db_filename: String,
    db_sha256: String,
    db_bytes: u64,
    included_raw_checkpoint_ids: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct CurrentSnapshot {
    snapshot_id: Option<String>,
    db_sha256: Option<String>,
    included_raw_checkpoint_ids: Option<Vec<String>>,
}

fn tmp_path(path: &Utf8Path) -> Utf8PathBuf {
    path.with_extension(format!(
        "{}tmp",
        path.extension()
            .map_or(String::new(), |ext| format!("{ext}."))
    ))
}

fn atomic_write_bytes(path: &Utf8Path, content: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    let tmp = tmp_path(path);
    fs::write(&tmp, content).with_context(|| format!("failed to write {tmp}"))?;
    fs::rename(&tmp, path).with_context(|| format!("failed to rename {tmp} to {path}"))?;
    Ok(())
}

fn utc_stamp() -> String {
    Utc::now().format("%Y%m%dT%H%M%S%6fZ").to_string()
}

fn iso_now() -> String {
    Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

pub(crate) fn join_command(parts: &[String]) -> String {
    parts.join(" ")
}

pub(crate) fn run_command(
    program: &str,
    args: &[String],
    cwd: Option<&Utf8Path>,
    envs: &BTreeMap<String, String>,
    stdin: Option<&str>,
) -> Result<Output> {
    let mut command = Command::new(program);
    command.args(args);
    if let Some(dir) = cwd {
        command.current_dir(dir);
    }
    if !envs.is_empty() {
        command.envs(envs);
    }
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    if stdin.is_some() {
        command.stdin(Stdio::piped());
    }
    let mut child = command
        .spawn()
        .with_context(|| format!("failed to spawn {program} {}", join_command(args)))?;
    if let Some(content) = stdin {
        let mut handle = child.stdin.take().context("failed to open child stdin")?;
        handle
            .write_all(content.as_bytes())
            .context("failed to write child stdin")?;
    }
    child
        .wait_with_output()
        .with_context(|| format!("failed to wait for {program} {}", join_command(args)))
}

pub(crate) fn check_command(
    program: &str,
    args: &[String],
    cwd: Option<&Utf8Path>,
    envs: &BTreeMap<String, String>,
    stdin: Option<&str>,
) -> Result<Output> {
    let output = run_command(program, args, cwd, envs, stdin)?;
    if !output.status.success() {
        bail!(
            "command failed ({} {})\nstdout:\n{}\nstderr:\n{}",
            program,
            join_command(args),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }
    Ok(output)
}

fn sha256_file(path: &Utf8Path) -> Result<String> {
    let mut digest = Sha256::new();
    let mut file = fs::File::open(path).with_context(|| format!("failed to read {path}"))?;
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let n = file
            .read(&mut buffer)
            .with_context(|| format!("failed to read {path}"))?;
        if n == 0 {
            break;
        }
        digest.update(&buffer[..n]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn load_manifest() -> Result<ProjectManifest> {
    discover_manifest(None)
}

fn resolve_machine() -> Result<MachineConfig> {
    load_machine_config()
}

fn surface_map(manifest: &ProjectManifest) -> Result<&BTreeMap<String, SurfaceConfig>> {
    manifest
        .spctr
        .as_ref()
        .filter(|spctr| !spctr.surfaces.is_empty())
        .map(|spctr| &spctr.surfaces)
        .ok_or_else(|| anyhow::anyhow!("{}: no spctr surfaces configured", manifest.path))
}

fn selected_surfaces(
    manifest: &ProjectManifest,
    machine: &MachineConfig,
    surface_name: &str,
) -> Result<Vec<ResolvedSurface>> {
    let surfaces = surface_map(manifest)?;
    if surface_name == "all" {
        let mut resolved = surfaces
            .values()
            .map(|surface| resolve_surface(manifest, surface, machine))
            .collect::<Result<Vec<_>>>()?;
        resolved.sort_by(|left, right| left.surface_name.cmp(&right.surface_name));
        return Ok(resolved);
    }
    let surface = surfaces
        .get(surface_name)
        .ok_or_else(|| anyhow::anyhow!("unknown surface: {surface_name}"))?;
    Ok(vec![resolve_surface(manifest, surface, machine)?])
}

pub fn list(json: bool) -> Result<()> {
    let repo_root = match repo_root() {
        Ok(root) => root,
        Err(_) => {
            let manifest = discover_manifest(None)?;
            manifest
                .root
                .parent()
                .and_then(Utf8Path::parent)
                .context("manifest is not under dossiers/ or addenda/")?
                .to_owned()
        }
    };
    let mut items = Vec::new();
    for manifest in discover_surfaced_manifests(&repo_root)? {
        let Some(spctr) = &manifest.spctr else {
            continue;
        };
        for (name, surface) in &spctr.surfaces {
            items.push(SurfaceListItem {
                name: name.clone(),
                project: spctr.project.clone(),
                kind: surface.kind.clone(),
                default: spctr.default_surface.as_deref() == Some(name.as_str()),
                raw_roots: surface.raw_roots.len(),
                db_path: surface.local_db_path.clone(),
            });
        }
    }
    items.sort_by(|left, right| {
        left.project
            .cmp(&right.project)
            .then_with(|| left.name.cmp(&right.name))
    });
    if json {
        println!("{}", serde_json::to_string_pretty(&items)?);
        return Ok(());
    }
    for item in items {
        let default = if item.default { " default" } else { "" };
        let db = item.db_path.as_deref().unwrap_or("-");
        println!(
            "{}\tproject={}\tkind={}\traw_roots={}\tdb={}{}",
            item.name, item.project, item.kind, item.raw_roots, db, default
        );
    }
    Ok(())
}

pub(crate) fn env_for_machine(machine: &MachineConfig) -> BTreeMap<String, String> {
    let mut envs = BTreeMap::new();
    envs.insert(
        "SPECTER_LOG_ROOT".to_owned(),
        machine
            .local_log_root
            .as_ref()
            .unwrap_or(&machine.durable_log_root)
            .clone(),
    );
    if let Some(local_log_root) = &machine.local_log_root {
        envs.insert("SPCTR_LOCAL_LOG_ROOT".to_owned(), local_log_root.clone());
    }
    envs.insert(
        "SPECTER_ARTIFACT_ROOT".to_owned(),
        machine
            .local_artifact_root
            .as_ref()
            .unwrap_or(&machine.durable_artifact_root)
            .clone(),
    );
    if let Some(local_artifact_root) = &machine.local_artifact_root {
        envs.insert(
            "SPCTR_LOCAL_ARTIFACT_ROOT".to_owned(),
            local_artifact_root.clone(),
        );
    }
    if let Some(runtime_root) = &machine.runtime_root {
        envs.insert("SPECTER_RUNTIME_ROOT".to_owned(), runtime_root.clone());
    }
    if let Some(ssh) = &machine.ssh {
        envs.insert(
            "SPECTER_REMOTE_SSH".to_owned(),
            format!("{}@{}:{}", ssh.user, ssh.host, ssh.port),
        );
    }
    envs
}

fn remote_join(base: &str, suffix: &str) -> String {
    let trimmed = base.trim_end_matches('/');
    if suffix.is_empty() {
        trimmed.to_owned()
    } else {
        format!("{trimmed}/{suffix}")
    }
}

fn remote_surface_root(machine: &MachineConfig, surface: &ResolvedSurface) -> String {
    remote_join(
        &machine.hot_snapshot_root,
        &format!(
            "{}/surfaces/{}",
            surface.project_name, surface.remote_snapshot_namespace
        ),
    )
}

fn remote_checkpoints_root(machine: &MachineConfig, surface: &ResolvedSurface) -> String {
    remote_join(&remote_surface_root(machine, surface), "raw-checkpoints")
}

fn remote_history_root(machine: &MachineConfig, surface: &ResolvedSurface) -> String {
    remote_join(&remote_surface_root(machine, surface), "history")
}

fn remote_current_path(machine: &MachineConfig, surface: &ResolvedSurface) -> String {
    remote_join(&remote_surface_root(machine, surface), "current.json")
}

fn remote_durable_target(
    machine: &MachineConfig,
    surface: &ResolvedSurface,
    raw_root: &RawRoot,
) -> String {
    let base = match raw_root.remote_base {
        RemoteBase::Logs => remote_join(
            &machine.durable_log_root,
            &format!("{}/logs", surface.remote_raw_namespace),
        ),
        RemoteBase::Artifacts => remote_join(
            &machine.durable_artifact_root,
            &format!("{}/artifacts", surface.remote_raw_namespace),
        ),
    };
    remote_join(&base, &raw_root.remote_relpath)
}

fn is_rsync_change_line(line: &str) -> bool {
    let trimmed = line.trim();
    if trimmed.is_empty()
        || trimmed == "./"
        || trimmed.starts_with("sending incremental file list")
        || trimmed.starts_with("sent ")
        || trimmed.starts_with("total size is ")
        || trimmed.starts_with("created directory ")
    {
        return false;
    }
    !trimmed.starts_with(".d")
}

fn resumable_file_rsync_args(fs: &dyn RemoteFs) -> Vec<String> {
    let mut args = vec![
        "-a".to_owned(),
        "--partial".to_owned(),
        "--append".to_owned(),
        "--inplace".to_owned(),
    ];
    args.extend(fs.rsync_transport_args());
    args
}

fn rsync_args(fs: &dyn RemoteFs, raw_root: &RawRoot, dry_run: bool) -> Vec<String> {
    let mut args = vec!["-a".to_owned()];
    if raw_root.sync_mode == "upsert" {
        args.push("--ignore-existing".to_owned());
        args.push("--omit-dir-times".to_owned());
        args.push("--no-perms".to_owned());
        args.push("--chmod=Du=rwx,Dg=rwx,Do=rx,Fu=rw,Fg=rw,Fo=r".to_owned());
    } else {
        args.push("--delete".to_owned());
    }
    if dry_run {
        args.push("--dry-run".to_owned());
        args.push("--itemize-changes".to_owned());
    }
    args.extend(fs.rsync_transport_args());
    for pattern in &raw_root.excludes {
        args.push("--exclude".to_owned());
        args.push(pattern.clone());
    }
    args
}

fn sync_check(fs: &dyn RemoteFs, raw_root: &RawRoot, target: &str) -> Result<bool> {
    fs.ensure_dir(target)?;
    let mut args = rsync_args(fs, raw_root, true);
    args.push(format!("{}/", raw_root.local_path.as_str()));
    args.push(format!("{}/", fs.rsync_target(target)));
    let output = run_command("rsync", &args, None, &BTreeMap::new(), None)?;
    let code = output.status.code().unwrap_or(-1);
    if code != 0 && code != 23 {
        bail!(
            "rsync dry-run failed\nstdout:\n{}\nstderr:\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    Ok(stdout.lines().any(is_rsync_change_line))
}

fn sync_root(fs: &dyn RemoteFs, raw_root: &RawRoot, target: &str) -> Result<()> {
    fs.ensure_dir(target)?;
    let mut args = rsync_args(fs, raw_root, false);
    args.push(format!("{}/", raw_root.local_path.as_str()));
    args.push(format!("{}/", fs.rsync_target(target)));
    check_command("rsync", &args, None, &BTreeMap::new(), None)?;
    Ok(())
}

fn copy_local_to_remote(fs: &dyn RemoteFs, source: &Utf8Path, target: &str) -> Result<()> {
    let parent = target
        .rsplit_once('/')
        .map_or_else(|| ".".to_owned(), |(base, _)| base.to_owned());
    fs.ensure_dir(&parent)?;
    let mut args = resumable_file_rsync_args(fs);
    args.push(source.to_string());
    args.push(fs.rsync_target(target));
    check_command("rsync", &args, None, &BTreeMap::new(), None)?;
    Ok(())
}

fn copy_remote_to_local(fs: &dyn RemoteFs, source: &str, target: &Utf8Path) -> Result<()> {
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).with_context(|| format!("failed to create {parent}"))?;
    }
    let tmp = tmp_path(target);
    fs.copy_to_local(source, &tmp)?;
    std::fs::rename(tmp.as_std_path(), target.as_std_path())
        .with_context(|| format!("failed to rename {tmp} to {target}"))?;
    Ok(())
}

fn git_commit(project_root: &Utf8Path) -> String {
    let output = run_command(
        "git",
        &["rev-parse".to_owned(), "HEAD".to_owned()],
        Some(project_root),
        &BTreeMap::new(),
        None,
    );
    match output {
        Ok(output) if output.status.success() => {
            String::from_utf8_lossy(&output.stdout).trim().to_owned()
        }
        _ => "unknown".to_owned(),
    }
}

fn status_payload(
    fs: &dyn RemoteFs,
    machine: &MachineConfig,
    surface: &ResolvedSurface,
) -> Result<StatusPayload> {
    let root = remote_checkpoints_root(machine, surface);
    let checkpoints = fs.list_json_stems(&root)?;
    let current: Option<CurrentSnapshot> = read_json(fs, &remote_current_path(machine, surface))?;
    let latest_checkpoint = checkpoints.last().cloned();
    let current_snapshot = current.as_ref().and_then(|c| c.snapshot_id.clone());
    let included = current
        .as_ref()
        .and_then(|c| c.included_raw_checkpoint_ids.clone())
        .unwrap_or_default();
    let state = if current.is_none() {
        "missing_snapshot"
    } else if latest_checkpoint
        .as_ref()
        .is_some_and(|checkpoint| !included.iter().any(|item| item == checkpoint))
    {
        "dirty"
    } else {
        "clean"
    };
    Ok(StatusPayload {
        surface: surface.surface_name.clone(),
        latest_checkpoint_id: latest_checkpoint,
        current_snapshot_id: current_snapshot,
        state: state.to_owned(),
        included_raw_checkpoint_ids: included,
    })
}

pub(crate) fn checkpoint_surface(
    machine: &MachineConfig,
    manifest: &ProjectManifest,
    resolved: &ResolvedSurface,
) -> Result<CheckpointResult> {
    let fs = fs_for(machine);
    let mut changed_roots = Vec::new();
    for raw_root in &resolved.raw_roots {
        if !raw_root.local_path.exists() {
            continue;
        }
        let remote_target = remote_durable_target(machine, resolved, raw_root);
        if !sync_check(&*fs, raw_root, &remote_target)? {
            continue;
        }
        sync_root(&*fs, raw_root, &remote_target)?;
        changed_roots.push(raw_root.local_path.to_string());
    }
    if changed_roots.is_empty() {
        return Ok(CheckpointResult {
            surface: resolved.surface_name.clone(),
            checkpoint_id: None,
            changed_roots: Vec::new(),
        });
    }
    let checkpoint_id = format!("{}-{}", utc_stamp(), machine.machine_id);
    let payload = CheckpointPayload {
        schema_version: 1,
        checkpoint_id: checkpoint_id.clone(),
        project: resolved.project_name.clone(),
        surface: resolved.surface_name.clone(),
        machine_id: machine.machine_id.clone(),
        created_at: iso_now(),
        commit: git_commit(&manifest.root),
        changed_roots: changed_roots.clone(),
    };
    let checkpoint_path = remote_join(
        &remote_checkpoints_root(machine, resolved),
        &format!("{checkpoint_id}.json"),
    );
    write_json(&*fs, &checkpoint_path, &payload)?;
    Ok(CheckpointResult {
        surface: resolved.surface_name.clone(),
        checkpoint_id: Some(checkpoint_id),
        changed_roots,
    })
}

pub fn checkpoint(surface: &str, json: bool) -> Result<()> {
    let manifest = load_manifest()?;
    let machine = resolve_machine()?;
    let mut results: Vec<CheckpointResult> = Vec::new();
    for resolved in selected_surfaces(&manifest, &machine, surface)? {
        let result = checkpoint_surface(&machine, &manifest, &resolved)?;
        if !json {
            match &result.checkpoint_id {
                Some(id) => println!("{}: checkpoint={id}", result.surface),
                None => println!("{}: checkpoint=no-op", result.surface),
            }
        }
        results.push(result);
    }
    if json {
        println!("{}", serde_json::to_string_pretty(&results)?);
    }
    Ok(())
}

pub fn status(surface: &str, json: bool) -> Result<()> {
    let manifest = load_manifest()?;
    let machine = resolve_machine()?;
    let fs = fs_for(&machine);
    let mut payloads: Vec<StatusPayload> = Vec::new();
    for resolved in selected_surfaces(&manifest, &machine, surface)? {
        let payload = status_payload(&*fs, &machine, &resolved)?;
        if !json {
            println!("surface={}", payload.surface);
            println!("state={}", payload.state);
            println!(
                "latest_checkpoint_id={}",
                payload.latest_checkpoint_id.as_deref().unwrap_or("-")
            );
            println!(
                "current_snapshot_id={}",
                payload.current_snapshot_id.as_deref().unwrap_or("-")
            );
        }
        payloads.push(payload);
    }
    if json {
        println!("{}", serde_json::to_string_pretty(&payloads)?);
    }
    Ok(())
}

pub fn refresh(surface: &str, json: bool) -> Result<()> {
    let manifest = load_manifest()?;
    let machine = resolve_machine()?;
    let resolved = selected_surfaces(&manifest, &machine, surface)?
        .into_iter()
        .next()
        .context("missing resolved surface")?;
    if resolved.refresh_commands.is_empty() {
        bail!("{surface} has no refresh command");
    }
    let envs = env_for_machine(&machine);
    for command in &resolved.refresh_commands {
        let program = command
            .first()
            .context("refresh command must include a program")?;
        check_command(program, &command[1..], Some(&manifest.root), &envs, None)?;
    }
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&RefreshResult {
                surface: resolved.surface_name.clone(),
                status: "ok".to_owned(),
            })?
        );
    } else {
        println!("{}: refresh=ok", resolved.surface_name);
    }
    Ok(())
}

pub(crate) fn promote_resolved_surface(
    machine: &MachineConfig,
    manifest: &ProjectManifest,
    resolved: &ResolvedSurface,
) -> Result<PromoteResult> {
    let fs = fs_for(machine);
    let db_path = resolved.db_path.as_ref().context(format!(
        "{} does not define a database surface",
        resolved.surface_name
    ))?;
    let db_filename = resolved.db_filename.as_ref().context(format!(
        "{} does not define a database surface",
        resolved.surface_name
    ))?;
    if !db_path.exists() {
        bail!("local DB not found: {db_path}");
    }
    let current: Option<CurrentSnapshot> =
        read_json(&*fs, &remote_current_path(machine, resolved))?;
    let expected_current = current.as_ref().and_then(|c| c.snapshot_id.clone());
    let local_sha = sha256_file(db_path)?;
    let checkpoints_root = remote_checkpoints_root(machine, resolved);
    let included = fs.list_json_stems(&checkpoints_root)?;
    if current.as_ref().is_some_and(|snapshot| {
        snapshot.db_sha256.as_deref() == Some(local_sha.as_str())
            && snapshot
                .included_raw_checkpoint_ids
                .as_ref()
                .is_some_and(|current_included| current_included == &included)
    }) {
        return Ok(PromoteResult {
            surface: resolved.surface_name.clone(),
            snapshot_id: expected_current.unwrap_or_default(),
            changed: false,
        });
    }
    let snapshot_id = format!("{}-{}", utc_stamp(), &local_sha[..12]);
    let remote_snapshot_root = remote_join(&remote_history_root(machine, resolved), &snapshot_id);
    let remote_db_path = remote_join(&remote_snapshot_root, db_filename);
    let remote_upload_path = remote_join(
        &remote_history_root(machine, resolved),
        &format!("_uploads/{}/{}", &local_sha[..12], db_filename),
    );
    copy_local_to_remote(&*fs, db_path, &remote_upload_path)?;
    let remote_sha = fs.checksum(&remote_upload_path)?;
    if remote_sha != local_sha {
        bail!(
            "remote checksum mismatch for {}: local={} remote={}",
            resolved.surface_name,
            local_sha,
            remote_sha
        );
    }
    fs.copy_remote_file(&remote_upload_path, &remote_db_path)?;
    let payload = SnapshotPayload {
        schema_version: 1,
        surface: resolved.surface_name.clone(),
        snapshot_id: snapshot_id.clone(),
        created_at: iso_now(),
        project: resolved.project_name.clone(),
        source_machine: machine.machine_id.clone(),
        source_commit: git_commit(&manifest.root),
        based_on_snapshot_id: expected_current.clone(),
        db_filename: db_filename.clone(),
        db_sha256: local_sha,
        db_bytes: db_path
            .metadata()
            .with_context(|| format!("failed to stat {db_path}"))?
            .len(),
        included_raw_checkpoint_ids: included,
    };
    write_json(
        &*fs,
        &remote_join(&remote_snapshot_root, "snapshot.json"),
        &payload,
    )?;
    let encoded =
        serde_json::to_string_pretty(&payload).context("failed to encode current payload")? + "\n";
    fs.cas_write_text(
        &remote_current_path(machine, resolved),
        &encoded,
        expected_current.as_deref(),
    )?;
    Ok(PromoteResult {
        surface: resolved.surface_name.clone(),
        snapshot_id,
        changed: true,
    })
}

pub fn promote(surface: &str, json: bool) -> Result<()> {
    let manifest = load_manifest()?;
    let machine = resolve_machine()?;
    let resolved = selected_surfaces(&manifest, &machine, surface)?
        .into_iter()
        .next()
        .context("missing resolved surface")?;
    let result = promote_resolved_surface(&machine, &manifest, &resolved)?;
    if json {
        println!("{}", serde_json::to_string_pretty(&result)?);
    } else if result.changed {
        println!("{}: promoted={}", result.surface, result.snapshot_id);
    } else {
        println!("{}: promote=no-op", result.surface);
    }
    Ok(())
}

pub(crate) fn sync_resolved_surface(
    machine: &MachineConfig,
    manifest: &ProjectManifest,
    resolved: &ResolvedSurface,
) -> Result<SurfaceSyncResult> {
    if let Some(path) = &resolved.db_path {
        if !path.exists() {
            bail!("local DB not found: {path}");
        }
    }
    let checkpoint = checkpoint_surface(machine, manifest, resolved)?;
    let promotion = match &resolved.db_path {
        Some(_) => Some(promote_resolved_surface(machine, manifest, resolved)?),
        _ => None,
    };
    Ok(SurfaceSyncResult {
        surface: resolved.surface_name.clone(),
        checkpoint_id: checkpoint.checkpoint_id,
        changed_roots: checkpoint.changed_roots,
        promoted_snapshot_id: promotion.as_ref().map(|result| result.snapshot_id.clone()),
        promoted: promotion.as_ref().is_some_and(|result| result.changed),
    })
}

pub fn sync(surface: &str, json: bool) -> Result<()> {
    let manifest = load_manifest()?;
    let machine = resolve_machine()?;
    let mut results = Vec::new();
    for resolved in selected_surfaces(&manifest, &machine, surface)? {
        let result = sync_resolved_surface(&machine, &manifest, &resolved)?;
        if !json {
            let checkpoint = result.checkpoint_id.as_deref().unwrap_or("no-op");
            let promoted = match (&result.promoted_snapshot_id, result.promoted) {
                (Some(id), true) => id.as_str(),
                (Some(_), false) => "no-op",
                (None, _) => "-",
            };
            println!(
                "{}: checkpoint={} promoted={}",
                result.surface, checkpoint, promoted
            );
        }
        results.push(result);
    }
    if json {
        println!("{}", serde_json::to_string_pretty(&results)?);
    }
    Ok(())
}

pub fn pull(surface: &str, json: bool) -> Result<()> {
    let manifest = load_manifest()?;
    let machine = resolve_machine()?;
    let fs = fs_for(&machine);
    let resolved = selected_surfaces(&manifest, &machine, surface)?
        .into_iter()
        .next()
        .context("missing resolved surface")?;
    let db_path = resolved
        .db_path
        .as_ref()
        .context(format!("{surface} does not define a database surface"))?;
    let db_filename = resolved
        .db_filename
        .as_ref()
        .context(format!("{surface} does not define a database surface"))?;
    let current: CurrentSnapshot = read_json(&*fs, &remote_current_path(&machine, &resolved))?
        .ok_or_else(|| anyhow::anyhow!("no current snapshot for {}", resolved.surface_name))?;
    let snapshot_id = current
        .snapshot_id
        .as_deref()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            anyhow::anyhow!(
                "remote current snapshot is invalid for {}",
                resolved.surface_name
            )
        })?;
    let remote_db_path = remote_join(
        &remote_join(&remote_history_root(&machine, &resolved), snapshot_id),
        db_filename,
    );
    copy_remote_to_local(&*fs, &remote_db_path, db_path)?;
    let local_sha = sha256_file(db_path)?;
    let expected_sha = current.db_sha256.as_deref().unwrap_or_default();
    if local_sha != expected_sha {
        bail!(
            "pulled DB checksum mismatch for {}: local={} expected={}",
            resolved.surface_name,
            local_sha,
            expected_sha
        );
    }
    if json {
        println!(
            "{}",
            serde_json::to_string_pretty(&PullResult {
                surface: resolved.surface_name.clone(),
                snapshot_id: snapshot_id.to_owned(),
            })?
        );
    } else {
        println!("{}: pulled={snapshot_id}", resolved.surface_name);
    }
    Ok(())
}
