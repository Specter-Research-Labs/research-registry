use egui::{Color32, Response, RichText, Ui};

use crate::core::{colors, typography};

pub enum LabelStyle {
    Caption,
    Body,
    Heading,
    Title,
}

pub struct Label<'a> {
    text: &'a str,
    style: LabelStyle,
    color: Option<Color32>,
}

impl<'a> Label<'a> {
    #[must_use]
    pub const fn caption(text: &'a str) -> Self {
        Self {
            text,
            style: LabelStyle::Caption,
            color: None,
        }
    }

    #[must_use]
    pub const fn body(text: &'a str) -> Self {
        Self {
            text,
            style: LabelStyle::Body,
            color: None,
        }
    }

    #[must_use]
    pub const fn heading(text: &'a str) -> Self {
        Self {
            text,
            style: LabelStyle::Heading,
            color: None,
        }
    }

    #[must_use]
    pub const fn title(text: &'a str) -> Self {
        Self {
            text,
            style: LabelStyle::Title,
            color: None,
        }
    }

    #[must_use]
    pub const fn color(mut self, color: Color32) -> Self {
        self.color = Some(color);
        self
    }

    pub fn show(self, ui: &mut Ui) -> Response {
        let (font_id, default_color, strong) = match self.style {
            LabelStyle::Caption => (typography::font_id_caption(), colors::TEXT_MUTED, false),
            LabelStyle::Body => (typography::font_id_body(), colors::TEXT_PRIMARY, false),
            LabelStyle::Heading => (typography::font_id_heading(), colors::TEXT_PRIMARY, true),
            LabelStyle::Title => (typography::font_id_title(), colors::TEXT_PRIMARY, true),
        };
        let mut text = RichText::new(self.text)
            .font(font_id)
            .color(self.color.unwrap_or(default_color));
        if strong {
            text = text.strong();
        }
        ui.label(text)
    }
}
