mod charts;
pub mod core;
pub mod data;
pub mod error;
pub mod primitives;
pub mod state;
pub mod types;
pub mod views;

pub use charts::{
    AxisFormat, AxisPolicy, AxisTransform, GraphView, GraphViewInteraction, GraphViewResponse,
    HeatMap, HeatScale, LineChart, PlotInteraction, ScatterPlot,
};
pub use core::{init, init_with_theme, presets, Theme};
pub use error::RenderError;
pub use primitives::{
    ChartHeader, GridFlow, GridItem, Label, LabelStyle, MetricCard, MetricGrid, Panel,
    ResponsiveColumns, ResponsiveGrid,
};
pub use state::SelectionState;
pub use types::{
    Graph, IntervalDatum, IntervalSeries, PointMeta, PointSeries, PointShape, Series, TreeNode,
};
pub use views::{TreeView, TreeViewInteraction, TreeViewResponse};

pub mod prelude {
    pub use crate::charts::{
        AxisFormat, AxisPolicy, AxisTransform, GraphView, GraphViewInteraction, GraphViewResponse,
        HeatMap, HeatScale, LineChart, PlotInteraction, ScatterPlot,
    };
    pub use crate::core::colors;
    pub use crate::core::spacing;
    pub use crate::core::typography;
    pub use crate::core::{init, init_with_theme, presets, Theme};
    pub use crate::error::RenderError;
    pub use crate::primitives::{
        ChartHeader, GridFlow, GridItem, Label, LabelStyle, MetricCard, MetricGrid, Panel,
        ResponsiveColumns, ResponsiveGrid,
    };
    pub use crate::state::SelectionState;
    pub use crate::types::{
        Graph, IntervalDatum, IntervalSeries, PointMeta, PointSeries, PointShape, Series,
        TreeNode,
    };
    pub use crate::views::{TreeView, TreeViewInteraction, TreeViewResponse};
}
