use egui::{FontData, FontDefinitions, FontFamily, FontId, TextStyle};

pub const SIZE_CAPTION: f32 = 13.0;
pub const SIZE_BODY: f32 = 15.0;
pub const SIZE_HEADING: f32 = 18.0;
pub const SIZE_TITLE: f32 = 24.0;

#[must_use]
pub const fn font_id_caption() -> FontId {
    FontId::new(SIZE_CAPTION, FontFamily::Monospace)
}

#[must_use]
pub const fn font_id_body() -> FontId {
    FontId::new(SIZE_BODY, FontFamily::Monospace)
}

#[must_use]
pub const fn font_id_heading() -> FontId {
    FontId::new(SIZE_HEADING, FontFamily::Monospace)
}

#[must_use]
pub const fn font_id_title() -> FontId {
    FontId::new(SIZE_TITLE, FontFamily::Monospace)
}

#[allow(clippy::missing_panics_doc)]
pub fn configure_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();

    fonts.font_data.insert(
        "berkeley_mono".to_owned(),
        std::sync::Arc::new(FontData::from_static(include_bytes!(
            "../fonts/BerkeleyMono-Regular.ttf"
        ))),
    );

    fonts.font_data.insert(
        "jetbrains_mono".to_owned(),
        std::sync::Arc::new(FontData::from_static(include_bytes!(
            "../fonts/JetBrainsMono-Regular.ttf"
        ))),
    );

    fonts
        .families
        .get_mut(&FontFamily::Monospace)
        .expect("monospace family exists")
        .insert(0, "berkeley_mono".to_owned());

    fonts
        .families
        .get_mut(&FontFamily::Monospace)
        .expect("monospace family exists")
        .insert(1, "jetbrains_mono".to_owned());

    fonts
        .families
        .get_mut(&FontFamily::Proportional)
        .expect("proportional family exists")
        .insert(0, "berkeley_mono".to_owned());

    fonts
        .families
        .get_mut(&FontFamily::Proportional)
        .expect("proportional family exists")
        .insert(1, "jetbrains_mono".to_owned());

    ctx.set_fonts(fonts);

    let mut style = (*ctx.style()).clone();
    style.text_styles = [
        (TextStyle::Small, font_id_caption()),
        (TextStyle::Body, font_id_body()),
        (TextStyle::Monospace, font_id_body()),
        (TextStyle::Button, font_id_body()),
        (TextStyle::Heading, font_id_heading()),
    ]
    .into();
    ctx.set_style(style);
}
