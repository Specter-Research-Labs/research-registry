use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use std::env;
use std::fs;
use toml::Table;

fn home_config_dir() -> Option<Utf8PathBuf> {
    dirs::home_dir().and_then(|h| Utf8PathBuf::try_from(h).ok().map(|u| u.join(".config")))
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SshConfig {
    pub user: String,
    pub host: String,
    pub port: u16,
}

impl SshConfig {
    pub fn parse(raw: &str) -> Result<Self> {
        let value = raw.trim();
        let (user, rest) = value
            .split_once('@')
            .ok_or_else(|| anyhow::anyhow!("ssh_target must be user@host:port, got: {raw:?}"))?;
        let (host, port_text) = rest
            .rsplit_once(':')
            .ok_or_else(|| anyhow::anyhow!("ssh_target must be user@host:port, got: {raw:?}"))?;
        if user.is_empty() || host.is_empty() || port_text.is_empty() {
            bail!("ssh_target must be user@host:port, got: {raw:?}");
        }
        let port = port_text
            .parse::<u16>()
            .with_context(|| format!("ssh_target port must be an integer, got: {port_text:?}"))?;
        Ok(Self {
            user: user.to_owned(),
            host: host.to_owned(),
            port,
        })
    }

    pub fn ssh_args(&self) -> Vec<String> {
        vec![
            "-p".to_owned(),
            self.port.to_string(),
            format!("{}@{}", self.user, self.host),
        ]
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MachineConfig {
    pub machine_id: String,
    pub hot_snapshot_root: String,
    pub durable_log_root: String,
    pub durable_artifact_root: String,
    pub runtime_root: Option<String>,
    pub ssh: Option<SshConfig>,
    pub config_path: Utf8PathBuf,
}

fn default_config_path() -> Utf8PathBuf {
    if let Some(override_path) = env::var("SPCTR_CONFIG").ok().filter(|s| !s.is_empty()) {
        return Utf8PathBuf::from(override_path);
    }
    if let Some(xdg) = env::var("XDG_CONFIG_HOME").ok().filter(|s| !s.is_empty()) {
        return Utf8PathBuf::from(xdg).join("spctr").join("config.toml");
    }
    match home_config_dir() {
        Some(cfg) => cfg.join("spctr/config.toml"),
        None => Utf8PathBuf::from(".config/spctr/config.toml"),
    }
}

fn read_config_file(path: &Utf8Path) -> Result<Table> {
    if !path.exists() {
        return Ok(Table::new());
    }
    let text = fs::read_to_string(path).with_context(|| format!("failed to read {path}"))?;
    let value = text
        .parse::<toml::Value>()
        .with_context(|| format!("invalid TOML in {path}"))?;
    value
        .as_table()
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("{path}: config root must be a table"))
}

fn string_value(
    data: &Table,
    key: &str,
    env_name: Option<&str>,
    required: bool,
) -> Result<Option<String>> {
    if let Some(name) = env_name {
        if let Ok(raw) = env::var(name) {
            let value = raw.trim().to_owned();
            if value.is_empty() {
                bail!("{name} is set but empty");
            }
            return Ok(Some(value));
        }
    }
    match data.get(key) {
        None => {
            if required {
                bail!("missing required config value: {}", env_name.unwrap_or(key));
            }
            Ok(None)
        }
        Some(value) => {
            let text = value
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("{key} must be a non-empty string"))?
                .trim()
                .to_owned();
            if text.is_empty() {
                bail!("{key} must be a non-empty string");
            }
            Ok(Some(text))
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReportConfig {
    pub dispatch_url: String,
    pub github_token: String,
    pub github_repo: String,
    pub server_ssh: Option<SshConfig>,
    pub services: Vec<String>,
    pub workflows: Vec<String>,
}

fn string_array_value(data: &Table, key: &str) -> Result<Vec<String>> {
    match data.get(key) {
        None => Ok(Vec::new()),
        Some(value) => {
            let arr = value
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("{key} must be an array of strings"))?;
            arr.iter()
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| anyhow::anyhow!("{key} entries must be strings"))
                })
                .collect()
        }
    }
}

#[allow(clippy::missing_errors_doc, clippy::missing_panics_doc)]
pub fn load_report_config() -> Result<ReportConfig> {
    let config_path = default_config_path();
    let root = read_config_file(&config_path)?;
    let data = root
        .get("report")
        .and_then(|v| v.as_table())
        .cloned()
        .unwrap_or_default();

    let dispatch_url = string_value(
        &data,
        "dispatch_url",
        Some("SPCTR_REPORT_DISPATCH_URL"),
        true,
    )?
    .unwrap();
    let github_token = string_value(
        &data,
        "github_token",
        Some("SPCTR_REPORT_GITHUB_TOKEN"),
        true,
    )?
    .unwrap();
    let github_repo =
        string_value(&data, "github_repo", Some("SPCTR_REPORT_GITHUB_REPO"), true)?.unwrap();
    let server_ssh = string_value(&data, "server_ssh", None, false)?
        .map(|raw| SshConfig::parse(&raw))
        .transpose()?;
    let services = string_array_value(&data, "services")?;
    let workflows = string_array_value(&data, "workflows")?;

    Ok(ReportConfig {
        dispatch_url,
        github_token,
        github_repo,
        server_ssh,
        services,
        workflows,
    })
}

pub fn load_machine_config() -> Result<MachineConfig> {
    let config_path = default_config_path();
    let data = read_config_file(&config_path)?;
    let machine_id = string_value(&data, "machine_id", Some("SPCTR_MACHINE_ID"), true)?.unwrap();
    let hot_snapshot_root = string_value(
        &data,
        "hot_snapshot_root",
        Some("SPCTR_HOT_SNAPSHOT_ROOT"),
        true,
    )?
    .unwrap();
    let durable_log_root =
        string_value(&data, "durable_log_root", Some("SPECTER_LOG_ROOT"), true)?.unwrap();
    let durable_artifact_root = string_value(
        &data,
        "durable_artifact_root",
        Some("SPECTER_ARTIFACT_ROOT"),
        true,
    )?
    .unwrap();
    let runtime_root = string_value(&data, "runtime_root", Some("SPECTER_RUNTIME_ROOT"), false)?;
    let ssh = string_value(&data, "ssh_target", Some("SPECTER_REMOTE_SSH"), false)?
        .map(|raw| SshConfig::parse(&raw))
        .transpose()?;
    Ok(MachineConfig {
        machine_id,
        hot_snapshot_root,
        durable_log_root,
        durable_artifact_root,
        runtime_root,
        ssh,
        config_path,
    })
}
