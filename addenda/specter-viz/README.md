# specter-viz

WASM-first `egui` dashboard components for research visualization.

The crate is UI-focused and works inside any `egui` app. A native desktop app will typically use `eframe`, but `specter-viz` itself only depends on `egui`/`egui_plot`.

MSRV: Rust 1.87.

## Environment

Enter the local project shell from `addenda/specter-viz/`:

```bash
nix develop
```

If you use direnv, `direnv allow` is equivalent. The shell auto-runs `cargo fetch --locked`.

## Install (in this repo)

```toml
[dependencies]
specter-viz = { path = "addenda/specter-viz" }
```

## Minimal Example (Native)

```rust
use eframe::egui;
use specter_viz::prelude::*;

struct App {
    loss: Series,
    loss_band: IntervalSeries,
}

impl Default for App {
    fn default() -> Self {
        Self {
            loss: Series::from_values("loss", vec![1.0, 0.82, 0.71, 0.64], colors::ACCENT_BLUE),
            loss_band: IntervalSeries::from_values(
                "loss 95% CI",
                vec![0.92, 0.75, 0.66, 0.60],
                vec![1.08, 0.89, 0.76, 0.68],
                colors::ACCENT_BLUE,
            )
            .expect("valid interval series"),
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        init(ctx);

        egui::CentralPanel::default().show(ctx, |ui| {
            Panel::new("Overview").show(ui, |ui| {
                let mut grid = MetricGrid::new().columns(3);
                grid.push(MetricCard::new("samples", "12_480"));
                grid.push(MetricCard::new("loss", "0.64").accent(colors::ACCENT_BLUE));
                grid.push(MetricCard::new("step", "918"));
                grid.show(ui);

                ui.add_space(spacing::MD);

                LineChart::new()
                    .interval(&self.loss_band)
                    .series(&self.loss)
                    .interactions(PlotInteraction::enabled())
                    .try_show(ui)
                    .expect("render overview chart");
            });
        });
    }
}

fn main() -> eframe::Result<()> {
    let opts = eframe::NativeOptions::default();
    eframe::run_native("specter-viz demo", opts, Box::new(|_cc| Ok(Box::<App>::default())))
}
```

`init(ctx)` is idempotent, so calling it from `update()` is fine.

## Data Model

`Series`, `IntervalSeries`, and `PointSeries` all support explicit coordinates.

- `Series::from_values(...)` uses the item index as `x`.
- `Series::from_xy(...)` accepts explicit `x`/`y` vectors and validates that lengths match.
- `IntervalSeries::from_values(...)` and `IntervalSeries::from_xy(...)` do the same for interval bands.
- `PointSeries::new(...)` creates scatter data with optional labels and metadata.

`LineChart::try_show(...)` and `ScatterPlot::try_show(...)` return `RenderError` when values are non-finite or incompatible with the selected axis policy instead of silently dropping points.

## Responsive Layout

Use `ResponsiveGrid` for dashboard sections and `ResponsiveColumns` for local sub-layouts.

```rust
use specter_viz::prelude::*;

let grid = ResponsiveGrid::new()
    .columns(1, 2, 3)
    .min_column_width(560.0)
    .flow(GridFlow::Masonry);

let columns = ResponsiveColumns::new()
    .columns(1, 2, 2)
    .min_column_width(520.0);
```

- `columns(...)`: preferred layout targets by breakpoint.
- `min_column_width(...)`: hard floor that collapses columns when space is tight.
- `flow(GridFlow::Rows | GridFlow::Masonry)`: row packing or compact masonry-style packing.

## Data Loading

The `specter_viz::data` helpers load JSON and JSONL.

- On `wasm32`, they use `window.fetch(...)`, so `path` is typically a URL.
- On native targets, they read from the filesystem, so `path` is a local file path.

Expected formats:

JSON:

```json
{"run_id":"run-001","metrics":[["loss",0.64],["accuracy",0.91]]}
```

JSONL:

```json
{"step":1,"loss":1.0}
{"step":2,"loss":0.82}
{"step":3,"loss":0.71}
```

### JSONL (native)

`fetch_jsonl` is `async`, so you need an executor. For small tools, `pollster` is a simple option:

```rust
use serde::Deserialize;
use specter_viz::data;

#[derive(Deserialize)]
struct Row {
    step: u64,
    loss: f64,
}

fn load_rows(path: &str) -> Vec<Row> {
    pollster::block_on(async { data::fetch_jsonl(path).await }).expect("load jsonl")
}
```

App crate deps for the snippet above:

```toml
pollster = "0.3"
serde = { version = "1", features = ["derive"] }
```

### JSON (wasm)

In wasm builds, load once by spawning an async task and storing the result in your app state:

```rust
use std::cell::RefCell;
use std::rc::Rc;

use serde::Deserialize;
use specter_viz::data;

#[derive(Clone, Deserialize)]
struct Snapshot {
    run_id: String,
    metrics: Vec<(String, f64)>,
}

fn start_loading(url: String, out: Rc<RefCell<Option<Result<Snapshot, String>>>>) {
    wasm_bindgen_futures::spawn_local(async move {
        let result = data::fetch_json::<Snapshot>(&url).await;
        *out.borrow_mut() = Some(result);
    });
}
```

App crate deps for the snippet above:

```toml
wasm-bindgen-futures = "0.4"
serde = { version = "1", features = ["derive"] }
```

## Example Project Layout

Create a tiny app crate that depends on this addendum:

```bash
cargo new --bin specter-viz-demo
```

`specter-viz-demo/Cargo.toml`:

```toml
[package]
name = "specter-viz-demo"
version = "0.1.0"
edition = "2021"

[dependencies]
eframe = "0.33"
specter-viz = { path = "../addenda/specter-viz" }
pollster = "0.3"
```

`specter-viz-demo/src/main.rs`: copy the native example above.

Run it:

```bash
cargo run --manifest-path specter-viz-demo/Cargo.toml
```

## Included

- Charts: `LineChart`, `ScatterPlot`, `HeatMap`, `GraphView`
- Views: `TreeView`
- Primitives: `Panel`, `MetricCard`, `MetricGrid`, `ChartHeader`, `Label`, `ResponsiveColumns`, `ResponsiveGrid`, `GridFlow`
- Data types: `Series`, `IntervalSeries`, `IntervalDatum`, `PointSeries`, `PointMeta`, `Graph`, `TreeNode`
- Data loading: `data::fetch_json`, `data::fetch_jsonl`

## License

Code in this addendum is licensed under PolyForm Noncommercial 1.0.0. Documentation and other non-code content, including this README, are licensed under CC-BY-NC-4.0. See `LICENSE` for the local project notice.
