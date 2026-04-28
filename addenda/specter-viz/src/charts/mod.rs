mod graph;
mod heatmap;
mod line;
mod scatter;

pub use graph::{GraphView, GraphViewInteraction, GraphViewResponse};
pub use heatmap::{HeatMap, HeatScale};
pub use line::LineChart;
pub use scatter::ScatterPlot;

use egui::{vec2, Rangef, Stroke, Ui};
use egui_plot::{Corner, Legend, Plot, PlotPoint, PlotPoints};

use crate::core::{colors, typography};
use crate::types::{IntervalSeries, PointSeries, Series};
use crate::RenderError;

#[derive(Clone, Copy)]
pub struct PlotInteraction {
    allow_zoom: bool,
    allow_scroll: bool,
    allow_drag: bool,
}

impl PlotInteraction {
    #[must_use]
    pub const fn enabled() -> Self {
        Self {
            allow_zoom: true,
            allow_scroll: true,
            allow_drag: true,
        }
    }

    #[must_use]
    pub const fn disabled() -> Self {
        Self {
            allow_zoom: false,
            allow_scroll: false,
            allow_drag: false,
        }
    }

    #[must_use]
    pub const fn allow_zoom(mut self, allow: bool) -> Self {
        self.allow_zoom = allow;
        self
    }

    #[must_use]
    pub const fn allow_scroll(mut self, allow: bool) -> Self {
        self.allow_scroll = allow;
        self
    }

    #[must_use]
    pub const fn allow_drag(mut self, allow: bool) -> Self {
        self.allow_drag = allow;
        self
    }
}

#[derive(Clone, Copy)]
pub struct AxisPolicy {
    auto_bounds: bool,
    include_zero: bool,
    include_one: bool,
    transform: AxisTransform,
    format: AxisFormat,
    clamp: Option<(f64, f64)>,
}

impl AxisPolicy {
    #[must_use]
    pub const fn auto() -> Self {
        Self {
            auto_bounds: true,
            include_zero: false,
            include_one: false,
            transform: AxisTransform::Linear,
            format: AxisFormat::Default,
            clamp: None,
        }
    }

    #[must_use]
    pub const fn fixed() -> Self {
        Self {
            auto_bounds: false,
            include_zero: false,
            include_one: false,
            transform: AxisTransform::Linear,
            format: AxisFormat::Default,
            clamp: None,
        }
    }

    #[must_use]
    pub const fn percent() -> Self {
        Self {
            auto_bounds: true,
            include_zero: true,
            include_one: true,
            transform: AxisTransform::Linear,
            format: AxisFormat::Percent,
            clamp: Some((0.0, 1.0)),
        }
    }

    #[must_use]
    pub const fn percent_strict() -> Self {
        Self {
            auto_bounds: true,
            include_zero: true,
            include_one: true,
            transform: AxisTransform::Linear,
            format: AxisFormat::Percent,
            clamp: None,
        }
    }

    #[must_use]
    pub const fn percent_clamped() -> Self {
        Self {
            auto_bounds: true,
            include_zero: true,
            include_one: true,
            transform: AxisTransform::Linear,
            format: AxisFormat::Percent,
            clamp: Some((0.0, 1.0)),
        }
    }

    #[must_use]
    pub const fn log10() -> Self {
        Self {
            auto_bounds: true,
            include_zero: false,
            include_one: false,
            transform: AxisTransform::Log10,
            format: AxisFormat::Log10,
            clamp: None,
        }
    }

    #[must_use]
    pub const fn auto_bounds(mut self, auto_bounds: bool) -> Self {
        self.auto_bounds = auto_bounds;
        self
    }

    #[must_use]
    pub const fn include_zero(mut self, include_zero: bool) -> Self {
        self.include_zero = include_zero;
        self
    }

    #[must_use]
    pub const fn include_one(mut self, include_one: bool) -> Self {
        self.include_one = include_one;
        self
    }

    #[must_use]
    pub const fn transform(mut self, transform: AxisTransform) -> Self {
        self.transform = transform;
        self
    }

    #[must_use]
    pub const fn format(mut self, format: AxisFormat) -> Self {
        self.format = format;
        self
    }

    #[must_use]
    pub const fn clamp_range(mut self, min: f64, max: f64) -> Self {
        self.clamp = Some((min, max));
        self
    }

    const fn should_auto(self) -> bool {
        self.auto_bounds
    }

    const fn should_include_zero(self) -> bool {
        self.include_zero
    }

    const fn should_include_one(self) -> bool {
        self.include_one
    }

    const fn needs_formatter(self) -> bool {
        !matches!(self.format, AxisFormat::Default)
            || !matches!(self.transform, AxisTransform::Linear)
    }

    pub(super) fn try_transform_value(self, value: f64) -> Option<f64> {
        if !value.is_finite() {
            return None;
        }
        let mut value = value;
        if let Some((min, max)) = self.clamp {
            value = value.clamp(min, max);
        } else if matches!(self.format, AxisFormat::Percent) && !(0.0..=1.0).contains(&value) {
            return None;
        }

        match self.transform {
            AxisTransform::Linear => Some(value),
            AxisTransform::Log10 => {
                if value > 0.0 {
                    Some(value.log10())
                } else {
                    None
                }
            }
        }
    }

    fn inverse_transform(self, value: f64) -> f64 {
        match self.transform {
            AxisTransform::Linear => value,
            AxisTransform::Log10 => 10.0_f64.powf(value),
        }
    }

    fn format_tick(self, value: f64) -> String {
        let value = self.inverse_transform(value);
        match self.format {
            AxisFormat::Default | AxisFormat::Log10 => format_number(value, 2),
            AxisFormat::Percent => format_percent(value, 1),
        }
    }

    fn format_hover(self, value: f64) -> String {
        let value = self.inverse_transform(value);
        match self.format {
            AxisFormat::Default | AxisFormat::Log10 => format_number(value, 3),
            AxisFormat::Percent => format_percent(value, 1),
        }
    }
}

#[derive(Clone, Copy)]
pub enum AxisTransform {
    Linear,
    Log10,
}

#[derive(Clone, Copy)]
pub enum AxisFormat {
    Default,
    Percent,
    Log10,
}

fn label_for_error(label: &str, fallback: &str) -> String {
    if label.is_empty() {
        fallback.to_string()
    } else {
        format!("{} '{}'", fallback, label)
    }
}

fn transform_value(
    widget: &'static str,
    label: &str,
    series_kind: &str,
    axis_name: &str,
    index: usize,
    value: f64,
    axis: AxisPolicy,
) -> Result<f64, RenderError> {
    axis.try_transform_value(value).ok_or_else(|| {
        RenderError::new(
            widget,
            format!(
                "{} has an invalid {axis_name} value at index {index}: {value}",
                label_for_error(label, series_kind),
            ),
        )
    })
}

fn series_points(
    widget: &'static str,
    series: &Series,
    x_axis: AxisPolicy,
    y_axis: AxisPolicy,
) -> Result<PlotPoints<'static>, RenderError> {
    series.validate(widget)?;
    let mut points = Vec::with_capacity(series.points.len());
    for (index, point) in series.points.iter().enumerate() {
        let x = transform_value(widget, &series.label, "series", "x", index, point[0], x_axis)?;
        let y = transform_value(widget, &series.label, "series", "y", index, point[1], y_axis)?;
        points.push([x, y]);
    }
    Ok(points.into())
}

fn point_series_points(
    widget: &'static str,
    series: &PointSeries,
    x_axis: AxisPolicy,
    y_axis: AxisPolicy,
) -> Result<PlotPoints<'static>, RenderError> {
    series.validate(widget)?;
    let mut points = Vec::with_capacity(series.points.len());
    for (index, point) in series.points.iter().enumerate() {
        let x = transform_value(widget, &series.label, "point series", "x", index, point[0], x_axis)?;
        let y = transform_value(widget, &series.label, "point series", "y", index, point[1], y_axis)?;
        points.push([x, y]);
    }
    Ok(points.into())
}

fn interval_series_polygon_points(
    widget: &'static str,
    series: &IntervalSeries,
    x_axis: AxisPolicy,
    y_axis: AxisPolicy,
) -> Result<PlotPoints<'static>, RenderError> {
    series.validate(widget)?;
    let len = series.intervals.len();
    let mut lower_points = Vec::with_capacity(len);
    let mut upper_points = Vec::with_capacity(len);

    for (index, interval) in series.intervals.iter().enumerate() {
        let x = transform_value(widget, &series.label, "interval series", "x", index, interval.x, x_axis)?;
        let y_low = transform_value(
            widget,
            &series.label,
            "interval series",
            "lower y",
            index,
            interval.lower,
            y_axis,
        )?;
        let y_high = transform_value(
            widget,
            &series.label,
            "interval series",
            "upper y",
            index,
            interval.upper,
            y_axis,
        )?;

        lower_points.push([x, y_low]);
        upper_points.push([x, y_high]);
    }

    upper_points.reverse();
    lower_points.extend(upper_points);
    Ok(lower_points.into())
}

fn default_plot_legend() -> Legend {
    Legend::default()
        .text_style(egui::TextStyle::Small)
        .position(Corner::RightTop)
        .background_alpha(0.16)
        .follow_insertion_order(true)
}

fn configure_plot<'a>(
    mut plot: Plot<'a>,
    x_axis: AxisPolicy,
    y_axis: AxisPolicy,
    x_label: Option<&str>,
    y_label: Option<&str>,
    height: Option<f32>,
    interactions: PlotInteraction,
    hover_labels: (String, String),
) -> Plot<'a> {
    plot = plot
        .legend(default_plot_legend())
        .show_background(true)
        .auto_bounds(egui::Vec2b::new(x_axis.should_auto(), y_axis.should_auto()))
        .allow_zoom(interactions.allow_zoom)
        .allow_scroll(interactions.allow_scroll)
        .allow_drag(interactions.allow_drag)
        .set_margin_fraction(vec2(0.03, 0.08))
        .grid_spacing(Rangef::new(24.0, 140.0))
        .clamp_grid(true)
        .cursor_color(colors::ACCENT_BLUE.gamma_multiply(0.75))
        .label_formatter(move |name: &str, value: &PlotPoint| {
            let x_value = x_axis.format_hover(value.x);
            let y_value = y_axis.format_hover(value.y);
            let x_caption = &hover_labels.0;
            let y_caption = &hover_labels.1;
            if name.is_empty() {
                format!("{x_caption}: {x_value}\n{y_caption}: {y_value}")
            } else {
                format!("{name}\n{x_caption}: {x_value}\n{y_caption}: {y_value}")
            }
        });

    if x_axis.should_include_zero() {
        if let Some(x) = x_axis.try_transform_value(0.0) {
            plot = plot.include_x(x);
        }
    }

    if x_axis.should_include_one() {
        if let Some(x) = x_axis.try_transform_value(1.0) {
            plot = plot.include_x(x);
        }
    }

    if y_axis.should_include_zero() {
        if let Some(y) = y_axis.try_transform_value(0.0) {
            plot = plot.include_y(y);
        }
    }

    if y_axis.should_include_one() {
        if let Some(y) = y_axis.try_transform_value(1.0) {
            plot = plot.include_y(y);
        }
    }

    if x_axis.needs_formatter() {
        plot = plot.x_axis_formatter(move |mark, _range| x_axis.format_tick(mark.value));
    }

    if y_axis.needs_formatter() {
        plot = plot.y_axis_formatter(move |mark, _range| y_axis.format_tick(mark.value));
    }

    if let Some(height) = height {
        plot = plot.height(height);
    }

    if let Some(label) = x_label {
        plot = plot.x_axis_label(
            egui::RichText::new(label)
                .font(typography::font_id_caption())
                .color(colors::TEXT_SECONDARY),
        );
    }

    if let Some(label) = y_label {
        plot = plot.y_axis_label(
            egui::RichText::new(label)
                .font(typography::font_id_caption())
                .color(colors::TEXT_SECONDARY),
        );
    }

    plot
}

fn with_plot_visuals<R>(ui: &mut Ui, add_contents: impl FnOnce(&mut Ui) -> R) -> R {
    ui.scope(|ui| {
        ui.style_mut().visuals.widgets.noninteractive.bg_stroke =
            Stroke::new(1.0, colors::BORDER_DEFAULT);
        ui.style_mut().visuals.widgets.noninteractive.fg_stroke =
            Stroke::new(1.0, colors::TEXT_SECONDARY);
        ui.style_mut().visuals.widgets.hovered.bg_stroke = Stroke::new(1.0, colors::ACCENT_BLUE);
        ui.style_mut().visuals.widgets.hovered.fg_stroke = Stroke::new(1.0, colors::TEXT_PRIMARY);
        add_contents(ui)
    })
    .inner
}

fn format_number(value: f64, decimals: usize) -> String {
    if !value.is_finite() {
        return "nan".to_string();
    }
    let abs = value.abs();
    if abs >= 1e6 || (abs > 0.0 && abs < 1e-3) {
        return format!("{value:.2e}");
    }
    format!("{value:.decimals$}")
}

fn format_percent(value: f64, decimals: usize) -> String {
    if !value.is_finite() {
        return "nan".to_string();
    }
    format!("{:.decimals$}%", value * 100.0)
}

#[cfg(test)]
mod tests {
    use super::{series_points, AxisPolicy};
    use crate::core::colors;
    use crate::types::Series;

    #[test]
    fn percent_strict_rejects_out_of_range_values() {
        assert_eq!(AxisPolicy::percent_strict().try_transform_value(1.25), None);
    }

    #[test]
    fn percent_clamped_clamps_values() {
        assert_eq!(AxisPolicy::percent().try_transform_value(1.25), Some(1.0));
    }

    #[test]
    fn log10_rejects_non_positive_values() {
        assert_eq!(AxisPolicy::log10().try_transform_value(0.0), None);
        assert_eq!(AxisPolicy::log10().try_transform_value(-1.0), None);
    }

    #[test]
    fn series_points_reject_axis_incompatible_values() {
        let series = Series::new("accuracy", vec![[0.0, 1.2]], colors::ACCENT_BLUE);
        let err = match series_points(
            "LineChart",
            &series,
            AxisPolicy::auto(),
            AxisPolicy::percent_strict(),
        ) {
            Ok(_) => panic!("strict percent axis should reject values above 1.0"),
            Err(err) => err,
        };
        assert_eq!(
            err.to_string(),
            "LineChart: series 'accuracy' has an invalid y value at index 0: 1.2"
        );
    }
}
