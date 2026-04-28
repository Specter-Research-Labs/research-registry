use crate::design_tokens::DesignTokens;
use anyhow::Result;
use std::collections::BTreeMap;
use std::fmt::Write;

pub fn generate_typst(tokens_fm: &DesignTokens, tokens_paper: &DesignTokens) -> Result<String> {
    // Typst contexts define their own complete token sets (luma/rgb values, not CSS hex).
    // These are NOT merged with base — each context is self-contained.
    //
    let mut out = String::from("#let tokens = (\n");

    emit_fonts(&mut out, tokens_fm);
    out.push('\n');
    emit_raw_section(&mut out, "colors", &tokens_fm.colors, tokens_fm);
    out.push('\n');
    emit_string_map(&mut out, "rules", &tokens_fm.rules);
    out.push('\n');
    emit_string_map(&mut out, "type_scale", &tokens_fm.type_scale);
    out.push('\n');
    emit_string_map(&mut out, "tracking", &tokens_fm.tracking);
    out.push('\n');
    emit_string_map(&mut out, "leading", &tokens_fm.leading);
    out.push('\n');
    emit_layout(&mut out, "layout", &tokens_fm.layout);
    out.push('\n');

    emit_raw_section(&mut out, "paper_colors", &tokens_paper.colors, tokens_paper);
    out.push('\n');
    emit_string_map(&mut out, "paper_rules", &tokens_paper.rules);
    out.push('\n');
    emit_string_map(&mut out, "paper_type_scale", &tokens_paper.type_scale);
    out.push('\n');
    emit_string_map(&mut out, "paper_leading", &tokens_paper.leading);
    out.push('\n');
    emit_layout(&mut out, "paper_layout", &tokens_paper.layout);

    out.push_str(")\n");
    Ok(out)
}

fn emit_fonts(out: &mut String, tokens: &DesignTokens) {
    out.push_str("  fonts: (\n");
    for (role, stack) in &tokens.fonts {
        let family = stack.0.first().map_or("", String::as_str);
        let _ = writeln!(out, "    {}: \"{family}\",", to_typst_key(role));
    }
    out.push_str("  ),\n");
}

fn emit_raw_section(
    out: &mut String,
    section: &str,
    colors: &BTreeMap<String, crate::design_tokens::ColorEntry>,
    tokens: &DesignTokens,
) {
    let _ = writeln!(out, "  {section}: (");
    for (name, entry) in colors {
        let raw = color_entry_raw(entry, tokens);
        let _ = writeln!(out, "    {}: {raw},", to_typst_key(name));
    }
    out.push_str("  ),\n");
}

fn color_entry_raw(entry: &crate::design_tokens::ColorEntry, tokens: &DesignTokens) -> String {
    match entry {
        crate::design_tokens::ColorEntry::Direct(cv) => cv.raw.clone(),
        crate::design_tokens::ColorEntry::Alpha(alpha) => {
            if let Some(base) = tokens.colors.get(&alpha.base) {
                if let crate::design_tokens::ColorEntry::Direct(cv) = base {
                    if let Some(ref parsed) = cv.parsed {
                        let [r, g, b, _] = parsed.to_rgba8();
                        return format!("rgba({r}, {g}, {b}, {})", alpha.alpha);
                    }
                }
            }
            format!("\"unresolved:{}@{}\"", alpha.base, alpha.alpha)
        }
    }
}

fn emit_string_map(out: &mut String, section: &str, map: &BTreeMap<String, String>) {
    if map.is_empty() {
        return;
    }
    let _ = writeln!(out, "  {section}: (");
    for (name, val) in map {
        let _ = writeln!(out, "    {}: {val},", to_typst_key(name));
    }
    out.push_str("  ),\n");
}

fn emit_layout(
    out: &mut String,
    section: &str,
    layout: &BTreeMap<String, crate::design_tokens::LayoutValue>,
) {
    if layout.is_empty() {
        return;
    }

    let _ = writeln!(out, "  {section}: (");

    let mut prev_was_group = false;
    for (key, val) in layout {
        match val {
            crate::design_tokens::LayoutValue::Scalar(s) => {
                if prev_was_group {
                    out.push('\n');
                }
                let _ = writeln!(out, "    {}: {s},", to_typst_key(key));
                prev_was_group = false;
            }
            crate::design_tokens::LayoutValue::Group(members) => {
                if prev_was_group {
                    out.push('\n');
                }
                let _ = writeln!(out, "    {}: (", to_typst_key(key));
                for (sub_key, sub_val) in members {
                    let _ = writeln!(out, "      {}: {sub_val},", to_typst_key(sub_key.as_str()));
                }
                out.push_str("    ),\n");
                prev_was_group = true;
            }
        }
    }

    out.push_str("  ),\n");
}

fn to_typst_key(key: &str) -> String {
    key.replace('-', "_")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_to_typst_key() {
        assert_eq!(to_typst_key("rule-strong"), "rule_strong");
        assert_eq!(to_typst_key("heading-1"), "heading_1");
        assert_eq!(to_typst_key("simple"), "simple");
    }

    #[test]
    fn test_generates_typst_structure() {
        let fm = r##"
[colors]
ink = "luma(8%)"

[fonts]
body = ["IBM Plex Serif"]
mono = ["IBM Plex Mono"]

[type-scale]
body = "10pt"

[leading]
body = "1.32em"

[layout.page-margin]
top = "16mm"
bottom = "18mm"

[layout]
standalone = "10pt"
"##;
        let paper = r##"
[colors]
ink = "luma(10%)"

[type-scale]
body = "10.5pt"

[leading]
body = "1.34em"

[layout.page-margin]
top = "20mm"
bottom = "20mm"
"##;
        let fm_tokens = crate::design_tokens::parse_context(fm).unwrap();
        let paper_tokens = crate::design_tokens::parse_context(paper).unwrap();
        let typst = generate_typst(&fm_tokens, &paper_tokens).unwrap();
        assert!(typst.starts_with("#let tokens = (\n"));
        assert!(typst.contains("ink: luma(8%)"));
        assert!(typst.contains("paper_colors:"));
        assert!(typst.contains("ink: luma(10%)"));
        assert!(typst.contains("page_margin: ("));
        assert!(typst.contains("standalone: 10pt,"));
    }
}
