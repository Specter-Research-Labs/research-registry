use egui::{Align, InnerResponse, Layout, Response, RichText, Ui};

use crate::core::{colors, typography};

pub struct ChartHeader<'a> {
    title: &'a str,
}

impl<'a> ChartHeader<'a> {
    #[must_use]
    pub const fn new(title: &'a str) -> Self {
        Self { title }
    }

    pub fn show(self, ui: &mut Ui) -> Response {
        self.show_with_actions(ui, |_| {}).response
    }

    pub fn show_with_actions<R>(
        self,
        ui: &mut Ui,
        add_actions: impl FnOnce(&mut Ui) -> R,
    ) -> InnerResponse<R> {
        ui.vertical(|ui| {
            let inner = ui
                .horizontal(|ui| {
                    ui.label(
                        RichText::new(self.title.to_ascii_uppercase())
                            .color(colors::TEXT_SECONDARY)
                            .size(typography::SIZE_CAPTION)
                            .strong(),
                    );
                    ui.with_layout(Layout::right_to_left(Align::Center), add_actions)
                        .inner
                })
                .inner;
            ui.add_space(2.0);
            ui.separator();
            inner
        })
    }
}
