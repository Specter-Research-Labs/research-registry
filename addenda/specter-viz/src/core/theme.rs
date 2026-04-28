use egui::{style::WidgetVisuals, Color32, CornerRadius, Shadow, Stroke, Visuals};

use super::spacing;

#[derive(Clone, Copy, PartialEq, Eq)]
pub struct Theme {
    pub bg_primary: Color32,
    pub bg_panel: Color32,
    pub bg_elevated: Color32,

    pub text_primary: Color32,
    pub text_secondary: Color32,
    pub text_muted: Color32,

    pub accent_primary: Color32,
    pub accent_secondary: Color32,
    pub accent_tertiary: Color32,

    pub border_default: Color32,
    pub border_subtle: Color32,

    pub success: Color32,
    pub warning: Color32,
    pub error: Color32,
    pub info: Color32,

    pub selection_bg: Color32,
    pub selection_fg: Color32,
}

impl Theme {
    const fn corner_radius() -> CornerRadius {
        CornerRadius::same(spacing::CORNER_RADIUS)
    }

    pub fn apply(&self, ctx: &egui::Context) {
        let mut visuals = Visuals::dark();

        visuals.panel_fill = self.bg_primary;
        visuals.window_fill = self.bg_panel;
        visuals.faint_bg_color = self.bg_elevated;
        visuals.extreme_bg_color = self.bg_primary;

        visuals.window_corner_radius = Self::corner_radius();
        visuals.window_shadow = Shadow::NONE;
        visuals.window_stroke = Stroke::new(spacing::BORDER_WIDTH, self.border_default);

        visuals.widgets.noninteractive = WidgetVisuals {
            bg_fill: self.bg_panel,
            weak_bg_fill: self.bg_panel,
            bg_stroke: Stroke::new(spacing::BORDER_WIDTH, self.border_default),
            fg_stroke: Stroke::new(1.0, self.text_secondary),
            corner_radius: Self::corner_radius(),
            expansion: 0.0,
        };

        visuals.widgets.inactive = WidgetVisuals {
            bg_fill: self.bg_elevated,
            weak_bg_fill: self.bg_elevated,
            bg_stroke: Stroke::new(spacing::BORDER_WIDTH, self.border_default),
            fg_stroke: Stroke::new(1.0, self.text_secondary),
            corner_radius: Self::corner_radius(),
            expansion: 0.0,
        };

        visuals.widgets.hovered = WidgetVisuals {
            bg_fill: self.bg_elevated,
            weak_bg_fill: self.bg_elevated,
            bg_stroke: Stroke::new(spacing::BORDER_WIDTH, self.accent_primary),
            fg_stroke: Stroke::new(1.0, self.text_primary),
            corner_radius: Self::corner_radius(),
            expansion: 1.0,
        };

        visuals.widgets.active = WidgetVisuals {
            bg_fill: self.accent_primary,
            weak_bg_fill: self.accent_primary,
            bg_stroke: Stroke::new(spacing::BORDER_WIDTH, self.accent_primary),
            fg_stroke: Stroke::new(1.0, self.bg_primary),
            corner_radius: Self::corner_radius(),
            expansion: 0.0,
        };

        visuals.widgets.open = WidgetVisuals {
            bg_fill: self.bg_elevated,
            weak_bg_fill: self.bg_elevated,
            bg_stroke: Stroke::new(spacing::BORDER_WIDTH, self.accent_primary),
            fg_stroke: Stroke::new(1.0, self.text_primary),
            corner_radius: Self::corner_radius(),
            expansion: 0.0,
        };

        visuals.selection.bg_fill = self.selection_bg;
        visuals.selection.stroke = Stroke::new(1.0, self.accent_primary);

        visuals.hyperlink_color = self.info;
        visuals.warn_fg_color = self.warning;
        visuals.error_fg_color = self.error;

        ctx.set_visuals(visuals);
    }
}

pub mod presets {
    use super::Theme;
    use egui::Color32;

    pub const SPECTER: Theme = Theme {
        bg_primary: Color32::from_rgb(8, 11, 16),
        bg_panel: Color32::from_rgb(13, 17, 23),
        bg_elevated: Color32::from_rgb(22, 27, 34),

        text_primary: Color32::from_rgb(230, 237, 243),
        text_secondary: Color32::from_rgb(154, 167, 178),
        text_muted: Color32::from_rgb(110, 118, 129),

        accent_primary: Color32::from_rgb(71, 166, 217),
        accent_secondary: Color32::from_rgb(39, 195, 123),
        accent_tertiary: Color32::from_rgb(255, 176, 0),

        border_default: Color32::from_rgb(48, 54, 61),
        border_subtle: Color32::from_rgb(58, 67, 78),

        success: Color32::from_rgb(39, 195, 123),
        warning: Color32::from_rgb(255, 176, 0),
        error: Color32::from_rgb(255, 92, 92),
        info: Color32::from_rgb(71, 166, 217),

        selection_bg: Color32::from_rgb(21, 50, 65),
        selection_fg: Color32::from_rgb(230, 237, 243),
    };

    pub const USGC_RETICLE: Theme = Theme {
        bg_primary: Color32::from_rgb(0, 0, 0),
        bg_panel: Color32::from_rgb(0, 0, 0),
        bg_elevated: Color32::from_rgb(0, 0, 102),

        text_primary: Color32::from_rgb(0, 166, 69),
        text_secondary: Color32::from_rgb(153, 153, 153),
        text_muted: Color32::from_rgb(102, 102, 102),

        accent_primary: Color32::from_rgb(0, 166, 69),
        accent_secondary: Color32::from_rgb(255, 0, 0),
        accent_tertiary: Color32::from_rgb(0, 0, 255),

        border_default: Color32::from_rgb(0, 166, 69),
        border_subtle: Color32::from_rgb(0, 102, 102),

        success: Color32::from_rgb(0, 255, 0),
        warning: Color32::from_rgb(255, 191, 0),
        error: Color32::from_rgb(255, 0, 0),
        info: Color32::from_rgb(0, 0, 255),

        selection_bg: Color32::from_rgb(255, 255, 255),
        selection_fg: Color32::from_rgb(0, 0, 255),
    };

    pub const USGC_HIGHK: Theme = Theme {
        bg_primary: Color32::from_rgb(255, 255, 255),
        bg_panel: Color32::from_rgb(255, 255, 255),
        bg_elevated: Color32::from_rgb(0, 255, 0),

        text_primary: Color32::from_rgb(0, 0, 0),
        text_secondary: Color32::from_rgb(102, 102, 102),
        text_muted: Color32::from_rgb(153, 153, 153),

        accent_primary: Color32::from_rgb(0, 0, 255),
        accent_secondary: Color32::from_rgb(255, 0, 0),
        accent_tertiary: Color32::from_rgb(0, 255, 0),

        border_default: Color32::from_rgb(0, 0, 0),
        border_subtle: Color32::from_rgb(153, 153, 153),

        success: Color32::from_rgb(0, 166, 69),
        warning: Color32::from_rgb(255, 191, 0),
        error: Color32::from_rgb(255, 0, 0),
        info: Color32::from_rgb(0, 0, 255),

        selection_bg: Color32::from_rgb(0, 255, 0),
        selection_fg: Color32::from_rgb(0, 0, 0),
    };

    pub const USGC_POLYIMIDE: Theme = Theme {
        bg_primary: Color32::from_rgb(0, 0, 0),
        bg_panel: Color32::from_rgb(0, 0, 0),
        bg_elevated: Color32::from_rgb(0, 0, 102),

        text_primary: Color32::from_rgb(255, 191, 0),
        text_secondary: Color32::from_rgb(153, 153, 153),
        text_muted: Color32::from_rgb(102, 102, 102),

        accent_primary: Color32::from_rgb(255, 191, 0),
        accent_secondary: Color32::from_rgb(255, 102, 0),
        accent_tertiary: Color32::from_rgb(0, 166, 69),

        border_default: Color32::from_rgb(255, 191, 0),
        border_subtle: Color32::from_rgb(102, 102, 0),

        success: Color32::from_rgb(0, 166, 69),
        warning: Color32::from_rgb(255, 102, 0),
        error: Color32::from_rgb(255, 0, 0),
        info: Color32::from_rgb(0, 255, 255),

        selection_bg: Color32::from_rgb(0, 0, 102),
        selection_fg: Color32::from_rgb(0, 255, 255),
    };

    pub const USGC_EPITAXY: Theme = Theme {
        bg_primary: Color32::from_rgb(0, 0, 0),
        bg_panel: Color32::from_rgb(0, 0, 0),
        bg_elevated: Color32::from_rgb(0, 0, 102),

        text_primary: Color32::from_rgb(255, 0, 255),
        text_secondary: Color32::from_rgb(153, 153, 153),
        text_muted: Color32::from_rgb(102, 102, 102),

        accent_primary: Color32::from_rgb(255, 0, 255),
        accent_secondary: Color32::from_rgb(255, 255, 0),
        accent_tertiary: Color32::from_rgb(0, 0, 255),

        border_default: Color32::from_rgb(255, 0, 255),
        border_subtle: Color32::from_rgb(102, 0, 102),

        success: Color32::from_rgb(0, 255, 0),
        warning: Color32::from_rgb(255, 255, 0),
        error: Color32::from_rgb(255, 0, 0),
        info: Color32::from_rgb(0, 0, 255),

        selection_bg: Color32::from_rgb(0, 0, 102),
        selection_fg: Color32::from_rgb(255, 255, 0),
    };

    pub const USGC_METALGATE: Theme = Theme {
        bg_primary: Color32::from_rgb(0, 0, 0),
        bg_panel: Color32::from_rgb(0, 0, 0),
        bg_elevated: Color32::from_rgb(0, 0, 102),

        text_primary: Color32::from_rgb(0, 255, 255),
        text_secondary: Color32::from_rgb(153, 153, 153),
        text_muted: Color32::from_rgb(102, 102, 102),

        accent_primary: Color32::from_rgb(0, 255, 255),
        accent_secondary: Color32::from_rgb(255, 255, 0),
        accent_tertiary: Color32::from_rgb(0, 0, 255),

        border_default: Color32::from_rgb(0, 255, 255),
        border_subtle: Color32::from_rgb(0, 102, 102),

        success: Color32::from_rgb(0, 255, 0),
        warning: Color32::from_rgb(255, 255, 0),
        error: Color32::from_rgb(255, 0, 0),
        info: Color32::from_rgb(0, 0, 255),

        selection_bg: Color32::from_rgb(102, 102, 0),
        selection_fg: Color32::from_rgb(255, 255, 0),
    };

    pub const GRUVBOX_DARK: Theme = Theme {
        bg_primary: Color32::from_rgb(40, 40, 40),
        bg_panel: Color32::from_rgb(50, 48, 47),
        bg_elevated: Color32::from_rgb(60, 56, 54),

        text_primary: Color32::from_rgb(235, 219, 178),
        text_secondary: Color32::from_rgb(168, 153, 132),
        text_muted: Color32::from_rgb(146, 131, 116),

        accent_primary: Color32::from_rgb(215, 153, 33),
        accent_secondary: Color32::from_rgb(152, 151, 26),
        accent_tertiary: Color32::from_rgb(69, 133, 136),

        border_default: Color32::from_rgb(80, 73, 69),
        border_subtle: Color32::from_rgb(60, 56, 54),

        success: Color32::from_rgb(152, 151, 26),
        warning: Color32::from_rgb(215, 153, 33),
        error: Color32::from_rgb(204, 36, 29),
        info: Color32::from_rgb(69, 133, 136),

        selection_bg: Color32::from_rgb(65, 46, 10),
        selection_fg: Color32::from_rgb(235, 219, 178),
    };
}

pub fn init(ctx: &egui::Context) {
    init_with_theme(ctx, &presets::SPECTER);
}

pub fn init_with_theme(ctx: &egui::Context, theme: &Theme) {
    let already_applied = ctx.data_mut(|data| {
        let key = egui::Id::new("specter_viz.theme");
        if data.get_temp::<Theme>(key) == Some(*theme) {
            true
        } else {
            data.insert_temp(key, *theme);
            false
        }
    });

    if already_applied {
        return;
    }

    super::typography::configure_fonts(ctx);
    theme.apply(ctx);
}
