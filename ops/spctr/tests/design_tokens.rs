use camino::Utf8Path;
use std::fs;

fn write(root: &Utf8Path, rel: &str, content: &str) {
    let path = root.join(rel);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, content).unwrap();
}

fn write_minimal_spec(root: &Utf8Path) {
    write(
        root,
        "base.toml",
        r##"
[colors]
ink = "#0b0e14"
paper = "#ffffff"
bg = "#edeef0"
accent = "#ff6600"
accent-2 = "#00a645"

[colors.alpha]
muted = { base = "ink", alpha = 0.68 }
rule = { base = "ink", alpha = 0.18 }

[overlays]
base = "ink"
stops = [0.02, 0.06, 0.12]

[shadows]
raised = "0 18px 46px {overlay.12}, 0 2px 0 {overlay.06}"

[fonts]
mono = ["Berkeley Mono", "monospace"]

[symbols]
active = { glyph = "\u25CF", label = "active" }
paused = { glyph = "\u25CB", label = "paused" }

[colors.status]
exploratory = "#5f6c7b"
paused = "#9f6f00"

[colors.workflow]
blocked = { stroke = "#b4573d", fill = "#fdf0eb" }

[colors.addenda-type]
tooling = "#556372"

[badges.project-status]
dossier = ["concept", "active", "hold"]
addenda = ["concept", "active", "operational", "hold", "archived"]

[badges.project-status.concept]
color = "status.exploratory"
symbol = "paused"

[badges.project-status.active]
color = "accent"
symbol = "active"

[badges.project-status.hold]
color = "status.paused"
symbol = "paused"

[badges.project-status.operational]
color = "accent-2"
symbol = "active"

[badges.project-status.archived]
color = "status.paused"
symbol = "paused"

[badges.addenda-type]
values = ["tooling"]

[badges.addenda-type.tooling]
color = "addenda-type.tooling"
"##,
    );
    write(root, "web.toml", "");
}

#[test]
fn roundtrip_css_contains_expected_properties() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    let css = spctr::design_tokens_css::generate_css(&tokens).unwrap();

    assert!(css.contains("--sl-font-mono:"));
    assert!(css.contains("--sl-color-ink:"));
    assert!(css.contains("--sl-color-paper:"));
    assert!(css.contains("--sl-color-accent:"));
    assert!(css.contains("--sl-color-muted:"));
    assert!(css.contains("--sl-shadow-raised:"));
    assert!(css.contains("--sl-overlay-ink-"));
    assert!(css.contains("--sl-color-workflow-blocked-stroke:"));
    assert!(css.contains("--sl-color-addenda-type-tooling:"));
}

#[test]
fn roundtrip_typst_produces_valid_dictionary() {
    let tmp = tempfile::tempdir().unwrap();
    let spec = Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8");

    write(
        spec,
        "field-manual.toml",
        r##"
[fonts]
body = ["IBM Plex Serif"]
mono = ["IBM Plex Mono"]

[colors]
ink = "luma(8%)"

[rules]
thin = "0.6pt"

[type-scale]
body = "10pt"

[leading]
body = "1.32em"

[layout.page-margin]
top = "16mm"
bottom = "18mm"
"##,
    );

    write(
        spec,
        "paper.toml",
        r##"
[colors]
ink = "luma(10%)"

[type-scale]
body = "10.5pt"

[leading]
body = "1.34em"

[layout.page-margin]
top = "20mm"
bottom = "20mm"
"##,
    );

    let fm = spctr::design_tokens::load_context_only(spec, "field-manual").unwrap();
    let paper = spctr::design_tokens::load_context_only(spec, "paper").unwrap();
    let typst = spctr::design_tokens_typst::generate_typst(&fm, &paper).unwrap();

    assert!(typst.starts_with("#let tokens = (\n"));
    assert!(typst.ends_with(")\n"));
    assert!(typst.contains("fonts:"));
    assert!(typst.contains("colors:"));
    assert!(typst.contains("paper_colors:"));
    assert!(typst.contains("page_margin: ("));
}

#[test]
fn merge_context_overrides_base_at_leaf_level() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    write(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "override.toml",
        r##"
[colors]
ink = "#222222"

[fonts]
mono = ["Menlo"]
body = ["Georgia"]
"##,
    );

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "override",
    )
    .unwrap();

    match &tokens.colors["ink"] {
        spctr::design_tokens::ColorEntry::Direct(cv) => assert_eq!(cv.raw, "#222222"),
        _ => panic!("expected direct color"),
    }
    assert_eq!(tokens.fonts["mono"].0, vec!["Menlo"]);
    assert_eq!(tokens.fonts["body"].0, vec!["Georgia"]);
    assert!(
        tokens.colors.contains_key("paper"),
        "base color should survive merge"
    );
}

#[test]
fn overlay_generates_correct_count() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    let css = spctr::design_tokens_css::generate_css(&tokens).unwrap();

    let overlay_count = css
        .lines()
        .filter(|l| l.contains("--sl-overlay-ink-") && l.contains(':'))
        .count();
    assert_eq!(overlay_count, 3, "should have 3 overlay stops");
}

#[test]
fn shadow_interpolation_resolves_to_var() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    let css = spctr::design_tokens_css::generate_css(&tokens).unwrap();

    assert!(
        css.contains("var(--sl-overlay-ink-12)"),
        "shadow should interpolate overlay ref"
    );
    assert!(
        css.contains("var(--sl-overlay-ink-6)"),
        "shadow should interpolate overlay ref"
    );
}

#[test]
fn badge_validation_rejects_unknown_status() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    let vocabs = spctr::manifest::Vocabularies::from_spec(&tokens).unwrap();

    assert!(vocabs.dossier_statuses.contains(&"active".to_owned()));
    assert!(!vocabs.dossier_statuses.contains(&"operational".to_owned()));
    assert!(vocabs.addenda_statuses.contains(&"operational".to_owned()));
}

#[test]
fn color_ref_resolution_follows_dotpath() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    assert!(spctr::design_tokens::resolve_color_ref(&tokens, "accent").is_ok());
    assert!(spctr::design_tokens::resolve_color_ref(&tokens, "status.exploratory").is_ok());
    assert!(spctr::design_tokens::resolve_color_ref(&tokens, "nonexistent").is_err());
}

#[test]
fn spec_consistency_catches_dangling_ref() {
    let tmp = tempfile::tempdir().unwrap();
    write(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "base.toml",
        r##"
[colors]
ink = "#0b0e14"

[symbols]
active = { glyph = "\u25CF", label = "active" }

[badges.test]
values = ["ok"]

[badges.test.ok]
color = "missing.color"
symbol = "active"
"##,
    );
    write(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web.toml",
        "",
    );

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    let result = spctr::design_tokens::validate_spec(&tokens);
    assert!(result.is_err());
    let msg = format!("{result:?}");
    assert!(
        msg.contains("missing.color"),
        "should mention the dangling ref"
    );
}

#[test]
fn email_json_flattens_alpha_colors() {
    let tmp = tempfile::tempdir().unwrap();
    write_minimal_spec(Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"));

    let tokens = spctr::design_tokens::load_spec(
        Utf8Path::from_path(tmp.path()).expect("temp dir is valid UTF-8"),
        "web",
    )
    .unwrap();
    let json = spctr::design_tokens_email::generate_email_json(&tokens).unwrap();

    let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
    assert!(parsed["ink"].is_string());
    assert!(
        parsed["muted"].is_string(),
        "alpha color should be flattened"
    );
    let muted = parsed["muted"].as_str().unwrap();
    assert!(
        muted.starts_with('#'),
        "flattened alpha should be hex: {muted}"
    );
}
