use egui::{
    Align2, Color32, FontId, Painter, Pos2, Rect, Response, RichText, Sense, Stroke, StrokeKind,
    Ui, Vec2,
};

use crate::core::{colors, spacing, typography};
use crate::RenderError;

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub enum HeatScale {
    /// Treat values as a ratio (0..=1) and clamp.
    #[default]
    UnitInterval,
    /// Map the finite min/max values in the matrix to 0..=1.
    MinMax,
    /// Map values around `mid`, using the maximum absolute deviation as scale.
    Diverging { mid: f64 },
}

pub struct HeatMap<'a> {
    data: &'a [Vec<f64>],
    row_labels: Option<&'a [String]>,
    col_labels: Option<&'a [String]>,
    height: Option<f32>,
    scale: HeatScale,
    legend: bool,
}

impl<'a> HeatMap<'a> {
    #[must_use]
    pub const fn new(data: &'a [Vec<f64>]) -> Self {
        Self {
            data,
            row_labels: None,
            col_labels: None,
            height: None,
            scale: HeatScale::UnitInterval,
            legend: false,
        }
    }

    #[must_use]
    pub const fn row_labels(mut self, labels: &'a [String]) -> Self {
        self.row_labels = Some(labels);
        self
    }

    #[must_use]
    pub const fn col_labels(mut self, labels: &'a [String]) -> Self {
        self.col_labels = Some(labels);
        self
    }

    #[must_use]
    pub const fn height(mut self, height: f32) -> Self {
        self.height = Some(height);
        self
    }

    #[must_use]
    pub const fn scale(mut self, scale: HeatScale) -> Self {
        self.scale = scale;
        self
    }

    #[must_use]
    pub const fn legend(mut self, legend: bool) -> Self {
        self.legend = legend;
        self
    }

    #[allow(clippy::cast_precision_loss)]
    /// Render the heatmap.
    ///
    /// # Panics
    /// Panics if rendering fails. Use [`Self::try_show`] to handle errors.
    pub fn show(self, ui: &mut Ui) -> Response {
        self.try_show(ui).unwrap_or_else(|err| panic!("{err}"))
    }

    #[allow(clippy::cast_precision_loss)]
    /// Render the heatmap.
    ///
    /// # Errors
    /// Returns an error if the data is empty, row lengths are inconsistent, or label counts do not
    /// match the data dimensions.
    ///
    /// # Panics
    /// Does not panic. Use [`Self::show`] if you want panicking behavior.
    #[allow(clippy::too_many_lines)]
    pub fn try_show(self, ui: &mut Ui) -> Result<Response, RenderError> {
        let info = validate_heatmap(self.data, self.row_labels, self.col_labels)?;
        let font_id = typography::font_id_caption();
        let label_color = colors::TEXT_SECONDARY;
        let label_padding = spacing::SM;

        let row_label_size = label_extents(ui, self.row_labels, &font_id, label_color);
        let col_label_size = label_extents(ui, self.col_labels, &font_id, label_color);

        // Legend uses a bar plus one line of labels under it.
        let legend_height = if self.legend {
            typography::SIZE_CAPTION.mul_add(2.0, spacing::SM)
        } else {
            0.0
        };

        let available_width = ui.available_width();
        let grid_width = (available_width - row_label_size.x - label_padding).max(0.0);
        let desired_height = self.height.unwrap_or_else(|| {
            let cell_size = grid_width / info.cols as f32;
            cell_size * info.rows as f32 + col_label_size.y + label_padding + legend_height
        });
        let grid_height =
            (desired_height - col_label_size.y - label_padding - legend_height).max(0.0);
        let cell_size = (grid_width / info.cols as f32).min(grid_height / info.rows as f32);
        let grid_size = Vec2::new(cell_size * info.cols as f32, cell_size * info.rows as f32);
        let desired_size = Vec2::new(
            grid_width + row_label_size.x + label_padding,
            desired_height,
        );

        let (mut response, painter) = ui.allocate_painter(desired_size, Sense::hover());
        let grid_origin = response.rect.min
            + Vec2::new(
                row_label_size.x + label_padding,
                col_label_size.y + label_padding,
            );
        let grid_rect = Rect::from_min_size(grid_origin, grid_size);

        painter.rect_stroke(
            grid_rect,
            0.0,
            Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_SUBTLE),
            StrokeKind::Inside,
        );

        let stats = HeatStats::from_data(self.data, self.scale);
        draw_cells(
            &painter,
            self.data,
            grid_origin,
            cell_size,
            self.scale,
            stats,
        );
        draw_row_labels(
            &painter,
            self.row_labels,
            grid_origin,
            label_padding,
            cell_size,
            &font_id,
            label_color,
        );
        draw_col_labels(
            &painter,
            self.col_labels,
            grid_origin,
            label_padding,
            cell_size,
            &font_id,
            label_color,
        );

        if self.legend && cell_size > 0.0 {
            let legend_origin = Pos2::new(grid_origin.x, grid_rect.max.y + spacing::XS);
            let legend_size = Vec2::new(grid_size.x, typography::SIZE_CAPTION);
            draw_legend(
                &painter,
                legend_origin,
                legend_size,
                self.scale,
                stats,
                &font_id,
                label_color,
            );
        }

        if cell_size > 0.0 {
            if let Some(pos) = response.hover_pos() {
                if grid_rect.contains(pos) {
                    if let (Some(row_index), Some(col_index)) = (
                        cell_index(pos.y, grid_origin.y, cell_size, info.rows),
                        cell_index(pos.x, grid_origin.x, cell_size, info.cols),
                    ) {
                        let value = self.data[row_index][col_index];
                        let row_label = self
                            .row_labels
                            .and_then(|labels| labels.get(row_index))
                            .map_or_else(|| format!("Row {}", row_index + 1), Clone::clone);
                        let col_label = self
                            .col_labels
                            .and_then(|labels| labels.get(col_index))
                            .map_or_else(|| format!("Col {}", col_index + 1), Clone::clone);

                        let value_text = if value.is_finite() {
                            format!("{value:.3}")
                        } else {
                            "missing".to_string()
                        };

                        response = response.on_hover_ui(|ui| {
                            ui.label(
                                RichText::new(format!(
                                    "Row: {row_label}\nCol: {col_label}\nValue: {value_text}"
                                ))
                                .color(colors::TEXT_PRIMARY)
                                .size(typography::SIZE_CAPTION),
                            );
                        });
                    }
                }
            }
        }

        Ok(response)
    }
}

struct HeatMapInfo {
    rows: usize,
    cols: usize,
}

fn validate_heatmap(
    data: &[Vec<f64>],
    row_labels: Option<&[String]>,
    col_labels: Option<&[String]>,
) -> Result<HeatMapInfo, RenderError> {
    let rows = data.len();
    if rows == 0 {
        return Err(RenderError::new(
            "HeatMap",
            "data must have at least one row",
        ));
    }
    let cols = data[0].len();
    if cols == 0 {
        return Err(RenderError::new(
            "HeatMap",
            "data must have at least one column",
        ));
    }

    for (row_index, row) in data.iter().enumerate() {
        if row.len() != cols {
            return Err(RenderError::new(
                "HeatMap",
                format!("row {row_index} length does not match column count"),
            ));
        }
    }

    if let Some(labels) = row_labels {
        if labels.len() != rows {
            return Err(RenderError::new(
                "HeatMap",
                "row label count does not match row count",
            ));
        }
    }

    if let Some(labels) = col_labels {
        if labels.len() != cols {
            return Err(RenderError::new(
                "HeatMap",
                "column label count does not match column count",
            ));
        }
    }

    Ok(HeatMapInfo { rows, cols })
}

fn label_extents(ui: &Ui, labels: Option<&[String]>, font_id: &FontId, color: Color32) -> Vec2 {
    let painter = ui.painter();
    labels.map_or(Vec2::ZERO, |labels| {
        labels
            .iter()
            .map(|label| painter.layout_no_wrap(label.clone(), font_id.clone(), color))
            .map(|galley| galley.size())
            .fold(Vec2::ZERO, |acc, size| {
                Vec2::new(acc.x.max(size.x), acc.y.max(size.y))
            })
    })
}

#[derive(Clone, Copy)]
struct HeatStats {
    min: f64,
    max: f64,
    max_abs_dev: f64,
}

impl HeatStats {
    fn from_data(data: &[Vec<f64>], scale: HeatScale) -> Option<Self> {
        let mut min = f64::INFINITY;
        let mut max = f64::NEG_INFINITY;
        for row in data {
            for value in row {
                if value.is_finite() {
                    min = min.min(*value);
                    max = max.max(*value);
                }
            }
        }
        if !min.is_finite() || !max.is_finite() {
            return None;
        }
        let max_abs_dev = match scale {
            HeatScale::Diverging { mid } => {
                let mut m: f64 = 0.0;
                for row in data {
                    for value in row {
                        if value.is_finite() {
                            m = m.max((*value - mid).abs());
                        }
                    }
                }
                m
            }
            _ => 0.0,
        };
        Some(Self {
            min,
            max,
            max_abs_dev,
        })
    }
}

#[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
fn draw_cells(
    painter: &Painter,
    data: &[Vec<f64>],
    origin: Pos2,
    cell_size: f32,
    scale: HeatScale,
    stats: Option<HeatStats>,
) {
    for (row_index, row) in data.iter().enumerate() {
        for (col_index, value) in row.iter().enumerate() {
            let min =
                origin + Vec2::new(col_index as f32 * cell_size, row_index as f32 * cell_size);
            let rect = Rect::from_min_size(min, Vec2::splat(cell_size));
            let ratio = ratio_from_value(*value, scale, stats);
            let color = heat_color_from_ratio(ratio, scale);
            painter.rect_filled(rect, 0.0, color);
        }
    }
}

#[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
fn ratio_from_value(value: f64, scale: HeatScale, stats: Option<HeatStats>) -> f32 {
    if !value.is_finite() {
        return f32::NAN;
    }
    match scale {
        HeatScale::UnitInterval => (value as f32).clamp(0.0, 1.0),
        HeatScale::MinMax => {
            let Some(stats) = stats else {
                return f32::NAN;
            };
            let span = stats.max - stats.min;
            if span <= 0.0 {
                return 0.5;
            }
            ((value - stats.min) / span) as f32
        }
        HeatScale::Diverging { mid } => {
            let Some(stats) = stats else {
                return f32::NAN;
            };
            let denom = stats.max_abs_dev.max(1e-12);
            let signed = (value - mid) / denom;
            (0.5_f64.mul_add(signed, 0.5)).clamp(0.0, 1.0) as f32
        }
    }
}

fn heat_color_from_ratio(ratio: f32, scale: HeatScale) -> Color32 {
    if !ratio.is_finite() {
        return colors::MISSING_DATA;
    }

    match scale {
        HeatScale::Diverging { .. } => colors::diverging_gradient(ratio),
        HeatScale::UnitInterval | HeatScale::MinMax => colors::sequential_gradient(ratio),
    }
}

#[allow(clippy::cast_precision_loss)]
fn draw_legend(
    painter: &Painter,
    origin: Pos2,
    size: Vec2,
    scale: HeatScale,
    stats: Option<HeatStats>,
    font_id: &FontId,
    label_color: Color32,
) {
    let steps: usize = 64;
    let steps_f = steps as f32;
    let step_w = (size.x / steps_f).max(1.0);
    for i in 0..steps {
        let ratio = i as f32 / (steps_f - 1.0);
        let rect = Rect::from_min_size(
            origin + Vec2::new(i as f32 * step_w, 0.0),
            Vec2::new(step_w, size.y),
        );
        painter.rect_filled(rect, 0.0, heat_color_from_ratio(ratio, scale));
    }

    let stroke = Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_SUBTLE);
    painter.rect_stroke(
        Rect::from_min_size(origin, size),
        0.0,
        stroke,
        StrokeKind::Inside,
    );

    let (left, mid, right): (String, Option<String>, String) = match scale {
        HeatScale::UnitInterval => ("0".to_string(), Some("0.5".to_string()), "1".to_string()),
        HeatScale::MinMax => {
            let Some(stats) = stats else {
                return;
            };
            (
                format!("{:.3}", stats.min),
                None,
                format!("{:.3}", stats.max),
            )
        }
        HeatScale::Diverging { mid } => {
            let Some(stats) = stats else {
                return;
            };
            (
                format!("{:.3}", mid - stats.max_abs_dev),
                Some(format!("{mid:.3}")),
                format!("{:.3}", mid + stats.max_abs_dev),
            )
        }
    };

    let y = origin.y + size.y + spacing::XS;
    painter.text(
        Pos2::new(origin.x, y),
        Align2::LEFT_TOP,
        left.as_str(),
        font_id.clone(),
        label_color,
    );
    if let Some(mid) = mid {
        painter.text(
            Pos2::new(size.x.mul_add(0.5, origin.x), y),
            Align2::CENTER_TOP,
            mid.as_str(),
            font_id.clone(),
            label_color,
        );
    }
    painter.text(
        Pos2::new(origin.x + size.x, y),
        Align2::RIGHT_TOP,
        right.as_str(),
        font_id.clone(),
        label_color,
    );
}

#[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
fn cell_index(pos: f32, origin: f32, cell_size: f32, max: usize) -> Option<usize> {
    let value = (pos - origin) / cell_size;
    if !value.is_finite() {
        return None;
    }
    let floored = value.floor();
    if floored < 0.0 {
        return None;
    }
    let index = floored as usize;
    if index >= max {
        None
    } else {
        Some(index)
    }
}

#[allow(clippy::cast_precision_loss)]
fn draw_row_labels(
    painter: &Painter,
    labels: Option<&[String]>,
    grid_origin: Pos2,
    label_padding: f32,
    cell_size: f32,
    font_id: &FontId,
    label_color: Color32,
) {
    let Some(labels) = labels else {
        return;
    };
    let x = grid_origin.x - label_padding;
    for (row_index, label) in labels.iter().enumerate() {
        let y = (row_index as f32 + 0.5).mul_add(cell_size, grid_origin.y);
        painter.text(
            Pos2::new(x, y),
            Align2::RIGHT_CENTER,
            label,
            font_id.clone(),
            label_color,
        );
    }
}

#[allow(clippy::cast_precision_loss)]
fn draw_col_labels(
    painter: &Painter,
    labels: Option<&[String]>,
    grid_origin: Pos2,
    label_padding: f32,
    cell_size: f32,
    font_id: &FontId,
    label_color: Color32,
) {
    let Some(labels) = labels else {
        return;
    };
    let y = grid_origin.y - label_padding;
    for (col_index, label) in labels.iter().enumerate() {
        let x = (col_index as f32 + 0.5).mul_add(cell_size, grid_origin.x);
        painter.text(
            Pos2::new(x, y),
            Align2::CENTER_BOTTOM,
            label,
            font_id.clone(),
            label_color,
        );
    }
}


#[cfg(test)]
mod tests {
    use super::{heat_color_from_ratio, validate_heatmap, HeatScale};
    use crate::core::colors;

    #[test]
    fn validate_heatmap_rejects_label_mismatch() {
        let data = vec![vec![0.1, 0.2]];
        let row_labels = vec!["r1".to_string(), "r2".to_string()];
        let err = match validate_heatmap(&data, Some(&row_labels), None) {
            Ok(_) => panic!("row labels should match heatmap height"),
            Err(err) => err,
        };
        assert_eq!(err.to_string(), "HeatMap: row label count does not match row count");
    }

    #[test]
    fn heat_color_uses_missing_color_for_nan() {
        assert_eq!(heat_color_from_ratio(f32::NAN, HeatScale::UnitInterval), colors::MISSING_DATA);
    }

    #[test]
    fn diverging_heat_color_differs_from_sequential() {
        assert_ne!(
            heat_color_from_ratio(0.25, HeatScale::Diverging { mid: 0.0 }),
            heat_color_from_ratio(0.25, HeatScale::UnitInterval),
        );
    }
}
