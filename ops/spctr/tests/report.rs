use spctr::report::{
    DispatchInfo, HardwareInfo, MachineInfo, ReportData, RunnerInfo, ServiceInfo, WorkflowInfo,
};

fn sample_data() -> ReportData {
    ReportData {
        machine: MachineInfo {
            hostname: "specter-control-1".into(),
            uptime: "47d 3h 12m".into(),
            load: "0.23  0.41  0.38".into(),
        },
        hardware: HardwareInfo {
            cpu: "AMD EPYC / 8 cores".into(),
            memory_used: "3.2G".into(),
            memory_total: "16.0G".into(),
            memory_percent: 20,
            disk_used: "47.0G".into(),
            disk_total: "200.0G".into(),
            disk_percent: 24,
            disk_mount: "/srv".into(),
        },
        services: vec![
            ServiceInfo {
                name: "caddy".into(),
                state: "active".into(),
                active_since: "3d 12h".into(),
            },
            ServiceInfo {
                name: "specter-dispatch".into(),
                state: "active".into(),
                active_since: "1d 2h".into(),
            },
        ],
        dispatch: DispatchInfo {
            queued: 0,
            active: 1,
            online_runners: 2,
        },
        runners: vec![RunnerInfo {
            display_name: "runner-macos-1".into(),
            status: "idle".into(),
            last_seen: "last seen 4s ago".into(),
        }],
        workflows: vec![WorkflowInfo {
            name: "Deploy site".into(),
            conclusion: "pass".into(),
            age: "2h ago".into(),
        }],
        generated_at: "2026-03-16T14:32:00Z".into(),
    }
}

#[test]
fn ascii_contains_header_and_box_drawing() {
    let output = spctr::report::format_ascii(&sample_data());
    assert!(output.contains("SPECTER LABS"));
    assert!(output.contains("SYSTEMS STATUS"));
    assert!(output.contains("\u{250c}"), "missing top-left corner");
    assert!(output.contains("\u{2518}"), "missing bottom-right corner");
    assert!(output.contains("\u{2502}"), "missing vertical border");
    assert!(output.contains("\u{2500}"), "missing horizontal border");
}

#[test]
fn ascii_contains_all_sections() {
    let output = spctr::report::format_ascii(&sample_data());
    assert!(output.contains("specter-control-1"));
    assert!(output.contains("47d 3h 12m"));
    assert!(output.contains("AMD EPYC / 8 cores"));
    assert!(output.contains("3.2G / 16.0G [20%]"));
    assert!(output.contains("CADDY"));
    assert!(output.contains("runner-macos-1"));
    assert!(output.contains("Deploy site"));
    assert!(output.contains("2026-03-16T14:32:00Z"));
}

#[test]
fn ascii_contains_bar_graphs() {
    let output = spctr::report::format_ascii(&sample_data());
    assert!(output.contains('\u{2588}'), "missing filled bar block");
    assert!(output.contains('\u{2591}'), "missing empty bar block");
}

#[test]
fn html_wraps_ascii_in_pre() {
    let output = spctr::report::format_html(&sample_data());
    assert!(output.contains("<!DOCTYPE html>"));
    assert!(output.contains("<pre>"));
    assert!(output.contains("SPECTER LABS"));
    assert!(output.contains("</pre>"));
}

#[test]
fn json_roundtrip_preserves_data() {
    let data = sample_data();
    let json = serde_json::to_string(&data).unwrap();
    let restored: ReportData = serde_json::from_str(&json).unwrap();
    assert_eq!(data.machine.hostname, restored.machine.hostname);
    assert_eq!(data.dispatch.queued, restored.dispatch.queued);
    assert_eq!(data.runners.len(), restored.runners.len());
    assert_eq!(data.workflows.len(), restored.workflows.len());
}
