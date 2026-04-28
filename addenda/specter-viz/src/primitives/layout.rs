use egui::{Align, Layout, Ui, Vec2};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GridFlow {
    Rows,
    Masonry,
}

#[derive(Clone, Copy)]
pub struct ResponsiveColumns {
    breakpoints: [f32; 2],
    columns: [usize; 3],
    gap: f32,
    min_column_width: f32,
    chart_ratio: f32,
    chart_min_height: f32,
    chart_max_height: f32,
}

impl ResponsiveColumns {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            breakpoints: [900.0, 1500.0],
            columns: [1, 2, 3],
            gap: 16.0,
            min_column_width: 0.0,
            chart_ratio: 0.55,
            chart_min_height: 180.0,
            chart_max_height: 320.0,
        }
    }

    #[must_use]
    pub const fn breakpoints(mut self, small: f32, medium: f32) -> Self {
        self.breakpoints = [small, medium];
        self
    }

    #[must_use]
    pub const fn columns(mut self, small: usize, medium: usize, large: usize) -> Self {
        self.columns = [small, medium, large];
        self
    }

    #[must_use]
    pub const fn gap(mut self, gap: f32) -> Self {
        self.gap = gap;
        self
    }

    #[must_use]
    pub const fn min_column_width(mut self, width: f32) -> Self {
        self.min_column_width = width;
        self
    }

    #[must_use]
    pub const fn chart_height(mut self, ratio: f32, min: f32, max: f32) -> Self {
        self.chart_ratio = ratio;
        self.chart_min_height = min;
        self.chart_max_height = max;
        self
    }

    #[must_use]
    pub fn columns_for_width(&self, width: f32) -> usize {
        let [small_bp, medium_bp] = self.breakpoints;
        let [small, medium, large] = self.columns;
        let desired = if width < small_bp {
            small
        } else if width < medium_bp {
            medium
        } else {
            large
        }
        .max(1);

        desired.min(self.max_columns_for_width(width))
    }

    #[must_use]
    fn max_columns_for_width(&self, width: f32) -> usize {
        if self.min_column_width <= 0.0 {
            return usize::MAX;
        }
        let denominator = self.min_column_width + self.gap;
        if denominator <= 0.0 {
            return usize::MAX;
        }
        let available = (width + self.gap).max(0.0);
        ((available / denominator).floor() as usize).max(1)
    }

    #[must_use]
    #[allow(clippy::cast_precision_loss)]
    pub fn chart_height_for_width(&self, width: f32) -> f32 {
        let columns = self.columns_for_width(width).max(1);
        let column_width = width / columns as f32;
        (column_width * self.chart_ratio).clamp(self.chart_min_height, self.chart_max_height)
    }

    /// # Panics
    /// Panics if the resolved column count is zero.
    pub fn show<R>(self, ui: &mut Ui, add_contents: impl FnOnce(&mut [Ui]) -> R) -> R {
        let columns = self.columns_for_width(ui.available_width());
        assert!(
            columns > 0,
            "ResponsiveColumns requires at least one column"
        );
        ui.columns(columns, add_contents)
    }
}

impl Default for ResponsiveColumns {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct GridItem<T> {
    pub value: T,
    pub span: usize,
}

#[derive(Clone, Copy, Debug)]
pub struct ResponsiveGrid {
    breakpoints: [f32; 2],
    columns: [usize; 3],
    gap: f32,
    min_column_width: f32,
    expand_singleton_rows: bool,
    flow: GridFlow,
}

impl ResponsiveGrid {
    #[must_use]
    pub const fn new() -> Self {
        Self {
            breakpoints: [900.0, 1500.0],
            columns: [1, 2, 3],
            gap: 16.0,
            min_column_width: 0.0,
            expand_singleton_rows: true,
            flow: GridFlow::Rows,
        }
    }

    #[must_use]
    pub const fn breakpoints(mut self, small: f32, medium: f32) -> Self {
        self.breakpoints = [small, medium];
        self
    }

    #[must_use]
    pub const fn columns(mut self, small: usize, medium: usize, large: usize) -> Self {
        self.columns = [small, medium, large];
        self
    }

    #[must_use]
    pub const fn gap(mut self, gap: f32) -> Self {
        self.gap = gap;
        self
    }

    #[must_use]
    pub const fn min_column_width(mut self, width: f32) -> Self {
        self.min_column_width = width;
        self
    }

    #[must_use]
    pub const fn flow(mut self, flow: GridFlow) -> Self {
        self.flow = flow;
        self
    }

    #[must_use]
    pub const fn expand_singleton_rows(mut self, expand: bool) -> Self {
        self.expand_singleton_rows = expand;
        self
    }

    #[must_use]
    pub fn columns_for_width(&self, width: f32) -> usize {
        let [small_bp, medium_bp] = self.breakpoints;
        let [small, medium, large] = self.columns;
        let desired = if width < small_bp {
            small
        } else if width < medium_bp {
            medium
        } else {
            large
        }
        .max(1);

        desired.min(self.max_columns_for_width(width))
    }

    #[must_use]
    fn max_columns_for_width(&self, width: f32) -> usize {
        if self.min_column_width <= 0.0 {
            return usize::MAX;
        }
        let denominator = self.min_column_width + self.gap;
        if denominator <= 0.0 {
            return usize::MAX;
        }
        let available = (width + self.gap).max(0.0);
        ((available / denominator).floor() as usize).max(1)
    }

    pub fn show<T>(self, ui: &mut Ui, items: &[GridItem<T>], mut render: impl FnMut(&mut Ui, T))
    where
        T: Copy,
    {
        let columns = self.columns_for_width(ui.available_width()).max(1);
        let original_spacing = ui.spacing().item_spacing;
        ui.spacing_mut().item_spacing.x = self.gap;

        match self.flow {
            GridFlow::Rows => self.show_rows(ui, items, columns, &mut render),
            GridFlow::Masonry => self.show_masonry(ui, items, columns, &mut render),
        }

        ui.spacing_mut().item_spacing = original_spacing;
    }

    fn show_rows<T>(
        &self,
        ui: &mut Ui,
        items: &[GridItem<T>],
        columns: usize,
        render: &mut impl FnMut(&mut Ui, T),
    ) where
        T: Copy,
    {
        let rows = pack_grid_rows(items, columns, self.expand_singleton_rows);

        for (row_index, row) in rows.iter().enumerate() {
            let row_width = ui.available_width();
            let item_count = row.len();
            let total_gap = self.gap * item_count.saturating_sub(1) as f32;
            let unit_width = ((row_width - total_gap).max(0.0)) / columns as f32;
            let expand_single = item_count == 1 && self.expand_singleton_rows;

            ui.horizontal_top(|ui| {
                for item in row {
                    let width = if expand_single {
                        row_width
                    } else {
                        unit_width * item.span as f32
                    };
                    ui.allocate_ui_with_layout(
                        Vec2::new(width.max(0.0), 0.0),
                        Layout::top_down(Align::Min),
                        |item_ui| render(item_ui, item.value),
                    );
                }
            });

            if row_index + 1 < rows.len() {
                ui.add_space(self.gap);
            }
        }
    }

    fn show_masonry<T>(
        &self,
        ui: &mut Ui,
        items: &[GridItem<T>],
        columns: usize,
        render: &mut impl FnMut(&mut Ui, T),
    ) where
        T: Copy,
    {
        if columns <= 1 {
            self.show_rows(ui, items, columns, render);
            return;
        }

        let normalized: Vec<GridItem<T>> = items
            .iter()
            .copied()
            .map(|item| GridItem {
                value: item.value,
                span: item.span.clamp(1, columns),
            })
            .collect();

        let mut pending: Vec<T> = Vec::new();
        let mut rendered_any = false;

        for item in normalized {
            if item.span == 1 {
                pending.push(item.value);
                continue;
            }

            if !pending.is_empty() {
                if rendered_any {
                    ui.add_space(self.gap);
                }
                show_masonry_block(ui, &pending, columns, self.gap, render);
                pending.clear();
                rendered_any = true;
            }

            if rendered_any {
                ui.add_space(self.gap);
            }
            ui.allocate_ui_with_layout(
                Vec2::new(ui.available_width().max(0.0), 0.0),
                Layout::top_down(Align::Min),
                |item_ui| render(item_ui, item.value),
            );
            rendered_any = true;
        }

        if !pending.is_empty() {
            if rendered_any {
                ui.add_space(self.gap);
            }
            show_masonry_block(ui, &pending, columns, self.gap, render);
        }
    }
}

impl Default for ResponsiveGrid {
    fn default() -> Self {
        Self::new()
    }
}

fn show_masonry_block<T: Copy>(
    ui: &mut Ui,
    values: &[T],
    columns: usize,
    gap: f32,
    render: &mut impl FnMut(&mut Ui, T),
) {
    ui.columns(columns, |uis| {
        let mut column_heights = vec![0.0f32; columns];

        for value in values.iter().copied() {
            let target = column_heights
                .iter()
                .enumerate()
                .min_by(|(_, left), (_, right)| left.total_cmp(right))
                .map(|(index, _)| index)
                .unwrap_or(0);
            let column_ui = &mut uis[target];

            if column_heights[target] > 0.0 {
                column_ui.add_space(gap);
                column_heights[target] += gap;
            }

            let before = column_ui.min_rect().bottom();
            column_ui.allocate_ui_with_layout(
                Vec2::new(column_ui.available_width().max(0.0), 0.0),
                Layout::top_down(Align::Min),
                |item_ui| render(item_ui, value),
            );
            let after = column_ui.min_rect().bottom();
            column_heights[target] += (after - before).max(0.0);
        }
    });
}

fn pack_grid_rows<T: Copy>(
    items: &[GridItem<T>],
    columns: usize,
    expand_singleton_rows: bool,
) -> Vec<Vec<GridItem<T>>> {
    let columns = columns.max(1);
    let mut rows: Vec<Vec<GridItem<T>>> = Vec::new();
    let mut row: Vec<GridItem<T>> = Vec::new();
    let mut used = 0usize;

    for item in items {
        let span = item.span.clamp(1, columns);
        let item = GridItem {
            value: item.value,
            span,
        };

        if span == columns {
            if !row.is_empty() {
                rows.push(std::mem::take(&mut row));
                used = 0;
            }
            rows.push(vec![item]);
            continue;
        }

        if used + span > columns {
            rows.push(std::mem::take(&mut row));
            used = 0;
        }

        row.push(item);
        used += span;

        if used == columns {
            rows.push(std::mem::take(&mut row));
            used = 0;
        }
    }

    if !row.is_empty() {
        rows.push(row);
    }

    if expand_singleton_rows {
        for row in &mut rows {
            if row.len() == 1 {
                row[0].span = columns;
            }
        }
    }

    rows
}

#[cfg(test)]
mod tests {
    use super::{GridItem, ResponsiveColumns, ResponsiveGrid};

    #[test]
    fn responsive_columns_enforce_min_column_width() {
        let columns = ResponsiveColumns::new()
            .breakpoints(900.0, 1500.0)
            .columns(1, 2, 3)
            .gap(16.0)
            .min_column_width(500.0);

        assert_eq!(columns.columns_for_width(920.0), 1);
        assert_eq!(columns.columns_for_width(1300.0), 2);
        assert_eq!(columns.columns_for_width(1900.0), 3);
    }

    #[test]
    fn responsive_grid_enforce_min_column_width() {
        let grid = ResponsiveGrid::new()
            .breakpoints(900.0, 1500.0)
            .columns(1, 2, 3)
            .gap(16.0)
            .min_column_width(560.0);

        assert_eq!(grid.columns_for_width(980.0), 1);
        assert_eq!(grid.columns_for_width(1400.0), 2);
        assert_eq!(grid.columns_for_width(1900.0), 3);
    }

    #[test]
    fn responsive_grid_clamps_spans_to_column_count() {
        let items = [
            GridItem {
                value: 1u8,
                span: 2,
            },
            GridItem {
                value: 2u8,
                span: 1,
            },
            GridItem {
                value: 3u8,
                span: 1,
            },
        ];

        let rows = super::pack_grid_rows(&items, 1, false);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0][0].span, 1);
        assert_eq!(rows[1][0].span, 1);
        assert_eq!(rows[2][0].span, 1);
    }
}
