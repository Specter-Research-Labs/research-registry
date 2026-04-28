import AppKit
import MetalKit
import SwiftUI
import UniformTypeIdentifiers
import LeniaCore
import LeniaVisuals

@MainActor
final class LeniaLabModel: ObservableObject {
    @Published var snapshot: FlowSandboxSnapshot?
    @Published var isRunning = false
    @Published var activeWorldEntryID: String?
    @Published var activeBackend: FlowSandboxBackend = .metalFull
    @Published var worldContract: FlowSandboxWorldContract?
    @Published var snapshotFps = 0.0
    @Published var activityEstimate = 0.0
    @Published var availableProjections: [LabFieldProjection] = [.matter]
    @Published var activeProjection: LabFieldProjection = .matter
    @Published var runtimeModeLabel = "Sandbox contract"
    @Published var runtimeStatusMessage: String?
    @Published var stepDurationMs = 0.0
    @Published var realizedStepRateHz = 0.0
    @Published var healthState: LabHealthState = .armed
    @Published var healthSummary = "Configure the contract, then launch."
    @Published var healthWarnings: [String] = []
    @Published var activityHistory: [Double] = []
    @Published var externalReplayTitle: String?

    private var runtime: LabRuntimeHandle?
    private var snapshotTask: Task<Void, Never>?
    private var targetSpeedCap = 60

    func rebuildWorld(
        sourceEntryID: String,
        baseConfigData: Data,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool = false,
        initialStampEntry: StudioCompareEntry? = nil,
        stampCache: LeniaLabStampCache? = nil
    ) {
        activeWorldEntryID = sourceEntryID
        activeBackend = backend
        targetSpeedCap = speedCap
        let previousRuntime = runtime
        runtime = nil
        snapshotTask?.cancel()
        snapshotTask = nil

        let currentRunning = shouldRun
        isRunning = currentRunning
        snapshot = nil
        externalReplayTitle = nil
        worldContract = nil
        snapshotFps = 0
        activityEstimate = 0
        runtimeStatusMessage = nil
        stepDurationMs = 0
        realizedStepRateHz = 0
        healthState = .armed
        healthSummary = "Contract is rebuilding."
        healthWarnings = []
        activityHistory = []

        Task {
            if let previousRuntime {
                await previousRuntime.stop()
            }
            do {
                let runtime: LabRuntimeHandle = try .replay(
                    CanonicalLabRuntime(
                        baseConfigData: baseConfigData,
                        backend: backend
                    )
                )
                await runtime.setSpeedCap(hz: speedCap)
                await runtime.setAutoFoodSpawn(
                    enabled: false,
                    probability: 0.03,
                    patchSize: 12,
                    value: 0.35
                )
                if currentRunning {
                    await runtime.start()
                }
                let worldContract = await runtime.worldContract()
                if let initialStampEntry, let stampCache {
                    let stamp = await stampCache.stamp(for: initialStampEntry)
                    let center = SIMD2<Int>(worldContract.gridSize / 2, worldContract.gridSize / 2)
                    await runtime.applyCreatureStamp(stamp, center: center)
                }
                let projections = await runtime.availableProjections()
                let activeProjection = projections.contains(self.activeProjection) ? self.activeProjection : .matter

                self.runtime = runtime
                self.isRunning = currentRunning
                self.worldContract = worldContract
                self.availableProjections = projections
                self.activeProjection = activeProjection
                self.runtimeModeLabel = runtime.modeLabel
                self.activityEstimate = 0
                self.startSnapshotLoop()
            } catch {
                self.runtime = nil
                self.snapshot = nil
                self.isRunning = false
                self.worldContract = nil
                self.activityEstimate = 0
                self.stepDurationMs = 0
                self.realizedStepRateHz = 0
                self.availableProjections = [.matter]
                self.activeProjection = .matter
                self.runtimeModeLabel = "Replay failed"
                self.runtimeStatusMessage = "Failed to load canonical replay world: \(error.localizedDescription)"
                self.healthState = .exploding
                self.healthSummary = "The edited runtime config failed validation or could not boot."
                self.healthWarnings = [error.localizedDescription]
            }
        }
    }

    func rebuildWorld(
        sourceEntryID: String,
        runtimeConfig: LeniaRuntimeConfig,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool = false,
        initialStampEntry: StudioCompareEntry? = nil,
        stampCache: LeniaLabStampCache? = nil
    ) {
        activeWorldEntryID = sourceEntryID
        activeBackend = backend
        targetSpeedCap = speedCap
        let previousRuntime = runtime
        runtime = nil
        snapshotTask?.cancel()
        snapshotTask = nil

        let currentRunning = shouldRun
        isRunning = currentRunning
        snapshot = nil
        externalReplayTitle = nil
        worldContract = nil
        snapshotFps = 0
        activityEstimate = 0
        runtimeStatusMessage = nil
        stepDurationMs = 0
        realizedStepRateHz = 0
        healthState = .armed
        healthSummary = "Contract is rebuilding."
        healthWarnings = []
        activityHistory = []

        Task {
            if let previousRuntime {
                await previousRuntime.stop()
            }
            do {
                let runtime: LabRuntimeHandle = try .replay(
                    CanonicalLabRuntime(
                        runtimeConfig: runtimeConfig
                    )
                )
                await runtime.setSpeedCap(hz: speedCap)
                await runtime.setAutoFoodSpawn(
                    enabled: false,
                    probability: 0.03,
                    patchSize: 12,
                    value: 0.35
                )
                let worldContract = await runtime.worldContract()
                if let initialStampEntry, let stampCache {
                    let stamp = await stampCache.stamp(for: initialStampEntry)
                    let center = SIMD2<Int>(worldContract.gridSize / 2, worldContract.gridSize / 2)
                    await runtime.applyCreatureStamp(stamp, center: center)
                }
                if currentRunning {
                    await runtime.start()
                }
                let projections = await runtime.availableProjections()
                let activeProjection = projections.contains(self.activeProjection) ? self.activeProjection : .matter

                self.runtime = runtime
                self.isRunning = currentRunning
                self.worldContract = worldContract
                self.availableProjections = projections
                self.activeProjection = activeProjection
                self.runtimeModeLabel = runtime.modeLabel
                self.activityEstimate = 0
                self.startSnapshotLoop()
            } catch {
                self.runtime = nil
                self.snapshot = nil
                self.isRunning = false
                self.worldContract = nil
                self.activityEstimate = 0
                self.stepDurationMs = 0
                self.realizedStepRateHz = 0
                self.availableProjections = [.matter]
                self.activeProjection = .matter
                self.runtimeModeLabel = "Replay failed"
                self.runtimeStatusMessage = "Failed to load canonical replay world: \(error.localizedDescription)"
                self.healthState = .exploding
                self.healthSummary = "The edited runtime config failed validation or could not boot."
                self.healthWarnings = [error.localizedDescription]
            }
        }
    }

    func loadFrameSequence(manifestURL: URL) {
        let previousRuntime = runtime
        runtime = nil
        snapshotTask?.cancel()
        snapshotTask = nil

        isRunning = false
        activeWorldEntryID = nil
        snapshot = nil
        worldContract = nil
        activityEstimate = 0
        runtimeStatusMessage = nil
        stepDurationMs = 0
        realizedStepRateHz = 0
        availableProjections = [.matter]
        activeProjection = .matter
        runtimeModeLabel = "TT export replay"
        healthState = .armed
        healthSummary = "Loading TT export frames."
        healthWarnings = []
        activityHistory = []

        Task { @MainActor in
            if let previousRuntime {
                await previousRuntime.stop()
            }
            let securityScoped = manifestURL.startAccessingSecurityScopedResource()
            defer {
                if securityScoped {
                    manifestURL.stopAccessingSecurityScopedResource()
                }
            }
            do {
                let sequence = try TTFrameSequence.load(manifestURL: manifestURL)
                let runtime = TTFrameSequenceRuntime(sequence: sequence)
                await runtime.setSpeedCap(hz: targetSpeedCap)
                let worldContract = await runtime.worldContract()
                let snapshot = await runtime.snapshot(refreshMetrics: true, projection: .matter)

                self.runtime = .frameSequence(runtime)
                self.snapshot = snapshot
                self.worldContract = worldContract
                self.externalReplayTitle = sequence.title
                self.runtimeModeLabel = "TT export replay"
                self.runtimeStatusMessage = nil
                self.healthState = .stable
                self.healthSummary = "TT export loaded. Press Launch to play the sampled quietbox trajectory."
                self.healthWarnings = []
                self.startSnapshotLoop()
            } catch {
                self.runtime = nil
                self.snapshot = nil
                self.worldContract = nil
                self.externalReplayTitle = manifestURL.lastPathComponent
                self.runtimeModeLabel = "TT export replay failed"
                self.runtimeStatusMessage = "Failed to load TT export: \(error.localizedDescription)"
                self.healthState = .exploding
                self.healthSummary = "The selected TT export manifest could not be loaded."
                self.healthWarnings = [error.localizedDescription]
            }
        }
    }

    func setRunning(_ running: Bool) {
        isRunning = running
        guard let runtime else { return }
        Task {
            if running {
                await runtime.resume()
            } else {
                await runtime.pause()
            }
        }
    }

    func reset() {
        guard let runtime else { return }
        Task {
            await runtime.reset()
            if isRunning {
                await runtime.resume()
            }
            await MainActor.run {
                self.activityHistory = []
                self.healthState = .armed
                self.healthSummary = "World reset. Inspect the contract, then relaunch."
                self.healthWarnings = []
            }
        }
    }

    func setSpeedCap(_ hz: Int) {
        targetSpeedCap = hz
        guard let runtime else { return }
        Task {
            await runtime.setSpeedCap(hz: hz)
        }
    }

    func setAutoFood(enabled: Bool, probability: Float = 0.03, patchSize: Int = 12, value: Float = 0.35) {
        guard let runtime else { return }
        Task {
            await runtime.setAutoFoodSpawn(
                enabled: enabled,
                probability: probability,
                patchSize: patchSize,
                value: value
            )
        }
    }

    func setProjection(_ projection: LabFieldProjection) {
        activeProjection = projection
        guard let runtime else { return }
        Task {
            let snapshot = await runtime.snapshot(refreshMetrics: false, projection: projection)
            await MainActor.run {
                self.snapshot = snapshot
            }
        }
    }

    func applyStroke(tool: SandboxTool, points: [SIMD2<Int>], radius: Int, strength: Float) {
        guard let runtime, !points.isEmpty else { return }
        let stroke = SandboxStroke(tool: tool, points: points, radius: radius, strength: strength)
        Task {
            await runtime.applyStroke(stroke)
        }
    }

    func applyStamp(entry: StudioCompareEntry, at point: SIMD2<Int>, stampCache: LeniaLabStampCache) {
        guard let runtime else { return }
        Task {
            let stamp = await stampCache.stamp(for: entry)
            await runtime.applyCreatureStamp(stamp, center: point)
        }
    }

    func shutdown() {
        let currentRuntime = runtime
        runtime = nil
        snapshotTask?.cancel()
        snapshotTask = nil
        if let currentRuntime {
            Task {
                await currentRuntime.stop()
            }
        }
    }

    private func startSnapshotLoop() {
        snapshotTask?.cancel()
        guard let runtime else { return }
        let runningDelay: Duration = activeBackend == .metalFull ? .milliseconds(8) : .milliseconds(16)
        let pausedDelay: Duration = .milliseconds(120)
        snapshotTask = Task {
            var lastMetricsRefresh = ContinuousClock.now - .milliseconds(250)
            var fpsTimestamps = [Date]()
            var previousMetrics: FlowSandboxMetrics?
            var latestActivity = 0.0
            fpsTimestamps.reserveCapacity(24)
            while !Task.isCancelled {
                let refreshMetrics = ContinuousClock.now - lastMetricsRefresh >= .milliseconds(250)
                let projection = await MainActor.run { self.activeProjection }
                let snapshot = await runtime.snapshot(
                    refreshMetrics: refreshMetrics,
                    projection: projection
                )
                let runtimeTelemetry = await runtime.telemetry()
                if refreshMetrics {
                    lastMetricsRefresh = ContinuousClock.now
                    latestActivity = labActivityEstimate(
                        previous: previousMetrics,
                        current: snapshot.metrics
                    )
                    previousMetrics = snapshot.metrics
                }
                let now = Date()
                fpsTimestamps.append(now)
                if fpsTimestamps.count > 24 {
                    fpsTimestamps.removeFirst()
                }
                let snapshotFps: Double = {
                    guard fpsTimestamps.count >= 2 else { return 0 }
                    let span = fpsTimestamps.last!.timeIntervalSince(fpsTimestamps.first!)
                    guard span > 0 else { return 0 }
                    return Double(fpsTimestamps.count - 1) / span
                }()
                let assessment = await MainActor.run {
                    labHealthAssessment(
                        metrics: snapshot.metrics,
                        isRunning: self.isRunning,
                        activity: latestActivity,
                        stepDurationMs: runtimeTelemetry.lastStepDurationMs,
                        stepRateHz: runtimeTelemetry.realizedStepRateHz,
                        snapshotFps: snapshotFps,
                        speedCap: self.targetSpeedCap,
                        history: self.activityHistory
                    )
                }
                await MainActor.run {
                    self.snapshot = snapshot
                    self.snapshotFps = snapshotFps
                    self.activityEstimate = latestActivity
                    self.stepDurationMs = runtimeTelemetry.lastStepDurationMs
                    self.realizedStepRateHz = runtimeTelemetry.realizedStepRateHz
                    if refreshMetrics {
                        self.activityHistory.append(latestActivity)
                        if self.activityHistory.count > 48 {
                            self.activityHistory.removeFirst(self.activityHistory.count - 48)
                        }
                    }
                    self.healthState = assessment.state
                    self.healthSummary = assessment.summary
                    self.healthWarnings = assessment.warnings
                }
                let delay = await MainActor.run { self.isRunning ? runningDelay : pausedDelay }
                try? await Task.sleep(for: delay)
            }
        }
    }
}

actor LeniaLabStampCache {
    private var cache: [String: CreatureStamp] = [:]

    func stamp(for entry: StudioCompareEntry) -> CreatureStamp {
        if let cached = cache[entry.id] {
            return cached
        }
        let stamp = buildSeedCreatureStamp(
            id: UUID(uuidString: entry.id.components(separatedBy: ":").last ?? "") ?? UUID(),
            name: entry.name,
            params: entry.creature.params,
            seed: entry.creature.seed
        )
        cache[entry.id] = stamp
        return stamp
    }
}

struct LeniaLabView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var model = LeniaLabModel()
    @State private var gridPreset: LabGridPreset = .standard256
    @State private var backend: FlowSandboxBackend = .metalFull
    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var primaryTool: SandboxTool = .creatureStamp
    @State private var secondaryTool: SandboxTool = .erase
    @State private var brushRadius = 8.0
    @State private var brushStrength = 0.35
    @State private var speedCap = 60
    @State private var diagnosticsEnabled = false
    @State private var autoFoodEnabled = false
    @State private var worldSelection: LabWorldSelection = .preset("paper-2c")
    @State private var selectedStampID: String?
    @State private var selectedStampPreview: CreatureStamp?
    @State private var worldDraft: LabWorldDraft?
    @State private var worldDraftError: String?
    @State private var stageZoom: CGFloat = 1.0
    @State private var stageOffset: CGSize = .zero
    @State private var hoveredGridPoint: SIMD2<Int>?
    @State private var showTTExportImporter = false

    private let stampCache = LeniaLabStampCache()
    private static let backendOrder: [FlowSandboxBackend] = [.metalFull, .mlx]
    private static let missionPresets = buildLabMissionPresets()

    private var stampEntries: [StudioCompareEntry] {
        let starter = orbiumStarterEntry()
        let saved = appState.library.prefix(10).map(appState.studioEntry)
        let live = appState.recentCreatures.prefix(10).map(appState.studioEntry)
        var seen: Set<String> = []
        return ([starter] + saved + live).filter { entry in
            seen.insert(entry.id).inserted
        }
    }

    private var selectedStampEntry: StudioCompareEntry {
        if let selectedStampID,
           let selected = stampEntries.first(where: { $0.id == selectedStampID }) {
            return selected
        }
        return stampEntries[0]
    }

    private var selectedWorldEntry: StudioCompareEntry {
        switch worldSelection {
        case .preset(let presetID):
            return Self.missionPresets.first(where: { $0.id == presetID })?.entry ?? Self.missionPresets[0].entry
        case .stamp(let entryID):
            return stampEntries.first(where: { $0.id == entryID }) ?? selectedStampEntry
        }
    }

    private var selectedWorldPreset: LabMissionPreset? {
        guard case .preset(let presetID) = worldSelection else { return nil }
        return Self.missionPresets.first(where: { $0.id == presetID })
    }

    private var activeWorldEntry: StudioCompareEntry? {
        guard let activeWorldEntryID = model.activeWorldEntryID else { return nil }
        return (Self.missionPresets.map(\.entry) + stampEntries).first(where: { $0.id == activeWorldEntryID })
    }

    private var selectedStampSourceSummary: String {
        if let saved = selectedStampEntry.savedCreature {
            let family = saved.initialConditionFamily?.trimmingCharacters(in: .whitespacesAndNewlines)
            if let family, !family.isEmpty {
                return "\(saved.ownerId) · \(family)"
            }
            return saved.ownerId
        }
        return selectedStampEntry.subtitle
    }

    private var primaryGhostSummary: String {
        switch primaryTool {
        case .creatureStamp:
            if let selectedStampPreview {
                return "\(selectedStampEntry.name) · \(selectedStampPreview.width)x\(selectedStampPreview.height) cells"
            }
            return "\(selectedStampEntry.name) · loading footprint"
        case .food, .wall, .erase, .mutation:
            let diameter = Int(brushRadius.rounded()) * 2 + 1
            return "\(primaryTool.rawValue) · d\(diameter) · \(String(format: "%.2f", brushStrength))"
        }
    }

    private var primaryGhostCompactLabel: String {
        switch primaryTool {
        case .creatureStamp:
            if let selectedStampPreview {
                return "\(selectedStampEntry.name) \(selectedStampPreview.width)x\(selectedStampPreview.height)"
            }
            return "\(selectedStampEntry.name) ..."
        case .food, .wall, .erase, .mutation:
            let diameter = Int(brushRadius.rounded()) * 2 + 1
            return "\(primaryTool.rawValue) d\(diameter)"
        }
    }

    var body: some View {
        GeometryReader { proxy in
            Group {
                if proxy.size.width < 1_150 {
                    ScrollView {
                        VStack(spacing: 16) {
                            stageSurface
                            controlSurface
                            paletteSurface
                            universeSurface
                            telemetrySurface
                        }
                        .padding(18)
                    }
                } else {
                    HSplitView {
                        ScrollView {
                            VStack(spacing: 16) {
                                stageSurface
                                controlSurface
                            }
                            .padding(18)
                        }
                        .frame(minWidth: 520, idealWidth: max(560, proxy.size.width * 0.58))
                        .layoutPriority(1)

                        ScrollView {
                            VStack(spacing: 16) {
                                paletteSurface
                                universeSurface
                                telemetrySurface
                            }
                            .padding(18)
                        }
                        .frame(minWidth: 320, idealWidth: 380, maxWidth: 480)
                    }
                }
            }
        }
        .background(
            StudioSceneBackground()
        )
        .navigationTitle("Lenia Lab")
        .toolbar {
            ToolbarItem(placement: .principal) {
                RenderModePicker(renderMode: $renderMode)
            }
            ToolbarItem(placement: .primaryAction) {
                Button("Open TT Export") {
                    showTTExportImporter = true
                }
            }
        }
        .fileImporter(isPresented: $showTTExportImporter, allowedContentTypes: [.json], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                model.loadFrameSequence(manifestURL: url)
                stageZoom = 1.0
                stageOffset = .zero
            }
        }
        .task(
            id: stampEntries.map(\.id).joined(separator: "|")
                + ":\(worldSelection.taskKey)"
        ) {
            if selectedStampID == nil {
                selectedStampID = stampEntries.first?.id
            }
            syncWorldDraft(rebuild: true)
        }
        .task(id: selectedStampEntry.id) {
            selectedStampPreview = await stampCache.stamp(for: selectedStampEntry)
        }
        .onChange(of: speedCap) { _, newValue in
            model.setSpeedCap(newValue)
        }
        .onChange(of: autoFoodEnabled) { _, newValue in
            model.setAutoFood(enabled: newValue)
        }
        .onChange(of: model.activeProjection) { _, newValue in
            model.setProjection(newValue)
        }
        .onChange(of: gridPreset) { _, newValue in
            applyDraftChange { draft in
                draft.setGridSize(newValue.rawValue)
            }
        }
        .onChange(of: backend) { _, newValue in
            rebuildActiveWorld(backend: newValue)
        }
        .onChange(of: worldSelection) { _, _ in
            stageZoom = 1.0
            stageOffset = .zero
            syncWorldDraft(rebuild: true)
        }
        .onDisappear {
            model.shutdown()
        }
    }

    private var stageSurface: some View {
        StudioSurface(
            title: "Mission Stage",
            subtitle: stageSubtitle,
            style: .console
        ) {
            VStack(spacing: 12) {
                if let runtimeStatusMessage = model.runtimeStatusMessage, model.snapshot == nil {
                    ContentUnavailableView(
                        "World failed to load",
                        systemImage: "exclamationmark.triangle",
                        description: Text(runtimeStatusMessage)
                    )
                    .frame(minHeight: 420)
                } else {
                    ZStack(alignment: .topLeading) {
                        LeniaLabStageView(
                            frame: model.snapshot.map(LeniaFieldFrame.init),
                            renderMode: renderMode,
                            zoom: stageZoom,
                            offset: stageOffset,
                            onTransformChange: updateStageTransform,
                            onPrimaryPoint: { handleStagePoint($0, tool: primaryTool) },
                            onSecondaryPoint: { handleStagePoint($0, tool: secondaryTool) },
                            onHoverPointChange: { hoveredGridPoint = $0 }
                        )

                        GeometryReader { proxy in
                            LabStageHoverOverlay(
                                point: hoveredGridPoint,
                                tool: primaryTool,
                                brushRadius: Int(brushRadius.rounded()),
                                selectedStamp: selectedStampEntry,
                                selectedStampPreview: selectedStampPreview,
                                transform: LeniaLabStageTransform(zoom: stageZoom, offset: stageOffset),
                                viewSize: proxy.size,
                                gridSize: model.snapshot?.width ?? gridPreset.rawValue
                            )
                        }
                        .allowsHitTesting(false)
                    }
                    .frame(minHeight: 420)
                }

                HStack(spacing: 10) {
                    StudioMetricPill(label: "State", value: model.isRunning ? "Running" : "Armed", accent: model.isRunning ? StudioPalette.moss : StudioPalette.ember, style: .console)
                    StudioMetricPill(label: "Mode", value: model.runtimeModeLabel, accent: StudioPalette.ink, style: .console)
                    let resolvedGrid = model.worldContract?.gridSize ?? model.snapshot?.width ?? gridPreset.rawValue
                    StudioMetricPill(label: "Grid", value: "\(resolvedGrid)x\(resolvedGrid)", accent: StudioPalette.ocean, style: .console)
                    if let contract = model.worldContract {
                        StudioMetricPill(label: "Lanes", value: "\(contract.channels)m/\(contract.parameterFieldMode.displayName)", accent: StudioPalette.ocean, style: .console)
                        StudioMetricPill(label: "Kernels", value: "\(contract.kernelCount)", accent: StudioPalette.ember, style: .console)
                    }
                    StudioMetricPill(label: "Ghost", value: primaryGhostCompactLabel, accent: hoverAccent(for: primaryTool), style: .console)
                    StudioMetricPill(label: "Step", value: "\(model.snapshot?.step ?? 0)", accent: StudioPalette.ember, style: .console)
                    StudioMetricPill(
                        label: "Activity",
                        value: String(format: "%.4f", model.activityEstimate),
                        accent: activityAccent(for: model.activityEstimate),
                        style: .console
                    )
                    if let metrics = model.snapshot?.metrics {
                        StudioMetricPill(label: "Mass", value: String(format: "%.3f", metrics.massMean), accent: StudioPalette.moss, style: .console)
                        StudioMetricPill(label: "Food", value: String(format: "%.3f", metrics.foodMean), accent: StudioPalette.ocean, style: .console)
                    }
                    StudioMetricPill(
                        label: "View",
                        value: model.snapshotFps > 0 ? String(format: "%.0f fps", model.snapshotFps) : "--",
                        accent: StudioPalette.ink,
                        style: .console
                    )
                    if let hoveredGridPoint {
                        StudioMetricPill(
                            label: "Hover",
                            value: "\(hoveredGridPoint.x),\(hoveredGridPoint.y)",
                            accent: StudioPalette.ink,
                            style: .console
                        )
                    }
                    Spacer()
                    if model.availableProjections.count > 1 {
                        Picker("Field", selection: $model.activeProjection) {
                            ForEach(model.availableProjections) { projection in
                                Text(projection.label).tag(projection)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 240)
                    }
                    Button {
                        adjustStageZoom(by: 0.85)
                    } label: {
                        Image(systemName: "minus.magnifyingglass")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Text("\(Int((stageZoom * 100).rounded()))%")
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(minWidth: 46)

                    Button {
                        adjustStageZoom(by: 1.15)
                    } label: {
                        Image(systemName: "plus.magnifyingglass")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Button("Fit") {
                        updateStageTransform(.init())
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
        }
    }

    private var controlSurface: some View {
        StudioSurface(
            title: "Mission Setup",
            subtitle: "Author the runtime contract, arm the backend, then launch",
            style: .console
        ) {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 10) {
                    Text("World Profiles")
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(StudioPalette.ink)

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(Self.missionPresets) { preset in
                                LabMissionPresetCard(
                                    preset: preset,
                                    isSelected: worldSelection == .preset(preset.id),
                                    onSelect: {
                                        worldSelection = .preset(preset.id)
                                    }
                                )
                            }
                        }
                        .padding(.vertical, 2)
                    }

                    if let selectedWorldPreset {
                        HStack(spacing: 10) {
                            StudioMetricPill(
                                label: "Basis",
                                value: selectedWorldPreset.name,
                                accent: StudioPalette.ink,
                                style: .console
                            )
                            StudioMetricPill(
                                label: "Native lanes",
                                value: "\(selectedWorldPreset.channels)m",
                                accent: StudioPalette.ocean,
                                style: .console
                            )
                            StudioMetricPill(
                                label: "Kernel bank",
                                value: "\(selectedWorldPreset.kernelCount)",
                                accent: StudioPalette.ember,
                                style: .console
                            )
                            if let fixedGrid = selectedWorldPreset.fixedGrid {
                                StudioMetricPill(
                                    label: "Source grid",
                                    value: "\(fixedGrid)x\(fixedGrid)",
                                    accent: StudioPalette.ocean,
                                    style: .console
                                )
                            }
                        }

                        Text(selectedWorldPreset.detail)
                            .font(.callout)
                            .foregroundStyle(StudioPalette.mutedInk)
                    } else {
                        Text("World basis is coming from the selected stamp, and the contract editor turns that specimen into a real runtime config rather than the old sandbox shortcut.")
                            .font(.callout)
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                }

                Divider()

                HStack(spacing: 10) {
                    Button(model.isRunning ? "Pause" : "Launch") {
                        model.setRunning(!model.isRunning)
                    }
                    .buttonStyle(.borderedProminent)

                    Button("Reset") {
                        model.reset()
                    }
                    .buttonStyle(.bordered)

                    Button("World From Stamp") {
                        selectedStampID = selectedStampEntry.id
                        worldSelection = .stamp(selectedStampEntry.id)
                    }
                    .buttonStyle(.bordered)

                    Button("Apply Contract") {
                        rebuildActiveWorld()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(worldDraft == nil)
                }

                if let worldDraft {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Contract Editor")
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(StudioPalette.ink)

                        StudioKeyValueRow(label: "Basis", value: worldDraft.sourceSummary, style: .readable)
                        StudioKeyValueRow(label: "Routing", value: worldDraft.connectivitySummary, style: .readable)

                        HStack(alignment: .top, spacing: 14) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Grid")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(StudioPalette.mutedInk)
                                Picker("Grid", selection: $gridPreset) {
                                    ForEach(LabGridPreset.allCases) { preset in
                                        Text("\(preset.rawValue)x\(preset.rawValue)").tag(preset)
                                    }
                                }
                                .pickerStyle(.segmented)
                                .controlSize(.small)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Speed")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(StudioPalette.mutedInk)
                                Picker("Speed", selection: $speedCap) {
                                    Text("30").tag(30)
                                    Text("60").tag(60)
                                    Text("90").tag(90)
                                    Text("120").tag(120)
                                }
                                .frame(width: 200)
                                .controlSize(.small)
                            }
                        }

                        HStack(alignment: .top, spacing: 14) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Matter lanes")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(StudioPalette.mutedInk)
                                Picker("Matter lanes", selection: channelCountBinding) {
                                    ForEach(1...4, id: \.self) { channelCount in
                                        Text("\(channelCount)").tag(channelCount)
                                    }
                                }
                                .pickerStyle(.segmented)
                                .controlSize(.small)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Border")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(StudioPalette.mutedInk)
                                Picker("Border", selection: borderBinding) {
                                    Text("Torus").tag("torus")
                                    Text("Wall").tag("wall")
                                }
                                .pickerStyle(.segmented)
                                .controlSize(.small)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        HStack(spacing: 12) {
                            Toggle("Parameter transport", isOn: parameterEmbeddingBinding)
                                .toggleStyle(.button)
                                .controlSize(.small)
                            Toggle("Food field", isOn: foodEnabledBinding)
                                .toggleStyle(.button)
                                .controlSize(.small)
                        }

                        if worldDraft.parameterEmbeddingEnabled {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Parameter mix")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(StudioPalette.mutedInk)
                                Picker("Parameter mix", selection: parameterMixBinding) {
                                    Text("Avg").tag("avg")
                                    Text("Softmax").tag("softmax")
                                }
                                .pickerStyle(.segmented)
                                .controlSize(.small)
                            }
                        }

                        if worldDraft.foodEnabled {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Food lane")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(StudioPalette.mutedInk)
                                Picker("Food lane", selection: foodChannelBinding) {
                                    ForEach(0..<worldDraft.channelCount, id: \.self) { channel in
                                        Text("c\(channel)").tag(channel)
                                    }
                                }
                                .pickerStyle(.segmented)
                                .controlSize(.small)
                            }
                        }

                        HStack(alignment: .top, spacing: 14) {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Init seed")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(StudioPalette.mutedInk)
                                Stepper(value: initSeedBinding, in: 0...999_999) {
                                    Text("\(worldDraft.initSeed)")
                                        .font(.system(.callout, design: .monospaced))
                                        .foregroundStyle(StudioPalette.ink)
                                }
                                .controlSize(.small)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }

                        LabSliderRow(label: "Patch Size", value: "\(worldDraft.patchSize)") {
                            Slider(value: patchSizeBinding, in: 12...72, step: 2)
                                .controlSize(.small)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text("Connectivity matrix")
                                    .font(.callout.weight(.semibold))
                                    .foregroundStyle(StudioPalette.ink)
                                Spacer()
                                Text("\(worldDraft.kernelCount) kernels")
                                    .font(.system(.callout, design: .monospaced))
                                    .foregroundStyle(StudioPalette.mutedInk)
                            }
                            LabConnectivityMatrixEditor(
                                channelCount: worldDraft.channelCount,
                                connectivityMatrix: worldDraft.connectivityMatrix,
                                onUpdate: { source, target, count in
                                    applyDraftChange { draft in
                                        draft.setEdgeCount(source: source, target: target, count: count)
                                    }
                                }
                            )
                        }

                        if let worldDraftError {
                            Text(worldDraftError)
                                .font(.callout)
                                .foregroundStyle(.red)
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Backend")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(StudioPalette.mutedInk)
                    Picker("Backend", selection: $backend) {
                        ForEach(Self.backendOrder) { backend in
                            Text(labBackendLabel(backend)).tag(backend)
                        }
                    }
                    .pickerStyle(.segmented)
                    .controlSize(.small)
                }

                if backend != .metalFull {
                    Text("Full Metal is the intended lab path. MLX remains available as the reference execution mode.")
                        .font(.callout)
                        .foregroundStyle(StudioPalette.mutedInk)
                }

                Divider()

                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Primary Tool")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(StudioPalette.mutedInk)
                        Picker("Primary", selection: $primaryTool) {
                            ForEach(SandboxTool.allCases) { tool in
                                Text(tool.rawValue).tag(tool)
                            }
                        }
                        .controlSize(.small)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Secondary Tool")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(StudioPalette.mutedInk)
                        Picker("Secondary", selection: $secondaryTool) {
                            ForEach(SandboxTool.allCases) { tool in
                                Text(tool.rawValue).tag(tool)
                            }
                        }
                        .controlSize(.small)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                VStack(alignment: .leading, spacing: 10) {
                    LabSliderRow(
                        label: "Brush Radius",
                        value: "\(Int(brushRadius))"
                    ) {
                        Slider(value: $brushRadius, in: 2...20, step: 1)
                            .controlSize(.small)
                    }

                    LabSliderRow(
                        label: "Brush Strength",
                        value: String(format: "%.2f", brushStrength)
                    ) {
                        Slider(value: $brushStrength, in: 0.05...1.0, step: 0.05)
                            .controlSize(.small)
                    }
                }

                HStack(spacing: 12) {
                    Toggle("Diagnostics", isOn: $diagnosticsEnabled)
                        .toggleStyle(.button)
                        .controlSize(.small)
                    Toggle("Auto Food", isOn: $autoFoodEnabled)
                        .toggleStyle(.button)
                        .controlSize(.small)
                }

                StudioKeyValueRow(label: "Primary ghost", value: primaryGhostSummary, style: .readable)

                if diagnosticsEnabled, let metrics = model.snapshot?.metrics {
                    HStack(spacing: 10) {
                        StudioMetricPill(label: "Occ", value: String(format: "%.3f", metrics.occupancy), accent: StudioPalette.ember, style: .console)
                        StudioMetricPill(label: "Wall", value: String(format: "%.3f", metrics.wallFraction), accent: StudioPalette.ink, style: .console)
                        StudioMetricPill(label: "Peak", value: String(format: "%.3f", metrics.massPeak), accent: StudioPalette.moss, style: .console)
                        StudioMetricPill(label: "Non-finite", value: String(format: "%.3f", metrics.nonFiniteFraction), accent: StudioPalette.ember, style: .console)
                    }
                }
            }
        }
    }

    private var universeSurface: some View {
        StudioSurface(
            title: "Universe Contract",
            subtitle: "Current lab physics, runtime, and topology",
            style: .console
        ) {
            if let contract = model.worldContract {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 10) {
                        StudioMetricPill(label: "Matter", value: "\(contract.channels)", accent: StudioPalette.ocean, style: .console)
                        StudioMetricPill(label: "Params", value: contract.parameterFieldMode.displayName, accent: StudioPalette.ocean, style: .console)
                        StudioMetricPill(label: "Kernels", value: "\(contract.kernelCount)", accent: StudioPalette.ember, style: .console)
                        StudioMetricPill(label: "Radius", value: String(format: "%.1f", contract.radius), accent: StudioPalette.moss, style: .console)
                        Spacer()
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Execution stack")
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(StudioPalette.mutedInk)

                        Group {
                            StudioKeyValueRow(label: "Mode", value: model.runtimeModeLabel, style: .readable)
                            StudioKeyValueRow(
                                label: "Backend",
                                value: model.externalReplayTitle == nil ? contract.backend.displayName : "Tenstorrent export",
                                style: .readable
                            )
                            StudioKeyValueRow(label: "Engine", value: contract.executionSummary, style: .readable)
                            StudioKeyValueRow(label: "Field stack", value: contract.fieldSummary, style: .readable)
                            StudioKeyValueRow(label: "Capabilities", value: contract.featureSummary, style: .readable)
                            StudioKeyValueRow(label: "Health", value: model.healthState.label, style: .readable)
                            StudioKeyValueRow(label: "Projection", value: model.activeProjection.label, style: .readable)
                            StudioKeyValueRow(
                                label: "View cadence",
                                value: model.snapshotFps > 0 ? String(format: "%.0f fps", model.snapshotFps) : "--",
                                style: .readable
                            )
                            StudioKeyValueRow(
                                label: "Solver cadence",
                                value: model.realizedStepRateHz > 0 ? String(format: "%.0f Hz · %.2f ms", model.realizedStepRateHz, model.stepDurationMs) : "--",
                                style: .readable
                            )
                            StudioKeyValueRow(label: "Speed cap", value: "\(speedCap) Hz", style: .readable)
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        Text("World source")
                            .font(.callout.weight(.semibold))
                            .foregroundStyle(StudioPalette.mutedInk)

                        Group {
                            StudioKeyValueRow(label: "World basis", value: activeWorldEntry?.name ?? "--", style: .readable)
                            if let worldDraft {
                                StudioKeyValueRow(label: "Draft contract", value: worldDraft.sourceSummary, style: .readable)
                            }
                            StudioKeyValueRow(label: "Stamp ghost", value: selectedStampEntry.name, style: .readable)
                            StudioKeyValueRow(label: "Stamp source", value: selectedStampSourceSummary, style: .readable)
                            if let replayReference = activeWorldEntry?.replayReference {
                                StudioKeyValueRow(label: "Replay base", value: replayReference.baseConfigPath, style: .readable)
                            }
                            if let worldDraft {
                                StudioKeyValueRow(label: "Init seed", value: "\(worldDraft.initSeed)", style: .readable)
                                if worldDraft.usesRandomKernelBank {
                                    StudioKeyValueRow(label: "Param seed", value: "\(worldDraft.paramsSeed)", style: .readable)
                                }
                            }
                            if let saved = selectedStampEntry.savedCreature {
                                StudioKeyValueRow(label: "Init family", value: saved.initialConditionFamily ?? "--", style: .readable)
                            }
                        }
                    }

                    Divider()

                    Group {
                        StudioKeyValueRow(label: "Grid", value: "\(contract.gridSize)x\(contract.gridSize)", style: .readable)
                        StudioKeyValueRow(label: "Profile", value: contract.kernelProfile, style: .readable)
                        StudioKeyValueRow(label: "Flow", value: "dt \(formatCompact(contract.dt)) · dd \(contract.dd) · sigma \(formatCompact(contract.sigma))", style: .readable)
                        StudioKeyValueRow(label: "Border", value: "\(contract.border) · n \(contract.n) · thetaA \(formatCompact(contract.thetaA))", style: .readable)
                        StudioKeyValueRow(label: "Kernel seed", value: "\(contract.seed)", style: .readable)
                        StudioKeyValueRow(label: "Connectivity", value: contract.connectivitySummary, style: .readable)
                    }

                    Divider()

                    DisclosureGroup("Kernel bank (\(contract.kernels.count))") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(contract.kernels) { kernel in
                                LabKernelRow(kernel: kernel)
                            }
                        }
                    }
                    .font(.callout)
                }
            } else if let runtimeStatusMessage = model.runtimeStatusMessage {
                Text(runtimeStatusMessage)
                    .font(.callout)
                    .foregroundStyle(StudioPalette.mutedInk)
            } else {
                Text("Runtime contract is materializing.")
                    .font(.callout)
                    .foregroundStyle(StudioPalette.mutedInk)
            }
        }
    }

    private var paletteSurface: some View {
        StudioSurface(title: "Creature Palette", subtitle: "Choose the current stamp or rebuild the world around a specimen", style: .console) {
            VStack(alignment: .leading, spacing: 14) {
                if let activeWorldEntry {
                    HStack {
                        Text("World physics")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(activeWorldEntry.name)
                            .font(.caption)
                            .foregroundStyle(StudioPalette.ink)
                    }
                }

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 14) {
                        ForEach(stampEntries) { entry in
                            VStack(spacing: 8) {
                                StudioCreatureCard(
                                    entry: entry,
                                    tone: selectedStampID == entry.id ? StudioPalette.ocean : StudioPalette.ember,
                                    onSelect: { selectedStampID = entry.id }
                                )
                                .frame(width: 180)

                                HStack(spacing: 8) {
                                    Button(selectedStampID == entry.id ? "Selected" : "Use Stamp") {
                                        selectedStampID = entry.id
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)

                                    Button("Set World") {
                                        selectedStampID = entry.id
                                        worldSelection = .stamp(entry.id)
                                    }
                                    .buttonStyle(.borderedProminent)
                                    .controlSize(.small)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private var telemetrySurface: some View {
        StudioSurface(title: "Mission Telemetry", subtitle: "Health, cadence, and saturation on the live runtime", style: .console) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    StudioMetricPill(label: "Health", value: model.healthState.label, accent: model.healthState.accent, style: .console)
                    StudioMetricPill(label: "Step", value: model.stepDurationMs > 0 ? String(format: "%.2f ms", model.stepDurationMs) : "--", accent: StudioPalette.ink, style: .console)
                    StudioMetricPill(label: "Solver", value: model.realizedStepRateHz > 0 ? String(format: "%.0f Hz", model.realizedStepRateHz) : "--", accent: StudioPalette.ocean, style: .console)
                    StudioMetricPill(label: "View", value: model.snapshotFps > 0 ? String(format: "%.0f fps", model.snapshotFps) : "--", accent: StudioPalette.ink, style: .console)
                }

                if !model.activityHistory.isEmpty {
                    LabTelemetrySparkline(
                        values: model.activityHistory,
                        accent: activityAccent(for: model.activityEstimate)
                    )
                    .frame(height: 74)
                }

                Text(model.healthSummary)
                    .font(.callout)
                    .foregroundStyle(StudioPalette.ink)

                if !model.healthWarnings.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(model.healthWarnings.enumerated()), id: \.offset) { _, warning in
                            Text(warning)
                                .font(.callout)
                                .foregroundStyle(StudioPalette.mutedInk)
                        }
                    }
                }

                if let metrics = model.snapshot?.metrics {
                    Divider()
                    VStack(alignment: .leading, spacing: 8) {
                        StudioKeyValueRow(label: "Mass mean", value: formatCompact(metrics.massMean), style: .readable)
                        StudioKeyValueRow(label: "Mass peak", value: formatCompact(metrics.massPeak), style: .readable)
                        StudioKeyValueRow(label: "Occupancy", value: formatCompact(metrics.occupancy), style: .readable)
                        StudioKeyValueRow(label: "Food mean", value: formatCompact(metrics.foodMean), style: .readable)
                        StudioKeyValueRow(label: "Food peak", value: formatCompact(metrics.foodPeak), style: .readable)
                        StudioKeyValueRow(label: "Non-finite", value: formatCompact(metrics.nonFiniteFraction), style: .readable)
                    }
                } else {
                    Text("Telemetry appears once the runtime has produced a field snapshot.")
                        .font(.callout)
                        .foregroundStyle(StudioPalette.mutedInk)
                }
            }
        }
    }

    private var stageSubtitle: String {
        if let externalReplayTitle = model.externalReplayTitle {
            return "\(externalReplayTitle) · \(model.isRunning ? "playing" : "loaded") · \(model.runtimeModeLabel)"
        }
        if let activeWorldEntry {
            if let contract = model.worldContract {
                return "Active world: \(activeWorldEntry.name) · \(model.isRunning ? "running" : "armed") · \(model.runtimeModeLabel) · \(model.activeBackend.displayName) · \(contract.channels)m/\(contract.parameterFieldMode.displayName)"
            }
            return "Active world: \(activeWorldEntry.name) · \(model.isRunning ? "running" : "armed") · \(model.runtimeModeLabel) · \(model.activeBackend.displayName)"
        }
        return "Building world"
    }

    private var selectedWorldBootstrapStampEntry: StudioCompareEntry? {
        switch worldSelection {
        case .stamp:
            return selectedWorldEntry
        case .preset(let presetID) where presetID == "orbium-sandbox":
            return selectedWorldEntry
        default:
            return nil
        }
    }

    private func syncWorldDraft(rebuild: Bool) {
        worldDraftError = nil
        do {
            let nextDraft: LabWorldDraft
            if let preset = selectedWorldPreset, let defaultDraft = preset.defaultDraft {
                nextDraft = defaultDraft
            } else {
                nextDraft = try makeLabWorldDraft(for: selectedWorldEntry, gridSize: gridPreset.rawValue)
            }
            worldDraft = nextDraft
            if let matchingGrid = LabGridPreset.allCases.first(where: { $0.rawValue == nextDraft.gridSize }),
               matchingGrid != gridPreset {
                gridPreset = matchingGrid
            }
            if rebuild {
                rebuildActiveWorld()
            }
        } catch {
            worldDraft = nil
            worldDraftError = "Failed to prepare world contract: \(error.localizedDescription)"
        }
    }

    private func rebuildActiveWorld(backend overrideBackend: FlowSandboxBackend? = nil) {
        worldDraftError = nil
        let targetBackend = overrideBackend ?? backend
        if let worldDraft {
            model.rebuildWorld(
                sourceEntryID: selectedWorldEntry.id,
                runtimeConfig: worldDraft.runtimeConfig(overridingBackend: targetBackend),
                backend: targetBackend,
                speedCap: speedCap,
                shouldRun: false,
                initialStampEntry: selectedWorldBootstrapStampEntry,
                stampCache: stampCache
            )
            return
        }

        guard let replayReference = selectedWorldEntry.replayReference else {
            worldDraftError = "No replay bundle or editable runtime contract is available for this world."
            return
        }
        do {
            let data = try Data(contentsOf: URL(fileURLWithPath: replayReference.baseConfigPath))
            model.rebuildWorld(
                sourceEntryID: selectedWorldEntry.id,
                baseConfigData: data,
                backend: targetBackend,
                speedCap: speedCap,
                shouldRun: false,
                initialStampEntry: selectedWorldBootstrapStampEntry,
                stampCache: stampCache
            )
        } catch {
            worldDraftError = "Failed to load replay base: \(error.localizedDescription)"
        }
    }

    private func applyDraftChange(_ edit: (inout LabWorldDraft) -> Void) {
        guard var draft = worldDraft else { return }
        edit(&draft)
        worldDraft = draft
        worldDraftError = nil
    }

    private var channelCountBinding: Binding<Int> {
        Binding(
            get: { worldDraft?.channelCount ?? 1 },
            set: { nextValue in
                applyDraftChange { draft in
                    draft.setChannels(nextValue)
                }
            }
        )
    }

    private var parameterEmbeddingBinding: Binding<Bool> {
        Binding(
            get: { worldDraft?.parameterEmbeddingEnabled ?? false },
            set: { enabled in
                applyDraftChange { draft in
                    draft.setParameterEmbeddingEnabled(enabled)
                }
            }
        )
    }

    private var foodEnabledBinding: Binding<Bool> {
        Binding(
            get: { worldDraft?.foodEnabled ?? false },
            set: { enabled in
                applyDraftChange { draft in
                    draft.setFoodEnabled(enabled)
                }
            }
        )
    }

    private var foodChannelBinding: Binding<Int> {
        Binding(
            get: { worldDraft?.foodChannelIndex ?? 0 },
            set: { nextChannel in
                applyDraftChange { draft in
                    draft.setFoodChannelIndex(nextChannel)
                }
            }
        )
    }

    private var borderBinding: Binding<String> {
        Binding(
            get: { worldDraft?.border ?? "torus" },
            set: { nextBorder in
                applyDraftChange { draft in
                    draft.setBorder(nextBorder)
                }
            }
        )
    }

    private var parameterMixBinding: Binding<String> {
        Binding(
            get: { worldDraft?.parameterMixMode ?? "avg" },
            set: { nextMode in
                applyDraftChange { draft in
                    draft.setParameterMixMode(nextMode)
                }
            }
        )
    }

    private var initSeedBinding: Binding<Int> {
        Binding(
            get: { worldDraft?.initSeed ?? 0 },
            set: { nextSeed in
                applyDraftChange { draft in
                    draft.setInitSeed(nextSeed)
                }
            }
        )
    }

    private var patchSizeBinding: Binding<Double> {
        Binding(
            get: { Double(worldDraft?.patchSize ?? 24) },
            set: { nextSize in
                applyDraftChange { draft in
                    draft.setPatchSize(Int(nextSize.rounded()))
                }
            }
        )
    }

    private func handleStagePoint(_ point: SIMD2<Int>, tool: SandboxTool) {
        switch tool {
        case .creatureStamp:
            model.applyStamp(entry: selectedStampEntry, at: point, stampCache: stampCache)
        case .food, .wall, .erase, .mutation:
            model.applyStroke(
                tool: tool,
                points: [point],
                radius: Int(brushRadius),
                strength: Float(brushStrength)
            )
        }
    }

    private func updateStageTransform(_ transform: LeniaLabStageTransform) {
        stageZoom = transform.zoom
        stageOffset = transform.offset
    }

    private func adjustStageZoom(by factor: CGFloat) {
        let next = LeniaLabStageTransform.clampedZoom(stageZoom * factor)
        updateStageTransform(
            LeniaLabStageTransform(zoom: next, offset: stageOffset)
        )
    }
}

enum LabHealthState {
    case armed
    case active
    case stable
    case drifting
    case dead
    case exploding

    var label: String {
        switch self {
        case .armed:
            "Armed"
        case .active:
            "Active"
        case .stable:
            "Stable"
        case .drifting:
            "Drifting"
        case .dead:
            "Dead"
        case .exploding:
            "Exploding"
        }
    }

    var accent: Color {
        switch self {
        case .armed:
            StudioPalette.ink
        case .active:
            StudioPalette.moss
        case .stable:
            StudioPalette.ocean
        case .drifting:
            StudioPalette.ember
        case .dead:
            StudioPalette.mutedInk
        case .exploding:
            .red
        }
    }
}

private struct LabHealthAssessment {
    let state: LabHealthState
    let summary: String
    let warnings: [String]
}

private func labHealthAssessment(
    metrics: FlowSandboxMetrics,
    isRunning: Bool,
    activity: Double,
    stepDurationMs: Double,
    stepRateHz: Double,
    snapshotFps: Double,
    speedCap: Int,
    history: [Double]
) -> LabHealthAssessment {
    guard isRunning else {
        return LabHealthAssessment(
            state: .armed,
            summary: "Contract is loaded. Launch to run.",
            warnings: []
        )
    }

    var warnings: [String] = []
    if metrics.nonFiniteFraction > 0 {
        warnings.append("Non-finite values were observed in the sampled field.")
    }
    if metrics.massPeak > 0.985 {
        warnings.append("Mass is clipping near 1.0.")
    }
    if metrics.foodPeak > 0.985 {
        warnings.append("Food field is clipping near 1.0.")
    }
    if stepDurationMs > 0, stepDurationMs > (1_000.0 / Double(max(1, speedCap))) * 0.9 {
        warnings.append("Solver step time is close to the requested cap budget.")
    }
    if snapshotFps > 0, snapshotFps < Double(speedCap) * 0.35 {
        warnings.append("View cadence is well below the requested cap.")
    }

    let recentHistory = Array(history.suffix(8))
    let recentActivity = recentHistory.isEmpty
        ? activity
        : recentHistory.reduce(0, +) / Double(recentHistory.count)

    if metrics.nonFiniteFraction > 0 || metrics.massPeak > 1.05 {
        return LabHealthAssessment(
            state: .exploding,
            summary: "The field is diverging or leaving the finite operating range.",
            warnings: warnings
        )
    }
    if metrics.massMean < 0.0005 || metrics.occupancy < 0.0005 {
        return LabHealthAssessment(
            state: .dead,
            summary: "Mass has collapsed into a near-empty field.",
            warnings: warnings
        )
    }
    if recentActivity < 0.0008 {
        return LabHealthAssessment(
            state: .stable,
            summary: "Activity is near zero; the world looks like a quiet attractor.",
            warnings: warnings
        )
    }
    if recentActivity < 0.01 || activity < 0.01 {
        return LabHealthAssessment(
            state: .drifting,
            summary: "The world is still changing, but only slowly across the recent window.",
            warnings: warnings
        )
    }
    return LabHealthAssessment(
        state: .active,
        summary: stepRateHz > 0
            ? String(format: "Solver is advancing at %.0f Hz with visible field motion.", stepRateHz)
            : "Solver is advancing and the field remains active.",
        warnings: warnings
    )
}

private struct LabSliderRow<Control: View>: View {
    let label: String
    let value: String
    let control: Control

    init(label: String, value: String, @ViewBuilder control: () -> Control) {
        self.label = label
        self.value = value
        self.control = control()
    }

    var body: some View {
        Grid(horizontalSpacing: 12, verticalSpacing: 0) {
            GridRow {
                Text(label)
                    .font(.callout)
                    .foregroundStyle(StudioPalette.ink)
                    .frame(width: 110, alignment: .leading)

                control
                    .frame(maxWidth: 260)

                Text(value)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(StudioPalette.mutedInk)
                    .frame(width: 48, alignment: .trailing)
            }
        }
    }
}

private struct LabMissionPresetCard: View {
    let preset: LabMissionPreset
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 8) {
                Text(preset.name)
                    .font(.system(.headline, design: .serif, weight: .semibold))
                    .foregroundStyle(StudioPalette.ink)
                    .multilineTextAlignment(.leading)

                Text(preset.subtitle)
                    .font(.callout)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .multilineTextAlignment(.leading)
                    .lineLimit(2)

                HStack(spacing: 8) {
                    StudioMetricPill(
                        label: "Lanes",
                        value: "\(preset.channels)m/\(preset.parameterFields)p",
                        accent: StudioPalette.ocean,
                        style: .console
                    )
                    StudioMetricPill(
                        label: "Kernels",
                        value: "\(preset.kernelCount)",
                        accent: StudioPalette.ember,
                        style: .console
                    )
                }

                Text(preset.detail)
                    .font(.caption)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
            }
            .frame(width: 248, alignment: .leading)
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(isSelected ? StudioPalette.surfaceRaised : StudioPalette.surfaceSoft)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(isSelected ? StudioPalette.ocean.opacity(0.7) : StudioPalette.hairline, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct LabConnectivityMatrixEditor: View {
    let channelCount: Int
    let connectivityMatrix: [[Int]]
    let onUpdate: (Int, Int, Int) -> Void

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
            GridRow {
                Text("")
                    .frame(width: 52)
                ForEach(0..<channelCount, id: \.self) { target in
                    Text("c\(target)")
                        .font(.system(.caption, design: .monospaced, weight: .semibold))
                        .foregroundStyle(StudioPalette.mutedInk)
                        .frame(maxWidth: .infinity)
                }
            }

            ForEach(0..<channelCount, id: \.self) { source in
                GridRow {
                    Text("c\(source)")
                        .font(.system(.caption, design: .monospaced, weight: .semibold))
                        .foregroundStyle(StudioPalette.ink)
                        .frame(width: 52, alignment: .leading)

                    ForEach(0..<channelCount, id: \.self) { target in
                        LabRouteCountCell(
                            count: connectivityMatrix[source][target],
                            onDecrement: {
                                onUpdate(source, target, max(0, connectivityMatrix[source][target] - 1))
                            },
                            onIncrement: {
                                onUpdate(source, target, connectivityMatrix[source][target] + 1)
                            }
                        )
                    }
                }
            }
        }
    }
}

private struct LabRouteCountCell: View {
    let count: Int
    let onDecrement: () -> Void
    let onIncrement: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            Button(action: onDecrement) {
                Image(systemName: "minus")
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)

            Text("\(count)")
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(StudioPalette.ink)
                .frame(minWidth: 22)

            Button(action: onIncrement) {
                Image(systemName: "plus")
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .background(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(StudioPalette.surfaceSoft)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .stroke(StudioPalette.hairline, lineWidth: 1)
        )
    }
}

private struct LabTelemetrySparkline: View {
    let values: [Double]
    let accent: Color

    var body: some View {
        GeometryReader { proxy in
            let points = sparklinePoints(size: proxy.size)
            ZStack {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(StudioPalette.surfaceSoft)
                Path { path in
                    guard let first = points.first else { return }
                    path.move(to: first)
                    for point in points.dropFirst() {
                        path.addLine(to: point)
                    }
                }
                .stroke(accent, style: StrokeStyle(lineWidth: 1.75, lineCap: .round, lineJoin: .round))
            }
        }
    }

    private func sparklinePoints(size: CGSize) -> [CGPoint] {
        guard !values.isEmpty else { return [] }
        let maxValue = max(values.max() ?? 1, 0.0001)
        let stepX = size.width / CGFloat(max(values.count - 1, 1))
        return values.enumerated().map { index, value in
            let x = CGFloat(index) * stepX
            let normalized = CGFloat(value / maxValue)
            let y = size.height - normalized * max(size.height - 8, 1) - 4
            return CGPoint(x: x, y: y)
        }
    }
}

struct LeniaLabStageView: NSViewRepresentable {
    let frame: LeniaFieldFrame?
    let renderMode: LeniaRenderMode
    let zoom: CGFloat
    let offset: CGSize
    let onTransformChange: (LeniaLabStageTransform) -> Void
    let onPrimaryPoint: (SIMD2<Int>) -> Void
    let onSecondaryPoint: (SIMD2<Int>) -> Void
    let onHoverPointChange: (SIMD2<Int>?) -> Void

    func makeNSView(context: Context) -> LeniaLabStageNSView {
        let view = LeniaLabStageNSView()
        view.onTransformChange = onTransformChange
        view.onPrimaryPoint = onPrimaryPoint
        view.onSecondaryPoint = onSecondaryPoint
        view.onHoverPointChange = onHoverPointChange
        return view
    }

    func updateNSView(_ nsView: LeniaLabStageNSView, context: Context) {
        nsView.onTransformChange = onTransformChange
        nsView.onPrimaryPoint = onPrimaryPoint
        nsView.onSecondaryPoint = onSecondaryPoint
        nsView.onHoverPointChange = onHoverPointChange
        nsView.update(
            frame: frame,
            renderMode: renderMode,
            transform: LeniaLabStageTransform(zoom: zoom, offset: offset)
        )
    }
}

final class LeniaLabStageNSView: MTKView {
    private let renderer: LeniaMetalFieldRenderer
    private var trackingAreaHandle: NSTrackingArea?
    private var renderMode: LeniaRenderMode = .smoothMagma
    var transform = LeniaLabStageTransform()
    var gridSize = 0
    var onTransformChange: ((LeniaLabStageTransform) -> Void)?
    var onPrimaryPoint: ((SIMD2<Int>) -> Void)?
    var onSecondaryPoint: ((SIMD2<Int>) -> Void)?
    var onHoverPointChange: ((SIMD2<Int>?) -> Void)?

    init() {
        guard let device = MTLCreateSystemDefaultDevice() else {
            preconditionFailure("Lenia Lab requires a Metal device")
        }
        renderer = LeniaMetalFieldRenderer(device: device)
        super.init(frame: .zero, device: device)
        clearColor = MTLClearColor(red: 0.01, green: 0.01, blue: 0.02, alpha: 1.0)
        colorPixelFormat = .bgra8Unorm
        framebufferOnly = false
        enableSetNeedsDisplay = true
        isPaused = true
        preferredFramesPerSecond = 60
        delegate = renderer
    }

    @available(*, unavailable)
    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var acceptsFirstResponder: Bool { true }
    override var isFlipped: Bool { true }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        window?.acceptsMouseMovedEvents = true
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let trackingAreaHandle {
            removeTrackingArea(trackingAreaHandle)
        }
        let handle = NSTrackingArea(
            rect: .zero,
            options: [.activeInKeyWindow, .inVisibleRect, .mouseMoved, .mouseEnteredAndExited],
            owner: self,
            userInfo: nil
        )
        addTrackingArea(handle)
        trackingAreaHandle = handle
    }

    override func layout() {
        super.layout()
        let scale = window?.backingScaleFactor ?? 2.0
        drawableSize = CGSize(width: bounds.width * scale, height: bounds.height * scale)
        renderer.viewSize = bounds.size
        needsDisplay = true
    }

    func update(frame: LeniaFieldFrame?, renderMode: LeniaRenderMode, transform: LeniaLabStageTransform) {
        gridSize = frame?.width ?? 0
        self.renderMode = renderMode
        self.transform = transform
        renderer.viewSize = bounds.size
        renderer.transform = transform
        renderer.renderMode = renderMode
        renderer.update(frame: frame)
        if gridSize == 0 {
            onHoverPointChange?(nil)
        }
        needsDisplay = true
    }

    override func mouseDown(with event: NSEvent) {
        if event.clickCount == 2 {
            applyTransform(.init())
            return
        }
        forward(event, primary: true)
    }

    override func mouseDragged(with event: NSEvent) {
        forward(event, primary: true)
    }

    override func mouseMoved(with event: NSEvent) {
        forwardHover(event)
    }

    override func rightMouseDown(with event: NSEvent) {
        forward(event, primary: false)
    }

    override func rightMouseDragged(with event: NSEvent) {
        forward(event, primary: false)
    }

    override func mouseEntered(with event: NSEvent) {
        forwardHover(event)
    }

    override func mouseExited(with event: NSEvent) {
        onHoverPointChange?(nil)
    }

    override func magnify(with event: NSEvent) {
        let location = convert(event.locationInWindow, from: nil)
        let next = transform.zoomed(
            to: transform.zoom * (1 + event.magnification),
            around: location,
            viewSize: bounds.size,
            gridSize: gridSize
        )
        applyTransform(next)
    }

    override func scrollWheel(with event: NSEvent) {
        if event.modifierFlags.contains(.option) {
            let location = convert(event.locationInWindow, from: nil)
            let factor = exp(-event.scrollingDeltaY * 0.01)
            let next = transform.zoomed(
                to: transform.zoom * factor,
                around: location,
                viewSize: bounds.size,
                gridSize: gridSize
            )
            applyTransform(next)
            return
        }

        let next = transform.panned(
            by: CGSize(
                width: -event.scrollingDeltaX,
                height: -event.scrollingDeltaY
            )
        )
        applyTransform(next)
    }

    private func forward(_ event: NSEvent, primary: Bool) {
        guard gridSize > 0 else { return }
        let location = convert(event.locationInWindow, from: nil)
        guard let point = transform.gridPoint(for: location, viewSize: bounds.size, gridSize: gridSize) else {
            return
        }
        if primary {
            onPrimaryPoint?(point)
        } else {
            onSecondaryPoint?(point)
        }
    }

    private func forwardHover(_ event: NSEvent) {
        guard gridSize > 0 else {
            onHoverPointChange?(nil)
            return
        }
        let location = convert(event.locationInWindow, from: nil)
        onHoverPointChange?(transform.gridPoint(for: location, viewSize: bounds.size, gridSize: gridSize))
    }

    private func applyTransform(_ next: LeniaLabStageTransform) {
        guard next != transform else { return }
        transform = next
        renderer.transform = next
        onTransformChange?(next)
        needsDisplay = true
    }
}

private struct LabKernelRow: View {
    let kernel: FlowSandboxKernelContract

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text("K\(kernel.id)")
                    .font(.system(.callout, design: .monospaced, weight: .semibold))
                    .foregroundStyle(StudioPalette.ink)
                Spacer()
                Text("r \(formatCompact(kernel.radius)) · m \(formatCompact(kernel.center)) · s \(formatCompact(kernel.sigma)) · h \(formatCompact(kernel.gain))")
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(StudioPalette.mutedInk)
            }

            Text("b \(formatKernelVector(kernel.beta))")
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(StudioPalette.mutedInk)
            Text("w \(formatKernelVector(kernel.weights))")
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(StudioPalette.mutedInk)
            Text("a \(formatKernelVector(kernel.anchors))")
                .font(.system(.callout, design: .monospaced))
                .foregroundStyle(StudioPalette.mutedInk)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(StudioPalette.surfaceSoft)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(StudioPalette.hairline, lineWidth: 1)
        )
    }
}

private struct LabStageHoverOverlay: View {
    let point: SIMD2<Int>?
    let tool: SandboxTool
    let brushRadius: Int
    let selectedStamp: StudioCompareEntry
    let selectedStampPreview: CreatureStamp?
    let transform: LeniaLabStageTransform
    let viewSize: CGSize
    let gridSize: Int

    var body: some View {
        guard let point, gridSize > 0 else {
            return AnyView(EmptyView())
        }

        let rect = transform.imageRect(
            viewSize: viewSize,
            gridSize: CGSize(width: gridSize, height: gridSize)
        )
        guard rect.width > 0, rect.height > 0 else {
            return AnyView(EmptyView())
        }

        let cellWidth = rect.width / CGFloat(gridSize)
        let cellHeight = rect.height / CGFloat(gridSize)
        let center = CGPoint(
            x: rect.minX + (CGFloat(point.x) + 0.5) * cellWidth,
            y: rect.minY + (CGFloat(point.y) + 0.5) * cellHeight
        )
        let previewCellsWidth: Int
        let previewCellsHeight: Int
        let label: String
        if tool == .creatureStamp {
            let stampWidth = max(1, selectedStampPreview?.width ?? (max(1, Int(selectedStamp.creature.params.R.rounded())) * 2 + 1))
            let stampHeight = max(1, selectedStampPreview?.height ?? (max(1, Int(selectedStamp.creature.params.R.rounded())) * 2 + 1))
            previewCellsWidth = stampWidth
            previewCellsHeight = stampHeight
            label = "\(selectedStamp.name) \(stampWidth)x\(stampHeight)"
        } else {
            let diameter = max(1, brushRadius * 2 + 1)
            previewCellsWidth = diameter
            previewCellsHeight = diameter
            label = "\(tool.rawValue) d\(diameter)"
        }
        let previewWidth = CGFloat(previewCellsWidth) * cellWidth
        let previewHeight = CGFloat(previewCellsHeight) * cellHeight
        let accent = hoverAccent(for: tool)
        let labelPosition = CGPoint(
            x: min(max(center.x, 70), viewSize.width - 70),
            y: max(20, center.y - previewHeight / 2 - 14)
        )

        return AnyView(
            ZStack {
                Path { path in
                    path.move(to: CGPoint(x: center.x, y: rect.minY))
                    path.addLine(to: CGPoint(x: center.x, y: rect.maxY))
                    path.move(to: CGPoint(x: rect.minX, y: center.y))
                    path.addLine(to: CGPoint(x: rect.maxX, y: center.y))
                }
                .stroke(accent.opacity(0.18), style: StrokeStyle(lineWidth: 1, dash: [4, 6]))

                if tool == .creatureStamp {
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .fill(accent.opacity(0.16))
                        .frame(width: previewWidth, height: previewHeight)
                        .overlay(
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .stroke(accent.opacity(0.96), style: StrokeStyle(lineWidth: 1.8, dash: [8, 6]))
                        )
                        .position(center)
                } else {
                    Circle()
                        .fill(accent.opacity(0.14))
                        .frame(width: previewWidth, height: previewHeight)
                        .overlay(
                            Circle()
                                .stroke(accent.opacity(0.98), lineWidth: 1.8)
                        )
                        .position(center)
                }

                Circle()
                    .fill(accent)
                    .frame(width: 7, height: 7)
                    .position(center)

                Text(label)
                    .font(.system(.caption2, design: .monospaced, weight: .semibold))
                    .foregroundStyle(StudioPalette.ink)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .fill(StudioPalette.surface)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .stroke(accent.opacity(0.45), lineWidth: 1)
                    )
                    .position(labelPosition)
            }
        )
    }
}

private func hoverAccent(for tool: SandboxTool) -> Color {
    switch tool {
    case .creatureStamp:
        StudioPalette.ocean
    case .food:
        StudioPalette.moss
    case .wall:
        StudioPalette.ink
    case .erase:
        StudioPalette.ember
    case .mutation:
        StudioPalette.ocean
    }
}

private func formatCompact<T: BinaryFloatingPoint>(_ value: T) -> String {
    let double = Double(value)
    if abs(double) >= 10 {
        return String(format: "%.1f", double)
    }
    if abs(double) >= 1 {
        return String(format: "%.2f", double)
    }
    return String(format: "%.3f", double)
}

private func formatKernelVector(_ values: [Float]) -> String {
    values.map(formatCompact).joined(separator: ", ")
}

private func labBackendLabel(_ backend: FlowSandboxBackend) -> String {
    switch backend {
    case .metalFull:
        return "Full Metal"
    case .mlx:
        return "MLX"
    }
}

private func labActivityEstimate(previous: FlowSandboxMetrics?, current: FlowSandboxMetrics) -> Double {
    guard let previous else {
        return 0
    }
    let massDelta = abs(Double(current.massMean - previous.massMean))
    let occupancyDelta = abs(Double(current.occupancy - previous.occupancy))
    let foodDelta = abs(Double(current.foodMean - previous.foodMean))
    let wallDelta = abs(Double(current.wallFraction - previous.wallFraction))
    return massDelta + occupancyDelta * 0.8 + foodDelta * 0.6 + wallDelta * 0.25
}

private func activityAccent(for activity: Double) -> Color {
    switch activity {
    case ..<0.001:
        StudioPalette.mutedInk
    case ..<0.01:
        StudioPalette.ocean
    default:
        StudioPalette.moss
    }
}
