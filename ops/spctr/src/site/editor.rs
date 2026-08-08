use std::fs;
use std::process::Command;
use std::sync::{Arc, Mutex};

use anyhow::{bail, Context, Result};
use axum::body::Body;
use axum::extract::{OriginalUri, State};
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::post;
use axum::{Json, Router};
use camino::{Utf8Path, Utf8PathBuf};
use serde::{Deserialize, Serialize};

use super::{blog, cabinet, editor_source, editor_ui};

#[derive(Clone)]
struct EditorState {
    repo_root: Utf8PathBuf,
    checkpoint: bool,
    save_lock: Arc<Mutex<()>>,
    origin: String,
    nonce: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ResolveRequest {
    page: String,
    value: String,
    #[serde(default)]
    tag_name: String,
    #[serde(default)]
    class_name: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct SaveRequest {
    source: String,
    old_value: String,
    new_value: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SaveResponse {
    path: String,
    checkpoint: Option<String>,
}

#[derive(Debug, Serialize)]
struct ErrorResponse {
    error: String,
}

pub fn run(repo_root: &Utf8Path, port: u16, checkpoint: bool) -> Result<()> {
    if checkpoint {
        ensure_checkpointable(repo_root)?;
    }
    rebuild_all(repo_root, true)?;

    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .context("failed to build site editor runtime")?;
    runtime.block_on(serve(repo_root, port, checkpoint))
}

async fn serve(repo_root: &Utf8Path, port: u16, checkpoint: bool) -> Result<()> {
    let host = "127.0.0.1";
    let origin = format!("http://{host}:{port}");
    let state = EditorState {
        repo_root: repo_root.to_owned(),
        checkpoint,
        save_lock: Arc::new(Mutex::new(())),
        origin: origin.clone(),
        nonce: uuid::Uuid::new_v4().simple().to_string(),
    };
    let app = Router::new()
        .route("/__spctr/resolve", post(resolve_source))
        .route("/__spctr/save", post(save_source))
        .fallback(serve_site_file)
        .with_state(state);
    let listener = tokio::net::TcpListener::bind((host, port))
        .await
        .with_context(|| format!("failed to bind site editor to {host}:{port}"))?;
    eprintln!("site editor: {origin}/");
    if checkpoint {
        eprintln!("site editor: each save creates a local Jujutsu checkpoint");
    } else {
        eprintln!("site editor: checkpoints disabled");
    }
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .context("site editor server failed")?;
    Ok(())
}

async fn resolve_source(
    State(state): State<EditorState>,
    headers: HeaderMap,
    Json(request): Json<ResolveRequest>,
) -> Response {
    if let Err(error) = authorize_mutation(&state, &headers) {
        return error_response(StatusCode::FORBIDDEN, error);
    }
    let hint = editor_source::ElementHint {
        tag_name: request.tag_name,
        class_name: request.class_name,
    };
    match editor_source::resolve(&state.repo_root, &request.page, &request.value, Some(&hint)) {
        Ok(resolved) => Json(resolved).into_response(),
        Err(error) => error_response(StatusCode::UNPROCESSABLE_ENTITY, error),
    }
}

async fn save_source(
    State(state): State<EditorState>,
    headers: HeaderMap,
    Json(request): Json<SaveRequest>,
) -> Response {
    if let Err(error) = authorize_mutation(&state, &headers) {
        return error_response(StatusCode::FORBIDDEN, error);
    }
    let _guard = match state.save_lock.lock() {
        Ok(guard) => guard,
        Err(error) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                anyhow::anyhow!("site editor save lock failed: {error}"),
            );
        }
    };
    match save(&state, request) {
        Ok(response) => Json(response).into_response(),
        Err(error) => {
            let message = format!("{error:#}");
            let status = if message.contains("stale") || message.contains("changed since") {
                StatusCode::CONFLICT
            } else {
                StatusCode::UNPROCESSABLE_ENTITY
            };
            error_response(status, error)
        }
    }
}

fn save(state: &EditorState, request: SaveRequest) -> Result<SaveResponse> {
    if request.old_value == request.new_value {
        bail!("the edited text is unchanged");
    }
    if state.checkpoint {
        ensure_checkpointable(&state.repo_root)?;
    }

    let edit = editor_source::apply(
        &state.repo_root,
        &request.source,
        &request.old_value,
        &request.new_value,
    )?;
    if let Err(error) = rebuild_for_source(&state.repo_root, &edit.path, false)
        .and_then(|()| rebuild_for_source(&state.repo_root, &edit.path, true))
    {
        editor_source::restore(&edit)
            .context("validation failed and the source could not be safely restored")?;
        let _ = rebuild_for_source(&state.repo_root, &edit.path, true);
        return Err(error.context("edit did not pass site validation; source was restored"));
    }

    let checkpoint = if state.checkpoint {
        let checkpoint_result = checkpoint_paths(&state.repo_root, &edit.path)
            .and_then(|paths| create_checkpoint(&state.repo_root, &edit.path, &paths));
        match checkpoint_result {
            Ok(checkpoint) => Some(checkpoint),
            Err(error) => {
                editor_source::restore(&edit)
                    .context("checkpoint failed and the source could not be safely restored")?;
                let _ = rebuild_for_source(&state.repo_root, &edit.path, true);
                return Err(error.context("checkpoint failed; source was restored"));
            }
        }
    } else {
        None
    };
    let relative = edit
        .path
        .strip_prefix(&state.repo_root)
        .context("edited source escaped repository root")?
        .to_owned();
    Ok(SaveResponse {
        path: relative.to_string(),
        checkpoint,
    })
}

async fn serve_site_file(State(state): State<EditorState>, uri: OriginalUri) -> Response {
    let relative = match request_file_path(uri.path()) {
        Ok(path) => path,
        Err(error) => return error_response(StatusCode::BAD_REQUEST, error),
    };
    let path = state.repo_root.join("site").join(&relative);
    if !path.is_file() {
        return error_response(
            StatusCode::NOT_FOUND,
            anyhow::anyhow!("site page not found: {relative}"),
        );
    }
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(error) => {
            return error_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                anyhow::anyhow!("failed to read {path}: {error}"),
            );
        }
    };
    let content_type = mime_type(&relative);
    let body = if content_type == "text/html; charset=utf-8" {
        match String::from_utf8(bytes) {
            Ok(html) => Body::from(inject_editor(&html, &state.nonce)),
            Err(error) => {
                return error_response(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    anyhow::anyhow!("site page is not UTF-8: {error}"),
                );
            }
        }
    } else {
        Body::from(bytes)
    };
    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CACHE_CONTROL, "no-store")
        .body(body)
        .expect("valid editor response")
}

fn request_file_path(path: &str) -> Result<Utf8PathBuf> {
    let raw = path.trim_start_matches('/');
    if raw
        .split('/')
        .any(|part| part == ".." || part.contains('\\'))
    {
        bail!("invalid site path");
    }
    let mut relative = Utf8PathBuf::from(raw);
    if relative.as_str().is_empty() || path.ends_with('/') {
        relative.push("index.html");
    }
    Ok(relative)
}

fn inject_editor(html: &str, nonce: &str) -> String {
    let style = format!(
        "<style id=\"spctr-editor-styles\">{}</style>",
        editor_ui::stylesheet()
    );
    let script = format!("<script>{}</script>", editor_ui::javascript(nonce));
    let with_style = if let Some(index) = html.rfind("</head>") {
        format!("{}{}{}", &html[..index], style, &html[index..])
    } else {
        format!("{style}{html}")
    };
    if let Some(index) = with_style.rfind("</body>") {
        format!("{}{}{}", &with_style[..index], script, &with_style[index..])
    } else {
        format!("{with_style}{script}")
    }
}

fn mime_type(path: &Utf8Path) -> &'static str {
    match path.extension() {
        Some("html") => "text/html; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("js") => "text/javascript; charset=utf-8",
        Some("json") => "application/json; charset=utf-8",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("webp") => "image/webp",
        Some("woff2") => "font/woff2",
        Some("pdf") => "application/pdf",
        _ => "application/octet-stream",
    }
}

fn rebuild_all(repo_root: &Utf8Path, write: bool) -> Result<()> {
    super::build(repo_root, write)?;
    blog::build_blog_preview(repo_root, write)?;
    cabinet::build_cabinet(repo_root, write)?;
    Ok(())
}

fn rebuild_for_source(repo_root: &Utf8Path, path: &Utf8Path, write: bool) -> Result<()> {
    let relative = path
        .strip_prefix(repo_root)
        .context("edited source escaped repository root")?;
    let text = relative.as_str();
    if text.starts_with("site/blog/") {
        blog::build_blog_preview(repo_root, write)?;
        super::build(repo_root, write)?;
    } else if text.starts_with("dossiers/") || text.starts_with("addenda/") {
        if text.contains("/docs/") {
            cabinet::build_cabinet(repo_root, write)?;
        } else {
            super::build(repo_root, write)?;
        }
    } else if text.starts_with("site/cabinet/") {
        cabinet::build_cabinet(repo_root, write)?;
    } else if text.starts_with("site/dossiers/") {
        // These are canonical static pages and need no projection step.
    } else {
        super::build(repo_root, write)?;
    }
    Ok(())
}

fn ensure_checkpointable(repo_root: &Utf8Path) -> Result<()> {
    let output = Command::new("jj")
        .args([
            "--no-pager",
            "-R",
            repo_root.as_str(),
            "log",
            "-r",
            "@",
            "--no-graph",
            "-T",
            "empty ++ \" \" ++ conflict ++ \"\\n\"",
        ])
        .output()
        .context("failed to run jj; install Jujutsu or pass --no-checkpoint")?;
    if !output.status.success() {
        bail!(
            "jj could not inspect the editor checkout: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let state = String::from_utf8(output.stdout).context("jj produced invalid UTF-8")?;
    if state.trim() != "true false" {
        bail!(
            "site editor checkpoints require an empty, conflict-free working copy; use a clean checkout or --no-checkpoint"
        );
    }
    Ok(())
}

fn checkpoint_paths(repo_root: &Utf8Path, source_path: &Utf8Path) -> Result<Vec<Utf8PathBuf>> {
    let source_relative = source_path
        .strip_prefix(repo_root)
        .context("edited source escaped repository root")?;
    let output = Command::new("jj")
        .args([
            "--no-pager",
            "--color",
            "never",
            "-R",
            repo_root.as_str(),
            "diff",
            "--name-only",
        ])
        .output()
        .context("failed to inspect files changed by the site edit")?;
    if !output.status.success() {
        bail!(
            "jj could not inspect files changed by the site edit: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let stdout = String::from_utf8(output.stdout).context("jj produced invalid changed paths")?;
    let mut paths = Vec::new();
    for line in stdout.lines().filter(|line| !line.is_empty()) {
        let path = Utf8PathBuf::from(line);
        let generated_projection = is_generated_projection(&path);
        if path != source_relative && !generated_projection {
            bail!("unrelated concurrent change appeared during save: {path}");
        }
        paths.push(path);
    }
    if !paths.iter().any(|path| path == source_relative) {
        bail!("edited source disappeared from the Jujutsu change: {source_relative}");
    }
    Ok(paths)
}

fn is_generated_projection(path: &Utf8Path) -> bool {
    let text = path.as_str();
    if matches!(
        text,
        "site/index.html"
            | "site/dossiers/index.html"
            | "site/addenda/index.html"
            | "site/blog/index.html"
            | "site/research-notes/index.html"
            | "site/sitemap/index.html"
            | "site/projects/catalog.json"
            | "site/projects/artifacts.json"
            | "site/projects/health.json"
            | "site/projects/health/index.html"
            | "site/updates/index.html"
            | "site/updates/index.json"
            | "site/cabinet/index.html"
    ) {
        return true;
    }
    let components = path.components().count();
    (text.starts_with("site/dossiers/") && text.ends_with("/index.html") && components == 4)
        || (text.starts_with("site/blog/") && text.ends_with("/index.html") && components == 4)
        || (text.starts_with("site/research-notes/")
            && text.ends_with("/index.html")
            && components == 4)
        || (text.starts_with("site/updates/") && text.ends_with("/index.html") && components == 4)
        || (text.starts_with("site/cabinet/") && text.ends_with("/index.html"))
}

fn create_checkpoint(
    repo_root: &Utf8Path,
    source_path: &Utf8Path,
    paths: &[Utf8PathBuf],
) -> Result<String> {
    let relative = source_path
        .strip_prefix(repo_root)
        .context("edited source escaped repository root")?;
    let message = format!("Edit site: {relative}");
    let snapshots = paths
        .iter()
        .map(|path| {
            let bytes = read_optional(repo_root.join(path))
                .with_context(|| format!("failed to snapshot checkpoint path {path}"))?;
            Ok((path, bytes))
        })
        .collect::<Result<Vec<_>>>()?;
    for (path, expected) in &snapshots {
        let current = read_optional(repo_root.join(path))
            .with_context(|| format!("failed to verify checkpoint path {path}"))?;
        if current != *expected {
            bail!("checkpoint path changed concurrently: {path}");
        }
    }
    let mut command = Command::new("jj");
    command
        .args(["--no-pager", "-R", repo_root.as_str(), "commit", "-m"])
        .arg(&message)
        .arg("--");
    for path in paths {
        command.arg(path);
    }
    let output = command
        .output()
        .context("failed to create Jujutsu checkpoint")?;
    if !output.status.success() {
        bail!(
            "site text was saved but its Jujutsu checkpoint failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    let output = Command::new("jj")
        .args([
            "--no-pager",
            "-R",
            repo_root.as_str(),
            "log",
            "-r",
            "@-",
            "--no-graph",
            "-T",
            "change_id ++ \"\\n\"",
        ])
        .output();
    let Ok(output) = output else {
        return Ok("checkpoint-created".to_owned());
    };
    if !output.status.success() {
        return Ok("checkpoint-created".to_owned());
    }
    Ok(String::from_utf8(output.stdout).map_or_else(
        |_| "checkpoint-created".to_owned(),
        |id| id.trim().to_owned(),
    ))
}

fn read_optional(path: Utf8PathBuf) -> Result<Option<Vec<u8>>> {
    match fs::read(&path) {
        Ok(bytes) => Ok(Some(bytes)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error).with_context(|| format!("failed to read {path}")),
    }
}

fn authorize_mutation(state: &EditorState, headers: &HeaderMap) -> Result<()> {
    let expected_host = state
        .origin
        .strip_prefix("http://")
        .expect("editor origin uses http");
    let host = headers
        .get(header::HOST)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    let origin = headers
        .get(header::ORIGIN)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    let nonce = headers
        .get("x-spctr-editor-nonce")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if host != expected_host || origin != state.origin || nonce != state.nonce {
        bail!("request did not originate from this site editor session");
    }
    Ok(())
}

fn error_response(status: StatusCode, error: anyhow::Error) -> Response {
    (
        status,
        Json(ErrorResponse {
            error: format!("{error:#}"),
        }),
    )
        .into_response()
}

async fn shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use axum::http::{header, HeaderMap, HeaderValue};

    use super::{
        authorize_mutation, inject_editor, is_generated_projection, mime_type, request_file_path,
        EditorState,
    };
    use camino::Utf8Path;
    use tempfile::tempdir;

    #[test]
    fn injects_editor_without_changing_saved_html() {
        let rendered = inject_editor(
            "<html><head></head><body><p>Hello</p></body></html>",
            "test-nonce",
        );
        assert!(rendered.contains("spctr-editor-toggle"));
        assert!(rendered.contains("id=\"spctr-editor-styles\""));
        assert!(rendered.contains("/__spctr/save"));
        assert!(rendered.contains("test-nonce"));
        assert!(rendered.contains("<p>Hello</p>"));
    }

    #[test]
    fn maps_routes_to_static_index_files() {
        assert_eq!(request_file_path("/").unwrap().as_str(), "index.html");
        assert_eq!(
            request_file_path("/blog/example/").unwrap().as_str(),
            "blog/example/index.html"
        );
        assert!(request_file_path("/../secret").is_err());
    }

    #[test]
    fn serves_known_content_types() {
        assert_eq!(
            mime_type(Utf8Path::new("index.html")),
            "text/html; charset=utf-8"
        );
        assert_eq!(mime_type(Utf8Path::new("font.woff2")), "font/woff2");
    }

    #[test]
    fn mutations_require_exact_origin_host_and_session_nonce() {
        let temp = tempdir().unwrap();
        let state = EditorState {
            repo_root: camino::Utf8PathBuf::from_path_buf(temp.path().to_owned()).unwrap(),
            checkpoint: false,
            save_lock: Arc::new(Mutex::new(())),
            origin: "http://127.0.0.1:4173".to_owned(),
            nonce: "secret".to_owned(),
        };
        let mut headers = HeaderMap::new();
        headers.insert(header::HOST, HeaderValue::from_static("127.0.0.1:4173"));
        headers.insert(
            header::ORIGIN,
            HeaderValue::from_static("http://127.0.0.1:4173"),
        );
        headers.insert("x-spctr-editor-nonce", HeaderValue::from_static("secret"));
        assert!(authorize_mutation(&state, &headers).is_ok());
        headers.insert(
            header::ORIGIN,
            HeaderValue::from_static("http://evil.example"),
        );
        assert!(authorize_mutation(&state, &headers).is_err());
    }

    #[test]
    fn checkpoint_projection_allowlist_excludes_canonical_site_assets() {
        assert!(is_generated_projection(Utf8Path::new(
            "site/blog/example/index.html"
        )));
        assert!(is_generated_projection(Utf8Path::new(
            "site/cabinet/alpha/contracts/example/index.html"
        )));
        assert!(!is_generated_projection(Utf8Path::new("site/style.css")));
        assert!(!is_generated_projection(Utf8Path::new(
            "site/atlas/app/page.tsx"
        )));
        assert!(!is_generated_projection(Utf8Path::new(
            "site/dossiers/example/showcase.html"
        )));
    }
}
