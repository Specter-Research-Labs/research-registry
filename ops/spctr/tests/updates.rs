use serde_json::Value;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::thread;
use tempfile::TempDir;

fn write(path: &Path, content: &str) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(path, content).unwrap();
}

fn create_repo(root: &Path) -> PathBuf {
    let repo_root = root.join("repo");
    write(
        &repo_root.join("site/updates/entries/existing-window.json"),
        "{\n\
  \"id\": \"existing-window\",\n\
  \"kind\": \"window\",\n\
  \"label\": \"Window 2026-03-01 to 2026-03-07\",\n\
  \"date\": \"2026-03-07\",\n\
  \"published_at\": \"2026-03-07T12:00:00Z\",\n\
  \"topic\": \"weekly / 2026-03-01 to 2026-03-07\",\n\
  \"window\": {\n\
    \"start\": \"2026-03-01\",\n\
    \"end\": \"2026-03-07\"\n\
  },\n\
  \"sections\": {\n\
    \"dossiers\": [\"lenia-swarm: added archive seed.\"],\n\
    \"addenda\": [],\n\
    \"ops\": [],\n\
    \"lab\": []\n\
  }\n\
}\n",
    );
    repo_root
}

fn output_text(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned() + &String::from_utf8_lossy(&output.stderr)
}

fn spctr(args: &[&str], cwd: &Path) -> Output {
    Command::new(env!("CARGO_BIN_EXE_spctr"))
        .args(args)
        .current_dir(cwd)
        .output()
        .unwrap()
}

fn spawn_dispatch_server(expected_secret: &'static str) -> String {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut reader = BufReader::new(stream.try_clone().unwrap());
        let mut request_line = String::new();
        reader.read_line(&mut request_line).unwrap();
        assert!(request_line.starts_with("POST /admin/ledger/post HTTP/1.1"));

        let mut authorization = None;
        let mut content_length = 0usize;
        loop {
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();
            if line == "\r\n" || line.is_empty() {
                break;
            }
            if let Some((name, value)) = line.split_once(':') {
                if name.eq_ignore_ascii_case("Authorization") {
                    authorization = Some(value.trim().to_string());
                }
                if name.eq_ignore_ascii_case("Content-Length") {
                    content_length = value.trim().parse().unwrap();
                }
            }
        }

        let expected_authorization = format!("Bearer {expected_secret}");
        assert_eq!(
            authorization.as_deref(),
            Some(expected_authorization.as_str())
        );

        let mut body = vec![0; content_length];
        reader.read_exact(&mut body).unwrap();
        let body = String::from_utf8(body).unwrap();
        assert!(body.contains("\"topic\":\"weekly / 2026-02-28 to 2026-03-14\""));
        assert!(body.contains("Dossiers:\\n- lenia-swarm: added Lenia Lab."));
        let body = concat!(
            "{\"entryId\":\"ledger-20260314-demo\",",
            "\"createdAt\":\"2026-03-14T22:14:20Z\",",
            "\"messageId\":4321,",
            "\"streamName\":\"ledger\",",
            "\"topic\":\"weekly / 2026-02-28 to 2026-03-14\",",
            "\"content\":\"ok\"}"
        );
        let response = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(),
            body
        );
        stream.write_all(response.as_bytes()).unwrap();
    });
    format!("http://{}", address)
}

#[test]
fn updates_create_materializes_window_entry_and_renders_archive() {
    let temp = TempDir::new().unwrap();
    let repo_root = create_repo(temp.path());
    let draft_path = repo_root.join("draft-window.txt");
    write(
        &draft_path,
        "Window: 2026-02-28 through 2026-03-14\n\n\
Dossiers:\n\
- lenia-swarm: added Lenia Lab.\n\n\
Ops:\n\
- added archive publication flow.\n",
    );

    let output = spctr(
        &[
            "updates",
            "create",
            "--repo-root",
            repo_root.to_str().unwrap(),
            "--body-file",
            draft_path.to_str().unwrap(),
            "--published-at",
            "2026-03-14T22:14:20Z",
            "--report",
        ],
        &repo_root,
    );
    assert!(output.status.success(), "{}", output_text(&output));

    let entry_path =
        repo_root.join("site/updates/entries/slu-20260314-window-2026-02-28-to-2026-03-14.json");
    let entry: Value = serde_json::from_str(&fs::read_to_string(&entry_path).unwrap()).unwrap();
    assert_eq!(entry["kind"], "window");
    assert_eq!(entry["label"], "Window 2026-02-28 to 2026-03-14");
    assert_eq!(entry["topic"], "weekly / 2026-02-28 to 2026-03-14");
    assert_eq!(entry["published_at"], "2026-03-14T22:14:20Z");
    assert_eq!(
        entry["sections"]["dossiers"][0],
        "lenia-swarm: added Lenia Lab."
    );
    assert_eq!(
        entry["sections"]["ops"][0],
        "added archive publication flow."
    );
    assert!(repo_root.join("site/updates/index.html").is_file());
    assert!(repo_root
        .join("site/updates/slu-20260314-window-2026-02-28-to-2026-03-14/index.html")
        .is_file());
    assert!(output_text(&output).contains(
        "created=site/updates/entries/slu-20260314-window-2026-02-28-to-2026-03-14.json"
    ));
}

#[test]
fn updates_create_main_entry_uses_next_series_number() {
    let temp = TempDir::new().unwrap();
    let repo_root = create_repo(temp.path());
    write(
        &repo_root.join("site/updates/entries/main-two.json"),
        "{\n\
  \"id\": \"main-two\",\n\
  \"kind\": \"main\",\n\
  \"label\": \"SPCTR-UPDATE-002\",\n\
  \"date\": \"2026-03-21\",\n\
  \"published_at\": \"2026-03-21T00:00:00Z\",\n\
  \"topic\": \"weekly / spctr-update-002\",\n\
  \"window\": {\n\
    \"start\": \"2026-03-15\",\n\
    \"end\": \"2026-03-21\"\n\
  },\n\
  \"series_number\": 2,\n\
  \"sections\": {\n\
    \"dossiers\": [\"alpha: added seed.\"],\n\
    \"addenda\": [],\n\
    \"ops\": [],\n\
    \"lab\": []\n\
  }\n\
}\n",
    );
    let draft_path = repo_root.join("draft-main.txt");
    write(
        &draft_path,
        "Window: 2026-03-22 through 2026-03-28\n\n\
Dossiers:\n\
- lenia-swarm: changed search backend.\n",
    );

    let output = spctr(
        &[
            "updates",
            "create",
            "--repo-root",
            repo_root.to_str().unwrap(),
            "--kind",
            "main",
            "--body-file",
            draft_path.to_str().unwrap(),
        ],
        &repo_root,
    );
    assert!(output.status.success(), "{}", output_text(&output));

    let entry_path = repo_root.join("site/updates/entries/spctr-update-003.json");
    let entry: Value = serde_json::from_str(&fs::read_to_string(&entry_path).unwrap()).unwrap();
    assert_eq!(entry["kind"], "main");
    assert_eq!(entry["series_number"], 3);
    assert_eq!(entry["label"], "SPCTR-UPDATE-003");
    assert_eq!(entry["topic"], "weekly / spctr-update-003");
    assert_eq!(entry["date"], "2026-03-28");
    assert_eq!(entry["published_at"], "2026-03-28T00:00:00Z");
}

#[test]
fn updates_approve_posts_to_dispatch_and_records_ids() {
    let temp = TempDir::new().unwrap();
    let repo_root = create_repo(temp.path());
    let draft_path = repo_root.join("draft-approve.txt");
    write(
        &draft_path,
        "Window: 2026-02-28 through 2026-03-14\n\n\
Dossiers:\n\
- lenia-swarm: added Lenia Lab.\n",
    );
    let dispatch_url = spawn_dispatch_server("secret-xyz");

    let output = spctr(
        &[
            "updates",
            "approve",
            "--repo-root",
            repo_root.to_str().unwrap(),
            "--body-file",
            draft_path.to_str().unwrap(),
            "--dispatch-url",
            &dispatch_url,
            "--dispatch-secret",
            "secret-xyz",
        ],
        &repo_root,
    );
    assert!(output.status.success(), "{}", output_text(&output));

    let entry_path =
        repo_root.join("site/updates/entries/slu-20260314-window-2026-02-28-to-2026-03-14.json");
    let entry: Value = serde_json::from_str(&fs::read_to_string(&entry_path).unwrap()).unwrap();
    assert_eq!(entry["published_at"], "2026-03-14T22:14:20Z");
    assert_eq!(entry["ledger_entry_id"], "ledger-20260314-demo");
    assert_eq!(entry["zulip_message_id"], 4321);
    assert!(output_text(&output).contains("approved topic=weekly / 2026-02-28 to 2026-03-14"));
}
