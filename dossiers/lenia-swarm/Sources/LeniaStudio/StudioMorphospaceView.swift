import SwiftUI
import LeniaArchive

enum StudioMorphospaceAxis: String, CaseIterable, Identifiable {
    case score
    case mass
    case occupancy
    case gyration
    case velocity
    case complexity
    case energy
    case efficiency

    var id: String { rawValue }

    var title: String {
        switch self {
        case .score: "Score"
        case .mass: "Mass"
        case .occupancy: "Occupancy"
        case .gyration: "Gyration"
        case .velocity: "Velocity"
        case .complexity: "Complexity"
        case .energy: "Energy"
        case .efficiency: "Efficiency"
        }
    }

    func value(for entry: CompendiumBrowseEntry) -> Double? {
        let metrics = entry.creature.metrics
        let value: Float?
        switch self {
        case .score:
            value = entry.score
        case .mass:
            value = metrics.massMean
        case .occupancy:
            value = metrics.occupancyMean
        case .gyration:
            value = metrics.gyration
        case .velocity:
            value = metrics.centerVelocity
        case .complexity:
            value = metrics.complexityMean
        case .energy:
            value = metrics.energyMean
        case .efficiency:
            value = metrics.pathLength > 1e-6
                ? metrics.displacement / metrics.pathLength
                : nil
        }
        guard let value, value.isFinite else { return nil }
        return Double(value)
    }
}

private struct StudioMorphospacePoint: Identifiable {
    let entry: CompendiumBrowseEntry
    let x: Double
    let y: Double
    let normalizedX: Double
    let normalizedY: Double

    var id: UUID { entry.id }
}

private struct StudioMorphospaceProjection {
    let points: [StudioMorphospacePoint]
    let xRange: ClosedRange<Double>
    let yRange: ClosedRange<Double>
    let density: [Int]
    let densitySide: Int

    init(entries: [CompendiumBrowseEntry], xAxis: StudioMorphospaceAxis, yAxis: StudioMorphospaceAxis) {
        let raw = entries.compactMap { entry -> (CompendiumBrowseEntry, Double, Double)? in
            guard let x = xAxis.value(for: entry), let y = yAxis.value(for: entry) else {
                return nil
            }
            return (entry, x, y)
        }
        let xRange = Self.range(raw.map(\.1))
        let yRange = Self.range(raw.map(\.2))
        self.xRange = xRange
        self.yRange = yRange
        self.points = raw.map { entry, x, y in
            StudioMorphospacePoint(
                entry: entry,
                x: x,
                y: y,
                normalizedX: Self.normalize(x, in: xRange),
                normalizedY: Self.normalize(y, in: yRange)
            )
        }
        densitySide = 12
        var density = [Int](repeating: 0, count: densitySide * densitySide)
        for point in points {
            let x = min(densitySide - 1, max(0, Int(point.normalizedX * Double(densitySide))))
            let y = min(densitySide - 1, max(0, Int(point.normalizedY * Double(densitySide))))
            density[y * densitySide + x] += 1
        }
        self.density = density
    }

    private static func range(_ values: [Double]) -> ClosedRange<Double> {
        guard let minimum = values.min(), let maximum = values.max() else {
            return 0...1
        }
        guard maximum > minimum else {
            return (minimum - 0.5)...(maximum + 0.5)
        }
        let padding = (maximum - minimum) * 0.04
        return (minimum - padding)...(maximum + padding)
    }

    private static func normalize(_ value: Double, in range: ClosedRange<Double>) -> Double {
        (value - range.lowerBound) / max(range.upperBound - range.lowerBound, .leastNonzeroMagnitude)
    }
}

struct StudioMorphospaceView: View {
    let entries: [CompendiumBrowseEntry]
    @Binding var selectedID: UUID?
    var canLaunchSweep = true
    var onOpen: (CompendiumBrowseEntry) -> Void
    var onLaunchSweep: (CompendiumBrowseEntry, StudioMorphospaceAxis, StudioMorphospaceAxis) -> Void

    @State private var xAxis: StudioMorphospaceAxis = .gyration
    @State private var yAxis: StudioMorphospaceAxis = .velocity
    @State private var hoveredID: UUID?

    private var projection: StudioMorphospaceProjection {
        StudioMorphospaceProjection(entries: entries, xAxis: xAxis, yAxis: yAxis)
    }

    private var selectedEntry: CompendiumBrowseEntry? {
        entries.first(where: { $0.id == selectedID })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    axisControls
                    Spacer()
                    legendSummary
                }
                VStack(alignment: .leading, spacing: 8) {
                    axisControls
                    legendSummary
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)

            Divider()

            mapContent
        }
        .background(StudioPalette.surface)
    }

    private var axisControls: some View {
        HStack(spacing: 12) {
            axisPicker("X", selection: $xAxis)
            axisPicker("Y", selection: $yAxis)
        }
    }

    private var legendSummary: some View {
        HStack(spacing: 10) {
            mapLegend(label: "Stable", color: StudioPalette.moss)
            mapLegend(label: "Other", color: StudioPalette.ocean)
            Text("\(projection.points.count.formatted()) specimens")
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)
        }
    }

    @ViewBuilder
    private var mapContent: some View {
        if projection.points.isEmpty {
            ContentUnavailableView(
                "No Plottable Specimens",
                systemImage: "chart.dots.scatter",
                description: Text("The selected axes have no finite values in this result set.")
            )
        } else {
            GeometryReader { proxy in
                if let selectedEntry {
                    if proxy.size.width >= 720 {
                        HStack(spacing: 0) {
                            plot
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                            Divider()
                            selectionInspector(selectedEntry)
                                .frame(width: 260)
                        }
                    } else {
                        VStack(spacing: 0) {
                            plot
                                .frame(maxWidth: .infinity, maxHeight: .infinity)
                            Divider()
                            compactSelectionInspector(selectedEntry)
                                .frame(height: 132)
                        }
                    }
                } else {
                    plot
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
    }

    private var plot: some View {
        GeometryReader { proxy in
            let leftInset: CGFloat = 58
            let bottomInset: CGFloat = 48
            let plotRect = CGRect(
                x: leftInset,
                y: 18,
                width: max(1, proxy.size.width - leftInset - 16),
                height: max(1, proxy.size.height - bottomInset - 18)
            )
            Canvas { context, _ in
                drawDensity(context: &context, rect: plotRect)
                drawGrid(context: &context, rect: plotRect)
                drawAxes(context: &context, rect: plotRect)
                for point in projection.points {
                    let position = CGPoint(
                        x: plotRect.minX + point.normalizedX * plotRect.width,
                        y: plotRect.maxY - point.normalizedY * plotRect.height
                    )
                    let selected = point.id == selectedID
                    let hovered = point.id == hoveredID
                    let radius: CGFloat = selected ? 6 : hovered ? 5 : 3.5
                    let color = point.entry.isStable ? StudioPalette.moss : StudioPalette.ocean
                    let pointPath = Path(ellipseIn: CGRect(
                        x: position.x - radius,
                        y: position.y - radius,
                        width: radius * 2,
                        height: radius * 2
                    ))
                    context.fill(
                        pointPath,
                        with: .color(selected ? StudioPalette.ember : color.opacity(hovered ? 1 : 0.84))
                    )
                    context.stroke(
                        pointPath,
                        with: .color(StudioPalette.stageBottom.opacity(0.9)),
                        lineWidth: hovered || selected ? 1.5 : 0.75
                    )
                    if selected {
                        context.stroke(
                            Path(ellipseIn: CGRect(
                                x: position.x - radius - 3,
                                y: position.y - radius - 3,
                                width: (radius + 3) * 2,
                                height: (radius + 3) * 2
                            )),
                            with: .color(StudioPalette.ember),
                            lineWidth: 1.5
                        )
                    }
                }
            }
            .background(StudioPalette.consoleSurface)
            .contentShape(Rectangle())
            .onContinuousHover { phase in
                switch phase {
                case .active(let location):
                    hoveredID = nearestPoint(to: location, in: plotRect)?.id
                case .ended:
                    hoveredID = nil
                }
            }
            .gesture(
                SpatialTapGesture()
                    .onEnded { gesture in
                        guard let point = nearestPoint(to: gesture.location, in: plotRect) else {
                            return
                        }
                        if selectedID == point.id {
                            onOpen(point.entry)
                        } else {
                            selectedID = point.id
                        }
                    }
            )
            .overlay(alignment: .bottom) {
                Text(xAxis.title)
                    .font(StudioType.labelStrong)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .padding(.bottom, 2)
            }
            .overlay(alignment: .leading) {
                Text(yAxis.title)
                    .font(StudioType.labelStrong)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .rotationEffect(.degrees(-90))
                    .fixedSize()
                    .offset(x: -10)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Morphospace map")
            .accessibilityValue("\(projection.points.count) specimens by \(xAxis.title) and \(yAxis.title)")
            .accessibilityChildren {
                ForEach(projection.points) { point in
                    let isSelected = point.id == selectedID
                    Button {
                        activateAccessiblePoint(point)
                    } label: {
                        Text(point.entry.name)
                    }
                    .accessibilityLabel(point.entry.name)
                    .accessibilityValue(accessibilityValue(point))
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                    .accessibilityAction(named: "Open Specimen") {
                        onOpen(point.entry)
                    }
                }
            }
        }
        .frame(minHeight: 320)
    }

    private func axisPicker(_ label: String, selection: Binding<StudioMorphospaceAxis>) -> some View {
        HStack(spacing: 6) {
            Text(label)
                .font(StudioType.labelStrong)
                .foregroundStyle(StudioPalette.mutedInk)
            Picker(label, selection: selection) {
                ForEach(StudioMorphospaceAxis.allCases) { axis in
                    Text(axis.title).tag(axis)
                }
            }
            .labelsHidden()
            .frame(width: 130)
        }
    }

    private func mapLegend(label: String, color: Color) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(label)
                .font(StudioType.label)
                .foregroundStyle(StudioPalette.mutedInk)
        }
    }

    private func selectionInspector(_ entry: CompendiumBrowseEntry) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                CreatureThumbnailView(creature: entry.creature.toLeniaCreature(), size: 112)

                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(entry.name)
                            .font(StudioType.title)
                            .foregroundStyle(StudioPalette.ink)
                            .lineLimit(2)
                        if entry.isStable {
                            Image(systemName: "checkmark.seal.fill")
                                .font(StudioType.labelStrong)
                                .foregroundStyle(StudioPalette.moss)
                        }
                    }
                    Text(inspectorSubtitle(entry))
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(2)
                }

                HStack(spacing: 8) {
                    StudioMetricPill(
                        label: "Score",
                        value: entry.score.map { String(format: "%.4f", $0) } ?? "--",
                        accent: StudioPalette.ember,
                        style: .console
                    )
                    StudioMetricPill(
                        label: "Seed",
                        value: "\(entry.previewSeed)",
                        accent: StudioPalette.moss,
                        style: .console
                    )
                }

                StudioKeyValueRow(label: xAxis.title, value: formatted(xAxis.value(for: entry)))
                StudioKeyValueRow(label: yAxis.title, value: formatted(yAxis.value(for: entry)))
                StudioKeyValueRow(label: "Catalog", value: entry.catalogStatus.capitalized)

                Divider()

                Button { onOpen(entry) } label: {
                    Label("Open Specimen", systemImage: "arrow.up.right.square")
                }
                .buttonStyle(.borderedProminent)
                Button {
                    onLaunchSweep(entry, xAxis, yAxis)
                } label: {
                    Label("Sweep From Here", systemImage: "point.3.connected.trianglepath.dotted")
                }
                .buttonStyle(.bordered)
                .disabled(!canLaunchSweep)
                .help(canLaunchSweep ? "Create a sweep from this specimen" : "Connect as a host to create a sweep")
            }
            .padding(14)
        }
        .background(StudioPalette.surfaceRaised.opacity(0.35))
    }

    private func compactSelectionInspector(_ entry: CompendiumBrowseEntry) -> some View {
        HStack(spacing: 12) {
            CreatureThumbnailView(creature: entry.creature.toLeniaCreature(), size: 84)
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.name)
                    .font(StudioType.title)
                    .foregroundStyle(StudioPalette.ink)
                    .lineLimit(1)
                Text(inspectorSubtitle(entry))
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .lineLimit(1)
                HStack(spacing: 12) {
                    compactMetric("Score", entry.score.map { String(format: "%.4f", $0) } ?? "--")
                    compactMetric(xAxis.title, formatted(xAxis.value(for: entry)))
                    compactMetric(yAxis.title, formatted(yAxis.value(for: entry)))
                }
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 8) {
                Button { onOpen(entry) } label: {
                    Label("Open", systemImage: "arrow.up.right.square")
                }
                .buttonStyle(.borderedProminent)
                Button {
                    onLaunchSweep(entry, xAxis, yAxis)
                } label: {
                    Label("Sweep", systemImage: "point.3.connected.trianglepath.dotted")
                }
                .buttonStyle(.bordered)
                .disabled(!canLaunchSweep)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(StudioPalette.surfaceRaised.opacity(0.35))
    }

    private func compactMetric(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label.uppercased())
                .font(StudioType.label)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.ink)
                .monospacedDigit()
        }
    }

    private func inspectorSubtitle(_ entry: CompendiumBrowseEntry) -> String {
        if let taxonomy = entry.taxonomy {
            let labels = [taxonomy.familyID, taxonomy.genusID, taxonomy.speciesID]
                .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            if !labels.isEmpty {
                return labels.joined(separator: " / ")
            }
        }
        if !entry.traitLabels.isEmpty {
            return entry.traitLabels.prefix(3).joined(separator: " · ")
        }
        return entry.displayRun
    }

    private func activateAccessiblePoint(_ point: StudioMorphospacePoint) {
        if selectedID == point.id {
            onOpen(point.entry)
        } else {
            selectedID = point.id
        }
    }

    private func accessibilityValue(_ point: StudioMorphospacePoint) -> String {
        let score = point.entry.score.map { String(format: "score %.4f", $0) } ?? "score unavailable"
        let stability = point.entry.isStable ? "stable" : "not stable"
        return "\(xAxis.title) \(formatted(point.x)), \(yAxis.title) \(formatted(point.y)), \(score), \(stability)"
    }

    private func nearestPoint(to location: CGPoint, in rect: CGRect) -> StudioMorphospacePoint? {
        guard rect.contains(location) else { return nil }
        return projection.points.min { lhs, rhs in
            distanceSquared(lhs, to: location, rect: rect) < distanceSquared(rhs, to: location, rect: rect)
        }.flatMap { point in
            distanceSquared(point, to: location, rect: rect) <= 18 * 18 ? point : nil
        }
    }

    private func distanceSquared(_ point: StudioMorphospacePoint, to location: CGPoint, rect: CGRect) -> CGFloat {
        let x = rect.minX + point.normalizedX * rect.width
        let y = rect.maxY - point.normalizedY * rect.height
        let dx = x - location.x
        let dy = y - location.y
        return dx * dx + dy * dy
    }

    private func drawAxes(context: inout GraphicsContext, rect: CGRect) {
        context.stroke(
            Path(rect),
            with: .color(StudioPalette.hairline.opacity(0.95)),
            lineWidth: 1
        )
    }

    private func drawGrid(context: inout GraphicsContext, rect: CGRect) {
        let tickCount = 5
        for index in 0..<tickCount {
            let progress = Double(index) / Double(tickCount - 1)
            let x = rect.minX + CGFloat(progress) * rect.width
            let y = rect.maxY - CGFloat(progress) * rect.height

            var vertical = Path()
            vertical.move(to: CGPoint(x: x, y: rect.minY))
            vertical.addLine(to: CGPoint(x: x, y: rect.maxY))
            context.stroke(vertical, with: .color(StudioPalette.hairline.opacity(0.5)), lineWidth: 0.5)

            var horizontal = Path()
            horizontal.move(to: CGPoint(x: rect.minX, y: y))
            horizontal.addLine(to: CGPoint(x: rect.maxX, y: y))
            context.stroke(horizontal, with: .color(StudioPalette.hairline.opacity(0.5)), lineWidth: 0.5)

            let xValue = projection.xRange.lowerBound
                + progress * (projection.xRange.upperBound - projection.xRange.lowerBound)
            let yValue = projection.yRange.lowerBound
                + progress * (projection.yRange.upperBound - projection.yRange.lowerBound)
            context.draw(
                Text(formattedTick(xValue))
                    .font(StudioType.dataSmall)
                    .foregroundColor(StudioPalette.mutedInk),
                at: CGPoint(x: x, y: rect.maxY + 7),
                anchor: .top
            )
            context.draw(
                Text(formattedTick(yValue))
                    .font(StudioType.dataSmall)
                    .foregroundColor(StudioPalette.mutedInk),
                at: CGPoint(x: rect.minX - 7, y: y),
                anchor: .trailing
            )
        }
    }

    private func drawDensity(context: inout GraphicsContext, rect: CGRect) {
        let side = projection.densitySide
        let maximum = max(1, projection.density.max() ?? 1)
        let cellWidth = rect.width / CGFloat(side)
        let cellHeight = rect.height / CGFloat(side)
        for y in 0..<side {
            for x in 0..<side {
                let count = projection.density[y * side + x]
                let cell = CGRect(
                    x: rect.minX + CGFloat(x) * cellWidth,
                    y: rect.maxY - CGFloat(y + 1) * cellHeight,
                    width: cellWidth,
                    height: cellHeight
                ).insetBy(dx: 1, dy: 1)
                if count > 0 {
                    let intensity = Double(count) / Double(maximum)
                    context.fill(
                        Path(cell),
                        with: .color(StudioPalette.ocean.opacity(0.06 + intensity * 0.22))
                    )
                }
            }
        }
    }

    private func formatted(_ value: Double?) -> String {
        guard let value else { return "--" }
        return value.formatted(.number.precision(.significantDigits(4)))
    }

    private func formattedTick(_ value: Double) -> String {
        value.formatted(.number.precision(.significantDigits(3)))
    }
}
