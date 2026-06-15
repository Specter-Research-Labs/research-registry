import SwiftUI
import LeniaCore
import LeniaVisuals

enum WorkerDetailSelection: Hashable {
    case home
    case arena
    case creature(StudioCompareEntry)

    static func == (lhs: WorkerDetailSelection, rhs: WorkerDetailSelection) -> Bool {
        switch (lhs, rhs) {
        case (.home, .home), (.arena, .arena):
            return true
        case (.creature(let left), .creature(let right)):
            return left.id == right.id
        default:
            return false
        }
    }

    func hash(into hasher: inout Hasher) {
        switch self {
        case .home:
            hasher.combine("home")
        case .arena:
            hasher.combine("arena")
        case .creature(let entry):
            hasher.combine(entry.id)
        }
    }
}

struct WorkerLayoutView: View {
    @EnvironmentObject var appState: AppState
    @State private var selection: WorkerDetailSelection = .home
    @State private var columnVisibility: NavigationSplitViewVisibility = .all
    @State private var showComparison = false

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            WorkerSidebarView(selection: $selection, showComparison: $showComparison)
        } detail: {
            detailView
                .background(
                    StudioSceneBackground()
                )
        }
        .navigationSplitViewStyle(.balanced)
        .safeAreaInset(edge: .bottom) {
            if !appState.compareTray.isEmpty {
                StudioCompareTrayView(
                    entries: appState.compareTray,
                    onSelect: { selection = .creature($0) },
                    onRemove: { appState.removeCompareEntry(id: $0.id) },
                    onCompare: { showComparison = true },
                    onClear: appState.clearCompareTray
                )
                .padding(.horizontal)
                .padding(.bottom, 10)
                .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .sheet(isPresented: $showComparison) {
            NavigationStack {
                ComparisonView(entries: appState.compareTray)
            }
            .frame(minWidth: 920, minHeight: 680)
        }
        .onChange(of: appState.arenaState?.status) { _, newStatus in
            if newStatus == .running {
                selection = .arena
            } else if newStatus == .ended, case .arena = selection {
                selection = .home
            }
        }
        .animation(.spring(response: 0.32, dampingFraction: 0.82), value: appState.compareTray)
    }

    @ViewBuilder
    private var detailView: some View {
        switch selection {
        case .home:
            WorkerHomeView(selection: $selection)
        case .arena:
            WorkerArenaView()
        case .creature(let entry):
            CreatureWorkbenchView(entry: entry)
        }
    }
}

struct WorkerSidebarView: View {
    @EnvironmentObject var appState: AppState
    @Binding var selection: WorkerDetailSelection
    @Binding var showComparison: Bool
    @State private var showConnect = false

    var body: some View {
        List {
            Section {
                ConnectionStatusRow(showConnect: $showConnect)
            }

            Section("Navigate") {
                Button {
                    selection = .home
                } label: {
                    Label("Cockpit", systemImage: "sparkles.tv")
                }
                .buttonStyle(.plain)

                Button {
                    if appState.compareTray.count >= 2 {
                        showComparison = true
                    }
                } label: {
                    HStack {
                        Label("Compare Tray", systemImage: "rectangle.split.3x1")
                        Spacer()
                        Text("\(appState.compareTray.count)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(appState.compareTray.count < 2)

                if let arena = appState.activeArenaConfig {
                    ArenaJoinRow(arena: arena, selection: $selection)
                }
            }

            if !appState.activeCampaigns.isEmpty {
                Section("Available Sweeps") {
                    ForEach(appState.activeCampaigns) { campaign in
                        CampaignJoinRow(campaign: campaign)
                    }
                }
            }

            if !appState.library.isEmpty {
                Section("Collection") {
                    ForEach(appState.library.prefix(10)) { savedCreature in
                        let entry = appState.studioEntry(for: savedCreature)
                        Button {
                            selection = .creature(entry)
                        } label: {
                            SidebarCreatureRow(
                                title: savedCreature.name,
                                subtitle: savedCreature.ownerId,
                                detail: String(format: "%.3f", savedCreature.score ?? savedCreature.metrics.massMean),
                                systemImage: savedCreature.metrics.isStable ? "checkmark.seal.fill" : "star.fill"
                            )
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            CreatureContextMenu(
                                seed: savedCreature.initialCondition.seed,
                                savedCreature: savedCreature,
                                onPreview: { selection = .creature(entry) },
                                onAddToComparison: { appState.addCompareEntry(entry) }
                            )
                        }
                    }
                }
            }

            if !appState.recentCreatures.isEmpty {
                Section("Recent") {
                    ForEach(appState.recentCreatures.prefix(8)) { creature in
                        let entry = liveEntry(for: creature)
                        Button {
                            selection = .creature(entry)
                        } label: {
                            SidebarCreatureRow(
                                title: "Seed \(creature.seed)",
                                subtitle: creature.sourceNode,
                                detail: String(format: "%.3f", creature.score),
                                systemImage: "sparkles"
                            )
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            CreatureContextMenu(
                                seed: creature.seed,
                                onPreview: { selection = .creature(entry) },
                                onAddToComparison: { appState.addCompareEntry(entry) }
                            )
                        }
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle("Worker")
        .sheet(isPresented: $showConnect) {
            ConnectView(node: nodeProxy)
        }
    }

    @EnvironmentObject private var nodeProxy: LeniaNode

    private func liveEntry(for creature: LeniaCreature) -> StudioCompareEntry {
        appState.studioEntry(for: creature)
    }
}

private struct SidebarCreatureRow: View {
    let title: String
    let subtitle: String
    let detail: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(StudioPalette.ember)
                .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text(detail)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }
}

struct WorkerHomeView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @Binding var selection: WorkerDetailSelection
    @State private var showArenaLobby = false

    private let exploreColumns = [
        GridItem(.adaptive(minimum: 220), spacing: 14)
    ]

    private var heroEntry: StudioCompareEntry? {
        appState.latestDiscovery
            ?? appState.library.first.map(appState.studioEntry)
            ?? appState.recentCreatures.first.map(appState.studioEntry)
    }

    private var exploreEntries: [StudioCompareEntry] {
        appState.filteredGlobalCreatures().prefix(12).map(makeLiveEntry)
    }

    private var localEntries: [StudioCompareEntry] {
        let savedEntries = appState.library.prefix(4).map(appState.studioEntry)
        let recentEntries = appState.topCreatures.prefix(4).map(appState.studioEntry)
        return Array(savedEntries + recentEntries)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                heroSurface

                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 16) {
                        campaignSurface
                        arenaSurface
                    }

                    VStack(spacing: 16) {
                        campaignSurface
                        arenaSurface
                    }
                }

                StudioSurface(title: "Cluster Explore", subtitle: "Shift lenses, search quickly, and dock anything interesting into the compare tray") {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack(spacing: 12) {
                            TextField("Search by seed or worker", text: $appState.workerSearchText)
                                .textFieldStyle(.roundedBorder)
                            Picker("Lens", selection: $appState.workerDiscoveryLens) {
                                ForEach(WorkerDiscoveryLens.allCases) { lens in
                                    Text(lens.rawValue).tag(lens)
                                }
                            }
                            .pickerStyle(.segmented)
                            .frame(maxWidth: 420)
                        }

                        if exploreEntries.isEmpty {
                            ContentUnavailableView(
                                "No discoveries yet",
                                systemImage: "sparkles.square.filled.on.square",
                                description: Text("As the cluster produces results, they will appear here.")
                            )
                            .frame(maxWidth: .infinity)
                        } else {
                            LazyVGrid(columns: exploreColumns, spacing: 14) {
                                ForEach(Array(exploreEntries.enumerated()), id: \.element.id) { index, entry in
                                    StudioCreatureCard(
                                        entry: entry,
                                        rank: appState.workerDiscoveryLens == .now ? nil : index + 1,
                                        tone: StudioPalette.ocean,
                                        onSelect: { selection = .creature(entry) },
                                        onAddToCompare: { appState.addCompareEntry(entry) }
                                    )
                                }
                            }
                        }
                    }
                }

                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 16) {
                        localDiscoveriesSurface
                        activityFeedSurface
                    }

                    VStack(spacing: 16) {
                        localDiscoveriesSurface
                        activityFeedSurface
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle("Worker Cockpit")
        .sheet(isPresented: $showArenaLobby) {
            if let arena = appState.activeArenaConfig {
                ArenaJoinSheet(arena: arena)
            }
        }
    }

    private var heroSurface: some View {
        StudioSurface(title: "Mission Control", subtitle: appState.clusterPulseText) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) {
                    heroPreviewPane
                        .frame(maxWidth: .infinity)
                    heroSummaryPane
                        .frame(width: 340, alignment: .topLeading)
                }

                VStack(alignment: .leading, spacing: 16) {
                    heroPreviewPane
                    heroSummaryPane
                }
            }
        }
    }

    private var campaignSurface: some View {
        StudioSurface(title: "Sweeps", subtitle: "What the cluster is currently searching") {
            VStack(alignment: .leading, spacing: 12) {
                if !appState.activeCampaigns.isEmpty {
                    Picker("Campaign", selection: Binding(
                        get: { appState.selectedCampaignId ?? appState.activeCampaigns.first?.id ?? UUID() },
                        set: { appState.selectedCampaignId = $0 }
                    )) {
                        ForEach(appState.activeCampaigns) { campaign in
                            Text(campaign.name).tag(campaign.id)
                        }
                    }
                    .pickerStyle(.menu)
                }

                if let campaign = appState.selectedCampaignSummary {
                    ProgressView(value: Double(campaign.processedSeeds), total: Double(max(campaign.totalSeeds, 1)))
                        .tint(StudioPalette.ocean)
                    StudioKeyValueRow(label: "Seeds", value: "\(campaign.processedSeeds) / \(campaign.totalSeeds)")
                    StudioKeyValueRow(label: "Jobs", value: "\(campaign.completedJobs) / \(campaign.totalJobs)")
                    StudioKeyValueRow(label: "Workers", value: "\(campaign.joinedWorkers.count)")
                    StudioKeyValueRow(label: "Status", value: campaign.isRunning ? "Running" : "Complete")

                    if !campaign.joinedWorkers.contains(appState.localWorkerId), campaign.isRunning {
                        Button("Join Sweep") {
                            Task { await node.joinCampaign(campaignId: campaign.id) }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                } else {
                    Text("No active campaigns right now")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity)
    }

    private var arenaSurface: some View {
        StudioSurface(title: "Arena", subtitle: appState.activeArenaSummaryText) {
            VStack(alignment: .leading, spacing: 12) {
                if let arena = appState.activeArenaConfig {
                    StudioKeyValueRow(label: "Grid", value: "\(arena.size)x\(arena.size)")
                    StudioKeyValueRow(label: "Capacity", value: "\(appState.arenaState?.participants.count ?? 0) / \(arena.maxPlayers)")
                    StudioKeyValueRow(label: "Status", value: appState.arenaState?.status.rawValue.capitalized ?? "Lobby")

                    HStack {
                        Button(appState.arenaState?.status == .running ? "Open Arena" : "Open Lobby") {
                            if appState.arenaState?.status == .running {
                                selection = .arena
                            } else {
                                showArenaLobby = true
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut("a", modifiers: .command)

                        if appState.arenaState?.participants.contains(appState.localWorkerId) == true {
                            Label("Ready", systemImage: "checkmark.seal.fill")
                                .font(.caption)
                                .foregroundStyle(StudioPalette.moss)
                        }
                    }
                } else {
                    Text("No arena is currently available")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private var heroPreviewPane: some View {
        if let heroEntry {
            CockpitLivePreview(entry: heroEntry)
        } else {
            ContentUnavailableView(
                "Waiting for a discovery",
                systemImage: "sparkles",
                description: Text("The first stable or high-scoring creature will anchor this cockpit.")
            )
            .frame(maxWidth: .infinity, minHeight: 320)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
        }
    }

    private var heroSummaryPane: some View {
        VStack(alignment: .leading, spacing: 14) {
            ClusterPulseStrip(
                snapshot: appState.clusterSnapshot,
                workers: appState.connectedWorkers,
                campaigns: appState.activeCampaigns,
                seedsProcessed: appState.seedsProcessed,
                rate: appState.currentRate
            )

            if let heroEntry {
                VStack(alignment: .leading, spacing: 8) {
                    Text(heroEntry.name)
                        .font(.system(.title2, design: .serif, weight: .semibold))
                        .foregroundStyle(StudioPalette.ink)
                    Text(heroEntry.subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    HStack(spacing: 10) {
                        StudioMetricPill(label: "Score", value: String(format: "%.3f", heroEntry.savedCreature?.score ?? heroEntry.creature.score), accent: StudioPalette.ember)
                        if let metrics = heroEntry.savedCreature?.metrics ?? heroEntry.metrics {
                            StudioMetricPill(label: "Vel", value: String(format: "%.3f", metrics.centerVelocity), accent: StudioPalette.ocean)
                        }
                    }
                }

                HStack {
                    Button("Open Inspector") {
                        selection = .creature(heroEntry)
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Add To Compare") {
                        appState.addCompareEntry(heroEntry)
                    }
                    .buttonStyle(.bordered)
                }
            } else {
                Text("Join a sweep or wait for local discoveries to start filling the cockpit.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                Text("Connected Peers")
                    .font(.headline)
                    .foregroundStyle(StudioPalette.ink)
                if appState.connectedWorkers.isEmpty {
                    Text("No workers online yet")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(appState.connectedWorkers.prefix(4), id: \.workerId) { worker in
                        HStack {
                            Circle()
                                .fill(worker.isAvailable ? StudioPalette.moss : StudioPalette.ember)
                                .frame(width: 8, height: 8)
                            Text(worker.workerId)
                                .font(.caption)
                            Spacer()
                            Text("\(worker.totalSeedsProcessed)")
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }

    private var localDiscoveriesSurface: some View {
        StudioSurface(title: "Local Discoveries", subtitle: "Your best and newest signals") {
            if localEntries.isEmpty {
                Text("No local discoveries yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                LazyVGrid(columns: exploreColumns, spacing: 14) {
                    ForEach(localEntries) { entry in
                        StudioCreatureCard(
                            entry: entry,
                            tone: StudioPalette.ember,
                            onSelect: { selection = .creature(entry) },
                            onAddToCompare: { appState.addCompareEntry(entry) }
                        )
                    }
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var activityFeedSurface: some View {
        StudioSurface(title: "Activity Feed", subtitle: "Recent motion across your worker and the cluster") {
            WorkerActivityFeedView(items: Array(appState.activityFeed.prefix(8)))
        }
        .frame(maxWidth: .infinity)
    }

    private func makeLiveEntry(for creature: LeniaCreature) -> StudioCompareEntry {
        appState.studioEntry(for: creature)
    }
}

private struct CockpitLivePreview: View {
    let entry: StudioCompareEntry
    @StateObject private var model = LiveSimulationModel()
    @State private var renderMode: LeniaRenderMode = .smoothMagma

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                LinearGradient(
                    colors: [StudioPalette.stageTop, StudioPalette.stageBottom],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                if let frame = model.displayFrame {
                    LeniaLabStageView(
                        frame: frame,
                        renderMode: renderMode,
                        zoom: 1.0,
                        offset: .zero,
                        onTransformChange: { _ in },
                        onPrimaryPoint: { _ in },
                        onSecondaryPoint: { _ in },
                        onHoverPointChange: { _ in },
                        onBrushRadiusDelta: nil
                    )
                    .padding(14)
                } else {
                    ProgressView()
                        .controlSize(.large)
                        .tint(.white)
                }
            }
            .frame(minHeight: 360)

            HStack {
                RenderModePicker(renderMode: $renderMode)
                Spacer()
                Text(model.stats)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(.thinMaterial)
        }
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(StudioPalette.hairline, lineWidth: 1)
        )
        .onAppear {
            model.start(
                creature: entry.creature,
                savedCreature: entry.savedCreature,
                replaySource: entry.replayReference
            )
        }
        .onChange(of: entry.id) { _, _ in
            model.restart(
                creature: entry.creature,
                savedCreature: entry.savedCreature,
                replaySource: entry.replayReference
            )
        }
        .onDisappear {
            model.stop()
        }
    }
}

struct ArenaJoinRow: View {
    @EnvironmentObject var appState: AppState
    let arena: ArenaConfig
    @Binding var selection: WorkerDetailSelection
    @State private var showJoinSheet = false

    private var isRunning: Bool {
        appState.arenaState?.status == .running
    }

    private var hasJoined: Bool {
        appState.arenaState?.participants.contains(appState.localWorkerId) ?? false
    }

    var body: some View {
        Button {
            if isRunning && hasJoined {
                selection = .arena
            } else {
                showJoinSheet = true
            }
        } label: {
            HStack {
                Image(systemName: "person.3.sequence.fill")
                    .foregroundStyle(isRunning ? StudioPalette.moss : StudioPalette.ember)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Arena \(arena.id.uuidString.prefix(4))")
                        .font(.caption.bold())
                    Text(isRunning ? "Running" : "Lobby")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(hasJoined ? (isRunning ? "View" : "Ready") : "Join")
                    .font(.caption)
                    .foregroundStyle(hasJoined ? StudioPalette.moss : StudioPalette.ocean)
            }
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showJoinSheet) {
            ArenaJoinSheet(arena: arena)
        }
    }
}

struct ArenaJoinSheet: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @Environment(\.dismiss) var dismiss
    let arena: ArenaConfig
    @State private var selectedCreatureId: UUID?
    @State private var enableQualification = true

    private let columns = [GridItem(.adaptive(minimum: 180), spacing: 12)]

    private var selectedCreature: SavedCreature? {
        guard let selectedCreatureId else { return nil }
        return appState.library.first(where: { $0.id == selectedCreatureId })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Arena Lobby")
                .font(.system(.title2, design: .serif, weight: .semibold))

            Text("Pick one of your collected creatures, optionally qualify it, and watch the lobby fill before the simulation starts.")
                .font(.caption)
                .foregroundStyle(.secondary)

            if appState.library.isEmpty {
                ContentUnavailableView(
                    "No Creatures",
                    systemImage: "tray",
                    description: Text("You need at least one collected creature before joining an arena.")
                )
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(appState.library) { creature in
                            let entry = appState.studioEntry(for: creature)
                            StudioCreatureCard(
                                entry: entry,
                                tone: selectedCreatureId == creature.id ? StudioPalette.moss : StudioPalette.ember,
                                onSelect: { selectedCreatureId = creature.id }
                            )
                        }
                    }
                    .padding(.vertical, 4)
                }
                .frame(minHeight: 280)

                Toggle("Run qualification before joining", isOn: $enableQualification)
                    .font(.caption)

                StudioSurface(title: "Lobby Status", subtitle: "\(appState.arenaState?.participants.count ?? 0) / \(arena.maxPlayers) ready") {
                    VStack(alignment: .leading, spacing: 8) {
                        if let participants = appState.arenaState?.participants, !participants.isEmpty {
                            ForEach(participants, id: \.self) { participant in
                                HStack {
                                    Circle()
                                        .fill(StudioPalette.moss)
                                        .frame(width: 8, height: 8)
                                    Text(participant)
                                        .font(.caption)
                                }
                            }
                        } else {
                            Text("No participants yet")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        let remaining = max(arena.maxPlayers - (appState.arenaState?.participants.count ?? 0), 0)
                        Text(remaining == 0 ? "Arena should start shortly." : "\(remaining) more player(s) needed.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            HStack {
                Button("Cancel") {
                    dismiss()
                }
                .buttonStyle(.bordered)

                Button("Join Arena") {
                    if let selectedCreature {
                        Task {
                            await node.joinArena(with: selectedCreature, qualify: enableQualification)
                            dismiss()
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(selectedCreature == nil)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(minWidth: 760, minHeight: 640)
    }
}
