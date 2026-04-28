use camino::Utf8Path;
use spctr::exec::build_plan;
use spctr::manifest::load_project_manifest;
use std::fs;
use tempfile::TempDir;

fn write(path: &Utf8Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

fn manifest(extra: &str) -> String {
    format!(
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = true
featured = false
{extra}
[release]
stage = "candidate"
"#
    )
}

#[test]
fn exec_plan_resolves_runtime_and_expected_outputs() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        &format!(
            "{}{}",
            manifest(""),
            r#"
[[release.surfaces]]
name = "python"
kind = "package"
publish = false
language = "python"
registry = "pypi"
publish_mode = "subdir"

[spctr]
project = "alpha"

[spctr.exec.smoke]
command = ["uv", "run", "pytest", "-q"]
expected_outputs = ["smoke-report"]
timeout_sec = 30
requires = ["pytest"]

[spctr.runtime]
platforms = ["linux"]
requires = ["python"]
network = "bootstrap"
cache_paths = ["tmp/cache"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "smoke-report"
path = "artifacts/smoke/report.json"
kind = "status_json"
required = true
surface = "python"
"#,
        ),
    );

    let loaded = load_project_manifest(&manifest_path, None).unwrap();
    let plan = build_plan(root, &loaded, "smoke").unwrap();

    assert_eq!(plan.project, "alpha");
    assert_eq!(plan.project_root, "dossiers/alpha");
    assert_eq!(plan.workdir, "dossiers/alpha");
    assert_eq!(plan.network.as_deref(), Some("bootstrap"));
    assert_eq!(plan.requires, vec!["python", "pytest"]);
    assert_eq!(plan.commands, vec![vec!["uv", "run", "pytest", "-q"]]);
    assert_eq!(plan.expected_outputs.len(), 1);
    assert_eq!(plan.expected_outputs[0].name, "smoke-report");
    assert_eq!(plan.expected_outputs[0].surface.as_deref(), Some("python"));
    assert_eq!(
        plan.runtime.as_ref().unwrap().cache_paths,
        vec!["tmp/cache"]
    );
}

#[test]
fn exec_plan_prefers_action_workdir_and_network() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        &format!(
            "{}{}",
            manifest(""),
            r#"
[spctr]
project = "alpha"

[spctr.exec.check]
command = ["uv", "run", "ruff", "check", "."]
workdir = "tools"
network = "off"

[spctr.runtime]
platforms = ["linux"]
network = "bootstrap"
"#,
        ),
    );

    let loaded = load_project_manifest(&manifest_path, None).unwrap();
    let plan = build_plan(root, &loaded, "check").unwrap();

    assert_eq!(plan.workdir, "dossiers/alpha/tools");
    assert_eq!(plan.network.as_deref(), Some("off"));
}
