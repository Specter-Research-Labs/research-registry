import SwiftUI
import LeniaCore
import LeniaVisuals

func comparisonGridColumnCount(availableWidth: CGFloat, entryCount: Int) -> Int {
    guard entryCount > 1 else { return 1 }
    return availableWidth < 780 ? 1 : min(entryCount, 2)
}

func comparisonMetricMatrixMinimumWidth(entryCount: Int) -> CGFloat {
    let count = max(1, entryCount)
    return 148 + CGFloat(count) * 172 + CGFloat(count) * 12
}

struct ComparisonPlaybackGroupState: Equatable {
    private(set) var pausedByEntryID: [String: Bool] = [:]

    mutating func record(entryID: String, isPaused: Bool) {
        pausedByEntryID[entryID] = isPaused
    }

    mutating func retain(entryIDs: Set<String>) {
        pausedByEntryID = pausedByEntryID.filter { entryIDs.contains($0.key) }
    }

    func anyPaused(entryIDs: [String]) -> Bool {
        entryIDs.contains { pausedByEntryID[$0] ?? true }
    }

    func targetPaused(entryIDs: [String]) -> Bool {
        !anyPaused(entryIDs: entryIDs)
    }
}

struct ComparisonView: View {
    let entries: [StudioCompareEntry]

    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var showCharts = false
    @State private var models: [String: LiveSimulationModel] = [:]
    @State private var playbackState = ComparisonPlaybackGroupState()
    @Environment(\.dismiss) private var dismiss

    private func gridColumns(for availableWidth: CGFloat) -> [GridItem] {
        let count = comparisonGridColumnCount(availableWidth: availableWidth, entryCount: entries.count)
        return Array(repeating: GridItem(.flexible(), spacing: 12), count: count)
    }

    private var baselineScore: Float? {
        entries.first.map { $0.savedCreature?.score ?? $0.creature.score }
    }

    var body: some View {
        Group {
            if entries.count < 2 {
                ContentUnavailableView(
                    "Comparison unavailable",
                    systemImage: "rectangle.split.2x1"
                )
            } else {
                GeometryReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 16) {
                            ComparisonHeaderStrip(
                                entries: entries,
                                baselineScore: baselineScore,
                                anyPaused: anyPaused,
                                showCharts: $showCharts,
                                onTogglePause: toggleAllPause,
                                onReset: resetAll
                            )

                            LazyVGrid(columns: gridColumns(for: proxy.size.width), spacing: 12) {
                                ForEach(entries) { entry in
                                    if let model = liveModel(for: entry) {
                                        ComparisonPanelView(
                                            entry: entry,
                                            model: model,
                                            renderMode: renderMode,
                                            showCharts: showCharts,
                                            isBaseline: entry.id == entries.first?.id,
                                            deltaScore: deltaScore(for: entry),
                                            onPauseStateChange: { isPaused in
                                                playbackState.record(entryID: entry.id, isPaused: isPaused)
                                            }
                                        )
                                    }
                                }
                            }

                            ComparisonMetricMatrix(entries: entries)
                        }
                        .padding(16)
                    }
                }
            }
        }
        .background(StudioSceneBackground())
        .onAppear {
            ensureModels()
            for entry in entries {
                liveModel(for: entry)?.start(
                    creature: entry.creature,
                    savedCreature: entry.savedCreature,
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
        playbackState.anyPaused(entryIDs: entries.map(\.id))
    }

    private func ensureModels() {
        playbackState.retain(entryIDs: Set(entries.map(\.id)))
        for entry in entries where models[entry.id] == nil {
            let model = LiveSimulationModel()
            models[entry.id] = model
            playbackState.record(entryID: entry.id, isPaused: model.isPaused)
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
        let newState = playbackState.targetPaused(entryIDs: entries.map(\.id))
        for entry in entries {
            liveModel(for: entry)?.setPaused(newState)
        }
    }

    private func resetAll() {
        for entry in entries {
            liveModel(for: entry)?.restart(
                creature: entry.creature,
                savedCreature: entry.savedCreature,
                replaySource: entry.replayReference
            )
        }
    }
}

private struct ComparisonHeaderStrip: View {
    let entries: [StudioCompareEntry]
    let baselineScore: Float?
    let anyPaused: Bool
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
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) {
                summary
                    .fixedSize()
                Spacer(minLength: 16)
                controls
                    .fixedSize()
            }

            VStack(alignment: .leading, spacing: 12) {
                summary
                controls
            }
        }
        .padding(.horizontal, 4)
        .controlSize(.small)
    }

    private var summary: some View {
        HStack(spacing: 14) {
            Text("\(entries.count) specimens")
                .font(StudioType.data)
                .foregroundStyle(StudioPalette.ink)

            if let baselineScore {
                ComparisonHeaderDatum(
                    label: "Baseline",
                    value: String(format: "%.3f", baselineScore),
                    color: StudioPalette.ember
                )
            }
            ComparisonHeaderDatum(label: "Stable", value: "\(stableCount)", color: StudioPalette.moss)
            ComparisonHeaderDatum(label: "Sources", value: "\(sourceCount)", color: StudioPalette.ocean)
        }
    }

    private var controls: some View {
        HStack(spacing: 8) {
            ControlGroup {
                Button(action: onTogglePause) {
                    Image(systemName: anyPaused ? "play.fill" : "pause.fill")
                }
                .help(anyPaused ? "Resume all replays" : "Pause all replays")
                .accessibilityLabel(anyPaused ? "Resume all replays" : "Pause all replays")

                Button(action: onReset) {
                    Image(systemName: "arrow.counterclockwise")
                }
                .help("Reset all replays")
                .accessibilityLabel("Reset all replays")
            }

            Toggle(isOn: $showCharts) {
                Image(systemName: "chart.xyaxis.line")
            }
            .toggleStyle(.button)
            .help("Metric charts")
            .accessibilityLabel("Metric charts")
        }
    }
}

private struct ComparisonHeaderDatum: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Text(label)
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(StudioType.dataSmall)
                .foregroundStyle(color)
        }
    }
}

private struct ComparisonMetricMatrix: View {
    let entries: [StudioCompareEntry]

    private var rows: [StudioMetricDiffRow] {
        studioMetricDiffRows(for: entries)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Metric Matrix")
                    .font(StudioType.panelTitle)
                    .foregroundStyle(StudioPalette.ink)
                Text("Values and signed change from the baseline")
                    .font(StudioType.panelSubtitle)
                    .foregroundStyle(StudioPalette.mutedInk)
            }

            if rows.isEmpty {
                Text("No comparable metrics are attached to these entries.")
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            } else {
                GeometryReader { proxy in
                    let gap: CGFloat = 12
                    let metricWidth: CGFloat = 148
                    let contentWidth = max(proxy.size.width, comparisonMetricMatrixMinimumWidth(entryCount: entries.count))
                    let columnWidth = max(
                        160,
                        (contentWidth - metricWidth - gap * CGFloat(entries.count)) / CGFloat(max(entries.count, 1))
                    )

                    ScrollView(.horizontal) {
                        VStack(alignment: .leading, spacing: 0) {
                            HStack(spacing: gap) {
                                MatrixHeaderCell(title: "Metric", subtitle: "Baseline delta")
                                    .frame(width: metricWidth, alignment: .leading)
                                ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                                    MatrixHeaderCell(
                                        title: index == 0 ? "Baseline" : compactName(entry.name),
                                        subtitle: entry.subtitle
                                    )
                                    .frame(width: columnWidth, alignment: .leading)
                                }
                            }
                            .padding(.bottom, 9)

                            Divider()

                            ForEach(Array(rows.enumerated()), id: \.element.id) { rowIndex, row in
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
                                .background(
                                    rowIndex.isMultiple(of: 2)
                                        ? StudioPalette.surfaceSoft.opacity(0.24)
                                        : Color.clear
                                )
                            }
                        }
                        .frame(width: contentWidth, alignment: .leading)
                    }
                    .scrollIndicators(.visible)
                }
                .frame(height: CGFloat(40 + rows.count * 34))
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(StudioPalette.surface)
        )
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
    let showCharts: Bool
    let isBaseline: Bool
    let deltaScore: Float?
    let onPauseStateChange: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
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
                if isBaseline {
                    Text("BASELINE")
                        .font(StudioType.label)
                        .foregroundStyle(StudioPalette.ember)
                } else if let deltaScore {
                    Text(String(format: "%+.3f", deltaScore))
                        .font(StudioType.dataSmall)
                        .foregroundStyle(deltaScore >= 0 ? StudioPalette.moss : StudioPalette.ember)
                }
            }

            ZStack {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(StudioPalette.stageBottom)

                if let frame = model.displayFrame {
                    LeniaLabStageView(
                        frame: frame,
                        renderMode: renderMode,
                        zoom: 2.4,
                        offset: .zero,
                        onTransformChange: { _ in },
                        onPrimaryPoint: { _ in },
                        onSecondaryPoint: { _ in },
                        onHoverPointChange: { _ in },
                        onBrushRadiusDelta: nil
                    )
                    .padding(10)
                } else {
                    VStack(spacing: 8) {
                        ProgressView()
                            .controlSize(.small)
                            .tint(.white)
                        Text("Preparing replay")
                            .font(StudioType.bodySmall)
                            .foregroundStyle(.white.opacity(0.72))
                    }
                }
            }
            .aspectRatio(1.6, contentMode: .fit)
            .frame(maxWidth: .infinity)
            .accessibilityLabel("\(entry.name) synchronized replay")

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 84), spacing: 12)],
                alignment: .leading,
                spacing: 8
            ) {
                ComparisonMetricValue(
                    label: "Score",
                    value: String(format: "%.3f", entry.savedCreature?.score ?? entry.creature.score),
                    color: StudioPalette.ember
                )
                if let metrics = entry.savedCreature?.metrics ?? entry.metrics {
                    ComparisonMetricValue(
                        label: "Velocity",
                        value: String(format: "%.3f", metrics.centerVelocity),
                        color: StudioPalette.ocean
                    )
                    if let complexity = metrics.complexityMean {
                        ComparisonMetricValue(
                            label: "Complexity",
                            value: String(format: "%.3f", complexity),
                            color: StudioPalette.moss
                        )
                    }
                    ComparisonMetricValue(
                        label: "Gyration",
                        value: String(format: "%.3f", metrics.gyration),
                        color: StudioPalette.ink
                    )
                }
            }

            ComparisonContextStrip(entry: entry)

            Text(model.stats)
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)

            if showCharts {
                MetricChartPanel(metricHistory: model.metricHistory)
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(StudioPalette.surface)
        )
        .onAppear {
            onPauseStateChange(model.isPaused)
        }
        .onChange(of: model.isPaused) { _, isPaused in
            onPauseStateChange(isPaused)
        }
    }
}

private struct ComparisonMetricValue: View {
    let label: String
    let value: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(StudioType.label)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(StudioType.data)
                .foregroundStyle(color)
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
