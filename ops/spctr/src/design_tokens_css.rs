use crate::design_tokens::{ColorEntry, DesignTokens, LayoutValue};
use anyhow::{bail, Result};
use std::fmt::Write;

pub fn generate_css(tokens: &DesignTokens) -> Result<String> {
    let mut out = String::from(
        "\
/* Generated from addenda/design-tokens/ — do not edit by hand.
   Source: base.toml (colors, symbols, badges, fonts), web.toml (layout, type scale)
   Regenerate: spctr tokens generate --target css */
:root {\n",
    );

    emit_fonts(&mut out, tokens);
    out.push('\n');
    emit_colors(&mut out, tokens)?;
    out.push('\n');
    emit_color_groups(&mut out, tokens)?;
    out.push('\n');
    emit_overlays(&mut out, tokens)?;
    out.push('\n');
    emit_shadows(&mut out, tokens);
    if !tokens.layout.is_empty() {
        out.push('\n');
        emit_layout(&mut out, tokens);
    }
    if !tokens.type_scale.is_empty() {
        out.push('\n');
        emit_string_map(&mut out, "type-scale", &tokens.type_scale);
    }
    if !tokens.tracking.is_empty() {
        out.push('\n');
        emit_string_map(&mut out, "tracking", &tokens.tracking);
    }
    if !tokens.leading.is_empty() {
        out.push('\n');
        emit_string_map(&mut out, "leading", &tokens.leading);
    }

    out.push_str("}\n");
    Ok(out)
}

fn emit_fonts(out: &mut String, tokens: &DesignTokens) {
    for (role, stack) in &tokens.fonts {
        let formatted: Vec<String> = stack
            .0
            .iter()
            .map(|family| {
                if family.contains(' ') {
                    format!("\"{family}\"")
                } else {
                    family.clone()
                }
            })
            .collect();

        let joined = formatted.join(", ");
        if joined.len() > 60 {
            let _ = write!(out, "    --sl-font-{role}:\n");
            emit_wrapped_list(out, &formatted, 8, 72);
        } else {
            let _ = writeln!(out, "    --sl-font-{role}: {joined};");
        }
    }
}

fn emit_wrapped_list(out: &mut String, items: &[String], indent: usize, max_width: usize) {
    let pad: String = " ".repeat(indent);
    let mut line = pad.clone();
    for (i, item) in items.iter().enumerate() {
        let suffix = if i < items.len() - 1 { ", " } else { ";" };
        let candidate = format!("{item}{suffix}");
        if line.len() + candidate.len() > max_width && line.len() > indent {
            out.push_str(line.trim_end());
            out.push('\n');
            line = pad.clone();
        }
        line.push_str(&candidate);
    }
    out.push_str(line.trim_end());
    out.push('\n');
}

fn emit_colors(out: &mut String, tokens: &DesignTokens) -> Result<()> {
    for (name, entry) in &tokens.colors {
        let css_val = resolve_color_to_css(name, entry, tokens)?;
        let _ = writeln!(out, "    --sl-color-{name}: {css_val};");
    }
    Ok(())
}

fn emit_color_groups(out: &mut String, tokens: &DesignTokens) -> Result<()> {
    for (group, entries) in &tokens.color_groups {
        let prefix = css_group_prefix(group);
        for (name, entry) in entries {
            let css_val = resolve_color_to_css(name, entry, tokens)?;
            let _ = writeln!(out, "    --sl-color-{prefix}-{name}: {css_val};");
        }
    }

    if !tokens.workflow_colors.is_empty() {
        for (name, wf) in &tokens.workflow_colors {
            let _ = writeln!(
                out,
                "    --sl-color-workflow-{name}-stroke: {};",
                wf.stroke.raw
            );
            let _ = writeln!(out, "    --sl-color-workflow-{name}-fill: {};", wf.fill.raw);
        }
    }

    Ok(())
}

fn css_group_prefix(group: &str) -> String {
    match group {
        "cabinet" => "cab".to_owned(),
        other => other.to_owned(),
    }
}

fn resolve_color_to_css(name: &str, entry: &ColorEntry, tokens: &DesignTokens) -> Result<String> {
    match entry {
        ColorEntry::Direct(cv) => Ok(cv.raw.clone()),
        ColorEntry::Alpha(alpha) => {
            let base = tokens.colors.get(&alpha.base).ok_or_else(|| {
                anyhow::anyhow!("unresolved base color for {name}: {}", alpha.base)
            })?;
            match base {
                ColorEntry::Direct(cv) => {
                    let parsed = cv.parsed.as_ref().ok_or_else(|| {
                        anyhow::anyhow!("base color {} has no parsed CSS value", alpha.base)
                    })?;
                    let [r, g, b, _] = parsed.to_rgba8();
                    Ok(format!(
                        "rgba({r}, {g}, {b}, {})",
                        format_alpha(alpha.alpha)
                    ))
                }
                ColorEntry::Alpha(_) => {
                    bail!(
                        "alpha color {name} references another alpha color: {}",
                        alpha.base
                    )
                }
            }
        }
    }
}

fn emit_overlays(out: &mut String, tokens: &DesignTokens) -> Result<()> {
    let Some(ref overlays) = tokens.overlays else {
        return Ok(());
    };

    let base_color = crate::design_tokens::resolve_base_color(tokens, &overlays.base)?;
    let [r, g, b, _] = base_color.to_rgba8();

    for &stop in &overlays.stops {
        let label = overlay_label(stop);
        let _ = writeln!(
            out,
            "    --sl-overlay-{}-{label}: rgba({r}, {g}, {b}, {});",
            overlays.base,
            format_alpha(stop)
        );
    }
    Ok(())
}

fn emit_shadows(out: &mut String, tokens: &DesignTokens) {
    for (name, template) in &tokens.shadows {
        let resolved = resolve_shadow_template(template, tokens);
        if resolved.len() > 60 {
            let parts: Vec<&str> = resolved.split(", ").collect();
            if parts.len() > 1 {
                let _ = write!(out, "    --sl-shadow-{name}:\n");
                for (i, part) in parts.iter().enumerate() {
                    let suffix = if i < parts.len() - 1 { "," } else { ";" };
                    let _ = writeln!(out, "        {part}{suffix}");
                }
            } else {
                let _ = writeln!(out, "    --sl-shadow-{name}: {resolved};");
            }
        } else {
            let _ = writeln!(out, "    --sl-shadow-{name}: {resolved};");
        }
    }
}

fn resolve_shadow_template(template: &str, tokens: &DesignTokens) -> String {
    let overlay_base = tokens
        .overlays
        .as_ref()
        .map(|o| o.base.as_str())
        .unwrap_or("ink");

    let re = regex_lite::Regex::new(r"\{overlay\.([^}]+)\}").expect("valid regex");
    re.replace_all(template, |caps: &regex_lite::Captures<'_>| {
        let stop_str = &caps[1];
        let stop_val: f64 = stop_str.parse().unwrap_or(0.0);
        let label = overlay_label(stop_val / 100.0);
        format!("var(--sl-overlay-{overlay_base}-{label})")
    })
    .to_string()
}

fn emit_layout(out: &mut String, tokens: &DesignTokens) {
    for (name, value) in &tokens.layout {
        match value {
            LayoutValue::Scalar(s) => {
                let _ = writeln!(out, "    --sl-layout-{name}: {s};");
            }
            LayoutValue::Group(group) => {
                for (sub, s) in group {
                    let _ = writeln!(out, "    --sl-layout-{name}-{sub}: {s};");
                }
            }
        }
    }
}

fn emit_string_map(
    out: &mut String,
    prefix: &str,
    map: &std::collections::BTreeMap<String, String>,
) {
    for (name, value) in map {
        let _ = writeln!(out, "    --sl-{prefix}-{name}: {value};");
    }
}

fn overlay_label(stop: f64) -> String {
    let scaled = stop * 100.0;
    let rounded = (scaled * 10.0).round() / 10.0;
    if (rounded - rounded.floor()).abs() < f64::EPSILON {
        format!("{}", rounded as u32)
    } else {
        let int_part = rounded as u32;
        let frac_part = ((rounded - f64::from(int_part)) * 10.0).round() as u32;
        format!("{int_part}-{frac_part}")
    }
}

fn format_alpha(alpha: f64) -> String {
    let s = format!("{alpha}");
    if s.contains('.') {
        s.trim_end_matches('0').trim_end_matches('.').to_owned()
    } else {
        s
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_overlay_label() {
        assert_eq!(overlay_label(0.02), "2");
        assert_eq!(overlay_label(0.025), "2-5");
        assert_eq!(overlay_label(0.03), "3");
        assert_eq!(overlay_label(0.06), "6");
        assert_eq!(overlay_label(0.12), "12");
        assert_eq!(overlay_label(0.32), "32");
        assert_eq!(overlay_label(0.82), "82");
    }

    #[test]
    fn test_format_alpha() {
        assert_eq!(format_alpha(0.68), "0.68");
        assert_eq!(format_alpha(0.18), "0.18");
        assert_eq!(format_alpha(0.025), "0.025");
        assert_eq!(format_alpha(0.02), "0.02");
    }

    #[test]
    fn test_generates_valid_css() {
        let spec = r##"
[colors]
ink = "#0b0e14"
paper = "#ffffff"

[colors.alpha]
muted = { base = "ink", alpha = 0.68 }

[fonts]
mono = ["Berkeley Mono", "ui-monospace", "monospace"]

[overlays]
base = "ink"
stops = [0.02, 0.06]

[shadows]
raised = "0 2px 0 {overlay.06}"
"##;
        let tokens = crate::design_tokens::parse_base(spec).unwrap();
        let css = generate_css(&tokens).unwrap();
        assert!(css.contains("--sl-font-mono:"));
        assert!(css.contains("--sl-color-ink: #0b0e14;"));
        assert!(css.contains("--sl-color-muted: rgba(11, 14, 20, 0.68);"));
        assert!(css.contains("--sl-overlay-ink-2: rgba(11, 14, 20, 0.02);"));
        assert!(css.contains("--sl-overlay-ink-6: rgba(11, 14, 20, 0.06);"));
        assert!(css.contains("var(--sl-overlay-ink-6)"));
    }
}
