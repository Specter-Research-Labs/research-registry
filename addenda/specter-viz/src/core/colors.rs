use egui::Color32;

pub const BG_PRIMARY: Color32 = Color32::from_rgb(8, 11, 16);
pub const BG_PANEL: Color32 = Color32::from_rgb(13, 17, 23);
pub const BG_ELEVATED: Color32 = Color32::from_rgb(22, 27, 34);

pub const TEXT_PRIMARY: Color32 = Color32::from_rgb(230, 237, 243);
pub const TEXT_SECONDARY: Color32 = Color32::from_rgb(154, 167, 178);
pub const TEXT_MUTED: Color32 = Color32::from_rgb(110, 118, 129);

pub const ACCENT_GOLD: Color32 = Color32::from_rgb(255, 176, 0);
pub const ACCENT_TEAL: Color32 = Color32::from_rgb(39, 195, 123);
pub const ACCENT_BLUE: Color32 = Color32::from_rgb(71, 166, 217);
pub const ACCENT_RED: Color32 = Color32::from_rgb(255, 92, 92);
pub const ACCENT_PURPLE: Color32 = Color32::from_rgb(163, 113, 247);

pub const BORDER_DEFAULT: Color32 = Color32::from_rgb(48, 54, 61);
pub const BORDER_SUBTLE: Color32 = Color32::from_rgb(58, 67, 78);

pub const SUCCESS: Color32 = ACCENT_TEAL;
pub const WARNING: Color32 = ACCENT_GOLD;
pub const ERROR: Color32 = ACCENT_RED;
pub const INFO: Color32 = ACCENT_BLUE;
pub const MISSING_DATA: Color32 = Color32::from_rgb(82, 89, 99);

#[must_use]
pub const fn series_color(index: usize) -> Color32 {
    const SERIES: [Color32; 6] = [
        ACCENT_TEAL,
        ACCENT_GOLD,
        ACCENT_BLUE,
        ACCENT_PURPLE,
        ACCENT_RED,
        Color32::from_rgb(255, 140, 105),
    ];
    SERIES[index % SERIES.len()]
}

#[must_use]
pub fn sequential_gradient(ratio: f32) -> Color32 {
    gradient(ratio, &[
        Color32::from_rgb(68, 1, 84),
        Color32::from_rgb(59, 82, 139),
        Color32::from_rgb(33, 145, 140),
        Color32::from_rgb(94, 201, 98),
        Color32::from_rgb(253, 231, 37),
    ])
}

#[must_use]
pub fn diverging_gradient(ratio: f32) -> Color32 {
    gradient(ratio, &[
        Color32::from_rgb(59, 76, 192),
        Color32::from_rgb(144, 178, 254),
        Color32::from_rgb(245, 245, 245),
        Color32::from_rgb(248, 156, 116),
        Color32::from_rgb(180, 4, 38),
    ])
}

#[must_use]
pub fn success_gradient(ratio: f32) -> Color32 {
    sequential_gradient(ratio)
}

#[must_use]
#[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss, clippy::cast_sign_loss)]
fn gradient(ratio: f32, stops: &[Color32]) -> Color32 {
    if !ratio.is_finite() {
        return MISSING_DATA;
    }
    if stops.is_empty() {
        return MISSING_DATA;
    }
    if stops.len() == 1 {
        return stops[0];
    }

    let ratio = ratio.clamp(0.0, 1.0);
    let scaled = ratio * (stops.len() - 1) as f32;
    let index = scaled.floor() as usize;
    let next_index = (index + 1).min(stops.len() - 1);
    let local = scaled - index as f32;
    lerp_color(stops[index], stops[next_index], local)
}

#[must_use]
#[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss, clippy::cast_sign_loss)]
fn lerp_color(start: Color32, end: Color32, t: f32) -> Color32 {
    let [sr, sg, sb, sa] = start.to_array();
    let [er, eg, eb, ea] = end.to_array();
    let lerp = |a: u8, b: u8| ((a as f32) + ((b as f32) - (a as f32)) * t).round() as u8;
    Color32::from_rgba_unmultiplied(lerp(sr, er), lerp(sg, eg), lerp(sb, eb), lerp(sa, ea))
}

#[cfg(test)]
mod tests {
    use super::{diverging_gradient, sequential_gradient, MISSING_DATA};

    #[test]
    fn sequential_gradient_returns_missing_color_for_nan() {
        assert_eq!(sequential_gradient(f32::NAN), MISSING_DATA);
    }

    #[test]
    fn diverging_gradient_uses_neutral_midpoint() {
        let mid = diverging_gradient(0.5);
        assert!(mid.r() > 200);
        assert!(mid.g() > 200);
        assert!(mid.b() > 200);
    }
}
