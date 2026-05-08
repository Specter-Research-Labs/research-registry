use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use tempfile::TempDir;

fn write(path: &Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

fn create_project(root: &Path) -> PathBuf {
    let project_root = root.join("dossiers/alpha");
    write(
        &project_root.join("spctr.toml"),
        "version = 1\n\
license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"\n\
title = \"Alpha\"\n\
summary = \"Alpha summary.\"\n\
status = \"active\"\n\n\
[site]\n\
visible = true\n\
featured = false\n\n\
[release]\n\
stage = \"candidate\"\n\n\
[spctr]\n\
project = \"alpha\"\n\
default_surface = \"demo\"\n\n\
[spctr.surfaces.demo]\n\
kind = \"raw_plus_db\"\n\
raw_roots = [\"logs\", \"outputs/raw\"]\n\
local_db_path = \"outputs/demo.sqlite\"\n\
refresh_command = [\"python3\", \"-c\", \"from pathlib import Path; Path('outputs/demo.sqlite').write_text('refreshed\\\\n', encoding='utf-8')\"]\n\
remote_raw_namespace = \"alpha\"\n\
remote_snapshot_namespace = \"demo\"\n",
    );
    write(&project_root.join("logs/run-a.log"), "alpha\n");
    write(
        &project_root.join("outputs/raw/result.json"),
        "{\"ok\": true}\n",
    );
    write(&project_root.join("outputs/demo.sqlite"), "db-v1\n");
    project_root
}

fn create_category_root_project(root: &Path) -> PathBuf {
    let project_root = root.join("dossiers/alpha");
    write(
        &project_root.join("spctr.toml"),
        "version = 1\n\
license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"\n\
title = \"Alpha\"\n\
summary = \"Alpha summary.\"\n\
status = \"active\"\n\n\
[site]\n\
visible = true\n\
featured = false\n\n\
[release]\n\
stage = \"candidate\"\n\n\
[spctr]\n\
project = \"alpha\"\n\
default_surface = \"demo\"\n\n\
[spctr.surfaces.demo]\n\
kind = \"raw_plus_db\"\n\
raw_roots = [\"logs\", \"artifacts\"]\n\
local_db_path = \"compendium.sqlite\"\n\
db_raw_root = 1\n\
remote_raw_namespace = \"alpha\"\n\
remote_snapshot_namespace = \"demo\"\n",
    );
    write(&project_root.join("logs/run.log"), "log\n");
    write(&project_root.join("artifacts/result.json"), "{}\n");
    write(&project_root.join("artifacts/compendium.sqlite"), "db\n");
    project_root
}

fn create_workspace_category_root_project(root: &Path) -> PathBuf {
    let workspace_project_root = root.join("research-registry-workspaces/ws/dossiers/alpha");
    write(
        &workspace_project_root.join("spctr.toml"),
        "version = 1\n\
license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"\n\
title = \"Alpha\"\n\
summary = \"Alpha summary.\"\n\
status = \"active\"\n\n\
[site]\n\
visible = true\n\
featured = false\n\n\
[release]\n\
stage = \"candidate\"\n\n\
[spctr]\n\
project = \"alpha\"\n\
default_surface = \"demo\"\n\n\
[spctr.surfaces.demo]\n\
kind = \"raw_plus_db\"\n\
raw_roots = [\"logs\", \"artifacts\"]\n\
local_db_path = \"compendium.sqlite\"\n\
db_raw_root = 1\n\
remote_raw_namespace = \"alpha\"\n\
remote_snapshot_namespace = \"demo\"\n",
    );
    let shared_project_root = root.join("research-registry/dossiers/alpha");
    write(&shared_project_root.join("logs/run.log"), "shared-log\n");
    write(&shared_project_root.join("artifacts/result.json"), "{}\n");
    write(
        &shared_project_root.join("artifacts/compendium.sqlite"),
        "shared-db\n",
    );
    workspace_project_root
}

fn create_config(root: &Path) -> PathBuf {
    let config_path = root.join("config/spctr.toml");
    write(
        &config_path,
        &format!(
            "machine_id = \"tester\"\n\
hot_snapshot_root = \"{}\"\n\
durable_log_root = \"{}\"\n\
durable_artifact_root = \"{}\"\n",
            root.join("remote/hot").display(),
            root.join("remote/durable-logs").display(),
            root.join("remote/durable-artifacts").display(),
        ),
    );
    config_path
}

fn create_config_with_local_artifact_root(root: &Path, local_artifact_root: &Path) -> PathBuf {
    let config_path = create_config(root);
    fs::write(
        &config_path,
        fs::read_to_string(&config_path).unwrap()
            + &format!(
                "local_artifact_root = \"{}\"\n",
                local_artifact_root.display()
            ),
    )
    .unwrap();
    config_path
}

fn spctr(args: &[&str], project_root: &Path, config_path: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_spctr"))
        .args(args)
        .current_dir(project_root)
        .env("SPCTR_CONFIG", config_path)
        .env_remove("SPECTER_REMOTE_SSH")
        .env_remove("SPCTR_MACHINE_ID")
        .env_remove("SPCTR_LOCAL_LOG_ROOT")
        .env_remove("SPCTR_LOCAL_ARTIFACT_ROOT")
        .env_remove("SPECTER_LOG_ROOT")
        .env_remove("SPECTER_ARTIFACT_ROOT")
        .output()
        .unwrap()
}

fn spctr_with_path(args: &[&str], project_root: &Path, config_path: &Path, path: &str) -> Output {
    Command::new(env!("CARGO_BIN_EXE_spctr"))
        .args(args)
        .current_dir(project_root)
        .env("SPCTR_CONFIG", config_path)
        .env("PATH", path)
        .env_remove("SPECTER_REMOTE_SSH")
        .env_remove("SPCTR_MACHINE_ID")
        .env_remove("SPCTR_LOCAL_LOG_ROOT")
        .env_remove("SPCTR_LOCAL_ARTIFACT_ROOT")
        .env_remove("SPECTER_LOG_ROOT")
        .env_remove("SPECTER_ARTIFACT_ROOT")
        .output()
        .unwrap()
}

fn make_executable(path: &Path) {
    let mut permissions = fs::metadata(path).unwrap().permissions();
    permissions.set_mode(0o755);
    fs::set_permissions(path, permissions).unwrap();
}

fn output_text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned() + &String::from_utf8_lossy(&output.stderr)
}

#[test]
fn checkpoint_promote_pull_and_status_flow() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    let config_path = create_config(temp.path());

    let first = spctr(
        &["surface", "checkpoint", "demo"],
        &project_root,
        &config_path,
    );
    assert!(first.status.success(), "{}", output_text(&first));
    assert!(output_text(&first).contains("checkpoint="));

    let missing = spctr(&["surface", "status", "demo"], &project_root, &config_path);
    assert!(missing.status.success(), "{}", output_text(&missing));
    assert!(output_text(&missing).contains("state=missing_snapshot"));

    let promote = spctr(&["surface", "promote", "demo"], &project_root, &config_path);
    assert!(promote.status.success(), "{}", output_text(&promote));
    assert!(output_text(&promote).contains("promoted="));

    let clean = spctr(&["surface", "status", "demo"], &project_root, &config_path);
    assert!(clean.status.success(), "{}", output_text(&clean));
    assert!(output_text(&clean).contains("state=clean"));

    fs::remove_file(project_root.join("outputs/demo.sqlite")).unwrap();
    let pull = spctr(&["surface", "pull", "demo"], &project_root, &config_path);
    assert!(pull.status.success(), "{}", output_text(&pull));
    assert_eq!(
        fs::read_to_string(project_root.join("outputs/demo.sqlite")).unwrap(),
        "db-v1\n"
    );

    write(&project_root.join("logs/run-a.log"), "alpha-updated\n");
    let second = spctr(
        &["surface", "checkpoint", "demo"],
        &project_root,
        &config_path,
    );
    assert!(second.status.success(), "{}", output_text(&second));
    assert!(output_text(&second).contains("checkpoint="));

    let dirty = spctr(&["surface", "status", "demo"], &project_root, &config_path);
    assert!(dirty.status.success(), "{}", output_text(&dirty));
    assert!(output_text(&dirty).contains("state=dirty"));
}

#[test]
fn list_reports_manifest_surfaces() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    let config_path = create_config(temp.path());

    let output = spctr(&["surface", "list"], &project_root, &config_path);
    assert!(output.status.success(), "{}", output_text(&output));
    let text = output_text(&output);
    assert!(text.contains("demo\tproject=alpha\tkind=raw_plus_db"));
    assert!(text.contains("raw_roots=2"));
    assert!(text.contains("db=outputs/demo.sqlite"));
    assert!(text.contains(" default"));
}

#[test]
fn durable_command_is_not_available() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    let config_path = create_config(temp.path());

    let output = spctr(&["durable", "status", "demo"], &project_root, &config_path);
    assert!(!output.status.success(), "{}", output_text(&output));
    assert!(output_text(&output).contains("unrecognized subcommand"));
}

#[test]
fn checkpoint_noop_does_not_create_new_checkpoint() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    let config_path = create_config(temp.path());

    let first = spctr(
        &["surface", "checkpoint", "demo"],
        &project_root,
        &config_path,
    );
    assert!(first.status.success(), "{}", output_text(&first));

    let second = spctr(
        &["surface", "checkpoint", "demo"],
        &project_root,
        &config_path,
    );
    assert!(second.status.success(), "{}", output_text(&second));
    assert!(output_text(&second).contains("checkpoint=no-op"));
}

#[test]
fn category_root_raw_paths_do_not_repeat_remote_category() {
    let temp = TempDir::new().unwrap();
    let project_root = create_category_root_project(temp.path());
    let config_path = create_config(temp.path());

    let output = spctr(
        &["surface", "checkpoint", "demo"],
        &project_root,
        &config_path,
    );
    assert!(output.status.success(), "{}", output_text(&output));
    assert!(temp
        .path()
        .join("remote/durable-logs/alpha/logs/run.log")
        .exists());
    assert!(!temp
        .path()
        .join("remote/durable-logs/alpha/logs/logs/run.log")
        .exists());
    assert!(temp
        .path()
        .join("remote/durable-artifacts/alpha/artifacts/result.json")
        .exists());
    assert!(!temp
        .path()
        .join("remote/durable-artifacts/alpha/artifacts/artifacts/result.json")
        .exists());
}

#[test]
fn workspace_without_local_roots_uses_shared_main_checkout() {
    let temp = TempDir::new().unwrap();
    let project_root = create_workspace_category_root_project(temp.path());
    let config_path = create_config(temp.path());

    let output = spctr(&["surface", "sync", "demo"], &project_root, &config_path);
    assert!(output.status.success(), "{}", output_text(&output));
    assert_eq!(
        fs::read_to_string(temp.path().join("remote/durable-logs/alpha/logs/run.log")).unwrap(),
        "shared-log\n"
    );
    assert_eq!(
        fs::read_to_string(
            temp.path()
                .join("remote/durable-artifacts/alpha/artifacts/result.json")
        )
        .unwrap(),
        "{}\n"
    );
    let history_root = temp.path().join("remote/hot/alpha/surfaces/demo/history");
    let snapshot_dir = fs::read_dir(history_root)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    assert_eq!(
        fs::read_to_string(snapshot_dir.join("compendium.sqlite")).unwrap(),
        "shared-db\n"
    );
}

#[test]
fn sync_promotes_db_from_machine_local_artifact_root() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    let local_artifact_root = temp.path().join("local-artifacts");
    let local_project_root = local_artifact_root.join("alpha");
    write(
        &local_project_root.join("outputs/raw/result.json"),
        "{\"source\":\"local\"}\n",
    );
    write(
        &local_project_root.join("outputs/demo.sqlite"),
        "local-db\n",
    );
    let config_path = create_config_with_local_artifact_root(temp.path(), &local_artifact_root);

    let output = spctr(&["surface", "sync", "demo"], &project_root, &config_path);
    assert!(output.status.success(), "{}", output_text(&output));
    let text = output_text(&output);
    assert!(text.contains("checkpoint="));
    assert!(text.contains("promoted="));
    assert_eq!(
        fs::read_to_string(
            temp.path()
                .join("remote/durable-artifacts/alpha/artifacts/outputs/raw/result.json")
        )
        .unwrap(),
        "{\"source\":\"local\"}\n"
    );
    assert!(temp
        .path()
        .join("remote/hot/alpha/surfaces/demo/current.json")
        .exists());
    let history_root = temp.path().join("remote/hot/alpha/surfaces/demo/history");
    let snapshot_dir = fs::read_dir(history_root)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    assert_eq!(
        fs::read_to_string(snapshot_dir.join("demo.sqlite")).unwrap(),
        "local-db\n"
    );
}

#[test]
fn sync_fails_before_checkpoint_when_configured_db_is_missing() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    fs::remove_file(project_root.join("outputs/demo.sqlite")).unwrap();
    let config_path = create_config(temp.path());

    let output = spctr(&["surface", "sync", "demo"], &project_root, &config_path);
    assert!(!output.status.success(), "{}", output_text(&output));
    let text = output_text(&output);
    assert!(text.contains("local DB not found"), "{text}");
    assert!(!temp
        .path()
        .join("remote/durable-artifacts/alpha/artifacts/outputs/raw/result.json")
        .exists());
    assert!(!temp
        .path()
        .join("remote/hot/alpha/surfaces/demo/current.json")
        .exists());
}

#[test]
fn refresh_runs_configured_command() {
    let temp = TempDir::new().unwrap();
    let project_root = create_project(temp.path());
    let config_path = create_config(temp.path());
    write(&project_root.join("outputs/demo.sqlite"), "stale\n");

    let refresh = spctr(&["surface", "refresh", "demo"], &project_root, &config_path);
    assert!(refresh.status.success(), "{}", output_text(&refresh));
    assert_eq!(
        fs::read_to_string(project_root.join("outputs/demo.sqlite")).unwrap(),
        "refreshed\n"
    );
}

#[test]
fn site_data_refresh_uses_named_surface_not_project_default() {
    let temp = TempDir::new().unwrap();
    let init = Command::new("git")
        .arg("init")
        .current_dir(temp.path())
        .output()
        .unwrap();
    assert!(init.status.success(), "{}", output_text(&init));
    let project_root = temp.path().join("dossiers/alpha");
    write(
        &project_root.join("spctr.toml"),
        "version = 1\n\
license = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"\n\
title = \"Alpha\"\n\
summary = \"Alpha summary.\"\n\
status = \"active\"\n\n\
[site]\n\
visible = true\n\
featured = false\n\n\
[release]\n\
stage = \"candidate\"\n\n\
[spctr]\n\
project = \"alpha\"\n\
default_surface = \"demo\"\n\n\
[spctr.surfaces.demo]\n\
kind = \"raw_plus_db\"\n\
raw_roots = [\"logs\"]\n\
local_db_path = \"outputs/demo.sqlite\"\n\
refresh_command = [\"/bin/sh\", \"-c\", \"printf demo > outputs/refreshed.txt\"]\n\
remote_raw_namespace = \"alpha\"\n\
remote_snapshot_namespace = \"demo\"\n\n\
[spctr.surfaces.alt]\n\
kind = \"raw_plus_db\"\n\
raw_roots = [\"outputs/raw\"]\n\
local_db_path = \"outputs/alt.sqlite\"\n\
refresh_command = [\"/bin/sh\", \"-c\", \"printf alt > outputs/refreshed.txt\"]\n\
remote_raw_namespace = \"alpha\"\n\
remote_snapshot_namespace = \"alt\"\n",
    );
    write(&project_root.join("logs/run.log"), "demo\n");
    write(&project_root.join("outputs/raw/result.json"), "{}\n");
    let config_path = create_config(temp.path());

    let fake_bin = temp.path().join("bin");
    write(
        &fake_bin.join("uv"),
        "#!/bin/sh\n\
out=''\n\
while [ \"$#\" -gt 0 ]; do\n\
  if [ \"$1\" = '--out-dir' ]; then shift; out=\"$1\"; fi\n\
  shift\n\
done\n\
mkdir -p \"$out\"\n\
printf '{\"selected_runs\":0}\\n' > \"$out/manifest.json\"\n",
    );
    write(&fake_bin.join("python3"), "#!/bin/sh\nexit 0\n");
    make_executable(&fake_bin.join("uv"));
    make_executable(&fake_bin.join("python3"));
    let path = format!(
        "{}:{}",
        fake_bin.display(),
        std::env::var("PATH").unwrap_or_default()
    );

    let output = spctr_with_path(
        &[
            "surface",
            "refresh",
            "alt",
            "--site-data-root",
            temp.path().join("site-data").to_str().unwrap(),
        ],
        &project_root,
        &config_path,
        &path,
    );
    assert!(output.status.success(), "{}", output_text(&output));
    assert_eq!(
        fs::read_to_string(project_root.join("outputs/refreshed.txt")).unwrap(),
        "alt"
    );
}
