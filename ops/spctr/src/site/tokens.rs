use anyhow::{bail, Result};
use camino::Utf8Path;
use std::fs;

struct WiringRule {
    path: &'static str,
    import_path: &'static str,
    required_snippets: &'static [&'static str],
}

const WIRING_RULES: &[WiringRule] = &[
    WiringRule {
        path: "site/style.css",
        import_path: "./tokens.css",
        required_snippets: &[
            "--site-ink: var(--sl-color-ink);",
            "--site-muted: var(--sl-color-muted);",
            "--site-rule: var(--sl-color-rule);",
            "--site-rule-strong: var(--sl-color-rule-strong);",
            "font-family: var(--sl-font-mono);",
        ],
    },
    WiringRule {
        path: "site/blog/blog.css",
        import_path: "../tokens.css",
        required_snippets: &[
            "--doc-bg: var(--sl-color-bg);",
            "--doc-paper: var(--sl-color-paper);",
            "--doc-ink: var(--sl-color-ink);",
            "--doc-muted: var(--sl-color-muted);",
            "font-family: var(--sl-font-mono);",
        ],
    },
    WiringRule {
        path: "site/cabinet/cabinet.css",
        import_path: "../tokens.css",
        required_snippets: &[
            "--cab-bg: var(--sl-color-bg);",
            "--cab-paper: var(--sl-color-paper);",
            "--cab-ink: var(--sl-color-ink);",
            "--cab-muted: var(--sl-color-muted);",
            "font-family: var(--sl-font-mono);",
        ],
    },
];

pub fn check_tokens(repo_root: &Utf8Path) -> Result<()> {
    let mut errors: Vec<String> = Vec::new();

    for rule in WIRING_RULES {
        let path = repo_root.join(rule.path);
        let text = read_required(&path, rule.path)?;
        let normalized = normalize_css(&text);

        if !has_tokens_import(&normalized, rule.import_path) {
            errors.push(format!("{} missing required tokens.css import", rule.path));
        }

        for snippet in rule.required_snippets {
            if !normalized.contains(&normalize_css(snippet)) {
                errors.push(format!("{} missing required snippet: {snippet}", rule.path));
            }
        }
    }

    if errors.is_empty() {
        eprintln!("ok: site canonical tokens are wired");
        Ok(())
    } else {
        let detail = errors
            .iter()
            .map(|e| format!("- {e}"))
            .collect::<Vec<_>>()
            .join("\n");
        bail!("site token wiring check failed:\n{detail}");
    }
}

fn read_required(path: &Utf8Path, label: &str) -> Result<String> {
    if !path.is_file() {
        bail!("missing file: {label}");
    }
    Ok(fs::read_to_string(path)?)
}

fn normalize_css(text: &str) -> String {
    text.chars()
        .filter(|ch| !ch.is_ascii_whitespace())
        .collect::<String>()
}

fn has_tokens_import(normalized_css: &str, import_path: &str) -> bool {
    matches_import(
        normalized_css,
        &format!("@import\"{import_path}"),
        "\";",
    ) || matches_import(
        normalized_css,
        &format!("@importurl(\"{import_path}"),
        "\");",
    )
}

fn matches_import(normalized_css: &str, prefix: &str, suffix: &str) -> bool {
    let Some(rest) = normalized_css.strip_prefix(prefix) else {
        return false;
    };
    if rest.starts_with(suffix) {
        return true;
    }
    let Some(query) = rest.strip_prefix('?') else {
        return false;
    };
    let Some(closing) = query.find('"') else {
        return false;
    };
    query[closing..].starts_with(suffix)
}

#[cfg(test)]
mod tests {
    use super::{has_tokens_import, normalize_css};

    #[test]
    fn token_import_accepts_plain_and_url_forms() {
        assert!(has_tokens_import(
            &normalize_css("@import \"./tokens.css\";\n:root{}"),
            "./tokens.css"
        ));
        assert!(has_tokens_import(
            &normalize_css("@import url(\"./tokens.css\");\n:root{}"),
            "./tokens.css"
        ));
    }

    #[test]
    fn token_import_accepts_cache_bust_query_string() {
        assert!(has_tokens_import(
            &normalize_css("@import \"./tokens.css?v=20260518\";\n:root{}"),
            "./tokens.css"
        ));
        assert!(has_tokens_import(
            &normalize_css("@import url(\"./tokens.css?v=20260518\");\n:root{}"),
            "./tokens.css"
        ));
    }

    #[test]
    fn token_import_rejects_wrong_path() {
        assert!(!has_tokens_import(
            &normalize_css("@import \"./other.css\";\n:root{}"),
            "./tokens.css"
        ));
        assert!(!has_tokens_import(
            &normalize_css("@import \"./tokens.css.bak\";\n:root{}"),
            "./tokens.css"
        ));
    }

    #[test]
    fn normalize_css_makes_snippet_checks_whitespace_agnostic() {
        let css = normalize_css(":root { --site-ink:var(--sl-color-ink); }");
        assert!(css.contains(&normalize_css("--site-ink: var(--sl-color-ink);")));
    }
}
