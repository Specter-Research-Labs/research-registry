import AppKit
import SwiftUI
import LeniaCore

enum StudioPalette {
    static let chrome = Color(nsColor: .windowBackgroundColor)
    static let chromeMuted = Color(nsColor: .underPageBackgroundColor)
    static let surface = Color(nsColor: .controlBackgroundColor)
    static let surfaceRaised = Color(nsColor: .textBackgroundColor)
    static let surfaceSoft = Color(nsColor: .unemphasizedSelectedContentBackgroundColor)
    static let surfaceInset = Color(nsColor: .underPageBackgroundColor)
    static let consoleSurface = Color(nsColor: .underPageBackgroundColor)
    static let consoleSurfaceRaised = Color(nsColor: .controlBackgroundColor)
    static let consoleControl = Color(nsColor: .textBackgroundColor).opacity(0.72)
    static let ink = Color(nsColor: .labelColor)
    static let mutedInk = Color(nsColor: .secondaryLabelColor)
    static let hairline = Color(nsColor: .separatorColor)
    static let hairlineStrong = Color(nsColor: .gridColor)
    static let selection = Color.accentColor.opacity(0.13)
    static let ember = Color(nsColor: .systemOrange)
    static let moss = Color(nsColor: .systemGreen)
    static let ocean = Color(nsColor: .systemTeal)
    static let rose = Color(nsColor: .systemPink)
    static let stageTop = Color(red: 0.060, green: 0.064, blue: 0.067)
    static let stageBottom = Color(red: 0.016, green: 0.018, blue: 0.020)
}

enum StudioType {
    static let panelTitle = Font.system(.subheadline, design: .default, weight: .semibold)
    static let panelSubtitle = Font.caption
    static let label = Font.system(.caption2, design: .default, weight: .semibold)
    static let labelStrong = Font.system(.caption, design: .default, weight: .semibold)
    static let data = Font.system(.callout, design: .monospaced, weight: .medium)
    static let dataSmall = Font.system(.caption, design: .monospaced)
    static let body = Font.body
    static let bodySmall = Font.callout
    static let title = Font.headline
}

enum StudioLayout {
    static let hairline: CGFloat = 1
    static let controlRadius: CGFloat = 5
    static let panelRadius: CGFloat = 7
    static let compactGap: CGFloat = 6
    static let sectionGap: CGFloat = 12
    static let panelPadding: CGFloat = 12
}

enum StudioPanelStyle: Equatable {
    case standard
    case console

    var cornerRadius: CGFloat {
        switch self {
        case .standard:
            StudioLayout.panelRadius
        case .console:
            StudioLayout.controlRadius
        }
    }

    var padding: CGFloat {
        switch self {
        case .standard:
            StudioLayout.panelPadding
        case .console:
            10
        }
    }
}

enum StudioMetricPillStyle: Equatable {
    case standard
    case console

    var cornerRadius: CGFloat {
        switch self {
        case .standard:
            4
        case .console:
            3
        }
    }

    var labelFont: Font {
        switch self {
        case .standard:
            StudioType.label
        case .console:
            StudioType.labelStrong
        }
    }

    var valueFont: Font {
        switch self {
        case .standard:
            StudioType.data
        case .console:
            StudioType.data
        }
    }
}

enum StudioKeyValueRowStyle: Equatable {
    case compact
    case readable

    var labelFont: Font {
        switch self {
        case .compact:
            StudioType.bodySmall
        case .readable:
            StudioType.body
        }
    }

    var valueFont: Font {
        switch self {
        case .compact:
            StudioType.dataSmall
        case .readable:
            StudioType.data
        }
    }
}

struct StudioSceneBackground: View {
    var body: some View {
        StudioPalette.chrome
            .ignoresSafeArea()
    }
}

struct StudioSurface<Content: View>: View {
    let title: String?
    let subtitle: String?
    let style: StudioPanelStyle
    let content: Content

    init(
        title: String? = nil,
        subtitle: String? = nil,
        style: StudioPanelStyle = .standard,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.subtitle = subtitle
        self.style = style
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: StudioLayout.sectionGap) {
            if title != nil || subtitle != nil {
                VStack(alignment: .leading, spacing: 3) {
                    if let title {
                        Text(title)
                            .font(StudioType.panelTitle)
                            .foregroundStyle(StudioPalette.ink)
                    }
                    if let subtitle {
                        Text(subtitle)
                            .font(StudioType.panelSubtitle)
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                }
            }
            content
        }
        .padding(style.padding)
        .background(
            RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                .fill(style == .console ? StudioPalette.consoleSurface : StudioPalette.surface)
        )
        .overlay {
            if style == .console {
                RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                    .stroke(StudioPalette.hairline.opacity(0.72), lineWidth: StudioLayout.hairline)
            }
        }
        .shadow(
            color: style == .standard ? Color.black.opacity(0.08) : .clear,
            radius: 1,
            y: 1
        )
    }
}

struct StudioMetricPill: View {
    let label: String
    let value: String
    var accent: Color = StudioPalette.ink
    var style: StudioMetricPillStyle = .standard

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(style.labelFont)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(style.valueFont)
                .foregroundStyle(accent)
        }
        .padding(.leading, 10)
        .padding(.trailing, 9)
        .padding(.vertical, style == .console ? 5 : 7)
        .frame(minHeight: style == .console ? 34 : 40, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                .fill(style == .console ? StudioPalette.consoleControl : StudioPalette.surfaceSoft.opacity(0.66))
        )
        .overlay(alignment: .leading) {
            Capsule(style: .continuous)
                .fill(accent.opacity(0.82))
                .frame(width: 2, height: style == .console ? 18 : 22)
                .padding(.leading, 4)
        }
    }
}

struct StudioKeyValueRow: View {
    let label: String
    let value: String
    var style: StudioKeyValueRowStyle = .compact

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(label)
                .font(style.labelFont)
                .foregroundStyle(StudioPalette.mutedInk)
            Spacer()
            Text(value)
                .multilineTextAlignment(.trailing)
                .font(style.valueFont)
                .foregroundStyle(StudioPalette.ink)
        }
        .font(style.labelFont)
    }
}

struct CreatureThumbnailView: View {
    let creature: LeniaCreature
    var size: CGFloat = 84
    @State private var thumbnail: CGImage?

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            if let thumbnail {
                Image(decorative: thumbnail, scale: 1.0)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFill()
            } else {
                ProgressView()
                    .controlSize(.small)
                    .tint(.white.opacity(0.8))
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .stroke(.white.opacity(0.10), lineWidth: StudioLayout.hairline)
        }
        .task(id: creature.id) {
            thumbnail = await ThumbnailRenderer.shared.render(creature: creature)
        }
    }
}

struct StudioCreatureCard: View {
    let entry: StudioCompareEntry
    var rank: Int? = nil
    var tone: Color = StudioPalette.ember
    var onSelect: (() -> Void)? = nil
    var onAddToCompare: (() -> Void)? = nil
    var onRemoveFromCompare: (() -> Void)? = nil
    var showRemove: Bool = false

    private var displayScore: Float {
        entry.savedCreature?.score ?? entry.creature.score
    }

    private var displayVelocity: Float? {
        entry.metrics?.centerVelocity
    }

    private var displayComplexity: Float? {
        entry.metrics?.complexityMean
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ZStack(alignment: .topLeading) {
                CreatureThumbnailView(creature: entry.creature, size: 120)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if let rank {
                    Text("#\(rank)")
                        .font(StudioType.labelStrong)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 5)
                        .background(.thinMaterial, in: Capsule(style: .continuous))
                        .padding(10)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(entry.name)
                    .font(StudioType.title)
                    .foregroundStyle(StudioPalette.ink)
                    .lineLimit(1)
                Text(entry.subtitle)
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .lineLimit(1)
            }

            HStack(spacing: 8) {
                StudioMetricPill(label: "Score", value: String(format: "%.3f", displayScore), accent: tone)
                StudioMetricPill(label: "Seed", value: "\(entry.creature.seed)")
            }

            if displayVelocity != nil || displayComplexity != nil {
                HStack(spacing: 8) {
                    if let displayVelocity {
                        StudioMetricPill(label: "Vel", value: String(format: "%.3f", displayVelocity), accent: StudioPalette.ocean)
                    }
                    if let displayComplexity {
                        StudioMetricPill(label: "Cx", value: String(format: "%.3f", displayComplexity), accent: StudioPalette.moss)
                    }
                }
            }

            HStack {
                if let onAddToCompare {
                    Button(action: onAddToCompare) {
                        Label("Compare", systemImage: "plus.rectangle.on.rectangle")
                    }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .tint(tone)
                }
                if showRemove, let onRemoveFromCompare {
                    Button(role: .destructive, action: onRemoveFromCompare) {
                        Label("Remove", systemImage: "xmark")
                    }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
                Spacer()
                if entry.savedCreature?.metrics.isStable == true {
                    Label("Stable", systemImage: "checkmark.seal.fill")
                        .font(.caption)
                        .foregroundStyle(StudioPalette.moss)
                }
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(StudioPalette.surfaceRaised)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(StudioPalette.hairline.opacity(0.52), lineWidth: StudioLayout.hairline)
        )
        .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .onTapGesture {
            onSelect?()
        }
    }
}

struct ClusterPulseStrip: View {
    let snapshot: ClusterSummary?
    let workers: [WorkerStatus]
    let campaigns: [CampaignStatus]
    let seedsProcessed: Int
    let rate: Double

    private var workerCount: Int {
        snapshot?.workers.count ?? workers.count
    }

    private var availabilityCount: Int {
        (snapshot?.workers ?? workers).filter { $0.isAvailable }.count
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                StudioMetricPill(label: "Workers", value: "\(workerCount)", accent: StudioPalette.ocean)
                StudioMetricPill(label: "Ready", value: "\(availabilityCount)", accent: StudioPalette.moss)
                StudioMetricPill(label: "Seeds", value: "\(seedsProcessed)", accent: StudioPalette.ember)
                StudioMetricPill(label: "Rate", value: rate > 0 ? String(format: "%.1f/s", rate) : "--")
                StudioMetricPill(label: "Campaigns", value: "\(campaigns.count)")
            }
        }
    }
}

struct WorkerActivityFeedView: View {
    let items: [WorkerActivityItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if items.isEmpty {
                Text("No activity yet")
                    .font(.caption)
                    .foregroundStyle(StudioPalette.mutedInk)
            } else {
                ForEach(items) { item in
                    HStack(alignment: .top, spacing: 10) {
                        Circle()
                            .fill(color(for: item.kind))
                            .frame(width: 9, height: 9)
                            .padding(.top, 4)
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(item.title)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(StudioPalette.ink)
                                Spacer()
                                Text(item.timestamp.formatted(date: .omitted, time: .shortened))
                                    .font(.caption2)
                                    .foregroundStyle(StudioPalette.mutedInk)
                            }
                            Text(item.detail)
                                .font(.caption)
                                .foregroundStyle(StudioPalette.mutedInk)
                        }
                    }
                }
            }
        }
    }

    private func color(for kind: WorkerActivityKind) -> Color {
        switch kind {
        case .localDiscovery: return StudioPalette.ember
        case .clusterUpdate: return StudioPalette.ocean
        case .campaign: return StudioPalette.moss
        case .arena: return StudioPalette.rose
        case .system: return .gray
        }
    }
}

struct StudioEmptyState: View {
    let symbol: String
    let title: String
    var detail: String? = nil

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: symbol)
                .font(.system(size: 24, weight: .light))
                .foregroundStyle(StudioPalette.mutedInk)
                .frame(height: 28)
            Text(title)
                .font(StudioType.panelTitle)
                .foregroundStyle(StudioPalette.ink)
            if let detail {
                Text(detail)
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 20)
        .accessibilityElement(children: .combine)
    }
}

struct StudioCompareTrayView: View {
    let entries: [StudioCompareEntry]
    let onSelect: (StudioCompareEntry) -> Void
    let onRemove: (StudioCompareEntry) -> Void
    let onCompare: () -> Void
    let onClear: () -> Void

    var body: some View {
        StudioSurface(
            title: "Compare Tray",
            subtitle: entries.isEmpty ? nil : "\(entries.count) of 4 specimens"
        ) {
            VStack(alignment: .leading, spacing: 14) {
                if entries.isEmpty {
                    StudioEmptyState(symbol: "rectangle.stack", title: "Tray empty")
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 12) {
                            ForEach(entries) { entry in
                                VStack(alignment: .leading, spacing: 8) {
                                    Button(action: { onSelect(entry) }) {
                                        HStack(spacing: 10) {
                                            CreatureThumbnailView(creature: entry.creature, size: 58)
                                            VStack(alignment: .leading, spacing: 3) {
                                                Text(entry.name)
                                                    .font(StudioType.title)
                                                    .foregroundStyle(StudioPalette.ink)
                                                    .lineLimit(1)
                                                Text(entry.subtitle)
                                                    .font(StudioType.bodySmall)
                                                    .foregroundStyle(StudioPalette.mutedInk)
                                                    .lineLimit(1)
                                                Text(String(format: "%.3f", entry.savedCreature?.score ?? entry.creature.score))
                                                    .font(StudioType.dataSmall)
                                                    .foregroundStyle(StudioPalette.ember)
                                            }
                                        }
                                    }
                                    .buttonStyle(.plain)

                                    Button(role: .destructive) { onRemove(entry) } label: {
                                        Label("Remove", systemImage: "xmark")
                                    }
                                        .buttonStyle(.bordered)
                                        .controlSize(.mini)
                                }
                                .padding(10)
                                .frame(width: 220, alignment: .leading)
                                .background(
                                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                                        .fill(StudioPalette.surfaceSoft.opacity(0.66))
                                )
                            }
                        }
                    }
                }

                HStack {
                    Button(action: onCompare) {
                        Label("Compare \(entries.count)", systemImage: "square.split.2x1")
                    }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(entries.count < 2)
                        .keyboardShortcut("c", modifiers: [.command, .shift])
                    Button(role: .destructive, action: onClear) {
                        Label("Clear", systemImage: "trash")
                    }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(entries.isEmpty)
                    Spacer()
                    Text("\(entries.count)/4")
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                }
            }
        }
    }
}
