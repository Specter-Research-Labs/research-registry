use egui::{Response, RichText, Ui};
use egui_plot::{MarkerShape, PlotPoint, PlotUi, Points};

use crate::core::{colors, typography};
use crate::types::{PointSeries, PointShape, Series};
use crate::RenderError;

use super::{
    configure_plot, point_series_points, series_points, transform_value, with_plot_visuals,
    AxisPolicy, PlotInteraction,
};

type HoverMetaFn<'a> = dyn Fn(&PointSeries, usize) -> Option<crate::types::PointMeta> + 'a;

pub struct ScatterPlot<'a> {
    series: Vec<&'a Series>,
    point_series: Vec<&'a PointSeries>,
    x_label: Option<&'a str>,
    y_label: Option<&'a str>,
    height: Option<f32>,
    x_axis: AxisPolicy,
    y_axis: AxisPolicy,
    interactions: PlotInteraction,
    hover_meta: Option<Box<HoverMetaFn<'a>>>,
}

struct HoverPoint<'a> {
    series: &'a PointSeries,
    point_index: usize,
    x: f64,
    y: f64,
    distance_sq: f32,
}

impl Default for ScatterPlot<'_> {
    fn default() -> Self {
        Self::new()
    }
}

impl<'a> ScatterPlot<'a> {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            series: Vec::new(),
            point_series: Vec::new(),
            x_label: None,
            y_label: None,
            height: None,
            x_axis: AxisPolicy::auto(),
            y_axis: AxisPolicy::auto(),
            interactions: PlotInteraction::disabled(),
            hover_meta: None,
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
    pub fn point_series(mut self, series: &'a PointSeries) -> Self {
        self.point_series.push(series);
        self
    }

    #[must_use]
    pub fn extend_point_series<I>(mut self, series: I) -> Self
    where
        I: IntoIterator<Item = &'a PointSeries>,
    {
        self.point_series.extend(series);
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

    #[must_use]
    pub fn hover_meta<F>(mut self, callback: F) -> Self
    where
        F: Fn(&PointSeries, usize) -> Option<crate::types::PointMeta> + 'a,
    {
        self.hover_meta = Some(Box::new(callback));
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
                let hover_pos = plot_ui.response().hover_pos();
                self.draw_series(plot_ui, x_axis, y_axis)?;
                let hover = self.draw_point_series(plot_ui, x_axis, y_axis, hover_pos)?;
                if let Some(hover) = hover.as_ref() {
                    self.show_hover_tooltip(plot_ui, hover, x_label, y_label, x_axis, y_axis);
                }
                Ok(())
            });

            inner.inner?;
            Ok(inner.response)
        })
    }

    fn draw_series(
        &self,
        plot_ui: &mut PlotUi<'a>,
        x_axis: AxisPolicy,
        y_axis: AxisPolicy,
    ) -> Result<(), RenderError> {
        for series in &self.series {
            let points = series_points("ScatterPlot", series, x_axis, y_axis)?;
            let scatter = Points::new(series.legend_name(), points)
                .color(series.color)
                .radius(3.5)
                .shape(MarkerShape::Circle);
            plot_ui.points(scatter);
        }
        Ok(())
    }

    fn draw_point_series(
        &self,
        plot_ui: &mut PlotUi<'a>,
        x_axis: AxisPolicy,
        y_axis: AxisPolicy,
        hover_pos: Option<egui::Pos2>,
    ) -> Result<Option<HoverPoint<'a>>, RenderError> {
        let mut closest: Option<HoverPoint<'a>> = None;
        for series in &self.point_series {
            let points = point_series_points("ScatterPlot", series, x_axis, y_axis)?;
            let scatter = Points::new(series.legend_name(), points)
                .color(series.color)
                .radius(series.radius)
                .shape(marker_shape(series.shape))
                .filled(series.filled)
                .highlight(series.highlight)
                .allow_hover(false);
            plot_ui.points(scatter);

            let Some(hover_pos) = hover_pos else {
                continue;
            };
            let threshold_sq = 64.0;
            for (idx, point) in series.points.iter().enumerate() {
                let x = transform_value(
                    "ScatterPlot",
                    &series.label,
                    "point series",
                    "x",
                    idx,
                    point[0],
                    x_axis,
                )?;
                let y = transform_value(
                    "ScatterPlot",
                    &series.label,
                    "point series",
                    "y",
                    idx,
                    point[1],
                    y_axis,
                )?;
                let plot_point = PlotPoint::new(x, y);
                let screen_pos = plot_ui.screen_from_plot(plot_point);
                let distance_sq = screen_pos.distance_sq(hover_pos);
                if distance_sq > threshold_sq {
                    continue;
                }
                let replace = closest
                    .as_ref()
                    .is_none_or(|current| distance_sq < current.distance_sq);
                if replace {
                    closest = Some(HoverPoint {
                        series,
                        point_index: idx,
                        x: plot_point.x,
                        y: plot_point.y,
                        distance_sq,
                    });
                }
            }
        }
        Ok(closest)
    }

    fn show_hover_tooltip(
        &self,
        plot_ui: &mut PlotUi,
        hover: &HoverPoint<'_>,
        x_label: &str,
        y_label: &str,
        x_axis: AxisPolicy,
        y_axis: AxisPolicy,
    ) {
        let meta_owned = self
            .hover_meta
            .as_ref()
            .and_then(|callback| callback(hover.series, hover.point_index));
        let meta_borrowed = hover
            .series
            .point_meta
            .as_ref()
            .and_then(|items| items.get(hover.point_index));
        let label = hover
            .series
            .point_labels
            .as_ref()
            .and_then(|items| items.get(hover.point_index));

        let (title, lines): (&str, &[String]) = if let Some(meta) = meta_owned.as_ref() {
            (meta.title.as_str(), meta.lines.as_slice())
        } else if let Some(meta) = meta_borrowed {
            (meta.title.as_str(), meta.lines.as_slice())
        } else if let Some(label) = label {
            (label.as_str(), &[])
        } else {
            return;
        };

        let x_value = x_axis.format_hover(hover.x);
        let y_value = y_axis.format_hover(hover.y);
        let tooltip_id = plot_ui.response().id.with("point_hover");
        egui::Tooltip::always_open(
            plot_ui.ctx().clone(),
            plot_ui.response().layer_id,
            tooltip_id,
            plot_ui.response().rect,
        )
        .at_pointer()
        .show(|ui| {
            ui.label(RichText::new(title).strong());
            if !hover.series.label.is_empty() {
                ui.label(
                    RichText::new(hover.series.label.as_str())
                        .color(colors::TEXT_MUTED)
                        .size(typography::SIZE_CAPTION),
                );
            }
            ui.label(
                RichText::new(format!("{x_label}: {x_value}"))
                    .color(colors::TEXT_PRIMARY)
                    .size(typography::SIZE_CAPTION),
            );
            ui.label(
                RichText::new(format!("{y_label}: {y_value}"))
                    .color(colors::TEXT_PRIMARY)
                    .size(typography::SIZE_CAPTION),
            );
            for line in lines {
                ui.label(
                    RichText::new(line)
                        .color(colors::TEXT_PRIMARY)
                        .size(typography::SIZE_CAPTION),
                );
            }
        });
    }
}

fn marker_shape(shape: PointShape) -> MarkerShape {
    match shape {
        PointShape::Circle => MarkerShape::Circle,
        PointShape::Diamond => MarkerShape::Diamond,
        PointShape::Square => MarkerShape::Square,
        PointShape::Up => MarkerShape::Up,
        PointShape::Cross => MarkerShape::Cross,
    }
}

#[cfg(test)]
mod tests {
    use super::ScatterPlot;
    use crate::core::colors;
    use crate::types::PointSeries;

    #[test]
    fn scatter_plot_try_show_rejects_metadata_mismatch() {
        let series = PointSeries::new("embeddings", vec![[0.0, 1.0]], colors::ACCENT_GOLD)
            .point_labels(vec!["p0".into(), "p1".into()]);
        egui::__run_test_ui(|ui| {
            let err = ScatterPlot::new()
                .point_series(&series)
                .try_show(ui)
                .expect_err("mismatched point labels should fail");
            assert_eq!(
                err.to_string(),
                "ScatterPlot: series 'embeddings' has 2 point labels, expected 1"
            );
        });
    }
}
