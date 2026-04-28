use crate::dispatch::surfaces::list_surfaces;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ParsedCommand {
    Help,
    StatusHealth,
    StatusQueue,
    StatusRunners,
    StatusCommands,
    StatusJob {
        job_id: String,
    },
    Publish {
        project: String,
        action: Option<String>,
        args: Vec<String>,
    },
    LedgerPost {
        topic: String,
        body: String,
    },
    LedgerPostInvalid {
        message: String,
    },
    Cancel {
        job_id: String,
    },
    Rerun {
        job_id: String,
    },
    NotEnabled {
        feature: String,
    },
}

pub fn strip_bot_mention(content: &str) -> String {
    regex_lite::Regex::new(r"^(@\*\*[^*]+\*\*\s*)+")
        .expect("regex is valid")
        .replace(content, "")
        .trim()
        .to_owned()
}

pub fn parse_command(content: &str) -> ParsedCommand {
    let normalized = strip_bot_mention(content);
    if normalized.is_empty() {
        return ParsedCommand::Help;
    }
    if let Some(command) = parse_ledger_post(&normalized) {
        return command;
    }
    let tokens = tokenize(&normalized);
    let Some(command) = tokens.first() else {
        return ParsedCommand::Help;
    };
    let rest = &tokens[1..];
    match command.to_ascii_lowercase().as_str() {
        "help" | "commands" => ParsedCommand::Help,
        "status" => match rest.first().map(|value| value.to_ascii_lowercase()) {
            None => ParsedCommand::StatusHealth,
            Some(value) if value == "health" => ParsedCommand::StatusHealth,
            Some(value) if value == "queue" || value == "jobs" => ParsedCommand::StatusQueue,
            Some(value) if value == "runners" => ParsedCommand::StatusRunners,
            Some(value) if value == "commands" || value == "presets" => {
                ParsedCommand::StatusCommands
            }
            Some(_) => ParsedCommand::StatusJob {
                job_id: rest[0].clone(),
            },
        },
        "publish" => {
            if rest.is_empty() {
                return ParsedCommand::Help;
            }
            if rest.len() >= 2 && !rest[1].starts_with('-') {
                ParsedCommand::Publish {
                    project: rest[0].clone(),
                    action: Some(rest[1].clone()),
                    args: rest[2..].to_vec(),
                }
            } else {
                ParsedCommand::Publish {
                    project: rest[0].clone(),
                    action: None,
                    args: rest[1..].to_vec(),
                }
            }
        }
        "cancel" => rest
            .first()
            .map_or(ParsedCommand::Help, |job_id| ParsedCommand::Cancel {
                job_id: job_id.clone(),
            }),
        "rerun" => rest
            .first()
            .map_or(ParsedCommand::Help, |job_id| ParsedCommand::Rerun {
                job_id: job_id.clone(),
            }),
        "run" | "gh" | "gate" | "summarize" | "triage" => ParsedCommand::NotEnabled {
            feature: command.to_ascii_lowercase(),
        },
        _ => ParsedCommand::Help,
    }
}

pub fn build_help_message() -> String {
    let example_lines = list_surfaces()
        .into_iter()
        .map(|surface| format!("- `{}`", surface.synopsis))
        .collect::<Vec<_>>()
        .join("\n");
    [
        "Available commands:",
        "- `status health`",
        "- `status queue`",
        "- `status runners`",
        "- `status commands`",
        "- `status <job-id>`",
        "- `publish site [--release-id <id>]`",
        "- `cancel <job-id>`",
        "- `rerun <job-id>`",
        "",
        "Mutating commands (`publish`, `ledger post`, `cancel`, `rerun`) are restricted to configured admin emails.",
        "- `ledger post <topic>` followed by a blank line and grouped section entries",
        "",
        "Examples:",
        &example_lines,
        "",
        "This dispatch build only queues canonical site publishes.",
    ]
    .join("\n")
}

fn tokenize(content: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut quote: Option<char> = None;
    let mut chars = content.chars().peekable();
    while let Some(ch) = chars.next() {
        if let Some(active) = quote {
            if ch == active {
                quote = None;
                continue;
            }
            if ch == '\\' && active == '"' {
                if let Some(next) = chars.next() {
                    current.push(next);
                }
                continue;
            }
            current.push(ch);
            continue;
        }
        if ch == '\'' || ch == '"' {
            quote = Some(ch);
            continue;
        }
        if ch.is_whitespace() {
            if !current.is_empty() {
                tokens.push(std::mem::take(&mut current));
            }
            continue;
        }
        current.push(ch);
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}

fn parse_ledger_post(content: &str) -> Option<ParsedCommand> {
    let suffix = regex_lite::Regex::new(r"(?is)^ledger\s+post\b([\s\S]*)$")
        .expect("regex is valid")
        .captures(content)
        .and_then(|caps| caps.get(1))
        .map(|m| m.as_str())?;
    let remainder = suffix.trim_start();
    if remainder.is_empty() {
        return Some(ParsedCommand::LedgerPostInvalid {
            message: "Missing ledger topic.".to_owned(),
        });
    }
    let parts = regex_lite::Regex::new(r"\n\s*\n")
        .expect("regex is valid")
        .split(remainder)
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let topic = parts.first().map_or("", |value| value.trim()).to_owned();
    let body = parts
        .iter()
        .skip(1)
        .map(String::as_str)
        .collect::<Vec<_>>()
        .join("\n\n");
    let body = body.trim().to_owned();
    if topic.is_empty() {
        return Some(ParsedCommand::LedgerPostInvalid {
            message: "Missing ledger topic.".to_owned(),
        });
    }
    if body.is_empty() {
        return Some(ParsedCommand::LedgerPostInvalid {
            message: "Ledger post requires a blank line followed by section blocks.".to_owned(),
        });
    }
    Some(ParsedCommand::LedgerPost { topic, body })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_leading_bot_mentions() {
        assert_eq!(
            strip_bot_mention("@**specter-bot** status health"),
            "status health"
        );
    }

    #[test]
    fn parses_publish_commands() {
        assert_eq!(
            parse_command("publish site --release-id auto"),
            ParsedCommand::Publish {
                project: "site".to_owned(),
                action: None,
                args: vec!["--release-id".to_owned(), "auto".to_owned()],
            }
        );
        assert_eq!(
            parse_command("publish site"),
            ParsedCommand::Publish {
                project: "site".to_owned(),
                action: None,
                args: Vec::new(),
            }
        );
    }

    #[test]
    fn flags_removed_command_families_as_not_enabled() {
        assert_eq!(
            parse_command("run wonton-soup lean-run --mode research --provider reprover --sample 100 --seed 7"),
            ParsedCommand::NotEnabled {
                feature: "run".to_owned(),
            }
        );
        assert_eq!(
            parse_command("gh workflow run --workflow site-projects.yml --ref main"),
            ParsedCommand::NotEnabled {
                feature: "gh".to_owned(),
            }
        );
    }

    #[test]
    fn parses_status_variants() {
        assert_eq!(parse_command("status"), ParsedCommand::StatusHealth);
        assert_eq!(parse_command("status queue"), ParsedCommand::StatusQueue);
        assert_eq!(
            parse_command("status runners"),
            ParsedCommand::StatusRunners
        );
        assert_eq!(
            parse_command("status commands"),
            ParsedCommand::StatusCommands
        );
        assert_eq!(
            parse_command("status presets"),
            ParsedCommand::StatusCommands
        );
    }

    #[test]
    fn parses_ledger_post_commands() {
        assert_eq!(
            parse_command(
                [
                    "ledger post weekly / 2026-03-14",
                    "",
                    "Dossiers:",
                    "- lenia-swarm: added Lenia Lab.",
                ]
                .join("\n")
                .as_str(),
            ),
            ParsedCommand::LedgerPost {
                topic: "weekly / 2026-03-14".to_owned(),
                body: ["Dossiers:", "- lenia-swarm: added Lenia Lab."].join("\n"),
            }
        );
    }

    #[test]
    fn flags_invalid_ledger_post_commands() {
        assert_eq!(
            parse_command("ledger post weekly / 2026-03-14"),
            ParsedCommand::LedgerPostInvalid {
                message: "Ledger post requires a blank line followed by section blocks.".to_owned(),
            }
        );
    }

    #[test]
    fn help_mentions_supported_surfaces() {
        let help = build_help_message();
        assert!(help.contains("status commands"));
        assert!(help.contains("publish site [--release-id <id>]"));
        assert!(help.contains("only queues canonical site publishes"));
        assert!(help.contains("ledger post <topic>"));
    }
}
