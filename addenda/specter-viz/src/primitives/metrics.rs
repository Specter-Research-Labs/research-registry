use egui::{Color32, CornerRadius, Frame, Margin, Response, Shadow, Stroke, Ui};

use crate::core::{colors, spacing, typography};

pub struct MetricCard {
    label: String,
    value: String,
    accent: Option<Color32>,
}

impl MetricCard {
    #[must_use]
    pub fn new(label: impl Into<String>, value: impl Into<String>) -> Self {
        Self {
            label: label.into(),
            value: value.into(),
            accent: None,
        }
    }

    #[must_use]
    pub const fn accent(mut self, color: Color32) -> Self {
        self.accent = Some(color);
        self
    }

    pub fn show(self, ui: &mut Ui) -> Response {
        let frame = Frame::new()
            .fill(colors::BG_ELEVATED)
            .stroke(Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_SUBTLE))
            .corner_radius(CornerRadius::same(spacing::CORNER_RADIUS))
            .shadow(Shadow {
                offset: [0, 2],
                blur: 12,
                spread: 0,
                color: Color32::from_black_alpha(20),
            })
            .inner_margin(Margin::same(8));
        frame
            .show(ui, |ui| {
                ui.label(
                    egui::RichText::new(self.label)
                        .color(colors::TEXT_SECONDARY)
                        .size(typography::SIZE_CAPTION),
                );
                ui.label(
                    egui::RichText::new(self.value)
                        .color(self.accent.unwrap_or(colors::TEXT_PRIMARY))
                        .size(typography::SIZE_BODY)
                        .strong(),
                );
            })
            .response
    }
}

pub struct MetricGrid {
    columns: usize,
    cards: Vec<MetricCard>,
}

impl MetricGrid {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            columns: 3,
            cards: Vec::new(),
        }
    }

    #[must_use]
    pub fn columns(mut self, columns: usize) -> Self {
        self.columns = columns.max(1);
        self
    }

    pub fn push(&mut self, card: MetricCard) {
        self.cards.push(card);
    }

    pub fn show(self, ui: &mut Ui) {
        let columns = self.columns.max(1);
        let spacing = ui.spacing().item_spacing;
        ui.spacing_mut().item_spacing = egui::vec2(spacing::SM, spacing::SM);
        ui.columns(columns, |cols| {
            for (index, card) in self.cards.into_iter().enumerate() {
                let column = index % columns;
                card.show(&mut cols[column]);
            }
        });
        ui.spacing_mut().item_spacing = spacing;
    }
}

impl Default for MetricGrid {
    fn default() -> Self {
        Self::new()
    }
}
