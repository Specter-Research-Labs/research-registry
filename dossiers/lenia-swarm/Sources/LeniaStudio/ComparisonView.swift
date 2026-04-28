import SwiftUI
import LeniaCore
import LeniaVisuals

struct ComparisonView: View {
    let entries: [StudioCompareEntry]

    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var useFluidVisuals = true
    @State private var showCharts = false
    @State private var models: [String: LiveSimulationModel] = [:]
    @Environment(\.dismiss) private var dismiss

    private func gridColumns(for availableWidth: CGFloat) -> [GridItem] {
        let count = availableWidth < 1_080 ? 1 : min(max(entries.count, 1), 2)
        return Array(repeating: GridItem(.flexible(), spacing: 12), count: count)
    }

    private var baselineScore: Float? {
        entries.first.map { $0.savedCreature?.score ?? $0.creature.score }
    }

    var body: some View {
        GeometryReader { proxy in
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        StudioSurface(title: "Comparison Workspace", subtitle: "Synced playback with metric deltas") {
                            comparisonSummary
                        }

                        LazyVGrid(columns: gridColumns(for: proxy.size.width), spacing: 12) {
                            ForEach(entries) { entry in
                                if let model = liveModel(for: entry) {
                                    ComparisonPanelView(
                                        entry: entry,
                                        model: model,
                                        renderMode: renderMode,
                                        useFluidVisuals: useFluidVisuals,
                                        showCharts: showCharts,
                                        deltaScore: deltaScore(for: entry)
                                    )
                                }
                            }
                        }
                    }
                    .padding(16)
                }

                controlBar
            }
        }
        .background(
            StudioSceneBackground()
        )
        .onAppear {
            ensureModels()
            for entry in entries {
                liveModel(for: entry)?.start(
                    creature: entry.creature,
                    replaySource: entry.replayReference
                )
            }
        }
        .onDisappear {
            for model in models.values {
                model.stop()
            }
        }
        .navigationTitle("Compare")
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Done") { dismiss() }
            }
            ToolbarItem(placement: .principal) {
                RenderModePicker(renderMode: $renderMode)
            }
        }
    }

    private var comparisonSummary: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("\(entries.count) creatures loaded")
                .font(.headline)
                .foregroundStyle(StudioPalette.ink)

            HStack(spacing: 10) {
                if let baselineScore {
                    StudioMetricPill(label: "Baseline", value: String(format: "%.3f", baselineScore), accent: StudioPalette.ember)
                }
                let stableCount = entries.filter { ($0.savedCreature?.metrics.isStable ?? $0.metrics?.isStable) == true }.count
                StudioMetricPill(label: "Stable", value: "\(stableCount)", accent: StudioPalette.moss)
                let sources = Set(entries.map { $0.creature.sourceNode }).count
                StudioMetricPill(label: "Sources", value: "\(sources)", accent: StudioPalette.ocean)
            }
        }
    }

    private var controlBar: some View {
        HStack(spacing: 12) {
            Button(action: toggleAllPause) {
                Label(
                    anyPaused ? "Play All" : "Pause All",
                    systemImage: anyPaused ? "play.fill" : "pause.fill"
                )
            }
            .buttonStyle(.bordered)

            Button("Reset All") {
                for entry in entries {
                    liveModel(for: entry)?.restart(
                        creature: entry.creature,
                        replaySource: entry.replayReference
                    )
                }
            }
            .buttonStyle(.bordered)

            Toggle(isOn: $useFluidVisuals) {
                Label("Fluid", systemImage: "drop.fill")
            }
            .toggleStyle(.button)

            Toggle(isOn: $showCharts) {
                Label("Charts", systemImage: "chart.xyaxis.line")
            }
            .toggleStyle(.button)

            Spacer()
        }
        .controlSize(.small)
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(.bar)
    }

    private var anyPaused: Bool {
        models.values.contains { $0.isPaused }
    }

    private func ensureModels() {
        for entry in entries where models[entry.id] == nil {
            models[entry.id] = LiveSimulationModel()
        }
    }

    private func liveModel(for entry: StudioCompareEntry) -> LiveSimulationModel? {
        models[entry.id]
    }

    private func deltaScore(for entry: StudioCompareEntry) -> Float? {
        guard let baselineScore else { return nil }
        let score = entry.savedCreature?.score ?? entry.creature.score
        return score - baselineScore
    }

    private func toggleAllPause() {
        let newState = !anyPaused
        for model in models.values {
            model.isPaused = newState
        }
    }
}

private struct ComparisonPanelView: View {
    let entry: StudioCompareEntry
    @ObservedObject var model: LiveSimulationModel
    let renderMode: LeniaRenderMode
    let useFluidVisuals: Bool
    let showCharts: Bool
    let deltaScore: Float?

    var body: some View {
        StudioSurface(title: entry.name, subtitle: entry.subtitle) {
            VStack(spacing: 0) {
                ZStack {
                    LinearGradient(
                        colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))

                    if let frame = model.displayFrame {
                        LeniaLabStageView(
                            frame: frame,
                            renderMode: renderMode,
                            zoom: 1.0,
                            offset: .zero,
                            onTransformChange: { _ in },
                            onPrimaryPoint: { _ in },
                            onSecondaryPoint: { _ in },
                            onHoverPointChange: { _ in }
                        )
                        .padding(10)
                    } else {
                        ProgressView()
                            .controlSize(.large)
                            .tint(.white)
                    }
                }
                .frame(height: 250)

                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 8) {
                        StudioMetricPill(label: "Score", value: String(format: "%.3f", entry.savedCreature?.score ?? entry.creature.score), accent: StudioPalette.ember)
                        if let deltaScore {
                            StudioMetricPill(label: "Delta", value: String(format: "%+.3f", deltaScore), accent: deltaScore >= 0 ? StudioPalette.moss : .red)
                        }
                    }

                    if let metrics = entry.savedCreature?.metrics ?? entry.metrics {
                        HStack(spacing: 8) {
                            StudioMetricPill(label: "Vel", value: String(format: "%.3f", metrics.centerVelocity), accent: StudioPalette.ocean)
                            if let complexity = metrics.complexityMean {
                                StudioMetricPill(label: "Cx", value: String(format: "%.3f", complexity), accent: StudioPalette.moss)
                            }
                            StudioMetricPill(label: "Gyr", value: String(format: "%.3f", metrics.gyration))
                        }
                    }

                    Text(model.stats)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)

                    if showCharts {
                        MetricChartPanel(metricHistory: model.metricHistory)
                    }
                }
                .padding(.top, 12)
            }
        }
    }
}
