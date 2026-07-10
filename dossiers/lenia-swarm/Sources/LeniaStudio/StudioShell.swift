import SwiftUI

enum StudioCompareTrayReadiness: Equatable {
    case empty
    case needsOneMore
    case ready
}

func studioCompareTrayReadiness(for count: Int) -> StudioCompareTrayReadiness {
    switch max(0, count) {
    case 0: .empty
    case 1: .needsOneMore
    default: .ready
    }
}

struct StudioCompareDestination: View {
    @EnvironmentObject private var appState: AppState
    @State private var showComparison = false
    let onCompose: () -> Void

    private var readiness: StudioCompareTrayReadiness {
        studioCompareTrayReadiness(for: appState.compareTray.count)
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if readiness == .empty {
                    ContentUnavailableView(
                        "No specimens selected",
                        systemImage: "rectangle.split.2x1"
                    )
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 24) {
                            HStack {
                                Text("Selection")
                                    .font(StudioType.panelTitle)
                                    .foregroundStyle(StudioPalette.mutedInk)

                                Spacer()

                                Button(role: .destructive) {
                                    appState.clearCompareTray()
                                } label: {
                                    Image(systemName: "trash")
                                }
                                .buttonStyle(.borderless)
                                .help("Clear comparison set")
                                .accessibilityLabel("Clear comparison set")
                            }

                            compareTray

                            if readiness == .needsOneMore {
                                Label("One more specimen required", systemImage: "plus.circle")
                                    .font(StudioType.bodySmall)
                                    .foregroundStyle(StudioPalette.mutedInk)
                                    .accessibilityLabel("One more specimen is required to compare")
                            } else {
                                compareActions
                            }
                        }
                        .frame(maxWidth: 960, alignment: .leading)
                        .padding(24)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(StudioSceneBackground())
            .navigationTitle("Compare")
        }
        .sheet(isPresented: $showComparison) {
            NavigationStack {
                ComparisonView(entries: appState.compareTray)
            }
            .frame(minWidth: 820, minHeight: 620)
        }
    }

    private var compareTray: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 12) {
                ForEach(Array(appState.compareTray.enumerated()), id: \.element.id) { index, entry in
                    VStack(alignment: .leading, spacing: 10) {
                        ZStack(alignment: .topTrailing) {
                            CreatureThumbnailView(creature: entry.creature, size: 120)

                            Button {
                                appState.removeCompareEntry(id: entry.id)
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .symbolRenderingMode(.palette)
                                    .foregroundStyle(StudioPalette.ink, StudioPalette.surfaceRaised)
                            }
                            .buttonStyle(.plain)
                            .help("Remove \(entry.name)")
                            .accessibilityLabel("Remove \(entry.name)")
                            .padding(6)
                        }

                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 6) {
                                Text(entry.name)
                                    .font(StudioType.panelTitle)
                                    .foregroundStyle(StudioPalette.ink)
                                    .lineLimit(1)

                                if index == 0 {
                                    Text("BASELINE")
                                        .font(StudioType.label)
                                        .foregroundStyle(StudioPalette.ember)
                                }
                            }

                            Text(String(format: "Score %.3f", entry.savedCreature?.score ?? entry.creature.score))
                                .font(StudioType.dataSmall)
                                .foregroundStyle(StudioPalette.mutedInk)
                        }
                    }
                    .padding(10)
                    .frame(width: 148, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(StudioPalette.surface)
                    )
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(index == 0 ? "Baseline, \(entry.name)" : entry.name)
                }
            }
            .padding(.vertical, 2)
        }
        .scrollIndicators(.hidden)
    }

    private var compareActions: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                comparisonButton
                composeButton
            }
            VStack(alignment: .leading, spacing: 10) {
                comparisonButton
                composeButton
            }
        }
        .controlSize(.regular)
    }

    private var comparisonButton: some View {
        Button {
            showComparison = true
        } label: {
            Label("Open Comparison", systemImage: "rectangle.split.2x1")
        }
        .buttonStyle(.borderedProminent)
        .keyboardShortcut(.defaultAction)
        .help("Open synchronized comparison")
    }

    private var composeButton: some View {
        Button {
            onCompose()
        } label: {
            Label("Compose in Lab", systemImage: "square.3.layers.3d")
        }
        .buttonStyle(.bordered)
        .help("Move this set to the Lab composition workspace")
    }
}

struct StudioRunsDestination: View {
    @EnvironmentObject private var appState: AppState
    @Binding var destination: StudioDestination
    let onConnect: () -> Void

    @ViewBuilder
    var body: some View {
        switch appState.connectionState {
        case .connected(role: .host):
            HostLayoutView()
        case .connected(role: .worker):
            WorkerLayoutView()
        case .connected(role: .compendium):
            StudioRunsStatusView(
                title: "Library ready",
                systemImage: "square.grid.2x2",
                detail: "Offline results are available in Library.",
                tone: StudioPalette.ocean,
                actionTitle: "Open Library",
                action: { destination = .library }
            )
        case .connecting:
            StudioRunsStatusView(
                title: "Connecting",
                systemImage: "network",
                detail: "Starting the cluster session.",
                isLoading: true
            )
        case .error(let message):
            StudioRunsStatusView(
                title: "Connection failed",
                systemImage: "exclamationmark.triangle",
                detail: message,
                tone: Color(nsColor: .systemRed),
                actionTitle: "Review Connection",
                action: onConnect
            )
        case .disconnected:
            StudioRunsStatusView(
                title: "No active run",
                systemImage: "point.3.connected.trianglepath.dotted",
                detail: "Cluster is offline.",
                actionTitle: "Connect",
                action: onConnect
            )
        }
    }
}

private struct StudioRunsStatusView: View {
    let title: String
    let systemImage: String
    let detail: String
    var tone = StudioPalette.mutedInk
    var isLoading = false
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 12) {
                    if isLoading {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: systemImage)
                            .font(.title3)
                            .foregroundStyle(tone)
                            .frame(width: 24)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text(title)
                            .font(StudioType.title)
                            .foregroundStyle(StudioPalette.ink)
                        Text(detail)
                            .font(StudioType.bodySmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                }

                if let actionTitle, let action {
                    Button(actionTitle, action: action)
                        .buttonStyle(.borderedProminent)
                        .controlSize(.regular)
                }
            }
            .padding(24)
            .frame(maxWidth: 520, alignment: .leading)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            .navigationTitle("Runs")
        }
        .background(StudioSceneBackground())
    }
}

struct StudioClusterControl: View {
    let connectionState: ConnectionState
    @Binding var destination: StudioDestination
    let onConnect: () -> Void
    let onStop: () -> Void

    var body: some View {
        Menu {
            switch connectionState {
            case .disconnected:
                Button("Connect...", action: onConnect)
            case .connecting:
                Button("Connecting...") {}
                    .disabled(true)
            case .connected(role: .host):
                Button("Open Runs") { destination = .runs }
                Divider()
                Button("Stop Host", role: .destructive, action: onStop)
            case .connected(role: .worker):
                Button("Open Runs") { destination = .runs }
                Divider()
                Button("Leave Session", role: .destructive, action: onStop)
            case .connected(role: .compendium):
                Button("Open Library") { destination = .library }
                Divider()
                Button("Close Library Session", role: .destructive, action: onStop)
            case .error:
                Button("Review Connection...", action: onConnect)
            }
        } label: {
            HStack(spacing: 7) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 7, height: 7)
                ViewThatFits(in: .horizontal) {
                    Text(statusTitle)
                        .font(StudioType.bodySmall)
                    Image(systemName: statusSystemImage)
                }
            }
        }
        .menuStyle(.borderlessButton)
        .help(accessibilitySummary)
        .accessibilityLabel("Cluster")
        .accessibilityValue(accessibilitySummary)
    }

    private var statusTitle: String {
        switch connectionState {
        case .disconnected: "Offline"
        case .connecting: "Connecting"
        case .connected(let role): role.rawValue
        case .error: "Connection Issue"
        }
    }

    private var statusSystemImage: String {
        switch connectionState {
        case .disconnected: "network.slash"
        case .connecting: "network"
        case .connected(role: .host): "server.rack"
        case .connected(role: .worker): "desktopcomputer"
        case .connected(role: .compendium): "square.grid.2x2"
        case .error: "exclamationmark.triangle"
        }
    }

    private var statusColor: Color {
        switch connectionState {
        case .disconnected: StudioPalette.mutedInk
        case .connecting: StudioPalette.ember
        case .connected: StudioPalette.moss
        case .error: Color(nsColor: .systemRed)
        }
    }

    private var accessibilitySummary: String {
        switch connectionState {
        case .disconnected:
            "Offline. Open cluster connection options."
        case .connecting:
            "Connecting to the cluster."
        case .connected(let role):
            "Connected as \(role.rawValue). Open cluster options."
        case .error(let message):
            "Connection issue: \(message)"
        }
    }
}
