use camino::Utf8Path;
use spctr::ci::{github_plan, render_github_workflow, sync};
use std::fs;
use tempfile::TempDir;

fn write(path: &Utf8Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

fn minimal_design_tokens(root: &Utf8Path) {
    write(
        &root.join("addenda/design-tokens/base.toml"),
        r##"
[colors]
ink = "#0b0e14"

[badges.project-status]
dossier = ["concept", "active", "active-writing", "hold"]
addenda = ["concept", "active", "operational", "hold", "archived"]

[badges.project-status.concept]
color = "ink"

[badges.project-status.active]
color = "ink"

[badges.project-status.active-writing]
color = "ink"

[badges.project-status.hold]
color = "ink"

[badges.project-status.operational]
color = "ink"

[badges.project-status.archived]
color = "ink"

[badges.addenda-type]
values = ["tooling", "research", "dataset", "benchmark"]

[badges.addenda-type.tooling]
color = "ink"

[badges.addenda-type.research]
color = "ink"

[badges.addenda-type.dataset]
color = "ink"

[badges.addenda-type.benchmark]
color = "ink"
"##,
    );
    write(&root.join("addenda/design-tokens/web.toml"), "");
}

fn write_swift_ci_project(root: &Utf8Path, cache_paths: &str) {
    write(
        &root.join("dossiers/alpha/Package.swift"),
        "// swift-tools-version: 6.0\n",
    );
    write(&root.join("dossiers/alpha/Package.resolved"), "{}\n");
    write(
        &root.join("dossiers/alpha/spctr.toml"),
        &format!(
            r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["swift", "test"]

[spctr.runtime]
platforms = ["macos"]
requires = ["swift"]
cache_paths = {cache_paths}

[spctr.ci]
runner = "macos-latest"
pull_request = ["check"]
push_main = ["check"]
"#
        ),
    );
}

#[test]
fn github_workflow_plan_renders_manifest_exec_jobs() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &root.join("dossiers/alpha/pyproject.toml"),
        r#"[project]
name = "alpha"
version = "0.1.0"
requires-python = ">=3.12,<3.13"

[tool.ty.environment]
python-version = "3.12"
"#,
    );
    write(&root.join("dossiers/alpha/uv.lock"), "version = 1\n");
    write(
        &manifest_path,
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]
timeout_sec = 61
requires = ["python", "uv"]

[spctr.exec.smoke]
command = ["python3", "-c", "print('smoke')"]
timeout_sec = 361
requires = ["python", "uv", "ffmpeg"]

[spctr.ci]
runner = "macos-latest"
pull_request = ["check"]
push_main = ["check", "smoke"]
nightly = ["smoke"]
"#,
    );

    let plan = github_plan(root, Some("alpha")).unwrap();
    assert_eq!(plan.name, "alpha-ci");
    assert_eq!(plan.workflow_path, ".github/workflows/alpha-ci.yml");
    assert_eq!(plan.project_root, "dossiers/alpha");
    assert_eq!(plan.runner, "macos-latest");
    assert_eq!(plan.python_version.as_deref(), Some("3.12"));
    assert!(plan.includes_pull_request);
    assert!(plan.includes_push_main);
    assert!(plan.includes_nightly);
    assert!(plan.requires_nightly_schedule);
    assert_eq!(plan.path_filters, vec!["dossiers/alpha/**"]);

    let rendered = render_github_workflow(&plan);
    assert!(rendered.contains("name: alpha-ci"));
    assert!(rendered.contains("runs-on: macos-latest"));
    assert!(rendered.contains("timeout-minutes: 8"));
    assert!(rendered.contains("uses: ./.github/actions/setup-spctr"));
    assert!(rendered.contains("use-python: 'true'"));
    assert!(rendered.contains("python-version: '3.12'"));
    assert!(rendered.contains("use-uv: 'true'"));
    assert!(rendered.contains("sync-python: 'true'"));
    assert!(rendered.contains("Verify declared runtime requirements"));
    assert!(rendered.contains("./ops/spctr/target/release/spctr exec run --project alpha check"));
    assert!(rendered.contains("./ops/spctr/target/release/spctr exec run --project alpha smoke"));
    assert!(!rendered.contains("./ops/spctr/target/release/spctr release gate alpha"));
    assert!(rendered.contains("# schedule:"));
    assert!(rendered.contains("missing required runtime: ffmpeg"));
}

#[test]
fn github_workflow_caches_only_declared_swiftpm_dependency_state() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    write_swift_ci_project(
        root,
        r#"[".build", ".swiftpm", "tmp/xcode-build/DerivedData"]"#,
    );

    let plan = github_plan(root, Some("alpha")).unwrap();
    assert!(plan.cache_swiftpm_dependencies);

    let rendered = render_github_workflow(&plan);
    assert!(rendered.contains("uses: actions/cache@v5.0.5"));
    assert!(rendered.contains("dossiers/alpha/.build/artifacts"));
    assert!(rendered.contains("dossiers/alpha/.build/checkouts"));
    assert!(rendered.contains("dossiers/alpha/.build/repositories"));
    assert!(!rendered.contains("dossiers/alpha/.build/plugins"));
    assert!(!rendered.contains("dossiers/alpha/.build/workspace-state.json"));
    assert!(!rendered.contains("dossiers/alpha/.swiftpm"));
    assert!(!rendered.contains("dossiers/alpha/tmp/xcode-build/DerivedData"));
    assert!(rendered
        .contains("hashFiles('dossiers/alpha/Package.swift', 'dossiers/alpha/Package.resolved')"));
    let cache_prefix = "spctr-swiftpm-deps-v1-${{ runner.os }}-${{ runner.arch }}-alpha-${{ hashFiles('dossiers/alpha/Package.swift', 'dossiers/alpha/Package.resolved') }}";
    assert!(rendered.contains(&format!("{cache_prefix}-pull_request")));
    assert!(rendered.contains(&format!("{cache_prefix}-push_main")));
    assert!(rendered.contains(&format!("{cache_prefix}-\n")));

    let cache_step = rendered.find("Cache SwiftPM dependencies").unwrap();
    let check = rendered.find("Run exec check").unwrap();
    assert!(cache_step < check);
}

#[test]
fn github_workflow_requires_declared_build_cache_for_swiftpm_caching() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    write_swift_ci_project(root, r#"[".swiftpm"]"#);

    let plan = github_plan(root, Some("alpha")).unwrap();
    assert!(!plan.cache_swiftpm_dependencies);
    assert!(!render_github_workflow(&plan).contains("Cache SwiftPM dependencies"));
}

#[test]
fn github_workflow_runs_release_gate_for_promoted_exec_lanes() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "promoted"

[[release.surfaces]]
name = "source"
kind = "source_bundle"
publish = true
path = "."
include_docs = false

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.exec.smoke]
command = ["python3", "-c", "print('smoke')"]

[spctr.exec.build]
command = ["python3", "-c", "print('build')"]

[spctr.exec.publish]
command = ["python3", "-c", "print('publish')"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[spctr.ci]
push_main = ["check", "smoke", "build", "publish"]
"#,
    );

    let plan = github_plan(root, Some("alpha")).unwrap();
    let rendered = render_github_workflow(&plan);
    assert!(rendered.contains("./ops/spctr/target/release/spctr exec run --project alpha publish"));
    assert!(rendered.contains("./ops/spctr/target/release/spctr release gate alpha"));
}

#[test]
fn github_workflow_installs_declared_rust_targets() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    let manifest_path = root.join("addenda/alpha/spctr.toml");
    write(
        &root.join("addenda/alpha/Cargo.toml"),
        r#"[package]
name = "alpha"
version = "0.1.0"
edition = "2021"
"#,
    );
    write(
        &manifest_path,
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "operational"

[site]
visible = false
featured = false

[labels]
type = "tooling"

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["cargo", "check", "--target", "wasm32-unknown-unknown"]
requires = ["rust", "wasm32-unknown-unknown"]

[spctr.ci]
pull_request = ["check"]
"#,
    );

    let plan = github_plan(root, Some("alpha")).unwrap();
    let rendered = render_github_workflow(&plan);
    assert!(rendered.contains("uses: ./.github/actions/setup-spctr"));
    assert!(rendered.contains("rust-targets: 'wasm32-unknown-unknown'"));
    assert!(!rendered.contains("missing required runtime: wasm32-unknown-unknown"));
}

#[test]
fn ci_sync_writes_managed_workflows_and_removes_stale_files() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.ci]
pull_request = ["check"]
nightly = ["check"]
nightly_cron = "0 8 * * 1"
"#,
    );
    write(
        &root.join(".github/workflows/stale-ci.yml"),
        "# Generated by `spctr ci sync --write`; edit spctr.toml instead.\n\nname: stale\n",
    );

    let report = sync(root, None, true).unwrap();
    assert!(report.entries.iter().any(|entry| entry.workflow_path
        == ".github/workflows/alpha-ci.yml"
        && entry.status == "created"));
    assert!(report.entries.iter().any(|entry| entry.workflow_path
        == ".github/workflows/stale-ci.yml"
        && entry.status == "removed"));

    let workflow = fs::read_to_string(root.join(".github/workflows/alpha-ci.yml")).unwrap();
    assert!(workflow.starts_with("# Generated by `spctr ci sync --write`;"));
    assert!(workflow.contains("schedule:"));
    assert!(workflow.contains("cron: '0 8 * * 1'"));

    let check_report = sync(root, None, false).unwrap();
    assert!(check_report.is_clean());
}

#[test]
fn targeted_ci_sync_does_not_remove_other_generated_workflows() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    for slug in ["alpha", "beta"] {
        write(
            &root.join(format!("dossiers/{slug}/spctr.toml")),
            &format!(
                r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "{slug}"
summary = "{slug} summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "{slug}"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.ci]
pull_request = ["check"]
"#
            ),
        );
    }

    sync(root, None, true).unwrap();
    let beta_workflow = root.join(".github/workflows/beta-ci.yml");
    assert!(beta_workflow.is_file());

    let report = sync(root, Some("alpha"), true).unwrap();
    assert!(!report.entries.iter().any(|entry| entry.status == "removed"));
    assert!(beta_workflow.is_file());
}

#[test]
fn ci_sync_requires_explicit_nightly_cron() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    minimal_design_tokens(root);
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        r#"version = 1
license = "Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)"
title = "Alpha"
summary = "Alpha summary."
status = "active"

[site]
visible = false
featured = false

[release]
stage = "candidate"

[spctr]
project = "alpha"

[spctr.exec.check]
command = ["python3", "-c", "print('check')"]

[spctr.ci]
nightly = ["check"]
"#,
    );

    let error = sync(root, None, true).unwrap_err().to_string();
    assert!(error.contains("spctr.ci.nightly_cron is required for ci sync"));
}
