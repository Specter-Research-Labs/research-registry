use std::collections::{HashMap, HashSet};

use egui::{Align2, Color32, Pos2, Response, Sense, Stroke, Ui, Vec2};

use crate::core::{colors, spacing, typography};
use crate::types::TreeNode;
use crate::RenderError;

#[derive(Clone, Debug, Default)]
pub struct TreeViewInteraction {
    pub hovered: Option<String>,
    pub clicked: Option<String>,
}

pub struct TreeViewResponse {
    pub response: Response,
    pub interaction: TreeViewInteraction,
}

pub struct TreeView<'a, T> {
    root_id: &'a str,
    nodes: &'a HashMap<String, TreeNode<T>>,
    node_radius: f32,
    level_gap: f32,
    sibling_gap: f32,
    padding: f32,
    min_size: Vec2,
    node_fill: Color32,
    node_stroke: Stroke,
    edge_stroke: Stroke,
    label_color: Color32,
    deterministic: bool,
}

impl<'a, T> TreeView<'a, T> {
    #[must_use]
    pub const fn new(root_id: &'a str, nodes: &'a HashMap<String, TreeNode<T>>) -> Self {
        Self {
            root_id,
            nodes,
            node_radius: 6.0,
            level_gap: spacing::XL,
            sibling_gap: spacing::LG,
            padding: spacing::MD,
            min_size: Vec2::ZERO,
            node_fill: colors::BG_ELEVATED,
            node_stroke: Stroke {
                width: spacing::BORDER_WIDTH,
                color: colors::BORDER_DEFAULT,
            },
            edge_stroke: Stroke {
                width: spacing::BORDER_WIDTH,
                color: colors::BORDER_SUBTLE,
            },
            label_color: colors::TEXT_PRIMARY,
            deterministic: false,
        }
    }

    #[must_use]
    pub const fn node_radius(mut self, radius: f32) -> Self {
        self.node_radius = radius;
        self
    }

    #[must_use]
    pub const fn level_gap(mut self, gap: f32) -> Self {
        self.level_gap = gap;
        self
    }

    #[must_use]
    pub const fn sibling_gap(mut self, gap: f32) -> Self {
        self.sibling_gap = gap;
        self
    }

    #[must_use]
    pub const fn padding(mut self, padding: f32) -> Self {
        self.padding = padding;
        self
    }

    #[must_use]
    pub const fn min_size(mut self, min_size: Vec2) -> Self {
        self.min_size = min_size;
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
    pub const fn label_color(mut self, color: Color32) -> Self {
        self.label_color = color;
        self
    }

    #[must_use]
    pub const fn deterministic(mut self, deterministic: bool) -> Self {
        self.deterministic = deterministic;
        self
    }

    /// Render the tree.
    ///
    /// # Panics
    /// Panics if rendering fails. Use [`Self::try_show`] to handle errors.
    #[allow(clippy::cast_precision_loss)]
    pub fn show(self, ui: &mut Ui, label: impl Fn(&TreeNode<T>) -> String) -> Response {
        self.try_show(ui, label)
            .unwrap_or_else(|err| panic!("{err}"))
    }

    /// Render the tree.
    ///
    /// # Errors
    /// Returns an error if the root node is missing, any child references are missing, or a cycle
    /// is detected.
    #[allow(clippy::cast_precision_loss)]
    pub fn try_show(
        self,
        ui: &mut Ui,
        label: impl Fn(&TreeNode<T>) -> String,
    ) -> Result<Response, RenderError> {
        Ok(self
            .try_show_with_sense(ui, label, Sense::hover(), false)?
            .response)
    }

    /// Render the tree and compute basic hover/click interaction.
    ///
    /// # Panics
    /// Panics if rendering fails. Use [`Self::try_show_interactive`] to handle errors.
    #[allow(clippy::cast_precision_loss)]
    pub fn show_interactive(
        self,
        ui: &mut Ui,
        label: impl Fn(&TreeNode<T>) -> String,
    ) -> TreeViewResponse {
        self.try_show_interactive(ui, label)
            .unwrap_or_else(|err| panic!("{err}"))
    }

    /// Render the tree and compute basic hover/click interaction.
    ///
    /// # Errors
    /// Returns the same errors as [`Self::try_show`].
    #[allow(clippy::cast_precision_loss)]
    pub fn try_show_interactive(
        self,
        ui: &mut Ui,
        label: impl Fn(&TreeNode<T>) -> String,
    ) -> Result<TreeViewResponse, RenderError> {
        self.try_show_with_sense(ui, label, Sense::click(), true)
    }

    fn try_show_with_sense(
        self,
        ui: &mut Ui,
        label: impl Fn(&TreeNode<T>) -> String,
        sense: Sense,
        interactive: bool,
    ) -> Result<TreeViewResponse, RenderError> {
        let layout = layout_tree(
            self.root_id,
            self.nodes,
            self.node_radius,
            self.level_gap,
            self.sibling_gap,
            self.deterministic,
        )?;
        let desired_size = (layout.size + Vec2::splat(self.padding * 2.0)).max(self.min_size);
        let (response, painter) = ui.allocate_painter(desired_size, sense);
        let origin = response.rect.min.to_vec2() + Vec2::splat(self.padding);

        let mut node_ids: Vec<&String> = layout.positions.keys().collect();
        if self.deterministic {
            node_ids.sort();
        }

        for parent_id in &node_ids {
            let node = self
                .nodes
                .get(parent_id.as_str())
                .ok_or_else(|| RenderError::new("TreeView", format!("missing node {parent_id}")))?;
            let parent_pos = layout.positions.get(parent_id.as_str()).ok_or_else(|| {
                RenderError::new(
                    "TreeView",
                    format!("missing layout position for node {parent_id}"),
                )
            })?;
            let start = *parent_pos + origin;

            let mut children: Vec<&String> = node.children.iter().collect();
            if self.deterministic {
                children.sort();
            }
            for child_id in children {
                let child_pos = layout.positions.get(child_id.as_str()).ok_or_else(|| {
                    RenderError::new(
                        "TreeView",
                        format!("missing layout position for child {child_id}"),
                    )
                })?;
                let end = *child_pos + origin;
                painter.line_segment([start, end], self.edge_stroke);
            }
        }

        for node_id in &node_ids {
            let node = self
                .nodes
                .get(node_id.as_str())
                .ok_or_else(|| RenderError::new("TreeView", format!("missing node {node_id}")))?;
            let pos = layout.positions.get(node_id.as_str()).ok_or_else(|| {
                RenderError::new(
                    "TreeView",
                    format!("missing layout position for node {node_id}"),
                )
            })?;
            let center = *pos + origin;
            painter.circle_filled(center, self.node_radius, self.node_fill);
            painter.circle_stroke(center, self.node_radius, self.node_stroke);

            let text = label(node);
            painter.text(
                center,
                Align2::CENTER_CENTER,
                text,
                typography::font_id_caption(),
                self.label_color,
            );
        }

        let mut interaction = TreeViewInteraction::default();
        if interactive {
            if let Some(pointer_pos) = ui.input(|i| i.pointer.interact_pos()) {
                if response.rect.contains(pointer_pos) {
                    interaction.hovered =
                        hit_test_node(pointer_pos, &layout.positions, origin, self.node_radius);
                    if response.clicked() {
                        interaction.clicked = interaction.hovered.clone();
                    }
                }
            }
        }

        Ok(TreeViewResponse {
            response,
            interaction,
        })
    }
}

struct TreeLayout {
    positions: HashMap<String, Pos2>,
    size: Vec2,
}

fn layout_tree<T>(
    root_id: &str,
    nodes: &HashMap<String, TreeNode<T>>,
    node_radius: f32,
    level_gap: f32,
    sibling_gap: f32,
    deterministic: bool,
) -> Result<TreeLayout, RenderError> {
    let mut sizes = HashMap::new();
    let mut visiting = HashSet::new();
    compute_subtree_size(root_id, nodes, &mut sizes, &mut visiting, deterministic)?;

    let unit_x = node_radius.mul_add(2.0, sibling_gap);
    let unit_y = node_radius.mul_add(2.0, level_gap);
    let mut positions = HashMap::new();
    let mut context = LayoutContext {
        nodes,
        sizes: &sizes,
        unit_x,
        unit_y,
        positions: &mut positions,
        deterministic,
    };
    assign_positions(root_id, 0.0, 0, &mut context)?;

    let mut min_x = f32::INFINITY;
    let mut min_y = f32::INFINITY;
    let mut max_x = f32::NEG_INFINITY;
    let mut max_y = f32::NEG_INFINITY;

    for pos in positions.values() {
        min_x = min_x.min(pos.x);
        min_y = min_y.min(pos.y);
        max_x = max_x.max(pos.x);
        max_y = max_y.max(pos.y);
    }

    let size = Vec2::new(
        node_radius.mul_add(2.0, max_x - min_x),
        node_radius.mul_add(2.0, max_y - min_y),
    );

    let shift = Vec2::new(node_radius - min_x, node_radius - min_y);
    for pos in positions.values_mut() {
        *pos += shift;
    }

    Ok(TreeLayout { positions, size })
}

fn compute_subtree_size<T>(
    node_id: &str,
    nodes: &HashMap<String, TreeNode<T>>,
    sizes: &mut HashMap<String, usize>,
    visiting: &mut HashSet<String>,
    deterministic: bool,
) -> Result<usize, RenderError> {
    if let Some(size) = sizes.get(node_id) {
        return Ok(*size);
    }
    if !visiting.insert(node_id.to_string()) {
        return Err(RenderError::new(
            "TreeView",
            format!("cycle detected at node {node_id}"),
        ));
    }

    let node = nodes
        .get(node_id)
        .ok_or_else(|| RenderError::new("TreeView", format!("missing node {node_id}")))?;

    let mut size = 0;
    let mut children: Vec<&String> = node.children.iter().collect();
    if deterministic {
        children.sort();
    }
    for child_id in children {
        size += compute_subtree_size(child_id, nodes, sizes, visiting, deterministic)?;
    }
    if size == 0 {
        size = 1;
    }

    visiting.remove(node_id);
    sizes.insert(node_id.to_string(), size);
    Ok(size)
}

#[allow(clippy::cast_precision_loss)]
struct LayoutContext<'a, T> {
    nodes: &'a HashMap<String, TreeNode<T>>,
    sizes: &'a HashMap<String, usize>,
    unit_x: f32,
    unit_y: f32,
    positions: &'a mut HashMap<String, Pos2>,
    deterministic: bool,
}

#[allow(clippy::cast_precision_loss)]
fn assign_positions<T>(
    node_id: &str,
    start: f32,
    depth: usize,
    context: &mut LayoutContext<'_, T>,
) -> Result<f32, RenderError> {
    let node = context
        .nodes
        .get(node_id)
        .ok_or_else(|| RenderError::new("TreeView", format!("missing node {node_id}")))?;
    let width =
        *context.sizes.get(node_id).ok_or_else(|| {
            RenderError::new("TreeView", format!("missing size for node {node_id}"))
        })? as f32;

    let mut cursor = start;
    let mut children: Vec<&String> = node.children.iter().collect();
    if context.deterministic {
        children.sort();
    }
    for child_id in children {
        let child_width = *context.sizes.get(child_id.as_str()).ok_or_else(|| {
            RenderError::new("TreeView", format!("missing size for node {child_id}"))
        })? as f32;
        assign_positions(child_id, cursor, depth + 1, context)?;
        cursor += child_width;
    }

    let center = start + width / 2.0;
    context.positions.insert(
        node_id.to_string(),
        Pos2::new(center * context.unit_x, depth as f32 * context.unit_y),
    );
    Ok(center)
}

fn hit_test_node(
    pointer: Pos2,
    positions: &HashMap<String, Pos2>,
    origin: Vec2,
    node_radius: f32,
) -> Option<String> {
    let threshold_sq = node_radius * node_radius;
    let mut best: Option<(&str, f32)> = None;
    for (node_id, pos) in positions {
        let center = *pos + origin;
        let dist_sq = center.distance_sq(pointer);
        if dist_sq > threshold_sq {
            continue;
        }
        let replace = best
            .as_ref()
            .is_none_or(|(_id, current)| dist_sq < *current);
        if replace {
            best = Some((node_id.as_str(), dist_sq));
        }
    }
    best.map(|(id, _)| id.to_string())
}


#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::layout_tree;
    use crate::types::TreeNode;

    #[test]
    fn layout_tree_rejects_cycles() {
        let mut nodes = HashMap::new();
        nodes.insert(
            "a".to_string(),
            TreeNode {
                id: "a".to_string(),
                data: (),
                children: vec!["b".to_string()],
            },
        );
        nodes.insert(
            "b".to_string(),
            TreeNode {
                id: "b".to_string(),
                data: (),
                children: vec!["a".to_string()],
            },
        );

        let err = match layout_tree("a", &nodes, 6.0, 24.0, 16.0, true) {
            Ok(_) => panic!("cycle should fail tree layout"),
            Err(err) => err,
        };
        assert_eq!(err.to_string(), "TreeView: cycle detected at node a");
    }
}
