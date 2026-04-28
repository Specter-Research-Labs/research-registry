use camino::{Utf8Path, Utf8PathBuf};
use std::fs;
use tempfile::TempDir;

fn write(root: &Utf8Path, rel: &str, content: &str) {
    let path = root.join(rel);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

fn minimal_entry(entry_id: &str) -> String {
    format!(
        "{{\n  \"id\": \"{entry_id}\",\n  \"kind\": \"window\",\n  \"label\": \"Window 2026-03-01 to 2026-03-07\",\n  \"date\": \"2026-03-07\",\n  \"published_at\": \"2026-03-07T12:00:00Z\",\n  \"topic\": \"weekly / 2026-03-01 to 2026-03-07\",\n  \"window\": {{\n    \"start\": \"2026-03-01\",\n    \"end\": \"2026-03-07\"\n  }},\n  \"sections\": {{\n    \"dossiers\": [\"lenia-swarm: added archived notebook entry.\"],\n    \"addenda\": [],\n    \"ops\": [],\n    \"lab\": []\n  }}\n}}\n"
    )
}

fn make_temp_repo() -> TempDir {
    let temp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    write(
        root,
        "site/updates/entries/sample-update.json",
        &minimal_entry("sample-update"),
    );
    temp
}

#[test]
fn repo_outputs_are_in_sync() {
    let root = Utf8PathBuf::from_path_buf(
        fs::canonicalize(
            Utf8Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../..")
                .as_std_path(),
        )
        .unwrap(),
    )
    .expect("repo root is valid UTF-8");
    let artifacts = spctr::updates_archive::build_update_artifacts(&root).unwrap();
    let expected = [
        "site/updates/index.html",
        "site/updates/index.json",
        "site/updates/spctr-update-001/index.html",
        "site/updates/spctr-update-002/index.html",
        "site/updates/spctr-update-003/index.html",
        "site/updates/spctr-update-004/index.html",
        "site/updates/spctr-update-005/index.html",
        "site/updates/spctr-update-006/index.html",
        "site/updates/spctr-update-007/index.html",
        "site/updates/spctr-update-008/index.html",
    ]
    .into_iter()
    .map(|path| root.join(path))
    .collect::<Vec<_>>();

    assert_eq!(
        artifacts.rendered_files.keys().cloned().collect::<Vec<_>>(),
        expected
    );
    assert!(artifacts.stale_paths.is_empty());
    assert!(artifacts.feed_json.contains("\"version\": 1"));
    assert!(artifacts
        .rendered_files
        .get(&root.join("site/updates/index.html"))
        .unwrap()
        .contains("Update Archive"));
}

#[test]
fn builds_index_and_entry_pages() {
    let temp = make_temp_repo();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let artifacts = spctr::updates_archive::build_update_artifacts(root).unwrap();

    assert!(artifacts
        .rendered_files
        .contains_key(&root.join("site/updates/index.html")));
    assert!(artifacts
        .rendered_files
        .contains_key(&root.join("site/updates/index.json")));
    assert!(artifacts
        .rendered_files
        .contains_key(&root.join("site/updates/sample-update/index.html")));
    assert!(artifacts.stale_paths.is_empty());
    assert!(artifacts.feed_json.contains("sample-update"));
    let index_html = artifacts
        .rendered_files
        .get(&root.join("site/updates/index.html"))
        .unwrap();
    let entry_html = artifacts
        .rendered_files
        .get(&root.join("site/updates/sample-update/index.html"))
        .unwrap();
    assert!(index_html.contains("Window 2026-03-01 to 2026-03-07"));
    assert!(!index_html.contains("weekly / 2026-03-01 to 2026-03-07"));
    assert!(!entry_html.contains("weekly / 2026-03-01 to 2026-03-07"));
}

#[test]
fn apply_or_check_removes_stale_entry_directories() {
    let temp = make_temp_repo();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    write(
        root,
        "site/updates/old-entry/index.html",
        "<html>stale</html>\n",
    );

    let result = spctr::updates_archive::apply_or_check(root, true, false).unwrap();

    assert_eq!(result, 0);
    assert!(!root.join("site/updates/old-entry").exists());
}

#[test]
fn rejects_unknown_section_keys() {
    let temp = make_temp_repo();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    write(
        root,
        "site/updates/entries/bad-entry.json",
        "{\n  \"id\": \"bad-entry\",\n  \"kind\": \"window\",\n  \"label\": \"Bad Entry\",\n  \"date\": \"2026-03-07\",\n  \"published_at\": \"2026-03-07T12:00:00Z\",\n  \"topic\": \"weekly / 2026-03-07\",\n  \"window\": {\n    \"start\": \"2026-03-01\",\n    \"end\": \"2026-03-07\"\n  },\n  \"sections\": {\n    \"other\": [\"invalid\"]\n  }\n}\n",
    );

    let error = spctr::updates_archive::build_update_artifacts(root)
        .unwrap_err()
        .to_string();
    assert!(error.contains("unsupported section keys"));
}
