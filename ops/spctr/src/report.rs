use std::fmt::Write as _;
use std::process::Command;

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};

use crate::config::{ReportConfig, SshConfig};
use crate::dispatch::client::get_health_blocking;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReportData {
    pub machine: MachineInfo,
    pub hardware: HardwareInfo,
    pub services: Vec<ServiceInfo>,
    pub dispatch: DispatchInfo,
    pub runners: Vec<RunnerInfo>,
    pub workflows: Vec<WorkflowInfo>,
    pub generated_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MachineInfo {
    pub hostname: String,
    pub uptime: String,
    pub load: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareInfo {
    pub cpu: String,
    pub memory_used: String,
    pub memory_total: String,
    pub memory_percent: u8,
    pub disk_used: String,
    pub disk_total: String,
    pub disk_percent: u8,
    pub disk_mount: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceInfo {
    pub name: String,
    pub state: String,
    pub active_since: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DispatchInfo {
    pub queued: u64,
    pub active: u64,
    pub online_runners: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunnerInfo {
    pub display_name: String,
    pub status: String,
    pub last_seen: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowInfo {
    pub name: String,
    pub conclusion: String,
    pub age: String,
}

fn run_remote(ssh: &SshConfig, cmd: &str) -> Result<String> {
    let output = Command::new("ssh")
        .args(ssh.ssh_args())
        .arg(cmd)
        .output()
        .with_context(|| format!("failed to run ssh command: {cmd}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("ssh command failed: {cmd}\n{stderr}");
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn run_local(cmd: &str) -> Result<String> {
    let output = Command::new("sh")
        .arg("-c")
        .arg(cmd)
        .output()
        .with_context(|| format!("failed to run: {cmd}"))?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("command failed: {cmd}\n{stderr}");
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn shell(ssh: Option<&SshConfig>, cmd: &str) -> Result<String> {
    match ssh {
        Some(s) => run_remote(s, cmd),
        None => run_local(cmd),
    }
}

#[allow(clippy::cast_precision_loss)]
fn format_bytes(bytes: u64) -> String {
    const GB: u64 = 1_073_741_824;
    const MB: u64 = 1_048_576;
    if bytes >= GB {
        format!("{:.1}G", bytes as f64 / GB as f64)
    } else {
        format!("{}M", bytes / MB)
    }
}

fn format_duration_seconds(total_seconds: u64) -> String {
    let days = total_seconds / 86400;
    let hours = (total_seconds % 86400) / 3600;
    let minutes = (total_seconds % 3600) / 60;
    let mut parts = Vec::new();
    if days > 0 {
        parts.push(format!("{days}d"));
    }
    if hours > 0 || days > 0 {
        parts.push(format!("{hours}h"));
    }
    parts.push(format!("{minutes}m"));
    parts.join(" ")
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn percent(used: u64, total: u64) -> u8 {
    if total == 0 {
        return 0;
    }
    #[allow(clippy::cast_precision_loss)]
    let ratio = used as f64 / total as f64;
    (ratio * 100.0) as u8
}

fn collect_machine(ssh: Option<&SshConfig>) -> Result<MachineInfo> {
    let hostname = shell(ssh, "uname -n")?;
    let uptime_raw = shell(ssh, "cat /proc/uptime")?;
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let uptime_secs: u64 = uptime_raw
        .split_whitespace()
        .next()
        .and_then(|s| s.parse::<f64>().ok())
        .map_or(0, |f| f as u64);
    let uptime = format_duration_seconds(uptime_secs);
    let load = shell(ssh, "cat /proc/loadavg")?
        .split_whitespace()
        .take(3)
        .collect::<Vec<_>>()
        .join("  ");
    Ok(MachineInfo {
        hostname,
        uptime,
        load,
    })
}

fn collect_hardware(ssh: Option<&SshConfig>) -> Result<HardwareInfo> {
    let cpu_model = shell(ssh, "lscpu | grep 'Model name' | sed 's/.*: *//'")
        .unwrap_or_else(|_| "unknown".to_owned());
    let cpu_cores = shell(ssh, "nproc").unwrap_or_else(|_| "?".to_owned());
    let cpu = format!("{cpu_model} / {cpu_cores} cores");

    let mem_raw = shell(ssh, "free -b | awk '/^Mem:/ {print $2, $3}'")?;
    let mem_parts: Vec<u64> = mem_raw
        .split_whitespace()
        .filter_map(|s| s.parse().ok())
        .collect();
    let (mem_total, mem_used) = if mem_parts.len() >= 2 {
        (mem_parts[0], mem_parts[1])
    } else {
        (0, 0)
    };

    let disk_raw = shell(ssh, "df -B1 /srv | awk 'NR==2 {print $2, $3, $6}'")?;
    let disk_parts: Vec<&str> = disk_raw.split_whitespace().collect();
    let (disk_total, disk_used, disk_mount) = if disk_parts.len() >= 3 {
        let total: u64 = disk_parts[0].parse().unwrap_or(0);
        let used: u64 = disk_parts[1].parse().unwrap_or(0);
        (total, used, disk_parts[2].to_owned())
    } else {
        (0, 0, "/srv".to_owned())
    };

    Ok(HardwareInfo {
        cpu,
        memory_used: format_bytes(mem_used),
        memory_total: format_bytes(mem_total),
        memory_percent: percent(mem_used, mem_total),
        disk_used: format_bytes(disk_used),
        disk_total: format_bytes(disk_total),
        disk_percent: percent(disk_used, disk_total),
        disk_mount,
    })
}

fn collect_services(ssh: Option<&SshConfig>, names: &[String]) -> Vec<ServiceInfo> {
    names
        .iter()
        .map(|name| {
            let state = shell(
                ssh,
                &format!("systemctl show {name} --property=ActiveState --value"),
            )
            .unwrap_or_else(|_| "unknown".to_owned());

            let since = shell(
                ssh,
                &format!("systemctl show {name} --property=ActiveEnterTimestamp --value"),
            )
            .unwrap_or_default();

            let active_since = if since.is_empty() || state != "active" {
                String::new()
            } else {
                parse_active_duration(&since)
            };

            ServiceInfo {
                name: name.clone(),
                state,
                active_since,
            }
        })
        .collect()
}

fn parse_active_duration(timestamp_str: &str) -> String {
    let parsed = chrono::DateTime::parse_from_str(timestamp_str.trim(), "%a %Y-%m-%d %H:%M:%S %Z")
        .or_else(|_| {
            chrono::NaiveDateTime::parse_from_str(timestamp_str.trim(), "%a %Y-%m-%d %H:%M:%S %Z")
                .map(|naive| naive.and_utc().fixed_offset())
        });
    match parsed {
        Ok(dt) => {
            let now = chrono::Utc::now();
            let diff = now.signed_duration_since(dt);
            let secs = diff.num_seconds().unsigned_abs();
            format_duration_seconds(secs)
        }
        Err(_) => timestamp_str.to_owned(),
    }
}

fn collect_dispatch(config: &ReportConfig) -> Result<(DispatchInfo, Vec<RunnerInfo>)> {
    let resp = get_health_blocking(&config.dispatch_url)?;

    let info = DispatchInfo {
        queued: resp.snapshot.queued_jobs,
        active: resp.snapshot.active_jobs,
        online_runners: resp.snapshot.online_runners,
    };

    let runners = resp
        .snapshot
        .runners
        .into_iter()
        .map(|runner| {
            let status = match &runner.current_job_id {
                Some(id) => format!("job#{}", id.rsplit('-').next().unwrap_or(id)),
                None => "idle".to_owned(),
            };
            let last_seen = format_relative_time(&runner.last_seen_at);
            RunnerInfo {
                display_name: runner.display_name,
                status,
                last_seen,
            }
        })
        .collect();

    Ok((info, runners))
}

fn format_relative_time(iso: &str) -> String {
    let Ok(dt) = chrono::DateTime::parse_from_rfc3339(iso) else {
        return iso.to_owned();
    };
    let now = chrono::Utc::now();
    let secs = now.signed_duration_since(dt).num_seconds();
    if secs < 60 {
        format!("last seen {secs}s ago")
    } else if secs < 3600 {
        format!("last seen {}m ago", secs / 60)
    } else if secs < 86400 {
        format!("last seen {}h ago", secs / 3600)
    } else {
        format!("last seen {}d ago", secs / 86400)
    }
}

#[derive(Deserialize)]
struct GithubRunsResponse {
    workflow_runs: Vec<GithubRun>,
}

#[derive(Deserialize)]
struct GithubRun {
    name: String,
    conclusion: Option<String>,
    created_at: String,
    path: String,
}

fn collect_workflows(config: &ReportConfig) -> Result<Vec<WorkflowInfo>> {
    if config.workflows.is_empty() {
        return Ok(Vec::new());
    }

    let url = format!(
        "https://api.github.com/repos/{}/actions/runs?per_page=30",
        config.github_repo
    );
    let client = reqwest::blocking::Client::new();
    let resp: GithubRunsResponse = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", config.github_token))
        .header("User-Agent", "spctr")
        .header("Accept", "application/vnd.github+json")
        .send()
        .with_context(|| "failed to reach GitHub API")?
        .json()
        .with_context(|| "failed to parse GitHub runs response")?;

    let workflow_set: std::collections::HashSet<&str> =
        config.workflows.iter().map(String::as_str).collect();

    let mut seen = std::collections::HashSet::new();
    let mut workflows = Vec::new();

    for run in &resp.workflow_runs {
        let filename = run.path.rsplit('/').next().unwrap_or(&run.path);
        if !workflow_set.contains(filename) {
            continue;
        }
        if !seen.insert(filename.to_owned()) {
            continue;
        }
        let conclusion = run.conclusion.as_deref().unwrap_or("in_progress");
        let display_conclusion = match conclusion {
            "success" => "pass",
            "failure" => "FAIL",
            "cancelled" => "skip",
            other => other,
        };
        workflows.push(WorkflowInfo {
            name: run.name.clone(),
            conclusion: display_conclusion.to_owned(),
            age: format_relative_time(&run.created_at).replace("last seen ", ""),
        });
    }

    Ok(workflows)
}

#[allow(clippy::missing_errors_doc)]
pub fn collect(config: &ReportConfig) -> Result<ReportData> {
    let ssh = config.server_ssh.as_ref();

    let (machine, hardware, services, dispatch_result, workflows) = rayon_join5(
        || collect_machine(ssh),
        || collect_hardware(ssh),
        || Ok::<_, anyhow::Error>(collect_services(ssh, &config.services)),
        || collect_dispatch(config),
        || collect_workflows(config),
    );

    let machine = machine?;
    let hardware = hardware?;
    let services = services?;
    let (dispatch, runners) = dispatch_result?;
    let workflows = workflows?;

    let generated_at = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true);

    Ok(ReportData {
        machine,
        hardware,
        services,
        dispatch,
        runners,
        workflows,
        generated_at,
    })
}

#[allow(clippy::missing_errors_doc)]
pub fn collect_from_cache(path: &str) -> Result<ReportData> {
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read cache file: {path}"))?;
    serde_json::from_str(&text).with_context(|| "failed to parse cached report JSON")
}

const NAME_W: usize = 16;
const DATA_W: usize = 42;
// total inner = NAME_W + 3 (` | `) + DATA_W = 61; outer = 61 + 4 (`| ` + ` |`) = 65

fn bar_graph(pct: u8, width: usize) -> String {
    let filled = (usize::from(pct) * width) / 100;
    let mut bar = String::with_capacity(width * 3);
    for _ in 0..filled {
        bar.push('\u{2588}');
    }
    for _ in filled..width {
        bar.push('\u{2591}');
    }
    bar
}

fn header_top(buf: &mut String) {
    let inner = NAME_W + 3 + DATA_W;
    let _ = write!(buf, "\u{250c}");
    for _ in 0..inner + 2 {
        let _ = write!(buf, "\u{252c}");
    }
    let _ = writeln!(buf, "\u{2510}");
    let _ = write!(buf, "\u{251c}");
    for _ in 0..inner + 2 {
        let _ = write!(buf, "\u{2534}");
    }
    let _ = writeln!(buf, "\u{2524}");
}

fn centered(buf: &mut String, text: &str) {
    let inner = NAME_W + 3 + DATA_W + 2;
    let pad_left = (inner.saturating_sub(text.len())) / 2;
    let pad_right = inner.saturating_sub(text.len()).saturating_sub(pad_left);
    let _ = writeln!(
        buf,
        "\u{2502}{:pad_left$}{text}{:pad_right$}\u{2502}",
        "", "",
    );
}

fn divider(buf: &mut String, left: char, mid: char, right: char) {
    let _ = write!(buf, "{left}");
    for _ in 0..NAME_W + 2 {
        let _ = write!(buf, "\u{2500}");
    }
    let _ = write!(buf, "{mid}");
    for _ in 0..DATA_W + 2 {
        let _ = write!(buf, "\u{2500}");
    }
    let _ = writeln!(buf, "{right}");
}

fn divider_top(buf: &mut String) {
    divider(buf, '\u{251c}', '\u{252c}', '\u{2524}');
}

fn divider_mid(buf: &mut String) {
    divider(buf, '\u{251c}', '\u{253c}', '\u{2524}');
}

fn divider_bot(buf: &mut String) {
    divider(buf, '\u{2514}', '\u{2534}', '\u{2518}');
}

fn truncate_chars(s: &str, max: usize) -> String {
    let char_count = s.chars().count();
    if char_count <= max {
        return s.to_owned();
    }
    let mut out: String = s.chars().take(max - 3).collect();
    out.push_str("...");
    out
}

fn row(buf: &mut String, name: &str, data: &str) {
    let display_name = truncate_chars(name, NAME_W);
    let display_data = truncate_chars(data, DATA_W);
    let _ = writeln!(
        buf,
        "\u{2502} {:<NAME_W$} \u{2502} {:<DATA_W$} \u{2502}",
        display_name, display_data
    );
}

#[must_use]
#[allow(clippy::too_many_lines)]
pub fn format_ascii(data: &ReportData) -> String {
    let mut buf = String::with_capacity(4096);

    header_top(&mut buf);
    centered(&mut buf, "SPECTER LABS");
    centered(&mut buf, "SYSTEMS STATUS");

    divider_top(&mut buf);
    row(&mut buf, "MACHINE", &data.machine.hostname);
    row(&mut buf, "UPTIME", &data.machine.uptime);
    row(&mut buf, "LOAD", &data.machine.load);

    divider_mid(&mut buf);
    row(&mut buf, "CPU", &data.hardware.cpu);
    row(
        &mut buf,
        "MEMORY",
        &format!(
            "{} / {} [{}%]",
            data.hardware.memory_used, data.hardware.memory_total, data.hardware.memory_percent
        ),
    );
    row(
        &mut buf,
        "MEM USAGE",
        &bar_graph(data.hardware.memory_percent, DATA_W),
    );
    row(
        &mut buf,
        "DISK",
        &format!(
            "{} / {} [{}%]  {}",
            data.hardware.disk_used,
            data.hardware.disk_total,
            data.hardware.disk_percent,
            data.hardware.disk_mount
        ),
    );
    row(
        &mut buf,
        "DISK USAGE",
        &bar_graph(data.hardware.disk_percent, DATA_W),
    );

    if !data.services.is_empty() {
        divider_mid(&mut buf);
        for svc in &data.services {
            row(
                &mut buf,
                &svc.name.to_uppercase(),
                &format!("{:<12}{}", svc.state, svc.active_since),
            );
        }
    }

    divider_mid(&mut buf);
    row(&mut buf, "QUEUED", &data.dispatch.queued.to_string());
    row(&mut buf, "ACTIVE", &data.dispatch.active.to_string());
    row(
        &mut buf,
        "ONLINE RUNNERS",
        &data.dispatch.online_runners.to_string(),
    );

    if !data.runners.is_empty() {
        divider_mid(&mut buf);
        for runner in &data.runners {
            row(
                &mut buf,
                &runner.display_name,
                &format!("{:<12}{}", runner.status, runner.last_seen),
            );
        }
    }

    if !data.workflows.is_empty() {
        divider_mid(&mut buf);
        for wf in &data.workflows {
            row(
                &mut buf,
                &wf.name,
                &format!("{:<12}{}", wf.conclusion, wf.age),
            );
        }
    }

    divider_mid(&mut buf);
    row(&mut buf, "GENERATED", &data.generated_at);
    divider_bot(&mut buf);

    buf
}

#[must_use]
pub fn format_html(data: &ReportData) -> String {
    let ascii = format_ascii(data);
    let escaped = ascii
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;");
    format!(
        r#"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Specter Labs -- Systems Status</title>
<style>
body {{ margin: 0; min-height: 100vh; padding: 2rem; background: #0a0a0a; color: #d4d4d4; font-family: "IBM Plex Mono", "Menlo", monospace; display: flex; justify-content: center; }}
pre {{ width: fit-content; max-width: 100%; margin: 0; font-size: 13px; line-height: 1.5; white-space: pre; overflow-x: auto; }}
</style>
</head>
<body>
<pre>{escaped}</pre>
</body>
</html>"#
    )
}

fn rayon_join5<RA, RB, RC, RD, RE, FA, FB, FC, FD, FE>(
    fa: FA,
    fb: FB,
    fc: FC,
    fd: FD,
    fe: FE,
) -> (RA, RB, RC, RD, RE)
where
    FA: FnOnce() -> RA + Send,
    FB: FnOnce() -> RB + Send,
    FC: FnOnce() -> RC + Send,
    FD: FnOnce() -> RD + Send,
    FE: FnOnce() -> RE + Send,
    RA: Send,
    RB: Send,
    RC: Send,
    RD: Send,
    RE: Send,
{
    let ((ra, rb), (rc, (rd, re))) = rayon::join(
        || rayon::join(fa, fb),
        || rayon::join(fc, || rayon::join(fd, fe)),
    );
    (ra, rb, rc, rd, re)
}
