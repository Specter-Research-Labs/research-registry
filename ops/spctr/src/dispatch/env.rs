use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::Path;

use anyhow::{bail, Result};

#[derive(Clone, Debug, Default)]
pub struct DispatchConfig {
    pub admin_emails: Option<String>,
    pub database_url: Option<String>,
    pub dispatch_host: Option<String>,
    pub dispatch_port: Option<String>,
    pub dispatch_public_url: Option<String>,
    pub github_repository: Option<String>,
    pub github_webhook_secret: Option<String>,
    pub runner_shared_secret: Option<String>,
    pub zulip_bot_api_key: Option<String>,
    pub zulip_bot_email: Option<String>,
    pub zulip_dispatch_stream: Option<String>,
    pub zulip_ledger_stream: Option<String>,
    pub zulip_site: Option<String>,
    pub zulip_webhook_token: Option<String>,
}

impl DispatchConfig {
    pub fn from_process() -> Self {
        Self {
            admin_emails: optional_env("ADMIN_EMAILS"),
            database_url: optional_env("DATABASE_URL"),
            dispatch_host: optional_env("DISPATCH_HOST"),
            dispatch_port: optional_env("DISPATCH_PORT"),
            dispatch_public_url: optional_env("DISPATCH_PUBLIC_URL"),
            github_repository: optional_env("GITHUB_REPOSITORY"),
            github_webhook_secret: optional_env("GITHUB_WEBHOOK_SECRET"),
            runner_shared_secret: optional_env("RUNNER_SHARED_SECRET"),
            zulip_bot_api_key: optional_env("ZULIP_BOT_API_KEY"),
            zulip_bot_email: optional_env("ZULIP_BOT_EMAIL"),
            zulip_dispatch_stream: optional_env("ZULIP_DISPATCH_STREAM"),
            zulip_ledger_stream: optional_env("ZULIP_LEDGER_STREAM"),
            zulip_site: optional_env("ZULIP_SITE"),
            zulip_webhook_token: optional_env("ZULIP_WEBHOOK_TOKEN"),
        }
    }

    pub fn require_database_url(&self) -> Result<&str> {
        self.database_url
            .as_deref()
            .ok_or_else(|| anyhow::anyhow!("missing required environment variable: DATABASE_URL"))
    }

    pub fn host(&self) -> &str {
        self.dispatch_host.as_deref().unwrap_or("127.0.0.1")
    }

    pub fn port(&self) -> Result<u16> {
        self.dispatch_port
            .as_deref()
            .unwrap_or("3001")
            .parse::<u16>()
            .map_err(|error| anyhow::anyhow!("invalid DISPATCH_PORT: {error}"))
    }

    pub fn admin_email_set(&self) -> HashSet<String> {
        self.admin_emails
            .as_deref()
            .map(|raw| {
                raw.split(',')
                    .map(str::trim)
                    .filter(|item| !item.is_empty())
                    .map(|item| item.to_ascii_lowercase())
                    .collect()
            })
            .unwrap_or_default()
    }
}

fn parse_env_line(line: &str) -> Option<(String, String)> {
    let trimmed = line.trim();
    if trimmed.is_empty() || trimmed.starts_with('#') {
        return None;
    }
    let normalized = trimmed.strip_prefix("export ").map_or(trimmed, str::trim);
    let separator = normalized.find('=')?;
    if separator == 0 {
        return None;
    }
    let key = normalized[..separator].trim();
    let value = normalized[separator + 1..].trim();
    let value = if value.len() >= 2
        && ((value.starts_with('"') && value.ends_with('"'))
            || (value.starts_with('\'') && value.ends_with('\'')))
    {
        value[1..value.len() - 1].to_owned()
    } else {
        value.to_owned()
    };
    Some((key.to_owned(), value))
}

pub fn load_env_file_from_var() -> Result<()> {
    if let Some(path) = env::var("DISPATCH_ENV_FILE")
        .ok()
        .filter(|value| !value.trim().is_empty())
    {
        load_env_file(Path::new(&path))?;
    }
    Ok(())
}

pub fn load_env_file(path: &Path) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    let contents = fs::read_to_string(path)
        .map_err(|error| anyhow::anyhow!("failed to read {}: {error}", path.display()))?;
    for raw_line in contents.lines() {
        let Some((key, value)) = parse_env_line(raw_line) else {
            continue;
        };
        if env::var_os(&key).is_none() {
            env::set_var(key, value);
        }
    }
    Ok(())
}

pub fn optional_env(name: &str) -> Option<String> {
    env::var(name).ok().and_then(|value| {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed.to_owned())
        }
    })
}

pub fn require_env(name: &str) -> Result<String> {
    optional_env(name)
        .ok_or_else(|| anyhow::anyhow!("missing required environment variable: {name}"))
}

pub fn trim_non_empty(value: Option<&str>, label: &str) -> Result<Option<String>> {
    match value {
        Some(value) => {
            let trimmed = value.trim();
            if trimmed.is_empty() {
                bail!("{label} must not be empty");
            }
            Ok(Some(trimmed.to_owned()))
        }
        None => Ok(None),
    }
}
