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
        let count = availableWidth < 760 ? 1 : min(max(entries.count, 1), 2)
        return Array(repeating: GridItem(.flexible(), spacing: 10), count: count)
    }

    private var baselineScore: Float? {
        entries.first.map { $0.savedCreature?.score ?? $0.creature.score }
    }

    var body: some View {
        GeometryReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ComparisonHeaderStrip(
                        entries: entries,
                        baselineScore: baselineScore,
                        anyPaused: anyPaused,
                        useFluidVisuals: $useFluidVisuals,
                        showCharts: $showCharts,
                        onTogglePause: toggleAllPause,
                        onReset: resetAll
                    )

                    LazyVGrid(columns: gridColumns(for: proxy.size.width), spacing: 10) {
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

                    ComparisonMetricMatrix(entries: entries)
                }
                .padding(12)
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

    private func resetAll() {
        for entry in entries {
            liveModel(for: entry)?.restart(
                creature: entry.creature,
                replaySource: entry.replayReference
            )
        }
    }
}

private struct ComparisonHeaderStrip: View {
    let entries: [StudioCompareEntry]
    let baselineScore: Float?
    let anyPaused: Bool
    @Binding var useFluidVisuals: Bool
    @Binding var showCharts: Bool
    let onTogglePause: () -> Void
    let onReset: () -> Void

    private var stableCount: Int {
        entries.filter { ($0.savedCreature?.metrics.isStable ?? $0.metrics?.isStable) == true }.count
    }

    private var sourceCount: Int {
        Set(entries.map { $0.creature.sourceNode }).count
    }

    var body: some View {
        StudioSurface(title: "Compare", subtitle: "Synchronized replay and baseline-normalized measurements", style: .console) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .center, spacing: 8) {
                    Text("\(entries.count) specimens")
                        .font(StudioType.data)
                        .foregroundStyle(StudioPalette.ink)
                        .frame(width: 120, alignment: .leading)

                    if let baselineScore {
                        StudioMetricPill(label: "Baseline", value: String(format: "%.3f", baselineScore), accent: StudioPalette.ember, style: .console)
                    }
                    StudioMetricPill(label: "Stable", value: "\(stableCount)", accent: StudioPalette.moss, style: .console)
                    StudioMetricPill(label: "Sources", value: "\(sourceCount)", accent: StudioPalette.ocean, style: .console)

                    Spacer(minLength: 8)

                    Button(action: onTogglePause) {
                        Label(anyPaused ? "Play" : "Pause", systemImage: anyPaused ? "play.fill" : "pause.fill")
                    }
                    .buttonStyle(.bordered)

                    Button("Reset", action: onReset)
                        .buttonStyle(.bordered)

                    Toggle(isOn: $useFluidVisuals) {
                        Label("Fluid", systemImage: "drop.fill")
                    }
                    .toggleStyle(.button)

                    Toggle(isOn: $showCharts) {
                        Label("Charts", systemImage: "chart.xyaxis.line")
                    }
                    .toggleStyle(.button)
                }
            }
            .controlSize(.small)
        }
    }
}

private struct ComparisonMetricMatrix: View {
    let entries: [StudioCompareEntry]

    private var rows: [StudioMetricDiffRow] {
        studioMetricDiffRows(for: entries)
    }

    var body: some View {
        StudioSurface(title: "Metric Matrix", subtitle: "Baseline row plus signed deltas", style: .console) {
            if rows.isEmpty {
                Text("No comparable metrics are attached to these entries.")
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            } else {
                GeometryReader { proxy in
                    let metricWidth: CGFloat = 150
                    let gap: CGFloat = 10
                    let columnWidth = max(160, (proxy.size.width - metricWidth - gap * CGFloat(max(entries.count, 1))) / CGFloat(max(entries.count, 1)))
                    VStack(alignment: .leading, spacing: 0) {
                        HStack(spacing: gap) {
                            MatrixHeaderCell(title: "Metric", subtitle: "delta")
                                .frame(width: metricWidth, alignment: .leading)
                            ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                                MatrixHeaderCell(
                                    title: index == 0 ? "Baseline" : compactName(entry.name),
                                    subtitle: entry.subtitle
                                )
                                .frame(width: columnWidth, alignment: .leading)
                            }
                        }
                        .padding(.bottom, 8)

                        Rectangle()
                            .fill(StudioPalette.hairline)
                            .frame(height: 1)

                        ForEach(rows) { row in
                            HStack(spacing: gap) {
                                Text(row.label)
                                    .font(StudioType.bodySmall)
                                    .foregroundStyle(StudioPalette.mutedInk)
                                    .frame(width: metricWidth, alignment: .leading)
                                ForEach(Array(entries.indices), id: \.self) { index in
                                    MatrixValueCell(row: row, index: index)
                                        .frame(width: columnWidth, alignment: .leading)
                                }
                            }
                            .padding(.vertical, 6)
                            .overlay(alignment: .bottom) {
                                Rectangle()
                                    .fill(StudioPalette.hairline.opacity(0.6))
                                    .frame(height: 1)
                            }
                        }
                    }
                }
                .frame(height: CGFloat(42 + rows.count * 40))
            }
        }
    }
}

private struct MatrixHeaderCell: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.ink)
                .lineLimit(1)
            Text(subtitle)
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.mutedInk)
                .lineLimit(1)
        }
    }
}

private struct MatrixValueCell: View {
    let row: StudioMetricDiffRow
    let index: Int

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(row.valueText(at: index))
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.ink)
                .frame(minWidth: 68, alignment: .leading)
            Text(row.deltaText(at: index))
                .font(StudioType.dataSmall)
                .foregroundStyle(deltaColor)
                .lineLimit(1)
        }
    }

    private var deltaColor: Color {
        guard index > 0, row.values.indices.contains(index),
              let baseline = row.values.first.flatMap({ $0 }), let value = row.values[index] else {
            return StudioPalette.mutedInk
        }
        let delta = value - baseline
        if abs(delta) < 1e-6 {
            return StudioPalette.mutedInk
        }
        return delta > 0 ? StudioPalette.moss : StudioPalette.ember
    }
}

private func compactName(_ value: String) -> String {
    if value.count <= 22 {
        return value
    }
    return String(value.prefix(21)) + "..."
}

private struct ComparisonPanelView: View {
    let entry: StudioCompareEntry
    @ObservedObject var model: LiveSimulationModel
    let renderMode: LeniaRenderMode
    let useFluidVisuals: Bool
    let showCharts: Bool
    let deltaScore: Float?

    var body: some View {
        StudioSurface(title: nil, subtitle: nil, style: .console) {
            VStack(spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(entry.name)
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(1)
                    Text(entry.subtitle)
                        .font(StudioType.bodySmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    if let deltaScore {
                        Text(String(format: "%+.3f", deltaScore))
                            .font(StudioType.dataSmall)
                            .foregroundStyle(deltaScore >= 0 ? StudioPalette.moss : StudioPalette.ember)
                    }
                }

                ZStack {
                    LinearGradient(
                        colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

                    if let frame = model.displayFrame {
                        LeniaLabStageView(
                            frame: frame,
                            renderMode: renderMode,
                            zoom: 2.4,
                            offset: .zero,
                            onTransformChange: { _ in },
                            onPrimaryPoint: { _ in },
                            onSecondaryPoint: { _ in },
                            onHoverPointChange: { _ in }
                        )
                        .padding(10)
                    } else {
                        ProgressView()
                            .controlSize(.small)
                            .tint(.white)
                    }
                }
                .frame(height: 170)

                VStack(alignment: .leading, spacing: 8) {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 72), spacing: 8)], alignment: .leading, spacing: 8) {
                        StudioMetricPill(label: "Score", value: String(format: "%.3f", entry.savedCreature?.score ?? entry.creature.score), accent: StudioPalette.ember, style: .console)
                        if let metrics = entry.savedCreature?.metrics ?? entry.metrics {
                            StudioMetricPill(label: "Vel", value: String(format: "%.3f", metrics.centerVelocity), accent: StudioPalette.ocean, style: .console)
                            if let complexity = metrics.complexityMean {
                                StudioMetricPill(label: "Cx", value: String(format: "%.3f", complexity), accent: StudioPalette.moss, style: .console)
                            }
                            StudioMetricPill(label: "Gyr", value: String(format: "%.3f", metrics.gyration), style: .console)
                        }
                    }

                    ComparisonContextStrip(entry: entry)

                    Text(model.stats)
                        .font(StudioType.dataSmall)
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

private struct ComparisonContextStrip: View {
    let entry: StudioCompareEntry

    private var rows: [(String, String)] {
        var values: [(String, String)] = []
        if let runtime = cleanComparisonLabel(entry.runtimeFamily ?? entry.replayReference?.runtimeFamily) {
            values.append(("Class", runtime))
        }
        let order = [entry.sourceMode, entry.sourceAlgorithm]
            .compactMap(cleanComparisonLabel)
            .joined(separator: " / ")
        if !order.isEmpty {
            values.append(("Order", order))
        }
        if let taxonomy = entry.taxonomy {
            if let family = cleanComparisonLabel(taxonomy.familyID) {
                values.append(("Family", family))
            }
            if let genus = cleanComparisonLabel(taxonomy.genusID) {
                values.append(("Genus", genus))
            }
            if let species = cleanComparisonLabel(taxonomy.speciesID) {
                values.append(("Species", species))
            }
        }
        if !entry.traitLabels.isEmpty {
            values.append(("Traits", entry.traitLabels.prefix(4).joined(separator: ", ")))
        }
        return values
    }

    var body: some View {
        if !rows.isEmpty {
            VStack(spacing: 4) {
                ForEach(rows, id: \.0) { row in
                    ComparisonContextRow(label: row.0, value: row.1)
                }
            }
            .padding(.vertical, 4)
        }
    }
}

private struct ComparisonContextRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.mutedInk)
                .frame(width: 48, alignment: .leading)
            Text(value)
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.ink)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer(minLength: 0)
        }
    }
}

private func cleanComparisonLabel(_ value: String?) -> String? {
    guard let value else { return nil }
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
}
