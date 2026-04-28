use anyhow::{bail, Result};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LedgerSectionKey {
    Dossiers,
    Addenda,
    Ops,
    Lab,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct LedgerSections {
    pub dossiers: Vec<String>,
    pub addenda: Vec<String>,
    pub ops: Vec<String>,
    pub lab: Vec<String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LedgerEntryDraft {
    pub id: String,
    pub topic: String,
    pub created_at: String,
    pub requested_by_email: Option<String>,
    pub requested_by_name: Option<String>,
    pub sections: LedgerSections,
}

const SECTION_TITLES: &[(LedgerSectionKey, &str)] = &[
    (LedgerSectionKey::Dossiers, "Dossiers"),
    (LedgerSectionKey::Addenda, "Addenda"),
    (LedgerSectionKey::Ops, "Ops / Infra"),
    (LedgerSectionKey::Lab, "Lab News"),
];

fn normalize_header(line: &str) -> Option<LedgerSectionKey> {
    let normalized = line
        .trim()
        .trim_start_matches('#')
        .trim_start()
        .trim_start_matches('*')
        .trim_end_matches('*')
        .trim_end_matches(':')
        .trim()
        .to_ascii_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    match normalized.as_str() {
        "dossier" | "dossiers" => Some(LedgerSectionKey::Dossiers),
        "addendum" | "addenda" => Some(LedgerSectionKey::Addenda),
        "ops" | "ops / infra" | "ops/infra" | "infra" => Some(LedgerSectionKey::Ops),
        "lab news" | "lab" | "labs" => Some(LedgerSectionKey::Lab),
        _ => None,
    }
}

fn normalize_item(line: &str) -> String {
    line.trim()
        .trim_start_matches(['-', '*', '+'])
        .trim()
        .to_owned()
}

fn requestor_label(name: Option<&str>, email: Option<&str>) -> Option<String> {
    match (name, email) {
        (Some(name), Some(email)) => Some(format!("{name} <{email}>")),
        (Some(name), None) => Some(name.to_owned()),
        (None, Some(email)) => Some(email.to_owned()),
        (None, None) => None,
    }
}

pub fn create_ledger_entry_id(created_at: &str) -> String {
    let stamp = created_at
        .chars()
        .filter(|ch| !matches!(ch, '-' | ':' | '.' | 'T' | 'Z'))
        .take(14)
        .collect::<String>();
    format!(
        "ledger-{stamp}-{}",
        &uuid::Uuid::new_v4().simple().to_string()[..6]
    )
}

pub fn parse_ledger_sections(body: &str) -> Result<LedgerSections> {
    let mut sections = LedgerSections::default();
    let mut current: Option<LedgerSectionKey> = None;
    for raw_line in body.lines() {
        let line = raw_line.trim();
        if line.is_empty() {
            continue;
        }
        if let Some(header) = normalize_header(line) {
            current = Some(header);
            continue;
        }
        let Some(section) = current else {
            bail!("Ledger body must start with a section heading: Dossiers, Addenda, Ops, or Lab.");
        };
        let item = normalize_item(line);
        if item.is_empty() {
            continue;
        }
        match section {
            LedgerSectionKey::Dossiers => sections.dossiers.push(item),
            LedgerSectionKey::Addenda => sections.addenda.push(item),
            LedgerSectionKey::Ops => sections.ops.push(item),
            LedgerSectionKey::Lab => sections.lab.push(item),
        }
    }
    let item_count =
        sections.dossiers.len() + sections.addenda.len() + sections.ops.len() + sections.lab.len();
    if item_count == 0 {
        bail!("Ledger body must include at least one added/changed/removed entry.");
    }
    Ok(sections)
}

pub fn format_ledger_entry(entry: &LedgerEntryDraft) -> String {
    let mut lines = vec![
        format!("**Ledger Entry** `{}`", entry.id),
        format!("- timestamp: `{}`", entry.created_at),
        format!("- topic: `{}`", entry.topic),
    ];
    if let Some(requested_by) = requestor_label(
        entry.requested_by_name.as_deref(),
        entry.requested_by_email.as_deref(),
    ) {
        lines.push(format!("- requested by: `{requested_by}`"));
    }
    for (key, title) in SECTION_TITLES {
        let items = match key {
            LedgerSectionKey::Dossiers => &entry.sections.dossiers,
            LedgerSectionKey::Addenda => &entry.sections.addenda,
            LedgerSectionKey::Ops => &entry.sections.ops,
            LedgerSectionKey::Lab => &entry.sections.lab,
        };
        if items.is_empty() {
            continue;
        }
        lines.push(String::new());
        lines.push(format!("**{title}**"));
        lines.extend(items.iter().map(|item| format!("- {item}")));
    }
    lines.join("\n")
}

pub fn build_ledger_post_usage() -> String {
    [
        "Ledger post format:",
        "- `ledger post <topic>`",
        "- add a blank line",
        "- then add section blocks headed by `Dossiers`, `Addenda`, `Ops`, or `Lab`",
        "",
        "Example:",
        "`ledger post weekly / 2026-03-14`",
        "",
        "Dossiers:",
        "- lenia-swarm: added Lenia Lab and discovery gallery.",
        "",
        "Addenda:",
        "- lean-tactic-representation: added runnable addendum.",
        "",
        "Ops:",
        "- added spctr CLI and migrated manifests.",
        "",
        "Lab:",
        "- tightened public site copy.",
    ]
    .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_grouped_section_bodies() {
        let sections = parse_ledger_sections(
            [
                "Dossiers:",
                "- lenia-swarm: added Lenia Lab.",
                "",
                "Addenda:",
                "- lean-tactic-representation: added runnable addendum.",
                "",
                "Ops:",
                "- added spctr CLI.",
                "",
                "Lab:",
                "- tightened public site copy.",
            ]
            .join("\n")
            .as_str(),
        )
        .unwrap();

        assert_eq!(
            sections,
            LedgerSections {
                dossiers: vec!["lenia-swarm: added Lenia Lab.".to_owned()],
                addenda: vec!["lean-tactic-representation: added runnable addendum.".to_owned()],
                ops: vec!["added spctr CLI.".to_owned()],
                lab: vec!["tightened public site copy.".to_owned()],
            }
        );
    }

    #[test]
    fn renders_formal_ledger_entries() {
        let message = format_ledger_entry(&LedgerEntryDraft {
            id: "ledger-20260314-220501-a1b2c3".to_owned(),
            topic: "weekly / 2026-03-14".to_owned(),
            created_at: "2026-03-14T22:05:01.000Z".to_owned(),
            requested_by_email: Some("operator@example.invalid".to_owned()),
            requested_by_name: Some("Operator".to_owned()),
            sections: LedgerSections {
                dossiers: vec!["lenia-swarm: added Lenia Lab.".to_owned()],
                addenda: Vec::new(),
                ops: vec!["added spctr CLI.".to_owned()],
                lab: Vec::new(),
            },
        });

        assert!(message.contains("**Ledger Entry** `ledger-20260314-220501-a1b2c3`"));
        assert!(message.contains("- timestamp: `2026-03-14T22:05:01.000Z`"));
        assert!(message.contains("- topic: `weekly / 2026-03-14`"));
        assert!(message.contains("- requested by: `Operator <operator@example.invalid>`"));
        assert!(message.contains("**Dossiers**"));
        assert!(message.contains("- lenia-swarm: added Lenia Lab."));
        assert!(message.contains("**Ops / Infra**"));
        assert!(message.contains("- added spctr CLI."));
    }

    #[test]
    fn provides_concrete_usage_template() {
        let usage = build_ledger_post_usage();
        assert!(usage.contains("ledger post <topic>"));
        assert!(usage.contains("Dossiers:"));
        assert!(usage.contains("Ops:"));
    }
}
