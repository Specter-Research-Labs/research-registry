use std::collections::HashMap;

use egui::Color32;

use crate::RenderError;

#[derive(Clone, Debug, PartialEq)]
pub struct TreeNode<T> {
    pub id: String,
    pub data: T,
    pub children: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Graph<N, E> {
    pub nodes: HashMap<String, N>,
    pub edges: Vec<(String, String, E)>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Series {
    pub label: String,
    pub points: Vec<[f64; 2]>,
    pub color: Color32,
    pub legend_label: Option<String>,
    pub show_in_legend: bool,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct IntervalDatum {
    pub x: f64,
    pub lower: f64,
    pub upper: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct IntervalSeries {
    pub label: String,
    pub intervals: Vec<IntervalDatum>,
    pub color: Color32,
    pub legend_label: Option<String>,
    pub show_in_legend: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PointShape {
    Circle,
    Diamond,
    Square,
    Up,
    Cross,
}

impl Default for PointShape {
    fn default() -> Self {
        Self::Circle
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct PointSeries {
    pub label: String,
    pub points: Vec<[f64; 2]>,
    pub color: Color32,
    pub point_labels: Option<Vec<String>>,
    pub point_meta: Option<Vec<PointMeta>>,
    pub radius: f32,
    pub highlight: bool,
    pub shape: PointShape,
    pub filled: bool,
    pub legend_label: Option<String>,
    pub show_in_legend: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PointMeta {
    pub title: String,
    pub lines: Vec<String>,
}

impl Series {
    #[must_use]
    pub fn new(label: impl Into<String>, points: Vec<[f64; 2]>, color: Color32) -> Self {
        Self {
            label: label.into(),
            points,
            color,
            legend_label: None,
            show_in_legend: true,
        }
    }

    #[must_use]
    #[allow(clippy::cast_precision_loss)]
    pub fn from_values(
        label: impl Into<String>,
        values: impl IntoIterator<Item = f64>,
        color: Color32,
    ) -> Self {
        let points = values
            .into_iter()
            .enumerate()
            .map(|(index, value)| [index as f64, value])
            .collect();
        Self::new(label, points, color)
    }

    pub fn from_xy(
        label: impl Into<String>,
        xs: impl IntoIterator<Item = f64>,
        ys: impl IntoIterator<Item = f64>,
        color: Color32,
    ) -> Result<Self, RenderError> {
        let points = zip_exact_pair("Series", "x", xs, "y", ys)?
            .into_iter()
            .map(|(x, y)| [x, y])
            .collect();
        Ok(Self::new(label, points, color))
    }

    #[must_use]
    pub fn legend_label(mut self, label: impl Into<String>) -> Self {
        self.legend_label = Some(label.into());
        self
    }

    #[must_use]
    pub const fn show_in_legend(mut self, show: bool) -> Self {
        self.show_in_legend = show;
        self
    }

    /// # Errors
    /// Returns an error if any point has a non-finite x/y coordinate.
    pub fn validate(&self, widget: &'static str) -> Result<(), RenderError> {
        validate_xy_points(widget, &self.label, &self.points)
    }

    #[must_use]
    pub fn legend_name(&self) -> &str {
        if !self.show_in_legend {
            ""
        } else {
            self.legend_label.as_deref().unwrap_or(&self.label)
        }
    }
}

impl IntervalSeries {
    #[must_use]
    pub fn new(label: impl Into<String>, intervals: Vec<IntervalDatum>, color: Color32) -> Self {
        Self {
            label: label.into(),
            intervals,
            color,
            legend_label: None,
            show_in_legend: true,
        }
    }

    #[must_use]
    #[allow(clippy::cast_precision_loss)]
    pub fn from_values(
        label: impl Into<String>,
        lower: impl IntoIterator<Item = f64>,
        upper: impl IntoIterator<Item = f64>,
        color: Color32,
    ) -> Result<Self, RenderError> {
        let intervals = zip_exact_pair("IntervalSeries", "lower", lower, "upper", upper)?
            .into_iter()
            .enumerate()
            .map(|(index, (lower, upper))| IntervalDatum {
                x: index as f64,
                lower,
                upper,
            })
            .collect();
        Ok(Self::new(label, intervals, color))
    }

    pub fn from_xy(
        label: impl Into<String>,
        xs: impl IntoIterator<Item = f64>,
        lower: impl IntoIterator<Item = f64>,
        upper: impl IntoIterator<Item = f64>,
        color: Color32,
    ) -> Result<Self, RenderError> {
        let intervals = zip_exact_triple("IntervalSeries", xs, lower, upper)?
            .into_iter()
            .map(|(x, lower, upper)| IntervalDatum { x, lower, upper })
            .collect();
        Ok(Self::new(label, intervals, color))
    }

    #[must_use]
    pub fn legend_label(mut self, label: impl Into<String>) -> Self {
        self.legend_label = Some(label.into());
        self
    }

    #[must_use]
    pub const fn show_in_legend(mut self, show: bool) -> Self {
        self.show_in_legend = show;
        self
    }

    /// # Errors
    /// Returns an error if any interval contains a non-finite value or `lower > upper`.
    pub fn validate(&self, widget: &'static str) -> Result<(), RenderError> {
        for (index, interval) in self.intervals.iter().enumerate() {
            if !(interval.x.is_finite() && interval.lower.is_finite() && interval.upper.is_finite())
            {
                return Err(RenderError::new(
                    widget,
                    format!(
                        "{} has a non-finite interval at index {index}",
                        label_for_error(&self.label, "interval series"),
                    ),
                ));
            }
            if interval.lower > interval.upper {
                return Err(RenderError::new(
                    widget,
                    format!(
                        "{} has an inverted interval at index {index}: lower {} > upper {}",
                        label_for_error(&self.label, "interval series"),
                        interval.lower,
                        interval.upper,
                    ),
                ));
            }
        }
        Ok(())
    }

    #[must_use]
    pub fn legend_name(&self) -> &str {
        if !self.show_in_legend {
            ""
        } else {
            self.legend_label.as_deref().unwrap_or(&self.label)
        }
    }
}

impl PointSeries {
    #[must_use]
    pub fn new(label: impl Into<String>, points: Vec<[f64; 2]>, color: Color32) -> Self {
        Self {
            label: label.into(),
            points,
            color,
            point_labels: None,
            point_meta: None,
            radius: 3.5,
            highlight: false,
            shape: PointShape::default(),
            filled: true,
            legend_label: None,
            show_in_legend: true,
        }
    }

    #[must_use]
    pub fn point_labels(mut self, labels: Vec<String>) -> Self {
        self.point_labels = Some(labels);
        self
    }

    #[must_use]
    pub fn point_meta(mut self, meta: Vec<PointMeta>) -> Self {
        self.point_meta = Some(meta);
        self
    }

    #[must_use]
    pub const fn radius(mut self, radius: f32) -> Self {
        self.radius = radius;
        self
    }

    #[must_use]
    pub const fn highlight(mut self, highlight: bool) -> Self {
        self.highlight = highlight;
        self
    }

    #[must_use]
    pub const fn shape(mut self, shape: PointShape) -> Self {
        self.shape = shape;
        self
    }

    #[must_use]
    pub const fn filled(mut self, filled: bool) -> Self {
        self.filled = filled;
        self
    }

    #[must_use]
    pub fn legend_label(mut self, label: impl Into<String>) -> Self {
        self.legend_label = Some(label.into());
        self
    }

    #[must_use]
    pub const fn show_in_legend(mut self, show: bool) -> Self {
        self.show_in_legend = show;
        self
    }

    /// # Errors
    /// Returns an error if any point is non-finite or metadata lengths disagree with the point
    /// count.
    pub fn validate(&self, widget: &'static str) -> Result<(), RenderError> {
        validate_xy_points(widget, &self.label, &self.points)?;

        if let Some(labels) = self.point_labels.as_ref() {
            validate_aux_len(widget, &self.label, "point labels", labels.len(), self.points.len())?;
        }

        if let Some(meta) = self.point_meta.as_ref() {
            validate_aux_len(widget, &self.label, "point metadata", meta.len(), self.points.len())?;
        }

        Ok(())
    }

    #[must_use]
    pub fn legend_name(&self) -> &str {
        if !self.show_in_legend {
            ""
        } else {
            self.legend_label.as_deref().unwrap_or(&self.label)
        }
    }
}

fn label_for_error(label: &str, fallback: &str) -> String {
    if label.is_empty() {
        fallback.to_string()
    } else {
        format!("series '{}'", label)
    }
}

fn validate_xy_points(
    widget: &'static str,
    label: &str,
    points: &[[f64; 2]],
) -> Result<(), RenderError> {
    for (index, point) in points.iter().enumerate() {
        if !(point[0].is_finite() && point[1].is_finite()) {
            return Err(RenderError::new(
                widget,
                format!(
                    "{} has a non-finite point at index {index}: ({}, {})",
                    label_for_error(label, "series"),
                    point[0],
                    point[1],
                ),
            ));
        }
    }
    Ok(())
}

fn validate_aux_len(
    widget: &'static str,
    label: &str,
    field: &str,
    actual: usize,
    expected: usize,
) -> Result<(), RenderError> {
    if actual == expected {
        Ok(())
    } else {
        Err(RenderError::new(
            widget,
            format!(
                "{} has {actual} {field}, expected {expected}",
                label_for_error(label, "series"),
            ),
        ))
    }
}

fn zip_exact_pair<A, B>(
    widget: &'static str,
    left_name: &str,
    left: impl IntoIterator<Item = A>,
    right_name: &str,
    right: impl IntoIterator<Item = B>,
) -> Result<Vec<(A, B)>, RenderError> {
    let mut left = left.into_iter();
    let mut right = right.into_iter();
    let mut items = Vec::new();
    let mut index = 0;

    loop {
        match (left.next(), right.next()) {
            (Some(a), Some(b)) => {
                items.push((a, b));
                index += 1;
            }
            (None, None) => return Ok(items),
            (Some(_), None) | (None, Some(_)) => {
                return Err(RenderError::new(
                    widget,
                    format!("{left_name} and {right_name} lengths differ at index {index}"),
                ))
            }
        }
    }
}

fn zip_exact_triple(
    widget: &'static str,
    xs: impl IntoIterator<Item = f64>,
    lower: impl IntoIterator<Item = f64>,
    upper: impl IntoIterator<Item = f64>,
) -> Result<Vec<(f64, f64, f64)>, RenderError> {
    let mut xs = xs.into_iter();
    let mut lower = lower.into_iter();
    let mut upper = upper.into_iter();
    let mut items = Vec::new();
    let mut index = 0;

    loop {
        match (xs.next(), lower.next(), upper.next()) {
            (Some(x), Some(low), Some(high)) => {
                items.push((x, low, high));
                index += 1;
            }
            (None, None, None) => return Ok(items),
            _ => {
                return Err(RenderError::new(
                    widget,
                    format!("x/lower/upper lengths differ at index {index}"),
                ))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{IntervalSeries, PointMeta, PointSeries, Series};
    use crate::core::colors;

    #[test]
    fn series_from_xy_rejects_length_mismatch() {
        let err = Series::from_xy("loss", [0.0, 1.0], [1.0], colors::ACCENT_BLUE)
            .expect_err("mismatched x/y lengths should fail");
        assert_eq!(err.to_string(), "Series: x and y lengths differ at index 1");
    }

    #[test]
    fn interval_series_from_values_rejects_length_mismatch() {
        let err = IntervalSeries::from_values("band", [0.2, 0.3], [0.4], colors::ACCENT_TEAL)
            .expect_err("mismatched interval lengths should fail");
        assert_eq!(
            err.to_string(),
            "IntervalSeries: lower and upper lengths differ at index 1"
        );
    }

    #[test]
    fn point_series_validation_rejects_metadata_length_mismatch() {
        let series = PointSeries::new("embeddings", vec![[0.0, 1.0]], colors::ACCENT_GOLD)
            .point_meta(vec![PointMeta {
                title: "p0".into(),
                lines: vec!["only".into()],
            }])
            .point_labels(vec!["p0".into(), "p1".into()]);
        let err = series
            .validate("ScatterPlot")
            .expect_err("point label mismatch should fail");
        assert_eq!(
            err.to_string(),
            "ScatterPlot: series 'embeddings' has 2 point labels, expected 1"
        );
    }
}
