use serde::de::DeserializeOwned;

/// Fetch a JSON document and deserialize it.
///
/// # Errors
/// Returns an error if the path is empty, the fetch/read fails, or the response is not valid JSON.
pub async fn fetch_json<T: DeserializeOwned>(path: &str) -> Result<T, String> {
    let text = fetch_text(path).await?;
    serde_json::from_str(&text).map_err(|err| format!("Failed to parse JSON from {path}: {err}"))
}

/// Fetch a JSONL document and deserialize each non-empty line.
///
/// # Errors
/// Returns an error if the path is empty, the fetch/read fails, or any non-empty line is not valid JSON.
pub async fn fetch_jsonl<T: DeserializeOwned>(path: &str) -> Result<Vec<T>, String> {
    let text = fetch_text(path).await?;
    let mut items = Vec::new();
    for (idx, line) in text.lines().enumerate() {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        let value: T = serde_json::from_str(trimmed)
            .map_err(|err| format!("Failed to parse JSONL line {} from {path}: {err}", idx + 1))?;
        items.push(value);
    }
    Ok(items)
}

// This is `async` because the wasm implementation is async. In native builds, the `await`
// disappears behind `cfg` and clippy would otherwise flag it.
#[allow(clippy::unused_async)]
async fn fetch_text(path: &str) -> Result<String, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("path is empty".to_string());
    }

    #[cfg(target_arch = "wasm32")]
    {
        fetch_text_wasm(trimmed).await
    }

    #[cfg(not(target_arch = "wasm32"))]
    {
        std::fs::read_to_string(trimmed)
            .map_err(|err| format!("{}: {err}", std::path::Path::new(trimmed).display()))
    }
}

#[cfg(target_arch = "wasm32")]
async fn fetch_text_wasm(path: &str) -> Result<String, String> {
    use wasm_bindgen::JsCast;
    use wasm_bindgen_futures::JsFuture;

    let window = web_sys::window().ok_or_else(|| "window missing".to_string())?;
    let response = JsFuture::from(window.fetch_with_str(path))
        .await
        .map_err(js_error_to_string)?;
    let response: web_sys::Response = response
        .dyn_into()
        .map_err(|_| "invalid response type".to_string())?;
    if !response.ok() {
        return Err(format!(
            "HTTP {} {}",
            response.status(),
            response.status_text()
        ));
    }
    let text_promise = response
        .text()
        .map_err(|_| "failed to read response body".to_string())?;
    let text = JsFuture::from(text_promise)
        .await
        .map_err(js_error_to_string)?;
    text.as_string()
        .ok_or_else(|| "response body is not text".to_string())
}

#[cfg(target_arch = "wasm32")]
fn js_error_to_string(error: wasm_bindgen::JsValue) -> String {
    error.as_string().unwrap_or_else(|| format!("{error:?}"))
}
