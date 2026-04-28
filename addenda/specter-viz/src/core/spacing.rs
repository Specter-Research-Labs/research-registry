pub const UNIT: f32 = 4.0;

pub const XS: f32 = UNIT;
pub const SM: f32 = UNIT * 2.0;
pub const MD: f32 = UNIT * 4.0;
pub const LG: f32 = UNIT * 6.0;
pub const XL: f32 = UNIT * 8.0;

pub const PANEL_PADDING: f32 = MD;
pub const PANEL_GAP: f32 = SM;

pub const CORNER_RADIUS: u8 = 0;
pub const BORDER_WIDTH: f32 = 1.0;

#[must_use]
pub const fn grid(n: u8) -> f32 {
    UNIT * n as f32
}
