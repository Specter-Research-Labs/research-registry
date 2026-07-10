import SwiftUI
import LeniaCore
import LeniaVisuals

struct MainLayoutView: View {
    @EnvironmentObject private var appState: AppState
    @EnvironmentObject private var node: LeniaNode
    @EnvironmentObject private var commandCenter: StudioCommandCenter
    @State private var selection: StudioDestination
    @State private var showConnect = false

    init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        _selection = State(initialValue: studioInitialDestination(environment: environment))
    }

    var body: some View {
        TabView(selection: $selection) {
            Tab(value: StudioDestination.lab) {
                NavigationStack {
                    LeniaLabView()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } label: {
                Label(StudioDestination.lab.title, systemImage: StudioDestination.lab.systemImage)
                    .accessibilityHint(StudioDestination.lab.accessibilityHint)
                    .help("Lab, Command 1")
            }

            Tab(value: StudioDestination.library) {
                NavigationStack {
                    CompendiumLayoutView()
                        .navigationTitle("Library")
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } label: {
                Label(StudioDestination.library.title, systemImage: StudioDestination.library.systemImage)
                    .accessibilityHint(StudioDestination.library.accessibilityHint)
                    .help("Library, Command 2")
            }

            Tab(value: StudioDestination.compare) {
                StudioCompareDestination(onCompose: { selection = .lab })
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } label: {
                Label(StudioDestination.compare.title, systemImage: StudioDestination.compare.systemImage)
                    .accessibilityHint(StudioDestination.compare.accessibilityHint)
                    .help("Compare, Command 3")
            }
            .badge(appState.compareTray.count)

            Tab(value: StudioDestination.runs) {
                StudioRunsDestination(destination: $selection, onConnect: { showConnect = true })
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } label: {
                Label(StudioDestination.runs.title, systemImage: StudioDestination.runs.systemImage)
                    .accessibilityHint(StudioDestination.runs.accessibilityHint)
                    .help("Runs, Command 4")
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(StudioPalette.chrome)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                StudioClusterControl(
                    connectionState: appState.connectionState,
                    destination: $selection,
                    onConnect: { showConnect = true },
                    onStop: stopCluster
                )
                .controlSize(.small)
            }
        }
        .sheet(isPresented: $showConnect) {
            ConnectView(node: node)
        }
        .onChange(of: appState.connectionState) { _, newValue in
            selection = studioDestinationAfterConnectionChange(
                current: selection,
                connectionState: newValue
            )
        }
        .onChange(of: commandCenter.latestEvent) { _, event in
            guard let event else { return }
            selection = studioDestination(current: selection, applying: event.command)
            if event.command == .openClusterConnection {
                showConnect = true
            }
        }
    }

    private func stopCluster() {
        if case .connected(role: .compendium) = appState.connectionState {
            appState.connectionState = .disconnected
        } else {
            node.stop()
        }
    }
}

// MARK: - Host Layout (Controller Admin)

struct HostLayoutView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @State private var selectedArenaId: UUID?
    @State private var selectedCreature: SavedCreature?
    @State private var selectedCampaignId: UUID?
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            HostSidebarView(
                selectedArenaId: $selectedArenaId,
                selectedCreature: $selectedCreature,
                selectedCampaignId: $selectedCampaignId
            )
        } detail: {
            if let creature = selectedCreature {
                CreatureDetailView(creature: creature)
            } else if let arenaId = selectedArenaId,
               let arena = appState.availableArenas.first(where: { $0.id == arenaId }) {
                ArenaDetailView(arena: arena)
            } else if let campaignId = selectedCampaignId,
               let campaign = appState.activeCampaigns.first(where: { $0.id == campaignId }) {
                CampaignDetailView(campaign: campaign)
            } else {
                HostDashboardView()
            }
        }
        .navigationSplitViewStyle(.balanced)
        .background(StudioSceneBackground())
    }
}

struct HostSidebarView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @Binding var selectedArenaId: UUID?
    @Binding var selectedCreature: SavedCreature?
    @Binding var selectedCampaignId: UUID?
    @State private var showConnect = false
    @State private var showCreateArena = false
    @State private var showCreateSweep = false
    @State private var expandedWorkers: Set<String> = []
    @State private var previewCreature: LeniaCreature?

    private func creaturesForWorker(_ workerId: String) -> [SavedCreature] {
        appState.library.filter { $0.ownerId == workerId }
    }

    var body: some View {
        List {
            Section {
                ConnectionStatusRow(showConnect: $showConnect)
            }

            Section("Workers (\(appState.connectedWorkers.count))") {
                if appState.connectedWorkers.isEmpty {
                    Label("Waiting for workers", systemImage: "desktopcomputer")
                        .foregroundStyle(StudioPalette.mutedInk)
                        .font(StudioType.bodySmall)
                } else {
                    ForEach(appState.connectedWorkers, id: \.workerId) { worker in
                        let creatures = creaturesForWorker(worker.workerId)
                        DisclosureGroup(
                            isExpanded: Binding(
                                get: { expandedWorkers.contains(worker.workerId) },
                                set: { isExpanded in
                                    if isExpanded {
                                        expandedWorkers.insert(worker.workerId)
                                    } else {
                                        expandedWorkers.remove(worker.workerId)
                                    }
                                }
                            )
                        ) {
                            if creatures.isEmpty {
                                Text("No creatures yet")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                    .padding(.leading, 8)
                            } else {
                                ForEach(creatures) { creature in
                                    Button {
                                        selectedCreature = creature
                                        selectedArenaId = nil
                                        selectedCampaignId = nil
                                    } label: {
                                        HStack {
                                            Image(systemName: "star.fill")
                                                .foregroundStyle(StudioPalette.ember)
                                                .font(.caption2)
                                            Text(creature.name)
                                                .font(.caption2)
                                            Spacer()
                                            Text(String(format: "G:%.1f", creature.metrics.gyration))
                                                .font(StudioType.dataSmall)
                                                .foregroundStyle(StudioPalette.mutedInk)
                                        }
                                        .padding(.leading, 8)
                                        .background(selectedCreature?.id == creature.id ? StudioPalette.surfaceSoft : Color.clear)
                                        .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                                    }
                                    .buttonStyle(.plain)
                                    .contextMenu {
                                        CreatureContextMenu(
                                            seed: creature.initialCondition.seed,
                                            savedCreature: creature,
                                            onPreview: { previewCreature = creature.toLeniaCreature() }
                                        )
                                    }
                                }
                            }
                        } label: {
                            HStack {
                                Circle()
                                    .fill(worker.isAvailable ? StudioPalette.moss : StudioPalette.ember)
                                    .frame(width: 8, height: 8)
                                Text(worker.workerId)
                                    .font(.caption)
                                Spacer()
                                Text("\(creatures.count)")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            .accessibilityElement(children: .combine)
                            .accessibilityLabel(
                                "\(worker.workerId), \(worker.isAvailable ? "ready" : "busy"), \(creatures.count) creatures"
                            )
                        }
                    }
                }
            }

            Section("Sweeps") {
                Button {
                    showCreateSweep = true
                } label: {
                    Label("New Sweep", systemImage: "plus.circle")
                }
                .help("Create a parameter sweep")

                if appState.activeCampaigns.isEmpty {
                    Label("No active sweeps", systemImage: "waveform.path.ecg")
                        .foregroundStyle(StudioPalette.mutedInk)
                        .font(StudioType.bodySmall)
                } else {
                    ForEach(appState.activeCampaigns) { campaign in
                        Button {
                            selectedCampaignId = campaign.id
                            selectedArenaId = nil
                            selectedCreature = nil
                        } label: {
                            CampaignRow(campaign: campaign)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            Section("Arenas") {
                Button {
                    showCreateArena = true
                } label: {
                    Label("New Arena", systemImage: "plus.circle")
                }
                .help("Create an arena")

                if appState.availableArenas.isEmpty {
                    Label("No arenas", systemImage: "square.dashed")
                        .foregroundStyle(StudioPalette.mutedInk)
                        .font(StudioType.bodySmall)
                } else {
                    ForEach(appState.availableArenas, id: \.id) { arena in
                        Button {
                            selectedArenaId = arena.id
                            selectedCreature = nil
                            selectedCampaignId = nil
                        } label: {
                            ArenaRow(arena: arena, state: appState.arenaStates[arena.id])
                                .background(selectedArenaId == arena.id ? StudioPalette.surfaceSoft : Color.clear)
                                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .background(StudioPalette.chromeMuted)
        .navigationSplitViewColumnWidth(min: 220, ideal: 260, max: 340)
        .navigationTitle("Runs")
        .sheet(isPresented: $showConnect) {
            ConnectView(node: node)
        }
        .sheet(isPresented: $showCreateArena) {
            CreateArenaSheet()
        }
        .sheet(isPresented: $showCreateSweep) {
            CreateSweepSheet()
        }
        .sheet(item: $previewCreature) { creature in
            NavigationStack {
                LeniaLiveView(creature: creature)
            }
            .frame(minWidth: 700, minHeight: 600)
        }
        .onChange(of: selectedArenaId) { _, newValue in
            if newValue != nil {
                selectedCreature = nil
                selectedCampaignId = nil
            }
        }
    }
}

struct CampaignRow: View {
    let campaign: CampaignStatus

    var body: some View {
        HStack {
            if campaign.isRunning {
                ProgressView()
                    .controlSize(.small)
            } else if campaign.processedSeeds >= campaign.totalSeeds {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(StudioPalette.moss)
            } else {
                Image(systemName: "clock.fill")
                    .foregroundStyle(StudioPalette.ember)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(campaign.name)
                    .font(.caption.bold())
                Text("\(campaign.processedSeeds)/\(campaign.totalSeeds) seeds")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.vertical, 2)
    }
}

struct CampaignJoinRow: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    let campaign: CampaignStatus

    private var hasJoined: Bool {
        campaign.joinedWorkers.contains(appState.localWorkerId)
    }

    var body: some View {
        HStack {
            if hasJoined && campaign.isRunning {
                ProgressView()
                    .controlSize(.small)
            } else if campaign.processedSeeds >= campaign.totalSeeds {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(StudioPalette.moss)
            } else if campaign.isRunning {
                Image(systemName: "person.2.fill")
                    .foregroundStyle(StudioPalette.ember)
            } else {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(StudioPalette.ocean)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(campaign.name)
                    .font(.caption.bold())
                HStack(spacing: 4) {
                    Text("\(campaign.processedSeeds)/\(campaign.totalSeeds)")
                    Text("(\(campaign.joinedWorkers.count) workers)")
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
            }
            Spacer()
            if hasJoined {
                if campaign.isRunning {
                    Text("Running")
                        .font(.caption2)
                        .foregroundStyle(StudioPalette.ember)
                } else {
                    Text("Done")
                        .font(.caption2)
                        .foregroundStyle(StudioPalette.moss)
                }
            } else if campaign.processedSeeds < campaign.totalSeeds {
                Button("Join") {
                    Task {
                        await node.joinCampaign(campaignId: campaign.id)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            }
        }
        .padding(.vertical, 4)
    }
}

struct CampaignDetailView: View {
    let campaign: CampaignStatus

    var body: some View {
        StudioDetailScroll {
            Text(campaign.name)
                .font(.title2)
                .fontWeight(.semibold)

            GroupBox("Progress") {
                VStack(alignment: .leading, spacing: 12) {
                    ProgressView(value: Double(campaign.processedSeeds), total: Double(campaign.totalSeeds))

                    HStack {
                        Text("Seeds:")
                        Spacer()
                        Text("\(campaign.processedSeeds) / \(campaign.totalSeeds)")
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Jobs:")
                        Spacer()
                        Text("\(campaign.completedJobs) / \(campaign.totalJobs)")
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Status:")
                        Spacer()
                        Text(campaign.isRunning ? "Running" : "Complete")
                            .foregroundStyle(campaign.isRunning ? .orange : .green)
                    }
                }
            }
            .frame(maxWidth: 460)
        }
        .navigationTitle(campaign.name)
    }
}

struct CreateSweepSheet: View {
    @EnvironmentObject var node: LeniaNode
    @Environment(\.dismiss) var dismiss
    @State private var sweepName = "Batch 1"
    @State private var seedCount = 100
    @State private var steps = 200
    @State private var gridSize = 128

    var body: some View {
        VStack(spacing: 20) {
            Text("Create Parameter Sweep")
                .font(.headline)

            Form {
                TextField("Name", text: $sweepName)
                Stepper("Seeds: \(seedCount)", value: $seedCount, in: 10...10000, step: 10)
                Stepper("Steps: \(steps)", value: $steps, in: 100...1000, step: 50)
                Picker("Grid Size", selection: $gridSize) {
                    Text("64x64").tag(64)
                    Text("128x128").tag(128)
                    Text("256x256").tag(256)
                }
            }
            .formStyle(.grouped)

            HStack {
                Button("Cancel") {
                    dismiss()
                }
                .buttonStyle(.bordered)

                Button("Start Sweep") {
                    Task {
                        await node.startSweep(name: sweepName, totalSeeds: seedCount, steps: steps, gridSize: gridSize)
                        dismiss()
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .frame(width: 320, height: 320)
    }
}

struct CreatureDetailView: View {
    @EnvironmentObject var node: LeniaNode
    let creature: SavedCreature
    @State private var exportStatus: String?
    @State private var isExporting = false

    var body: some View {
        StudioDetailScroll {
            Text(creature.name)
                .font(.title2)
                .fontWeight(.semibold)

            GroupBox("Metrics") {
                VStack(alignment: .leading, spacing: 8) {
                    MetricRow(label: "Gyration", value: String(format: "%.2f", creature.metrics.gyration))
                    MetricRow(label: "Velocity", value: String(format: "%.3f", creature.metrics.centerVelocity))
                    MetricRow(label: "Mass Mean", value: String(format: "%.2f", creature.metrics.massMean))
                    MetricRow(label: "Mass Std", value: String(format: "%.3f", creature.metrics.massStd))
                    MetricRow(label: "Stable", value: creature.metrics.isStable ? "Yes" : "No")
                }
            }
            .frame(maxWidth: 520)

            GroupBox("Score") {
                ScoreBreakdownView(creature: creature)
            }
            .frame(maxWidth: 520)

            GroupBox("Genotype") {
                VStack(alignment: .leading, spacing: 6) {
                    Text("R: \(String(format: "%.1f", creature.genotype.R))")
                    Text("r: \(creature.genotype.r.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                    Text("m: \(creature.genotype.m.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                    Text("s: \(creature.genotype.s.map { String(format: "%.3f", $0) }.joined(separator: ", "))")
                    Text("h: \(creature.genotype.h.map { String(format: "%.2f", $0) }.joined(separator: ", "))")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .frame(maxWidth: 520)

            Text("Owner: \(creature.ownerId)")
                .font(.caption)
                .foregroundStyle(.tertiary)

            VStack(spacing: 8) {
                Button(isExporting ? "Exporting..." : "Export Config") {
                    guard !isExporting else { return }
                    isExporting = true
                    exportStatus = nil
                    Task {
                        let path = await node.exportCreature(creature)
                        if let path = path {
                            exportStatus = "Exported to \(path)"
                        } else {
                            exportStatus = "Export failed"
                        }
                        isExporting = false
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isExporting)

                if let exportStatus = exportStatus {
                    Text(exportStatus)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
            }
        }
        .navigationTitle(creature.name)
    }

}

struct MetricRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
            Spacer()
            Text(value)
                .foregroundStyle(.secondary)
        }
    }
}

struct CreateArenaSheet: View {
    @EnvironmentObject var node: LeniaNode
    @Environment(\.dismiss) var dismiss
    @State private var gridSize: Int = 256
    @State private var maxPlayers: Int = 2

    let gridSizes = [128, 256, 512]
    let playerCounts = [2, 3, 4]

    var body: some View {
        VStack(spacing: 20) {
            Text("Create Arena")
                .font(.headline)

            Form {
                Picker("Grid Size", selection: $gridSize) {
                    ForEach(gridSizes, id: \.self) { size in
                        Text("\(size)x\(size)").tag(size)
                    }
                }

                Picker("Max Players", selection: $maxPlayers) {
                    ForEach(playerCounts, id: \.self) { count in
                        Text("\(count) players").tag(count)
                    }
                }

                Text("Arena will auto-start when all \(maxPlayers) players have joined.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .formStyle(.grouped)

            HStack {
                Button("Cancel") {
                    dismiss()
                }
                .buttonStyle(.bordered)

                Button("Create") {
                    Task {
                        await node.createArena(size: gridSize, maxPlayers: maxPlayers)
                        dismiss()
                    }
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .frame(width: 300, height: 280)
    }
}

struct ArenaRow: View {
    let arena: ArenaConfig
    let state: ArenaState?

    var body: some View {
        HStack {
            Image(systemName: "gamecontroller")
                .foregroundStyle(statusColor)
            VStack(alignment: .leading, spacing: 2) {
                Text("Arena \(arena.id.uuidString.prefix(4))")
                    .font(.caption.bold())
                Text("\(arena.size)x\(arena.size)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let state = state {
                Text("\(state.participants.count)/\(arena.maxPlayers)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    private var statusColor: Color {
        guard let state = state else { return StudioPalette.mutedInk }
        switch state.status {
        case .lobby: return StudioPalette.ember
        case .running: return StudioPalette.moss
        case .ended: return StudioPalette.mutedInk
        }
    }
}

struct ArenaDetailView: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    let arena: ArenaConfig
    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var zoom: CGFloat = 1.0
    @State private var stageOffset: CGSize = .zero
    @FocusState private var isFocused: Bool

    private static let renderModes = LeniaRenderMode.allCases

    private var state: ArenaState? {
        appState.arenaStates[arena.id]
    }

    private var isLive: Bool {
        state?.status == .running && appState.activeArenaConfig?.id == arena.id && appState.currentArenaFrame != nil
    }

    var body: some View {
        StudioDetailScroll {
            if isLive, let frame = appState.currentArenaFrame {
                ArenaFrameView(
                    frame: frame,
                    renderMode: renderMode,
                    zoom: $zoom,
                    offset: $stageOffset
                )
                    .aspectRatio(1, contentMode: .fit)
                    .frame(maxHeight: 400)
                    .padding(.horizontal)
            }

            GroupBox("Arena Configuration") {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("ID:")
                        Spacer()
                        Text(arena.id.uuidString.prefix(8) + "...")
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Grid Size:")
                        Spacer()
                        Text("\(arena.size)x\(arena.size)")
                            .foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Max Players:")
                        Spacer()
                        Text("\(arena.maxPlayers)")
                            .foregroundStyle(.secondary)
                    }
                    if let state = state {
                        HStack {
                            Text("Status:")
                            Spacer()
                            Text(state.status.rawValue.capitalized)
                                .foregroundStyle(statusColor(state.status))
                        }
                        HStack {
                            Text("Participants:")
                            Spacer()
                            Text("\(state.participants.count)")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            .frame(maxWidth: 460)

            if let state = state, !state.participants.isEmpty {
                GroupBox("Participants") {
                    ForEach(state.participants, id: \.self) { workerId in
                        HStack {
                            Image(systemName: "person.fill")
                            Text(workerId)
                            Spacer()
                        }
                        .font(.caption)
                    }
                }
                .frame(maxWidth: 460)
            }

            if state?.status == .lobby {
                Text("Waiting for \(arena.maxPlayers - (state?.participants.count ?? 0)) more player(s)...")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                Button("Trigger Radiation Storm") {
                    Task {
                        await node.triggerArenaMutation(id: arena.id)
                    }
                }
                .buttonStyle(.bordered)
                .foregroundStyle(StudioPalette.ember)

                Button("Stop Arena") {
                    Task {
                        await node.stopArena(id: arena.id)
                    }
                }
                .buttonStyle(.bordered)
                .foregroundStyle(Color(nsColor: .systemRed))
            }
        }
        .focusable()
        .focused($isFocused)
        .focusEffectDisabled()
        .onKeyPress { handleKey($0) }
        .onAppear { isFocused = true }
        .navigationTitle("Arena \(arena.id.uuidString.prefix(4))")
        .toolbar {
            if isLive {
                ToolbarItem(placement: .principal) {
                    RenderModePicker(renderMode: $renderMode)
                }
            }
        }
    }

    private func handleKey(_ press: KeyPress) -> KeyPress.Result {
        guard isLive else { return .ignored }
        switch press.characters {
        case "0":
            zoom = 1.0
            return .handled
        case "1":
            renderMode = Self.renderModes[0]
            return .handled
        case "2":
            renderMode = Self.renderModes[1]
            return .handled
        case "3":
            renderMode = Self.renderModes[2]
            return .handled
        case "4":
            renderMode = Self.renderModes[3]
            return .handled
        case "5":
            renderMode = Self.renderModes[4]
            return .handled
        default:
            return .ignored
        }
    }

    private func statusColor(_ status: ArenaStatus) -> Color {
        switch status {
        case .lobby: return StudioPalette.ember
        case .running: return StudioPalette.moss
        case .ended: return StudioPalette.mutedInk
        }
    }
}

private struct StudioDetailScroll<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                content
            }
            .frame(maxWidth: .infinity, alignment: .top)
            .padding()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }
}

// MARK: - Shared Components

struct ConnectionStatusRow: View {
    @EnvironmentObject var appState: AppState
    @EnvironmentObject var node: LeniaNode
    @Binding var showConnect: Bool

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)

            Text(statusText)
                .font(.caption)
                .foregroundStyle(.secondary)

            Spacer()

            if case .disconnected = appState.connectionState {
                Button("Connect") {
                    showConnect = true
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            } else if case .error = appState.connectionState {
                Button("Retry") {
                    showConnect = true
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            } else {
                Button(stopTitle) {
                    handleStop()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(statusText)
    }

    private var statusColor: Color {
        switch appState.connectionState {
        case .connected: return StudioPalette.moss
        case .connecting: return StudioPalette.ember
        case .error: return Color(nsColor: .systemRed)
        case .disconnected: return StudioPalette.mutedInk
        }
    }

    private var statusText: String {
        switch appState.connectionState {
        case .connected(let role): return role.rawValue
        case .connecting: return "Connecting..."
        case .error(let msg): return "Error: \(msg)"
        case .disconnected: return "Offline"
        }
    }

    private var stopTitle: String {
        if case .connected(let role) = appState.connectionState, role == .compendium {
            return "Close"
        }
        return "Stop"
    }

    private func handleStop() {
        if case .connected(let role) = appState.connectionState, role == .compendium {
            appState.connectionState = .disconnected
        } else {
            node.stop()
        }
    }
}
