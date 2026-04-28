use crate::design_tokens::{ColorEntry, DesignTokens};
use anyhow::Result;
use std::collections::BTreeMap;

pub fn generate_email_json(tokens: &DesignTokens) -> Result<String> {
    let mut map: BTreeMap<String, String> = BTreeMap::new();

    for (name, entry) in &tokens.colors {
        map.insert(name.clone(), flatten_color(entry, tokens));
    }

    for (group, entries) in &tokens.color_groups {
        for (name, entry) in entries {
            map.insert(format!("{group}-{name}"), flatten_color(entry, tokens));
        }
    }

    for (name, stack) in &tokens.fonts {
        let val = stack.0.join(", ");
        map.insert(format!("font-{name}"), val);
    }

    Ok(serde_json::to_string_pretty(&map)?)
}

fn flatten_color(entry: &ColorEntry, tokens: &DesignTokens) -> String {
    match entry {
        ColorEntry::Direct(cv) => {
            if let Some(ref parsed) = cv.parsed {
                let [r, g, b, _] = parsed.to_rgba8();
                return format!("#{r:02x}{g:02x}{b:02x}");
            }
            cv.raw.clone()
        }
        ColorEntry::Alpha(alpha) => {
            if let Some(ColorEntry::Direct(cv)) = tokens.colors.get(&alpha.base) {
                if let Some(ref parsed) = cv.parsed {
                    let [br, bg, bb, _] = parsed.to_rgba8();
                    let a = alpha.alpha;
                    let r = blend(br, a);
                    let g = blend(bg, a);
                    let b = blend(bb, a);
                    return format!("#{r:02x}{g:02x}{b:02x}");
                }
            }
            format!("unresolved:{}", alpha.base)
        }
    }
}

fn blend(channel: u8, alpha: f64) -> u8 {
    let fg = f64::from(channel);
    let bg = 255.0;
    let blended = fg * alpha + bg * (1.0 - alpha);
    blended.round().clamp(0.0, 255.0) as u8
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_blend_against_white() {
        assert_eq!(blend(0, 1.0), 0);
        assert_eq!(blend(0, 0.0), 255);
        assert_eq!(blend(11, 0.68), 89);
    }

    #[test]
    fn test_generates_json() {
        let spec = r##"
[colors]
ink = "#0b0e14"

[colors.alpha]
muted = { base = "ink", alpha = 0.68 }

[fonts]
mono = ["Menlo", "monospace"]
"##;
        let tokens = crate::design_tokens::parse_base(spec).unwrap();
        let json = generate_email_json(&tokens).unwrap();
        let parsed: BTreeMap<String, String> = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["ink"], "#0b0e14");
        assert!(parsed.contains_key("muted"));
        assert!(parsed.contains_key("font-mono"));
    }
}
