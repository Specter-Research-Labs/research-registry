use camino::Utf8Path;
use spctr::manifest::{discover_manifest, load_project_manifest};
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
        "version = 1\nlicense = \"Mixed: PolyForm-Noncommercial-1.0.0 (code), CC-BY-NC-4.0 (docs)\"\ntitle = \"Alpha\"\nsummary = \"Alpha summary.\"\nstatus = \"active\"\n\n[site]\nvisible = true\nfeatured = false\n{extra}\n[release]\nstage = \"candidate\"\n"
    )
}

#[test]
fn discover_manifest_finds_spctr_toml_from_nested_directory() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let project_root = root.join("dossiers/alpha");
    write(&project_root.join("spctr.toml"), &manifest(""));
    let nested = project_root.join("subdir/deeper");
    fs::create_dir_all(&nested).unwrap();

    let loaded = discover_manifest(Some(&nested)).unwrap();

    assert_eq!(loaded.slug, "alpha");
    assert_eq!(loaded.path, project_root.join("spctr.toml"));
}

#[test]
fn manifest_allows_spctr_table() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        &manifest(
            "\n[spctr]\nproject = \"alpha\"\ndefault_surface = \"demo\"\n\n[spctr.surfaces.demo]\nkind = \"raw_plus_db\"\nraw_roots = [\"logs\"]\nlocal_db_path = \"outputs/demo.sqlite\"\nrefresh_command = [\"python3\", \"-c\", \"print('ok')\"]\nremote_raw_namespace = \"alpha\"\nremote_snapshot_namespace = \"demo\"\n",
        ),
    );

    let loaded = load_project_manifest(&manifest_path, None).unwrap();
    let spctr = loaded.spctr.unwrap();
    assert_eq!(spctr.project, "alpha");
    assert_eq!(spctr.default_surface.as_deref(), Some("demo"));
    assert_eq!(
        spctr
            .surfaces
            .get("demo")
            .and_then(|surface| surface.local_db_path.as_deref()),
        Some("outputs/demo.sqlite")
    );
}

#[test]
fn manifest_rejects_unsupported_spctr_surface_keys() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        &manifest(
            "\n[spctr]\nproject = \"alpha\"\n\n[spctr.surfaces.demo]\nkind = \"raw\"\ndriver = \"generic\"\nmystery = \"nope\"\n",
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("unsupported spctr.surfaces.demo keys"));
}

#[test]
fn publish_docs_defaults_to_true_when_omitted() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(&manifest_path, &manifest(""));

    let loaded = load_project_manifest(&manifest_path, None).unwrap();
    assert!(loaded.site.publish_docs);
}

#[test]
fn publish_docs_false_is_parsed() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(&manifest_path, &manifest("publish_docs = false"));

    let loaded = load_project_manifest(&manifest_path, None).unwrap();
    assert!(!loaded.site.publish_docs);
}

#[test]
fn manifest_rejects_absolute_local_db_path() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        &manifest(
            "\n[spctr]\nproject = \"alpha\"\n\n[spctr.surfaces.demo]\nkind = \"raw_plus_db\"\nraw_roots = [\"logs\"]\nlocal_db_path = \"/tmp/demo.sqlite\"\n",
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("local_db_path must be relative"));
}

#[test]
fn manifest_rejects_release_surface_path_parent_traversal() {
    let temp = TempDir::new().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let manifest_path = root.join("dossiers/alpha/spctr.toml");
    write(
        &manifest_path,
        &format!(
            "{}\n[[release.surfaces]]\nname = \"source\"\nkind = \"source_bundle\"\npublish = true\npath = \"../..\"\n",
            manifest("")
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(
        error.contains("must stay within the project root"),
        "got: {error}"
    );
}

#[test]
fn manifest_parses_v2_spctr_sections() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest", "-q"]
expected_outputs = ["smoke-report"]
network = "off"

[spctr.runtime]
platforms = ["macos", "linux"]
requires = ["python"]
cache_paths = ["tmp"]

[spctr.ci]
pull_request = ["check"]
push_main = ["check"]
nightly = ["check"]
nightly_cron = "0 8 * * 1"

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.expected_outputs]]
name = "smoke-report"
path = "artifacts/smoke/report.json"
kind = "status_json"
required = true
surface = "python"

[spctr.docs]
root = "docs"
landing = "README.md"
require_frontmatter = true
"#,
        ),
    );

    let loaded = load_project_manifest(&manifest_path, None).unwrap();
    let spctr = loaded.spctr.unwrap();
    let check = spctr.exec.get("check").unwrap();
    assert_eq!(check.command.as_ref().unwrap()[0], "uv");
    assert_eq!(check.expected_outputs, vec!["smoke-report"]);
    assert_eq!(
        spctr.runtime.as_ref().unwrap().platforms,
        vec!["macos", "linux"]
    );
    assert_eq!(spctr.ci.as_ref().unwrap().pull_request, vec!["check"]);
    assert_eq!(
        spctr.ci.as_ref().unwrap().nightly_cron.as_deref(),
        Some("0 8 * * 1")
    );
    assert_eq!(spctr.expected_outputs[0].surface.as_deref(), Some("python"));
    assert_eq!(
        spctr.docs.as_ref().unwrap().landing.as_deref(),
        Some("README.md")
    );
}

#[test]
fn manifest_rejects_exec_action_with_both_command_and_commands() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest"]
commands = [["uv", "run", "ruff", "check", "."]]
"#,
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("must define exactly one of command or commands"));
}

#[test]
fn manifest_rejects_exec_outputs_not_declared_in_expected_outputs() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest"]
expected_outputs = ["missing-output"]

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"
"#,
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("expected_outputs references unknown output 'missing-output'"));
}

#[test]
fn manifest_rejects_ci_lane_referencing_unknown_exec_action() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest"]

[spctr.ci]
pull_request = ["smoke"]
"#,
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("spctr.ci.pull_request references unknown exec action 'smoke'"));
}

#[test]
fn manifest_rejects_nightly_cron_without_nightly_lane() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest"]

[spctr.ci]
pull_request = ["check"]
nightly_cron = "0 8 * * 1"
"#,
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("spctr.ci.nightly_cron requires at least one spctr.ci.nightly action"));
}

#[test]
fn manifest_rejects_evidence_surface_unknown_release_surface() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest"]
expected_outputs = ["smoke-report"]

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

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(
        error.contains("unknown release surface 'python'"),
        "got: {error}"
    );
}

#[test]
fn manifest_rejects_legacy_exec_outputs_alias() {
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

[spctr.exec.check]
command = ["uv", "run", "pytest"]
outputs = ["smoke-report"]
"#,
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error
        .contains("spctr.exec.check.outputs was removed; use spctr.exec.check.expected_outputs"));
}

#[test]
fn manifest_rejects_legacy_evidence_outputs_alias() {
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

[spctr.evidence]
card_path = "artifacts/evidence/latest.json"

[[spctr.evidence.outputs]]
name = "smoke-report"
path = "artifacts/smoke/report.json"
kind = "status_json"
required = true
"#,
        ),
    );

    let error = load_project_manifest(&manifest_path, None)
        .unwrap_err()
        .to_string();
    assert!(error.contains("spctr.evidence.outputs was removed; use [[spctr.expected_outputs]]"));
}
