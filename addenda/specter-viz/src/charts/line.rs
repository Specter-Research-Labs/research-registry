use egui::{Response, Ui};
use egui_plot::{Line, Polygon};

use crate::types::{IntervalSeries, Series};
use crate::RenderError;

use super::{
    configure_plot, interval_series_polygon_points, series_points, with_plot_visuals, AxisPolicy,
    PlotInteraction,
};

#[allow(clippy::struct_excessive_bools)]
pub struct LineChart<'a> {
    series: Vec<&'a Series>,
    intervals: Vec<&'a IntervalSeries>,
    x_label: Option<&'a str>,
    y_label: Option<&'a str>,
    height: Option<f32>,
    x_axis: AxisPolicy,
    y_axis: AxisPolicy,
    interactions: PlotInteraction,
}

impl Default for LineChart<'_> {
    fn default() -> Self {
        Self::new()
    }
}

impl<'a> LineChart<'a> {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            series: Vec::new(),
            intervals: Vec::new(),
            x_label: None,
            y_label: None,
            height: None,
            x_axis: AxisPolicy::auto(),
            y_axis: AxisPolicy::auto(),
            interactions: PlotInteraction::disabled(),
        }
    }

    #[must_use]
    pub fn series(mut self, series: &'a Series) -> Self {
        self.series.push(series);
        self
    }

    #[must_use]
    pub fn extend_series<I>(mut self, series: I) -> Self
    where
        I: IntoIterator<Item = &'a Series>,
    {
        self.series.extend(series);
        self
    }

    #[must_use]
    pub fn interval(mut self, series: &'a IntervalSeries) -> Self {
        self.intervals.push(series);
        self
    }

    #[must_use]
    pub fn extend_intervals<I>(mut self, intervals: I) -> Self
    where
        I: IntoIterator<Item = &'a IntervalSeries>,
    {
        self.intervals.extend(intervals);
        self
    }

    #[must_use]
    pub const fn x_label(mut self, label: &'a str) -> Self {
        self.x_label = Some(label);
        self
    }

    #[must_use]
    pub const fn y_label(mut self, label: &'a str) -> Self {
        self.y_label = Some(label);
        self
    }

    #[must_use]
    pub const fn height(mut self, height: f32) -> Self {
        self.height = Some(height);
        self
    }

    #[must_use]
    pub const fn auto_bounds(mut self, x: bool, y: bool) -> Self {
        self.x_axis = self.x_axis.auto_bounds(x);
        self.y_axis = self.y_axis.auto_bounds(y);
        self
    }

    #[must_use]
    pub const fn include_zero_x(mut self) -> Self {
        self.x_axis = self.x_axis.include_zero(true);
        self
    }

    #[must_use]
    pub const fn include_zero_y(mut self) -> Self {
        self.y_axis = self.y_axis.include_zero(true);
        self
    }

    #[must_use]
    pub const fn include_zero(mut self) -> Self {
        self.x_axis = self.x_axis.include_zero(true);
        self.y_axis = self.y_axis.include_zero(true);
        self
    }

    #[must_use]
    pub const fn axis_policy(mut self, x: AxisPolicy, y: AxisPolicy) -> Self {
        self.x_axis = x;
        self.y_axis = y;
        self
    }

    #[must_use]
    pub const fn x_axis_policy(mut self, policy: AxisPolicy) -> Self {
        self.x_axis = policy;
        self
    }

    #[must_use]
    pub const fn y_axis_policy(mut self, policy: AxisPolicy) -> Self {
        self.y_axis = policy;
        self
    }

    #[must_use]
    pub const fn interactions(mut self, interactions: PlotInteraction) -> Self {
        self.interactions = interactions;
        self
    }

    #[must_use]
    pub const fn interactive(mut self, enabled: bool) -> Self {
        self.interactions = if enabled {
            PlotInteraction::enabled()
        } else {
            PlotInteraction::disabled()
        };
        self
    }

    /// # Panics
    /// Panics if rendering fails. Use [`Self::try_show`] to handle invalid input.
    pub fn show(self, ui: &mut Ui) -> Response {
        self.try_show(ui).unwrap_or_else(|err| panic!("{err}"))
    }

    /// # Errors
    /// Returns an error if any series contains invalid values for the configured axes.
    pub fn try_show(self, ui: &mut Ui) -> Result<Response, RenderError> {
        let x_axis = self.x_axis;
        let y_axis = self.y_axis;
        let x_label = self.x_label.unwrap_or("x");
        let y_label = self.y_label.unwrap_or("y");
        with_plot_visuals(ui, |ui| {
            let plot = configure_plot(
                egui_plot::Plot::new(ui.next_auto_id()),
                x_axis,
                y_axis,
                self.x_label,
                self.y_label,
                self.height,
                self.interactions,
                (x_label.to_string(), y_label.to_string()),
            );

            let inner = plot.show(ui, |plot_ui| -> Result<(), RenderError> {
                for interval in self.intervals {
                    let points = interval_series_polygon_points("LineChart", interval, x_axis, y_axis)?;
                    if points.points().is_empty() {
                        continue;
                    }
                    let fill = interval.color.gamma_multiply(0.2);
                    let stroke = interval.color.gamma_multiply(0.5);
                    let polygon = Polygon::new(interval.legend_name(), points)
                        .fill_color(fill)
                        .stroke(egui::Stroke::new(1.0, stroke));
                    plot_ui.polygon(polygon);
                }
                for series in self.series {
                    let points = series_points("LineChart", series, x_axis, y_axis)?;
                    let line = Line::new(series.legend_name(), points)
                        .color(series.color)
                        .width(1.8);
                    plot_ui.line(line);
                }
                Ok(())
            });

            inner.inner?;
            Ok(inner.response)
        })
    }
}

#[cfg(test)]
mod tests {
    use super::LineChart;
    use crate::core::colors;
    use crate::types::Series;

    #[test]
    fn line_chart_try_show_rejects_non_finite_points() {
        let series = Series::new("loss", vec![[0.0, f64::NAN]], colors::ACCENT_BLUE);
        egui::__run_test_ui(|ui| {
            let err = LineChart::new()
                .series(&series)
                .try_show(ui)
                .expect_err("nan should fail validation");
            assert_eq!(
                err.to_string(),
                "LineChart: series 'loss' has a non-finite point at index 0: (0, NaN)"
            );
        });
    }
}
