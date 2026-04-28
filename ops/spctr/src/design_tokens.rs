use anyhow::{bail, Context, Result};
use camino::{Utf8Path, Utf8PathBuf};
use std::collections::BTreeMap;

#[derive(Clone, Debug)]
pub struct ColorValue {
    pub raw: String,
    pub parsed: Option<csscolorparser::Color>,
}

impl ColorValue {
    fn from_css(raw: &str) -> Self {
        let parsed = csscolorparser::parse(raw).ok();
        Self {
            raw: raw.to_owned(),
            parsed,
        }
    }

    fn from_raw(raw: &str) -> Self {
        Self {
            raw: raw.to_owned(),
            parsed: None,
        }
    }
}

#[derive(Clone, Debug)]
pub struct AlphaColor {
    pub base: String,
    pub alpha: f64,
}

#[derive(Clone, Debug)]
pub enum ColorEntry {
    Direct(ColorValue),
    Alpha(AlphaColor),
}

#[derive(Clone, Debug)]
pub struct WorkflowColor {
    pub stroke: ColorValue,
    pub fill: ColorValue,
}

#[derive(Clone, Debug)]
pub struct FontStack(pub Vec<String>);

#[derive(Clone, Debug)]
pub struct Symbol {
    pub glyph: String,
    pub label: Option<String>,
}

#[derive(Clone, Debug)]
pub struct BadgeStyle {
    pub color: String,
    pub symbol: Option<String>,
}

#[derive(Clone, Debug)]
pub struct BadgeVocabulary {
    pub dossier: Option<Vec<String>>,
    pub addenda: Option<Vec<String>>,
    pub values: Option<Vec<String>>,
    pub styles: BTreeMap<String, BadgeStyle>,
}

#[derive(Clone, Debug)]
pub enum LayoutValue {
    Scalar(String),
    Group(BTreeMap<String, String>),
}

#[derive(Clone, Debug)]
pub struct OverlaySpec {
    pub base: String,
    pub stops: Vec<f64>,
}

#[derive(Clone, Debug, Default)]
pub struct DesignTokens {
    pub colors: BTreeMap<String, ColorEntry>,
    pub color_groups: BTreeMap<String, BTreeMap<String, ColorEntry>>,
    pub workflow_colors: BTreeMap<String, WorkflowColor>,
    pub overlays: Option<OverlaySpec>,
    pub shadows: BTreeMap<String, String>,
    pub fonts: BTreeMap<String, FontStack>,
    pub symbols: BTreeMap<String, Symbol>,
    pub badges: BTreeMap<String, BadgeVocabulary>,
    pub layout: BTreeMap<String, LayoutValue>,
    pub rules: BTreeMap<String, String>,
    pub type_scale: BTreeMap<String, String>,
    pub tracking: BTreeMap<String, String>,
    pub leading: BTreeMap<String, String>,
}

pub fn load_spec(spec_dir: &Utf8Path, context: &str) -> Result<DesignTokens> {
    let base_path = spec_dir.join("base.toml");
    let base_text = std::fs::read_to_string(&base_path)
        .with_context(|| format!("failed to read {}", base_path))?;
    let base = parse_base(&base_text)?;

    let ctx_path = spec_dir.join(format!("{context}.toml"));
    if !ctx_path.is_file() {
        return Ok(base);
    }
    let ctx_text = std::fs::read_to_string(&ctx_path)
        .with_context(|| format!("failed to read {}", ctx_path))?;
    let ctx = parse_context(&ctx_text)?;
    Ok(merge(&base, &ctx))
}

pub fn load_context_only(spec_dir: &Utf8Path, context: &str) -> Result<DesignTokens> {
    let ctx_path = spec_dir.join(format!("{context}.toml"));
    let ctx_text = std::fs::read_to_string(&ctx_path)
        .with_context(|| format!("failed to read {}", ctx_path))?;
    parse_context(&ctx_text)
}

pub fn parse_base(toml_str: &str) -> Result<DesignTokens> {
    let value: toml::Value = toml_str.parse().context("invalid TOML")?;
    let root = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("TOML root must be a table"))?;
    parse_tokens(root, true)
}

pub fn parse_context(toml_str: &str) -> Result<DesignTokens> {
    let value: toml::Value = toml_str.parse().context("invalid TOML")?;
    let root = value
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("TOML root must be a table"))?;
    parse_tokens(root, false)
}

fn parse_tokens(root: &toml::Table, parse_css: bool) -> Result<DesignTokens> {
    let mut tokens = DesignTokens::default();

    if let Some(colors) = root.get("colors").and_then(|v| v.as_table()) {
        parse_colors_table(colors, &mut tokens, parse_css)?;
    }

    if let Some(overlays) = root.get("overlays").and_then(|v| v.as_table()) {
        let base = overlays
            .get("base")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("overlays.base must be a string"))?;
        let stops = overlays
            .get("stops")
            .and_then(|v| v.as_array())
            .ok_or_else(|| anyhow::anyhow!("overlays.stops must be an array"))?
            .iter()
            .map(|v| {
                v.as_float()
                    .or_else(|| v.as_integer().map(|i| i as f64))
                    .ok_or_else(|| anyhow::anyhow!("overlay stop must be a number"))
            })
            .collect::<Result<Vec<_>>>()?;
        tokens.overlays = Some(OverlaySpec {
            base: base.to_owned(),
            stops,
        });
    }

    if let Some(shadows) = root.get("shadows").and_then(|v| v.as_table()) {
        for (key, val) in shadows {
            let s = val
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("shadows.{key} must be a string"))?;
            tokens.shadows.insert(key.clone(), s.to_owned());
        }
    }

    if let Some(fonts) = root.get("fonts").and_then(|v| v.as_table()) {
        for (key, val) in fonts {
            let families = val
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("fonts.{key} must be an array"))?
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(String::from)
                        .ok_or_else(|| anyhow::anyhow!("font family must be a string"))
                })
                .collect::<Result<Vec<_>>>()?;
            tokens.fonts.insert(key.clone(), FontStack(families));
        }
    }

    if let Some(symbols) = root.get("symbols").and_then(|v| v.as_table()) {
        for (key, val) in symbols {
            let sym = parse_symbol(key, val)?;
            tokens.symbols.insert(key.clone(), sym);
        }
    }

    if let Some(badges) = root.get("badges").and_then(|v| v.as_table()) {
        for (key, val) in badges {
            let vocab = parse_badge_vocabulary(key, val)?;
            tokens.badges.insert(key.clone(), vocab);
        }
    }

    parse_layout_map(root, &mut tokens.layout)?;
    parse_string_map(root, "rules", &mut tokens.rules)?;
    parse_string_map(root, "type-scale", &mut tokens.type_scale)?;
    parse_string_map(root, "tracking", &mut tokens.tracking)?;
    parse_string_map(root, "leading", &mut tokens.leading)?;

    Ok(tokens)
}

fn parse_colors_table(
    colors: &toml::Table,
    tokens: &mut DesignTokens,
    parse_css: bool,
) -> Result<()> {
    let group_keys = [
        "alpha",
        "status",
        "idea",
        "workflow",
        "addenda-type",
        "cabinet",
        "series",
    ];

    for (key, val) in colors {
        if group_keys.contains(&key.as_str()) {
            let group = val
                .as_table()
                .ok_or_else(|| anyhow::anyhow!("colors.{key} must be a table"))?;

            if key == "alpha" {
                for (name, entry) in group {
                    let color = parse_color_entry(name, entry, parse_css)?;
                    tokens.colors.insert(name.clone(), color);
                }
            } else if key == "workflow" {
                for (name, entry) in group {
                    let wf = parse_workflow_color(name, entry, parse_css)?;
                    tokens.workflow_colors.insert(name.clone(), wf);
                }
            } else {
                let mut entries = BTreeMap::new();
                for (name, entry) in group {
                    let color = parse_color_entry(name, entry, parse_css)?;
                    entries.insert(name.clone(), color);
                }
                tokens.color_groups.insert(key.clone(), entries);
            }
        } else {
            let color = parse_color_entry(key, val, parse_css)?;
            tokens.colors.insert(key.clone(), color);
        }
    }

    Ok(())
}

fn parse_color_entry(name: &str, val: &toml::Value, parse_css: bool) -> Result<ColorEntry> {
    if let Some(s) = val.as_str() {
        let cv = if parse_css {
            ColorValue::from_css(s)
        } else {
            ColorValue::from_raw(s)
        };
        return Ok(ColorEntry::Direct(cv));
    }
    if let Some(table) = val.as_table() {
        if let (Some(base), Some(alpha)) = (
            table.get("base").and_then(|v| v.as_str()),
            table
                .get("alpha")
                .and_then(|v| v.as_float().or_else(|| v.as_integer().map(|i| i as f64))),
        ) {
            return Ok(ColorEntry::Alpha(AlphaColor {
                base: base.to_owned(),
                alpha,
            }));
        }
    }
    bail!("invalid color entry: {name}")
}

fn parse_workflow_color(name: &str, val: &toml::Value, parse_css: bool) -> Result<WorkflowColor> {
    let table = val
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("workflow color {name} must be a table"))?;
    let stroke = table
        .get("stroke")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow::anyhow!("workflow.{name}.stroke must be a string"))?;
    let fill = table
        .get("fill")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow::anyhow!("workflow.{name}.fill must be a string"))?;
    Ok(WorkflowColor {
        stroke: if parse_css {
            ColorValue::from_css(stroke)
        } else {
            ColorValue::from_raw(stroke)
        },
        fill: if parse_css {
            ColorValue::from_css(fill)
        } else {
            ColorValue::from_raw(fill)
        },
    })
}

fn parse_symbol(key: &str, val: &toml::Value) -> Result<Symbol> {
    if let Some(s) = val.as_str() {
        return Ok(Symbol {
            glyph: s.to_owned(),
            label: None,
        });
    }
    if let Some(table) = val.as_table() {
        let glyph = table
            .get("glyph")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("symbols.{key}.glyph must be a string"))?;
        let label = table
            .get("label")
            .and_then(|v| v.as_str())
            .map(String::from);
        return Ok(Symbol {
            glyph: glyph.to_owned(),
            label,
        });
    }
    bail!("invalid symbol: {key}")
}

fn parse_badge_vocabulary(key: &str, val: &toml::Value) -> Result<BadgeVocabulary> {
    let table = val
        .as_table()
        .ok_or_else(|| anyhow::anyhow!("badges.{key} must be a table"))?;

    let dossier = table
        .get("dossier")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .map(|v| {
                    v.as_str()
                        .map(String::from)
                        .ok_or_else(|| anyhow::anyhow!("badge value must be a string"))
                })
                .collect::<Result<Vec<_>>>()
        })
        .transpose()?;

    let addenda = table
        .get("addenda")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .map(|v| {
                    v.as_str()
                        .map(String::from)
                        .ok_or_else(|| anyhow::anyhow!("badge value must be a string"))
                })
                .collect::<Result<Vec<_>>>()
        })
        .transpose()?;

    let values = table
        .get("values")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .map(|v| {
                    v.as_str()
                        .map(String::from)
                        .ok_or_else(|| anyhow::anyhow!("badge value must be a string"))
                })
                .collect::<Result<Vec<_>>>()
        })
        .transpose()?;

    let mut styles = BTreeMap::new();
    for (sub_key, sub_val) in table {
        if sub_key == "dossier" || sub_key == "addenda" || sub_key == "values" {
            continue;
        }
        let style_table = sub_val
            .as_table()
            .ok_or_else(|| anyhow::anyhow!("badges.{key}.{sub_key} must be a table"))?;
        let color = style_table
            .get("color")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("badges.{key}.{sub_key}.color must be a string"))?;
        let symbol = style_table
            .get("symbol")
            .and_then(|v| v.as_str())
            .map(String::from);
        styles.insert(
            sub_key.clone(),
            BadgeStyle {
                color: color.to_owned(),
                symbol,
            },
        );
    }

    Ok(BadgeVocabulary {
        dossier,
        addenda,
        values,
        styles,
    })
}

fn parse_string_map(
    root: &toml::Table,
    key: &str,
    target: &mut BTreeMap<String, String>,
) -> Result<()> {
    let Some(table) = root.get(key).and_then(|v| v.as_table()) else {
        return Ok(());
    };
    for (name, val) in table {
        let s = val
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("{key}.{name} must be a string"))?;
        target.insert(name.clone(), s.to_owned());
    }
    Ok(())
}

fn parse_layout_map(root: &toml::Table, target: &mut BTreeMap<String, LayoutValue>) -> Result<()> {
    let Some(table) = root.get("layout").and_then(|v| v.as_table()) else {
        return Ok(());
    };
    for (name, val) in table {
        if let Some(s) = val.as_str() {
            target.insert(name.clone(), LayoutValue::Scalar(s.to_owned()));
        } else if let Some(sub) = val.as_table() {
            let mut group = BTreeMap::new();
            for (sub_name, sub_val) in sub {
                let s = sub_val
                    .as_str()
                    .ok_or_else(|| anyhow::anyhow!("layout.{name}.{sub_name} must be a string"))?;
                group.insert(sub_name.clone(), s.to_owned());
            }
            target.insert(name.clone(), LayoutValue::Group(group));
        } else {
            bail!("layout.{name} must be a string or table");
        }
    }
    Ok(())
}

pub fn merge(base: &DesignTokens, ctx: &DesignTokens) -> DesignTokens {
    let mut result = base.clone();

    for (k, v) in &ctx.colors {
        result.colors.insert(k.clone(), v.clone());
    }
    for (group, entries) in &ctx.color_groups {
        let target = result.color_groups.entry(group.clone()).or_default();
        for (k, v) in entries {
            target.insert(k.clone(), v.clone());
        }
    }
    for (k, v) in &ctx.workflow_colors {
        result.workflow_colors.insert(k.clone(), v.clone());
    }
    if ctx.overlays.is_some() {
        result.overlays.clone_from(&ctx.overlays);
    }
    for (k, v) in &ctx.shadows {
        result.shadows.insert(k.clone(), v.clone());
    }
    for (k, v) in &ctx.fonts {
        result.fonts.insert(k.clone(), v.clone());
    }
    for (k, v) in &ctx.symbols {
        result.symbols.insert(k.clone(), v.clone());
    }
    for (k, v) in &ctx.badges {
        result.badges.insert(k.clone(), v.clone());
    }
    for (k, v) in &ctx.layout {
        result.layout.insert(k.clone(), v.clone());
    }
    merge_string_map(&mut result.rules, &ctx.rules);
    merge_string_map(&mut result.type_scale, &ctx.type_scale);
    merge_string_map(&mut result.tracking, &ctx.tracking);
    merge_string_map(&mut result.leading, &ctx.leading);

    result
}

fn merge_string_map(base: &mut BTreeMap<String, String>, overlay: &BTreeMap<String, String>) {
    for (k, v) in overlay {
        base.insert(k.clone(), v.clone());
    }
}

pub fn resolve_color_ref<'a>(tokens: &'a DesignTokens, dotpath: &str) -> Result<&'a ColorEntry> {
    if let Some(entry) = tokens.colors.get(dotpath) {
        return Ok(entry);
    }
    if let Some((group, name)) = dotpath.split_once('.') {
        if let Some(entries) = tokens.color_groups.get(group) {
            if let Some(entry) = entries.get(name) {
                return Ok(entry);
            }
        }
    }
    bail!("unresolved color reference: {dotpath}")
}

pub fn resolve_base_color(tokens: &DesignTokens, base_name: &str) -> Result<csscolorparser::Color> {
    let entry = tokens
        .colors
        .get(base_name)
        .ok_or_else(|| anyhow::anyhow!("unresolved base color: {base_name}"))?;
    match entry {
        ColorEntry::Direct(cv) => cv
            .parsed
            .clone()
            .ok_or_else(|| anyhow::anyhow!("base color {base_name} has no parsed CSS value")),
        ColorEntry::Alpha(_) => bail!("alpha color cannot be used as overlay base: {base_name}"),
    }
}

pub fn validate_spec(tokens: &DesignTokens) -> Result<()> {
    let mut errors: Vec<String> = Vec::new();

    for (badge_key, vocab) in &tokens.badges {
        for (style_name, style) in &vocab.styles {
            if resolve_color_ref(tokens, &style.color).is_err() {
                errors.push(format!(
                    "badges.{badge_key}.{style_name}.color references unknown color: {}",
                    style.color
                ));
            }
            if let Some(ref sym) = style.symbol {
                if !tokens.symbols.contains_key(sym) {
                    errors.push(format!(
                        "badges.{badge_key}.{style_name}.symbol references unknown symbol: {sym}"
                    ));
                }
            }
        }
    }

    if let Some(ref overlays) = tokens.overlays {
        if resolve_base_color(tokens, &overlays.base).is_err() {
            errors.push(format!(
                "overlays.base references unknown color: {}",
                overlays.base
            ));
        }
    }

    if errors.is_empty() {
        Ok(())
    } else {
        let detail = errors.join("\n  - ");
        bail!("design token spec validation failed:\n  - {detail}");
    }
}

pub fn badge_statuses_for_kind(tokens: &DesignTokens, kind: &str) -> Result<Vec<String>> {
    let vocab = tokens
        .badges
        .get("project-status")
        .ok_or_else(|| anyhow::anyhow!("missing badges.project-status in design token spec"))?;
    match kind {
        "dossier" => vocab
            .dossier
            .clone()
            .ok_or_else(|| anyhow::anyhow!("missing badges.project-status.dossier")),
        "addendum" => vocab
            .addenda
            .clone()
            .ok_or_else(|| anyhow::anyhow!("missing badges.project-status.addenda")),
        _ => bail!("unknown project kind: {kind}"),
    }
}

pub fn badge_type_values(tokens: &DesignTokens, badge_key: &str) -> Result<Vec<String>> {
    let vocab = tokens
        .badges
        .get(badge_key)
        .ok_or_else(|| anyhow::anyhow!("missing badges.{badge_key} in design token spec"))?;
    vocab
        .values
        .clone()
        .ok_or_else(|| anyhow::anyhow!("missing badges.{badge_key}.values"))
}

pub fn spec_dir(repo_root: &Utf8Path) -> Utf8PathBuf {
    repo_root.join("addenda/design-tokens")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_and_merge() {
        let base = r##"
[colors]
ink = "#0b0e14"
paper = "#ffffff"

[colors.alpha]
muted = { base = "ink", alpha = 0.68 }

[fonts]
mono = ["Menlo", "monospace"]
"##;
        let ctx = r##"
[colors]
ink = "luma(8%)"
paper = "luma(97%)"

[fonts]
mono = ["IBM Plex Mono"]
body = ["IBM Plex Serif"]
"##;
        let base_tokens = parse_base(base).unwrap();
        let ctx_tokens = parse_context(ctx).unwrap();
        let merged = merge(&base_tokens, &ctx_tokens);

        assert_eq!(merged.fonts.len(), 2);
        assert_eq!(merged.fonts["mono"].0, vec!["IBM Plex Mono"]);
        assert_eq!(merged.fonts["body"].0, vec!["IBM Plex Serif"]);

        match &merged.colors["ink"] {
            ColorEntry::Direct(cv) => assert_eq!(cv.raw, "luma(8%)"),
            _ => panic!("expected direct color"),
        }
        assert!(merged.colors.contains_key("muted"));
    }

    #[test]
    fn test_resolve_color_ref() {
        let base = r##"
[colors]
accent = "#ff6600"

[colors.status]
exploratory = "#5f6c7b"
"##;
        let tokens = parse_base(base).unwrap();
        assert!(resolve_color_ref(&tokens, "accent").is_ok());
        assert!(resolve_color_ref(&tokens, "status.exploratory").is_ok());
        assert!(resolve_color_ref(&tokens, "nonexistent").is_err());
        assert!(resolve_color_ref(&tokens, "status.nonexistent").is_err());
    }

    #[test]
    fn test_validate_invalid_ref() {
        let base = r##"
[colors]
accent = "#ff6600"

[symbols]
active = { glyph = "\u25CF", label = "active" }

[badges.test]
values = ["good"]

[badges.test.good]
color = "nonexistent.color"
symbol = "active"
"##;
        let tokens = parse_base(base).unwrap();
        assert!(validate_spec(&tokens).is_err());
    }

    #[test]
    fn test_validate_invalid_symbol_ref() {
        let base = r##"
[colors]
accent = "#ff6600"

[badges.test]
values = ["good"]

[badges.test.good]
color = "accent"
symbol = "nonexistent"
"##;
        let tokens = parse_base(base).unwrap();
        assert!(validate_spec(&tokens).is_err());
    }
}
