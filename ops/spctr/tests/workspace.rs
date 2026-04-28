use camino::Utf8Path;
use std::fs;

fn write(path: &Utf8Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

#[test]
fn init_creates_default_sibling_repos_next_to_repo_root() {
    let temp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let repo_root = root.join("specter");
    fs::create_dir_all(&repo_root).unwrap();

    spctr::workspace::init(
        spctr::workspace::InitOptions {
            repo_root: Some(repo_root),
            generated_root: None,
            records_bureau_root: None,
        },
        false,
    )
    .unwrap();

    let generated_root = root.join("generated");
    let records_root = root.join("records-bureau");
    assert!(generated_root.join(".git").exists());
    assert!(records_root.join(".git").exists());
    assert_eq!(
        fs::read_to_string(generated_root.join("README.md")).unwrap(),
        "# generated\n\nPrivate local repository for Specter Labs.\n"
    );
    assert_eq!(
        fs::read_to_string(records_root.join("README.md")).unwrap(),
        "# records-bureau\n\nPrivate local repository for Specter Labs.\n"
    );
    assert_eq!(
        fs::read_to_string(generated_root.join(".gitignore")).unwrap(),
        ".DS_Store\n"
    );
}

#[test]
fn init_honors_overrides_and_preserves_existing_files() {
    let temp = tempfile::tempdir().unwrap();
    let root = Utf8Path::from_path(temp.path()).expect("temp dir is valid UTF-8");
    let repo_root = root.join("specter");
    let generated_root = root.join("private/generated-local");
    let records_root = root.join("private/records-bureau-local");
    fs::create_dir_all(&repo_root).unwrap();
    write(&generated_root.join("README.md"), "# custom\n");
    write(&generated_root.join(".gitignore"), "custom\n");

    let options = spctr::workspace::InitOptions {
        repo_root: Some(repo_root),
        generated_root: Some(generated_root.clone()),
        records_bureau_root: Some(records_root.clone()),
    };

    spctr::workspace::init(
        spctr::workspace::InitOptions {
            repo_root: options.repo_root.clone(),
            generated_root: options.generated_root.clone(),
            records_bureau_root: options.records_bureau_root.clone(),
        },
        false,
    )
    .unwrap();
    spctr::workspace::init(options, false).unwrap();

    assert!(generated_root.join(".git").exists());
    assert!(records_root.join(".git").exists());
    assert_eq!(
        fs::read_to_string(generated_root.join("README.md")).unwrap(),
        "# custom\n"
    );
    assert_eq!(
        fs::read_to_string(generated_root.join(".gitignore")).unwrap(),
        "custom\n"
    );
}
