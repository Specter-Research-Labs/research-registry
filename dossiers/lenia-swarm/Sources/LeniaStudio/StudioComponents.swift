import AppKit
import SwiftUI
import LeniaCore

enum StudioPalette {
    private static func dynamicColor(
        light: (CGFloat, CGFloat, CGFloat, CGFloat),
        dark: (CGFloat, CGFloat, CGFloat, CGFloat)
    ) -> Color {
        Color(
            nsColor: NSColor(name: nil) { appearance in
                let match = appearance.bestMatch(from: [.darkAqua, .vibrantDark, .aqua, .vibrantLight])
                let components = (match == .darkAqua || match == .vibrantDark) ? dark : light
                return NSColor(
                    deviceRed: components.0,
                    green: components.1,
                    blue: components.2,
                    alpha: components.3
                )
            }
        )
    }

    static let chrome = dynamicColor(
        light: (0.93, 0.90, 0.86, 1.0),
        dark: (0.10, 0.11, 0.13, 1.0)
    )
    static let chromeMuted = dynamicColor(
        light: (0.84, 0.80, 0.75, 1.0),
        dark: (0.16, 0.17, 0.20, 1.0)
    )
    static let surface = dynamicColor(
        light: (0.97, 0.96, 0.94, 1.0),
        dark: (0.14, 0.15, 0.18, 1.0)
    )
    static let surfaceRaised = dynamicColor(
        light: (0.99, 0.985, 0.975, 1.0),
        dark: (0.18, 0.19, 0.22, 1.0)
    )
    static let surfaceSoft = dynamicColor(
        light: (0.95, 0.93, 0.90, 1.0),
        dark: (0.16, 0.17, 0.20, 1.0)
    )
    static let consoleSurface = dynamicColor(
        light: (0.96, 0.95, 0.93, 1.0),
        dark: (0.11, 0.12, 0.15, 1.0)
    )
    static let consoleSurfaceRaised = dynamicColor(
        light: (0.99, 0.98, 0.96, 1.0),
        dark: (0.14, 0.15, 0.18, 1.0)
    )
    static let consoleControl = dynamicColor(
        light: (0.92, 0.90, 0.86, 1.0),
        dark: (0.17, 0.18, 0.21, 1.0)
    )
    static let ink = dynamicColor(
        light: (0.15, 0.13, 0.11, 1.0),
        dark: (0.92, 0.90, 0.87, 1.0)
    )
    static let mutedInk = dynamicColor(
        light: (0.42, 0.38, 0.34, 1.0),
        dark: (0.67, 0.64, 0.60, 1.0)
    )
    static let hairline = dynamicColor(
        light: (0.76, 0.71, 0.65, 0.75),
        dark: (0.33, 0.35, 0.39, 0.95)
    )
    static let panelShadow = dynamicColor(
        light: (0.00, 0.00, 0.00, 0.08),
        dark: (0.00, 0.00, 0.00, 0.32)
    )
    static let ember = Color(red: 0.83, green: 0.43, blue: 0.17)
    static let moss = Color(red: 0.29, green: 0.50, blue: 0.34)
    static let ocean = Color(red: 0.21, green: 0.46, blue: 0.62)
    static let stageTop = Color(red: 0.11, green: 0.08, blue: 0.07)
    static let stageBottom = Color(red: 0.04, green: 0.04, blue: 0.06)

    static var sceneGradient: LinearGradient {
        LinearGradient(
            colors: [chrome.opacity(0.96), surface.opacity(0.99)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var surfaceGradient: LinearGradient {
        LinearGradient(
            colors: [surfaceRaised, surface],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var consoleSurfaceGradient: LinearGradient {
        LinearGradient(
            colors: [consoleSurfaceRaised.opacity(0.96), consoleSurface],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

enum StudioType {
    static func interface(_ size: CGFloat, weight _: Font.Weight = .regular) -> Font {
        .custom("DINAlternate-Bold", size: size)
    }

    static func mono(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom(berkeleyName(for: weight), size: size)
    }

    static let panelTitle = mono(11, weight: .semibold)
    static let panelSubtitle = interface(12)
    static let label = mono(9.5, weight: .medium)
    static let labelStrong = mono(10, weight: .semibold)
    static let data = mono(12, weight: .medium)
    static let dataSmall = mono(10.5, weight: .regular)
    static let body = interface(13)
    static let bodySmall = interface(12)
    static let title = interface(15, weight: .semibold)

    private static func berkeleyName(for weight: Font.Weight) -> String {
        switch weight {
        case .black, .heavy, .bold:
            "BerkeleyMono-Bold"
        case .semibold:
            "BerkeleyMono-SemiBold"
        case .medium:
            "BerkeleyMono-Medium"
        case .light, .thin, .ultraLight:
            "BerkeleyMono-Light"
        default:
            "BerkeleyMono-Regular"
        }
    }

}

enum StudioPanelStyle: Equatable {
    case standard
    case console

    var cornerRadius: CGFloat {
        switch self {
        case .standard:
            6
        case .console:
            4
        }
    }

    var shadowRadius: CGFloat {
        switch self {
        case .standard:
            4
        case .console:
            2
        }
    }

    var shadowYOffset: CGFloat {
        switch self {
        case .standard:
            1
        case .console:
            1
        }
    }

    var padding: CGFloat {
        switch self {
        case .standard:
            12
        case .console:
            8
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
        StudioPalette.sceneGradient
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
        VStack(alignment: .leading, spacing: style == .console ? 10 : 12) {
            if title != nil || subtitle != nil {
                VStack(alignment: .leading, spacing: 4) {
                    if let title {
                        Text(style == .console ? title.uppercased() : title)
                            .font(style == .console ? StudioType.panelTitle : StudioType.title)
                            .tracking(style == .console ? 0.7 : 0)
                            .foregroundStyle(StudioPalette.ink)
                    }
                    if let subtitle {
                        Text(subtitle)
                            .font(StudioType.panelSubtitle)
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                }
                Rectangle()
                    .fill(StudioPalette.hairline)
                    .frame(height: 1)
            }
            content
        }
        .padding(style.padding)
        .background(
            RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                .fill(style == .console ? StudioPalette.consoleSurfaceGradient : StudioPalette.surfaceGradient)
        )
        .overlay(
            RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                .stroke(StudioPalette.hairline, lineWidth: 1)
        )
        .shadow(color: StudioPalette.panelShadow, radius: style.shadowRadius, y: style.shadowYOffset)
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
        .padding(.horizontal, 10)
        .padding(.vertical, style == .console ? 5 : 8)
        .background(
            RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                .fill(style == .console ? StudioPalette.consoleControl : StudioPalette.surfaceSoft)
        )
        .overlay {
            if style == .console {
                RoundedRectangle(cornerRadius: style.cornerRadius, style: .continuous)
                    .stroke(StudioPalette.hairline, lineWidth: 1)
            }
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
                    Button("Add To Compare", action: onAddToCompare)
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .tint(tone)
                }
                if showRemove, let onRemoveFromCompare {
                    Button("Remove", action: onRemoveFromCompare)
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
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(StudioPalette.surfaceRaised)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(tone.opacity(0.25), lineWidth: 1)
        )
        .shadow(color: StudioPalette.panelShadow.opacity(0.72), radius: 14, y: 8)
        .contentShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
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
        case .arena: return .purple
        case .system: return .gray
        }
    }
}

struct StudioCompareTrayView: View {
    let entries: [StudioCompareEntry]
    let onSelect: (StudioCompareEntry) -> Void
    let onRemove: (StudioCompareEntry) -> Void
    let onCompare: () -> Void
    let onClear: () -> Void

    var body: some View {
        StudioSurface(title: "Compare Tray", subtitle: "Dock discoveries here while you browse") {
            VStack(alignment: .leading, spacing: 14) {
                if entries.isEmpty {
                    Text("Add up to four creatures from the cockpit to build a comparison set.")
                        .font(StudioType.bodySmall)
                        .foregroundStyle(StudioPalette.mutedInk)
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

                                    Button("Remove") { onRemove(entry) }
                                        .buttonStyle(.bordered)
                                        .controlSize(.mini)
                                }
                                .padding(10)
                                .frame(width: 220, alignment: .leading)
                                .background(
                                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                                        .fill(StudioPalette.surfaceSoft)
                                )
                            }
                        }
                    }
                }

                HStack {
                    Button("Compare \(entries.count)") { onCompare() }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .disabled(entries.count < 2)
                        .keyboardShortcut("c", modifiers: [.command, .shift])
                    Button("Clear Tray") { onClear() }
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
