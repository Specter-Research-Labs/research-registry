use anyhow::{bail, Context, Result};
use reqwest::blocking::Client;

use crate::dispatch::env::{optional_env, trim_non_empty};
use crate::dispatch::types::{
    AdminLedgerPostRequest, AdminLedgerPostResponse, DispatchHealthResponse,
};

pub const ADMIN_LEDGER_POST_PATH: &str = "/admin/ledger/post";

pub fn resolve_dispatch_url(value: Option<&str>) -> Result<String> {
    if let Some(url) = trim_non_empty(value, "dispatch_url")? {
        return Ok(url);
    }
    if let Some(url) = optional_env("SPECTER_DISPATCH_URL") {
        return Ok(url);
    }
    if let Some(url) = optional_env("DISPATCH_PUBLIC_URL") {
        return Ok(url);
    }
    bail!("updates approve requires --dispatch-url or SPECTER_DISPATCH_URL/DISPATCH_PUBLIC_URL")
}

pub fn resolve_dispatch_secret(value: Option<&str>) -> Result<String> {
    if let Some(secret) = trim_non_empty(value, "dispatch_secret")? {
        return Ok(secret);
    }
    if let Some(secret) = optional_env("SPECTER_DISPATCH_SHARED_SECRET") {
        return Ok(secret);
    }
    if let Some(secret) = optional_env("RUNNER_SHARED_SECRET") {
        return Ok(secret);
    }
    bail!("updates approve requires --dispatch-secret or SPECTER_DISPATCH_SHARED_SECRET/RUNNER_SHARED_SECRET")
}

pub fn get_health_blocking(dispatch_url: &str) -> Result<DispatchHealthResponse> {
    let url = format!("{}/health", dispatch_url.trim_end_matches('/'));
    reqwest::blocking::get(&url)
        .with_context(|| format!("failed to reach dispatch at {url}"))?
        .json()
        .with_context(|| "failed to parse dispatch health response")
}

pub fn post_admin_ledger_entry_blocking(
    dispatch_url: &str,
    dispatch_secret: &str,
    payload: &AdminLedgerPostRequest,
) -> Result<AdminLedgerPostResponse> {
    let endpoint = format!(
        "{}{}",
        dispatch_url.trim_end_matches('/'),
        ADMIN_LEDGER_POST_PATH
    );
    let client = Client::builder()
        .build()
        .context("failed to build dispatch HTTP client")?;
    let response = client
        .post(endpoint)
        .bearer_auth(dispatch_secret)
        .json(payload)
        .send()
        .context("failed to post approved ledger entry to dispatch")?;
    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().unwrap_or_default();
        bail!("dispatch ledger post failed: {status} {body}");
    }
    response
        .json::<AdminLedgerPostResponse>()
        .context("failed to parse dispatch ledger response")
}
