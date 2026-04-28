use egui::{Color32, CornerRadius, Frame, InnerResponse, Margin, Shadow, Stroke, Ui};

use crate::core::{colors, spacing};
use crate::primitives::ChartHeader;

pub struct Panel<'a> {
    title: &'a str,
}

impl<'a> Panel<'a> {
    #[must_use]
    pub const fn new(title: &'a str) -> Self {
        Self { title }
    }

    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    pub fn show<R>(self, ui: &mut Ui, add_contents: impl FnOnce(&mut Ui) -> R) -> InnerResponse<R> {
        self.show_with_actions(ui, |_| {}, add_contents)
    }

    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    pub fn show_with_actions<R>(
        self,
        ui: &mut Ui,
        add_actions: impl FnOnce(&mut Ui),
        add_contents: impl FnOnce(&mut Ui) -> R,
    ) -> InnerResponse<R> {
        let frame = Frame::new()
            .fill(colors::BG_PANEL)
            .stroke(Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_DEFAULT))
            .corner_radius(CornerRadius::same(spacing::CORNER_RADIUS))
            .shadow(Shadow {
                offset: [0, 4],
                blur: 18,
                spread: 0,
                color: Color32::from_black_alpha(28),
            })
            .inner_margin(Margin::same(spacing::PANEL_PADDING as i8));

        frame.show(ui, |ui| {
            ui.vertical(|ui| {
                ChartHeader::new(self.title).show_with_actions(ui, add_actions);
                ui.add_space(spacing::XS);
                add_contents(ui)
            })
            .inner
        })
    }
}
