use std::collections::HashMap;

use egui::{Align2, Color32, Pos2, Rect, Response, Sense, Stroke, StrokeKind, Ui, Vec2};

use crate::core::{colors, spacing, typography};
use crate::types::Graph;
use crate::RenderError;

#[derive(Clone, Debug, Default)]
pub struct GraphViewInteraction {
    pub hovered: Option<String>,
    pub clicked: Option<String>,
}

pub struct GraphViewResponse {
    pub response: Response,
    pub interaction: GraphViewInteraction,
}

pub struct GraphView<'a, N, E> {
    graph: &'a Graph<N, E>,
    positions: &'a HashMap<String, Pos2>,
    size: Vec2,
    padding: f32,
    node_radius: f32,
    node_fill: Color32,
    node_stroke: Stroke,
    edge_stroke: Stroke,
    show_labels: bool,
    deterministic: bool,
}

impl<'a, N, E> GraphView<'a, N, E> {
    #[must_use]
    pub fn new(graph: &'a Graph<N, E>, positions: &'a HashMap<String, Pos2>, size: Vec2) -> Self {
        Self {
            graph,
            positions,
            size,
            padding: spacing::MD,
            node_radius: spacing::SM,
            node_fill: colors::ACCENT_TEAL,
            node_stroke: Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_DEFAULT),
            edge_stroke: Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_SUBTLE),
            show_labels: false,
            deterministic: false,
        }
    }

    #[must_use]
    pub const fn padding(mut self, padding: f32) -> Self {
        self.padding = padding;
        self
    }

    #[must_use]
    pub const fn node_radius(mut self, radius: f32) -> Self {
        self.node_radius = radius;
        self
    }

    #[must_use]
    pub const fn node_fill(mut self, color: Color32) -> Self {
        self.node_fill = color;
        self
    }

    #[must_use]
    pub const fn node_stroke(mut self, stroke: Stroke) -> Self {
        self.node_stroke = stroke;
        self
    }

    #[must_use]
    pub const fn edge_stroke(mut self, stroke: Stroke) -> Self {
        self.edge_stroke = stroke;
        self
    }

    #[must_use]
    pub const fn labels(mut self, show: bool) -> Self {
        self.show_labels = show;
        self
    }

    #[must_use]
    pub const fn deterministic(mut self, deterministic: bool) -> Self {
        self.deterministic = deterministic;
        self
    }

    /// Render the graph.
    ///
    /// # Panics
    /// Panics if rendering fails. Use [`Self::try_show`] to handle errors.
    pub fn show(self, ui: &mut Ui) -> Response {
        self.try_show(ui).unwrap_or_else(|err| panic!("{err}"))
    }

    /// Render the graph.
    ///
    /// # Errors
    /// Returns an error if the size is non-positive, required nodes/positions are missing, or
    /// edges reference unknown nodes.
    pub fn try_show(self, ui: &mut Ui) -> Result<Response, RenderError> {
        Ok(self
            .try_show_with_sense(ui, Sense::hover(), false)?
            .response)
    }

    /// Render the graph and compute basic hover/click interaction.
    ///
    /// # Panics
    /// Panics if rendering fails. Use [`Self::try_show_interactive`] to handle errors.
    pub fn show_interactive(self, ui: &mut Ui) -> GraphViewResponse {
        self.try_show_interactive(ui)
            .unwrap_or_else(|err| panic!("{err}"))
    }

    /// Render the graph and compute basic hover/click interaction.
    ///
    /// # Errors
    /// Returns the same errors as [`Self::try_show`].
    pub fn try_show_interactive(self, ui: &mut Ui) -> Result<GraphViewResponse, RenderError> {
        self.try_show_with_sense(ui, Sense::click(), true)
    }

    fn try_show_with_sense(
        self,
        ui: &mut Ui,
        sense: Sense,
        interactive: bool,
    ) -> Result<GraphViewResponse, RenderError> {
        if !(self.size.x > 0.0 && self.size.y > 0.0) {
            return Err(RenderError::new("GraphView", "size must be positive"));
        }

        let node_ids = ordered_node_ids(self.graph, self.deterministic);
        let first_id = node_ids
            .first()
            .copied()
            .ok_or_else(|| RenderError::new("GraphView", "requires at least one node"))?;
        let layout_bounds = layout_bounds(self.positions, first_id, node_ids.iter().copied())?;
        validate_edges(self.graph, self.positions)?;

        let (response, painter) = ui.allocate_painter(self.size, sense);
        let draw_rect = response.rect;
        let padded_rect = padded_rect(draw_rect, self.padding);

        painter.rect_stroke(
            draw_rect,
            0.0,
            Stroke::new(spacing::BORDER_WIDTH, colors::BORDER_SUBTLE),
            StrokeKind::Inside,
        );

        let mut edges: Vec<(&String, &String)> =
            self.graph.edges.iter().map(|(s, t, _)| (s, t)).collect();
        if self.deterministic {
            edges.sort_by(|(a0, a1), (b0, b1)| {
                (a0.as_str(), a1.as_str()).cmp(&(b0.as_str(), b1.as_str()))
            });
        }
        for (source, target) in edges {
            let start = mapped_position(
                position_for(self.positions, source)?,
                layout_bounds,
                padded_rect,
            );
            let end = mapped_position(
                position_for(self.positions, target)?,
                layout_bounds,
                padded_rect,
            );
            painter.line_segment([start, end], self.edge_stroke);
        }

        let label_font = typography::font_id_caption();
        for node_id in node_ids.iter().copied() {
            let position = mapped_position(
                position_for(self.positions, node_id)?,
                layout_bounds,
                padded_rect,
            );
            painter.circle_filled(position, self.node_radius, self.node_fill);
            painter.circle_stroke(position, self.node_radius, self.node_stroke);

            if self.show_labels {
                let label_pos = Pos2::new(position.x, position.y - self.node_radius - spacing::XS);
                painter.text(
                    label_pos,
                    Align2::CENTER_BOTTOM,
                    node_id,
                    label_font.clone(),
                    colors::TEXT_SECONDARY,
                );
            }
        }

        let mut interaction = GraphViewInteraction::default();
        if interactive {
            if let Some(pointer_pos) = ui.input(|i| i.pointer.interact_pos()) {
                if response.rect.contains(pointer_pos) {
                    interaction.hovered = hit_test_node(
                        pointer_pos,
                        node_ids.iter().copied(),
                        self.positions,
                        layout_bounds,
                        padded_rect,
                        self.node_radius,
                    )?;
                    if response.clicked() {
                        interaction.clicked = interaction.hovered.clone();
                    }
                }
            }
        }

        Ok(GraphViewResponse {
            response,
            interaction,
        })
    }
}

fn ordered_node_ids<'a, N, E>(graph: &'a Graph<N, E>, deterministic: bool) -> Vec<&'a str> {
    let mut nodes: Vec<&'a str> = graph.nodes.keys().map(String::as_str).collect();
    if deterministic {
        nodes.sort_unstable();
    }
    nodes
}

fn layout_bounds<'a>(
    positions: &HashMap<String, Pos2>,
    first_id: &str,
    node_ids: impl IntoIterator<Item = &'a str>,
) -> Result<Rect, RenderError> {
    let first_pos = position_for(positions, first_id)?;
    let mut min = first_pos;
    let mut max = first_pos;

    for node_id in node_ids {
        let pos = position_for(positions, node_id)?;
        min.x = min.x.min(pos.x);
        min.y = min.y.min(pos.y);
        max.x = max.x.max(pos.x);
        max.y = max.y.max(pos.y);
    }

    Ok(Rect::from_min_max(min, max))
}

fn validate_edges<N, E>(
    graph: &Graph<N, E>,
    positions: &HashMap<String, Pos2>,
) -> Result<(), RenderError> {
    for (source, target, _edge) in &graph.edges {
        if !graph.nodes.contains_key(source) {
            return Err(RenderError::new(
                "GraphView",
                format!("edge references missing node: {source}"),
            ));
        }
        if !graph.nodes.contains_key(target) {
            return Err(RenderError::new(
                "GraphView",
                format!("edge references missing node: {target}"),
            ));
        }
        let _ = position_for(positions, source)?;
        let _ = position_for(positions, target)?;
    }
    Ok(())
}

fn position_for(positions: &HashMap<String, Pos2>, node_id: &str) -> Result<Pos2, RenderError> {
    let pos = positions.get(node_id).ok_or_else(|| {
        RenderError::new("GraphView", format!("missing position for node {node_id}"))
    })?;
    if !(pos.x.is_finite() && pos.y.is_finite()) {
        return Err(RenderError::new(
            "GraphView",
            format!("position for node {node_id} must be finite"),
        ));
    }
    Ok(*pos)
}

fn padded_rect(rect: Rect, padding: f32) -> Rect {
    let padded = rect.shrink(padding);
    if padded.width() > 0.0 && padded.height() > 0.0 {
        padded
    } else {
        rect
    }
}

fn mapped_position(pos: Pos2, bounds: Rect, target: Rect) -> Pos2 {
    let layout_size = Vec2::new(bounds.width().max(1.0), bounds.height().max(1.0));
    let scale_x = target.width() / layout_size.x;
    let scale_y = target.height() / layout_size.y;
    let scale = scale_x.min(scale_y);

    let scaled_size = layout_size * scale;
    let origin = Pos2::new(
        scaled_size.x.mul_add(-0.5, target.center().x),
        scaled_size.y.mul_add(-0.5, target.center().y),
    );
    origin + (pos - bounds.min) * scale
}

fn hit_test_node<'a>(
    pointer: Pos2,
    node_ids: impl IntoIterator<Item = &'a str>,
    positions: &HashMap<String, Pos2>,
    bounds: Rect,
    target: Rect,
    node_radius: f32,
) -> Result<Option<String>, RenderError> {
    let threshold_sq = node_radius * node_radius;
    let mut best: Option<(&str, f32)> = None;
    for node_id in node_ids {
        let layout_pos = position_for(positions, node_id)?;
        let center = mapped_position(layout_pos, bounds, target);
        let dist_sq = center.distance_sq(pointer);
        if dist_sq > threshold_sq {
            continue;
        }
        let replace = best
            .as_ref()
            .is_none_or(|(_id, current)| dist_sq < *current);
        if replace {
            best = Some((node_id, dist_sq));
        }
    }
    Ok(best.map(|(id, _)| id.to_string()))
}


#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use egui::Vec2;

    use super::GraphView;
    use crate::types::Graph;

    #[test]
    fn graph_view_try_show_rejects_missing_positions() {
        let mut nodes = HashMap::new();
        nodes.insert("a".to_string(), ());
        let graph = Graph {
            nodes,
            edges: Vec::<(String, String, ())>::new(),
        };
        let positions = HashMap::new();

        egui::__run_test_ui(|ui| {
            let err = GraphView::new(&graph, &positions, Vec2::new(120.0, 80.0))
                .try_show(ui)
                .expect_err("missing positions should fail");
            assert_eq!(err.to_string(), "GraphView: missing position for node a");
        });
    }
}
