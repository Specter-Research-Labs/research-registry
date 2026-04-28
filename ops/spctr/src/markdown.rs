use std::collections::HashMap;

#[must_use]
pub fn parse_front_matter(text: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();
    let mut lines = text.lines();
    let first = match lines.next() {
        Some(l) if l.trim() == "---" => true,
        _ => return map,
    };
    if !first {
        return map;
    }
    for line in lines {
        if line.trim() == "---" {
            break;
        }
        if let Some(colon) = line.find(':') {
            let key = line[..colon].trim().to_owned();
            let mut value = line[colon + 1..].trim().to_owned();
            if value.len() >= 2 {
                let first_ch = value.as_bytes()[0];
                let last_ch = value.as_bytes()[value.len() - 1];
                if first_ch == last_ch && (first_ch == b'\'' || first_ch == b'"') {
                    let unquoted = value[1..value.len() - 1].trim().to_owned();
                    value = unquoted;
                }
            }
            map.insert(key, value);
        }
    }
    map
}

#[must_use]
pub fn extract_title(text: &str) -> String {
    let mut in_front_matter = text.starts_with("---\n") || text.starts_with("---\r");
    let mut past_fm = !in_front_matter;
    for line in text.lines().skip(usize::from(in_front_matter)) {
        if in_front_matter {
            if line.trim() == "---" {
                in_front_matter = false;
                past_fm = true;
            }
            continue;
        }
        if !past_fm {
            continue;
        }
        if let Some(title) = line.strip_prefix("# ") {
            return title.trim().to_owned();
        }
    }
    String::new()
}

#[must_use]
pub fn extract_summary(text: &str, front_matter: &HashMap<String, String>) -> String {
    if let Some(summary) = front_matter.get("summary") {
        if !summary.is_empty() {
            return summary.clone();
        }
    }
    let mut in_front_matter = text.starts_with("---\n") || text.starts_with("---\r");
    let mut saw_h1 = false;
    let mut in_code_fence = false;
    let mut current: Vec<String> = Vec::new();
    let mut paragraphs: Vec<String> = Vec::new();

    let skip = usize::from(in_front_matter);
    for line in text.lines().skip(skip) {
        let stripped = line.trim();
        if in_front_matter {
            if stripped == "---" {
                in_front_matter = false;
            }
            continue;
        }
        if stripped.starts_with("```") || stripped.starts_with("~~~") {
            in_code_fence = !in_code_fence;
            continue;
        }
        if in_code_fence {
            continue;
        }
        if !saw_h1 {
            if stripped.starts_with("# ") {
                saw_h1 = true;
            }
            continue;
        }
        if stripped.is_empty() {
            if !current.is_empty() {
                paragraphs.push(current.join(" "));
                current.clear();
            }
            continue;
        }
        if stripped.starts_with('#') || stripped.starts_with("![") {
            if !current.is_empty() {
                paragraphs.push(current.join(" "));
                current.clear();
            }
            continue;
        }
        current.push(stripped.to_owned());
    }
    if !current.is_empty() {
        paragraphs.push(current.join(" "));
    }
    for paragraph in &paragraphs {
        let cleaned = strip_markdown_inline(paragraph);
        if cleaned.is_empty() || cleaned.ends_with(':') || cleaned.ends_with('?') {
            continue;
        }
        return cleaned;
    }
    String::new()
}

fn strip_markdown_inline(text: &str) -> String {
    let mut s = text.to_owned();
    let link_re = regex_lite::Regex::new(r"\[([^\]]+)\]\([^)]+\)").unwrap();
    s = link_re.replace_all(&s, "$1").to_string();
    let code_re = regex_lite::Regex::new(r"`([^`]+)`").unwrap();
    s = code_re.replace_all(&s, "$1").to_string();
    s = s.replace(['*', '_'], "");
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}
