import AppKit
import MetalKit
import SwiftUI
import UniformTypeIdentifiers
import LeniaCore
import LeniaVisuals

@MainActor
final class LeniaLabFrameStore {
    private weak var stageView: LeniaLabStageNSView?
    private var latestFrame: LeniaFieldFrame?

    func attach(_ stageView: LeniaLabStageNSView) {
        guard self.stageView !== stageView else { return }
        self.stageView = stageView
        if let latestFrame {
            stageView.updateFrame(latestFrame)
        }
    }

    func clear() {
        latestFrame = nil
        stageView?.updateFrame(nil)
    }

    func present(_ snapshot: FlowSandboxSnapshot) {
        let frame = LeniaFieldFrame(snapshot: snapshot)
        latestFrame = frame
        stageView?.updateFrame(frame)
    }
}

@MainActor
final class LeniaLabModel: ObservableObject {
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
    @Published var hasSnapshot = false
    @Published var fieldWidth: Int?
    @Published var latestStep = 0
    @Published var latestMetrics: FlowSandboxMetrics?

    let frames: LeniaLabFrameStore
    private var runtime: LabRuntimeHandle?
    private var snapshotTask: Task<Void, Never>?
    private var targetSpeedCap = 60

    init(frameStore: LeniaLabFrameStore = LeniaLabFrameStore()) {
        self.frames = frameStore
    }

    func rebuildWorld(
        sourceEntryID: String,
        baseConfigData: Data,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool = false
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
        clearFrameState()
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
                let runtimeConfig = try loadRuntimeConfig(
                    from: baseConfigData,
                    overrides: ["backend": backend.rawValue]
                )
                let runtime: LabRuntimeHandle
                if let engine = makeLeniaInteractiveEngine(from: runtimeConfig, backend: backend) {
                    runtime = .engine(engine)
                } else {
                    runtime = try .replay(
                        CanonicalLabRuntime(
                            baseConfigData: baseConfigData,
                            backend: backend
                        )
                    )
                }
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
                self.clearFrameState()
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
        shouldRun: Bool = false
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
        clearFrameState()
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
                let runtime: LabRuntimeHandle
                if let engine = makeLeniaInteractiveEngine(from: runtimeConfig, backend: backend) {
                    runtime = .engine(engine)
                } else {
                    runtime = try .replay(
                        CanonicalLabRuntime(
                            runtimeConfig: runtimeConfig
                        )
                    )
                }
                await runtime.setSpeedCap(hz: speedCap)
                await runtime.setAutoFoodSpawn(
                    enabled: false,
                    probability: 0.03,
                    patchSize: 12,
                    value: 0.35
                )
                let worldContract = await runtime.worldContract()
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
                self.clearFrameState()
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
        clearFrameState()
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
                self.applyFrameSnapshot(snapshot)
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
                self.clearFrameState()
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
                self.applyFrameSnapshot(snapshot)
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

    private func clearFrameState() {
        frames.clear()
        hasSnapshot = false
        fieldWidth = nil
        latestStep = 0
        latestMetrics = nil
    }

    private func applyFrameSnapshot(_ snapshot: FlowSandboxSnapshot) {
        frames.present(snapshot)
        hasSnapshot = true
        fieldWidth = snapshot.width
        latestStep = snapshot.step
        latestMetrics = snapshot.metrics
    }

    private func startSnapshotLoop() {
        snapshotTask?.cancel()
        guard let runtime else { return }
        let pausedDelay: Duration = .milliseconds(120)
        snapshotTask = Task {
            var lastMetricsRefresh = ContinuousClock.now - .milliseconds(250)
            var fpsTimestamps = [Date]()
            var previousMetrics: FlowSandboxMetrics?
            var latestActivity = 0.0
            var latestRuntimeTelemetry = FlowSandboxRuntimeTelemetry(lastStepDurationMs: 0, realizedStepRateHz: 0)
            fpsTimestamps.reserveCapacity(24)
            while !Task.isCancelled {
                let frameStartedAt = ContinuousClock.now
                let refreshMetrics = ContinuousClock.now - lastMetricsRefresh >= .milliseconds(250)
                let projection = await MainActor.run { self.activeProjection }
                let snapshot = await runtime.snapshot(
                    refreshMetrics: refreshMetrics,
                    projection: projection
                )
                if refreshMetrics {
                    latestRuntimeTelemetry = await runtime.telemetry()
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
                let assessment = refreshMetrics ? await MainActor.run {
                    labHealthAssessment(
                        metrics: snapshot.metrics,
                        isRunning: self.isRunning,
                        activity: latestActivity,
                        stepDurationMs: latestRuntimeTelemetry.lastStepDurationMs,
                        stepRateHz: latestRuntimeTelemetry.realizedStepRateHz,
                        snapshotFps: snapshotFps,
                        speedCap: self.targetSpeedCap,
                        history: self.activityHistory
                    )
                } : nil
                await MainActor.run {
                    self.frames.present(snapshot)
                    if !self.hasSnapshot {
                        self.hasSnapshot = true
                    }
                    if self.fieldWidth != snapshot.width {
                        self.fieldWidth = snapshot.width
                    }
                    if refreshMetrics {
                        self.snapshotFps = snapshotFps
                        self.latestStep = snapshot.step
                        self.latestMetrics = snapshot.metrics
                        self.activityEstimate = latestActivity
                        self.stepDurationMs = latestRuntimeTelemetry.lastStepDurationMs
                        self.realizedStepRateHz = latestRuntimeTelemetry.realizedStepRateHz
                    }
                    if refreshMetrics {
                        self.activityHistory.append(latestActivity)
                        if self.activityHistory.count > 48 {
                            self.activityHistory.removeFirst(self.activityHistory.count - 48)
                        }
                    }
                    if refreshMetrics, let assessment {
                        self.healthState = assessment.state
                        self.healthSummary = assessment.summary
                        self.healthWarnings = assessment.warnings
                    }
                }
                let targetDelay = await MainActor.run {
                    guard self.isRunning else { return pausedDelay }
                    let frameCap = max(1, min(60, self.targetSpeedCap))
                    return .milliseconds(max(1, Int((1_000.0 / Double(frameCap)).rounded())))
                }
                let elapsed = ContinuousClock.now - frameStartedAt
                let remaining = targetDelay - elapsed
                if remaining > .zero {
                    try? await Task.sleep(for: remaining)
                }
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
        let stamp = buildWarmCreatureStamp(
            id: UUID(uuidString: entry.id.components(separatedBy: ":").last ?? "") ?? UUID(),
            name: entry.name,
            params: entry.creature.params,
            seed: entry.creature.seed,
            warmupSteps: 80,
            warmupGridSize: 128,
            cropThreshold: 0.01,
            padding: 4
        )
        cache[entry.id] = stamp
        return stamp
    }
}

struct LeniaLabView: View {
    @EnvironmentObject private var appState: AppState
    @StateObject private var model: LeniaLabModel
    @State private var frameStore: LeniaLabFrameStore
    @StateObject private var track1Catalog = Track1TaxonomyCatalogStore()
    @AppStorage("track1ConfigRoot") private var track1ConfigRoot = ""
    @State private var gridPreset: LabGridPreset = .compact128
    @State private var backend: FlowSandboxBackend = .metalFull
    @State private var renderMode: LeniaRenderMode = .smoothMagma
    @State private var primaryTool: SandboxTool = .food
    @State private var secondaryTool: SandboxTool = .erase
    @State private var brushRadius = 3.0
    @State private var brushStrength = 0.35
    @State private var speedCap = 60
    @State private var diagnosticsEnabled = false
    @State private var autoFoodEnabled = false
    @State private var worldSelection: LabWorldSelection = .preset("orbium-sandbox")
    @State private var selectedStampID: String?
    @State private var selectedStampPreview: CreatureStamp?
    @State private var worldDraft: LabWorldDraft?
    @State private var worldDraftError: String?
    @State private var stageZoom: CGFloat = 1.35
    @State private var stageOffset: CGSize = .zero
    @State private var hoveredGridPoint: SIMD2<Int>?
    @State private var showTTExportImporter = false
    @State private var showContractEditor = false
    @State private var selectedTrack1FamilyID: String?
    @State private var inspectorPanel: LabInspectorPanel = .bay

    private let stampCache = LeniaLabStampCache()
    private static let backendOrder: [FlowSandboxBackend] = [.metalFull, .mlx]
    private static let missionPresets = buildLabMissionPresets()

    init() {
        let frameStore = LeniaLabFrameStore()
        _frameStore = State(initialValue: frameStore)
        _model = StateObject(wrappedValue: LeniaLabModel(frameStore: frameStore))
    }

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
        case .track1Config(let path):
            return track1Catalog.catalog.config(path: path)?.studioEntry() ?? fallbackTrack1Entry(path: path)
        }
    }

    private var selectedWorldPreset: LabMissionPreset? {
        guard case .preset(let presetID) = worldSelection else { return nil }
        return Self.missionPresets.first(where: { $0.id == presetID })
    }

    private var activeWorldEntry: StudioCompareEntry? {
        guard let activeWorldEntryID = model.activeWorldEntryID else { return nil }
        if let preset = Self.missionPresets.first(where: { $0.entry.id == activeWorldEntryID }) {
            return preset.entry
        }
        if let selectedStampID,
           selectedStampID == activeWorldEntryID,
           let selected = stampEntries.first(where: { $0.id == selectedStampID }) {
            return selected
        }
        if activeWorldEntryID.hasPrefix("track1:") {
            let path = String(activeWorldEntryID.dropFirst("track1:".count))
            return track1Catalog.catalog.config(path: path)?.studioEntry()
        }
        return stampEntries.first(where: { $0.id == activeWorldEntryID })
    }

    private var selectedTrack1Family: Track1TaxonomyFamily? {
        let familyID = selectedTrack1FamilyID
            ?? selectedTrack1Config?.family
            ?? track1Catalog.catalog.families.first?.id
        guard let familyID else { return nil }
        return track1Catalog.catalog.families.first(where: { $0.id == familyID })
    }

    private var selectedTrack1Config: Track1TaxonomyConfig? {
        guard case .track1Config(let path) = worldSelection else { return nil }
        return track1Catalog.catalog.config(path: path)
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
                if proxy.size.width < 1_080 {
                    ScrollView {
                        VStack(spacing: 10) {
                            stageSurface
                            controlSurface
                            inspectorSurface
                        }
                        .padding(12)
                    }
                } else {
                    let inspectorWidth = min(420, max(340, proxy.size.width * 0.25))
                    ScrollView {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(spacing: 10) {
                                stageSurface
                                controlSurface
                            }
                            .frame(minWidth: 620, maxWidth: .infinity)
                            .layoutPriority(1)

                            VStack(spacing: 10) {
                                inspectorSurface
                            }
                            .frame(width: inspectorWidth)
                        }
                        .padding(12)
                        .frame(minWidth: proxy.size.width, alignment: .topLeading)
                    }
                }
            }
        }
        .background(
            StudioSceneBackground()
        )
        .navigationTitle("Lenia Lab")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showTTExportImporter = true
                } label: {
                    Image(systemName: "square.and.arrow.down")
                }
                .help("Open TT export")
            }
        }
        .fileImporter(isPresented: $showTTExportImporter, allowedContentTypes: [.json], allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let url = urls.first {
                model.loadFrameSequence(manifestURL: url)
                stageZoom = 1.35
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
        .task(id: track1ConfigRoot) {
            if track1ConfigRoot.isEmpty {
                if let defaultRoot = defaultTrack1ConfigRoot() {
                    track1ConfigRoot = defaultRoot
                }
                return
            }
            track1Catalog.load(rootPath: track1ConfigRoot)
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
        .onChange(of: worldSelection) { _, newSelection in
            stageZoom = 1.35
            stageOffset = .zero
            if case .track1Config = newSelection {
                return
            }
            syncWorldDraft(rebuild: true)
        }
        .onDisappear {
            model.shutdown()
        }
    }

    private var stageSurface: some View {
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    Button {
                        model.setRunning(!model.isRunning)
                    } label: {
                        Label(model.isRunning ? "Hold" : "Run", systemImage: model.isRunning ? "pause.fill" : "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)

                    Button {
                        model.reset()
                    } label: {
                        Image(systemName: "arrow.counterclockwise")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Reset runtime")

                    Button {
                        rebuildActiveWorld()
                    } label: {
                        Image(systemName: "checkmark.seal")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(worldDraft == nil)
                    .help("Apply contract")

                    Button {
                        selectedStampID = selectedStampEntry.id
                        worldSelection = .stamp(selectedStampEntry.id)
                    } label: {
                        Image(systemName: "scope")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Build world from selected stamp")

                    Text(stageStatusLine)
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                        .truncationMode(.tail)

                    Spacer(minLength: 8)

                    if model.availableProjections.count > 1 {
                        Picker("Field", selection: $model.activeProjection) {
                            ForEach(model.availableProjections) { projection in
                                Text(projection.label).tag(projection)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .controlSize(.small)
                        .frame(width: 238)
                    }

                    Menu {
                        ForEach(Self.backendOrder) { option in
                            Button {
                                backend = option
                            } label: {
                                if backend == option {
                                    Label(labBackendLabel(option), systemImage: "checkmark")
                                } else {
                                    Text(labBackendLabel(option))
                                }
                            }
                        }
                    } label: {
                        Image(systemName: "cpu")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Compute backend: \(labBackendLabel(backend))")

                    Menu {
                        ForEach(LeniaRenderMode.allCases) { mode in
                            Button {
                                renderMode = mode
                            } label: {
                                if renderMode == mode {
                                    Label(mode.rawValue, systemImage: "checkmark")
                                } else {
                                    Text(mode.rawValue)
                                }
                            }
                        }
                    } label: {
                        Image(systemName: "paintpalette")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Color map")

                    Button {
                        adjustStageZoom(by: 0.85)
                    } label: {
                        Image(systemName: "minus.magnifyingglass")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Text("\(Int((stageZoom * 100).rounded()))%")
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .frame(width: 46)

                    Button {
                        adjustStageZoom(by: 1.15)
                    } label: {
                        Image(systemName: "plus.magnifyingglass")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Button("Focus") {
                        updateStageTransform(LeniaLabStageTransform(zoom: 1.85, offset: .zero))
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Button("Fit") {
                        updateStageTransform(.init())
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }

                if diagnosticsEnabled {
                    ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        LabTacticalReadout(label: "State", value: model.isRunning ? "Running" : "Armed", accent: model.isRunning ? StudioPalette.moss : StudioPalette.ember)
                        LabTacticalReadout(label: "Mode", value: model.runtimeModeLabel, accent: StudioPalette.ink)
                        LabTacticalReadout(label: "Compute", value: labBackendLabel(model.activeBackend), accent: StudioPalette.ocean)
                        let resolvedGrid = model.worldContract?.gridSize ?? model.fieldWidth ?? gridPreset.rawValue
                        LabTacticalReadout(label: "Grid", value: "\(resolvedGrid)x\(resolvedGrid)", accent: StudioPalette.ocean)
                        if let contract = model.worldContract {
                            LabTacticalReadout(label: "Lanes", value: "\(contract.channels)m/\(contract.parameterFieldMode.displayName)", accent: StudioPalette.ocean)
                            LabTacticalReadout(label: "Kernels", value: "\(contract.kernelCount)", accent: StudioPalette.ember)
                            LabTacticalReadout(label: "Radius", value: formatCompact(contract.radius), accent: StudioPalette.moss)
                        }
                        LabTacticalReadout(label: "Step", value: "\(model.latestStep)", accent: StudioPalette.ember)
                        LabTacticalReadout(label: "Activity", value: String(format: "%.4f", model.activityEstimate), accent: activityAccent(for: model.activityEstimate))
                        if let metrics = model.latestMetrics {
                            LabTacticalReadout(label: "Mass", value: formatCompact(metrics.massMean), accent: StudioPalette.moss)
                            LabTacticalReadout(label: "Food", value: formatCompact(metrics.foodMean), accent: StudioPalette.ocean)
                        }
                        LabTacticalReadout(label: "View", value: model.snapshotFps > 0 ? String(format: "%.0f fps", model.snapshotFps) : "--", accent: StudioPalette.ink)
                        LabTacticalReadout(label: "Ghost", value: primaryGhostCompactLabel, accent: hoverAccent(for: primaryTool))
                        if let hoveredGridPoint {
                            LabTacticalReadout(label: "Cursor", value: "\(hoveredGridPoint.x),\(hoveredGridPoint.y)", accent: StudioPalette.ink)
                        }
                    }
                    }
                }

                if let runtimeStatusMessage = model.runtimeStatusMessage, !model.hasSnapshot {
                    ContentUnavailableView(
                        "World failed to load",
                        systemImage: "exclamationmark.triangle",
                        description: Text(runtimeStatusMessage)
                    )
                    .frame(minHeight: 500)
                } else {
                    LabStageFrameSurface(
                        frameStore: frameStore,
                        renderMode: renderMode,
                        zoom: stageZoom,
                        offset: stageOffset,
                        gridSize: model.fieldWidth ?? gridPreset.rawValue,
                        projectionLabel: model.activeProjection.label,
                        healthLabel: model.healthState.label,
                        healthAccent: model.healthState.accent,
                        hoveredGridPoint: hoveredGridPoint,
                        primaryTool: primaryTool,
                        brushRadius: Int(brushRadius.rounded()),
                        selectedStampEntry: selectedStampEntry,
                        selectedStampPreview: selectedStampPreview,
                        onTransformChange: updateStageTransform,
                        onPrimaryPoint: { handleStagePoint($0, tool: primaryTool) },
                        onSecondaryPoint: { handleStagePoint($0, tool: secondaryTool) },
                        onHoverPointChange: { hoveredGridPoint = $0 },
                        onBrushRadiusDelta: adjustBrushRadius
                    )
                    .frame(minHeight: 420)
                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .stroke(StudioPalette.hairline.opacity(0.85), lineWidth: 1)
                    )
                }
            }
        }
    }

    private var controlSurface: some View {
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 10) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
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
                }

                Divider()

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 10)], alignment: .leading, spacing: 10) {
                    LabControlGroup(label: "Primary") {
                        Picker("Primary", selection: $primaryTool) {
                            ForEach(SandboxTool.allCases) { tool in
                                Text(tool.rawValue).tag(tool)
                            }
                        }
                        .controlSize(.small)
                    }

                    LabControlGroup(label: "Secondary") {
                        Picker("Secondary", selection: $secondaryTool) {
                            ForEach(SandboxTool.allCases) { tool in
                                Text(tool.rawValue).tag(tool)
                            }
                        }
                        .controlSize(.small)
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    LabSliderRow(label: "Brush Radius", value: "\(Int(brushRadius))") {
                        Slider(value: $brushRadius, in: labBrushRadiusRange, step: 1)
                            .controlSize(.small)
                    }
                    LabSliderRow(label: "Brush Strength", value: String(format: "%.2f", brushStrength)) {
                        Slider(value: $brushStrength, in: 0.05...1.0, step: 0.05)
                            .controlSize(.small)
                    }
                }

                HStack(spacing: 8) {
                    Toggle("Diagnostics", isOn: $diagnosticsEnabled)
                        .toggleStyle(.button)
                        .controlSize(.small)
                    Toggle("Auto Food", isOn: $autoFoodEnabled)
                        .toggleStyle(.button)
                        .controlSize(.small)
                    Spacer(minLength: 6)
                    Text(primaryGhostSummary)
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                if diagnosticsEnabled, let metrics = model.latestMetrics {
                    HStack(spacing: 6) {
                        LabTacticalReadout(label: "Occ", value: formatCompact(metrics.occupancy), accent: StudioPalette.ember)
                        LabTacticalReadout(label: "Wall", value: formatCompact(metrics.wallFraction), accent: StudioPalette.ink)
                        LabTacticalReadout(label: "Peak", value: formatCompact(metrics.massPeak), accent: StudioPalette.moss)
                        LabTacticalReadout(label: "NaN", value: formatCompact(metrics.nonFiniteFraction), accent: StudioPalette.ember)
                    }
                }

                DisclosureGroup(isExpanded: $showContractEditor) {
                    contractEditorContent
                } label: {
                    HStack {
                        Text("Advanced")
                            .font(StudioType.body)
                            .foregroundStyle(StudioPalette.ink)
                        Spacer()
                        Text(worldDraft?.sourceSummary ?? "--")
                            .font(StudioType.dataSmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
            }
        }
    }

    private var inspectorSurface: some View {
        VStack(spacing: 10) {
            StudioSurface(style: .console) {
                Picker("Inspector", selection: $inspectorPanel) {
                    ForEach(LabInspectorPanel.allCases) { panel in
                        Text(panel.title).tag(panel)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .controlSize(.small)
            }

            switch inspectorPanel {
            case .bay:
                paletteSurface
            case .catalog:
                taxonomySurface
            case .runtime:
                universeSurface
            case .signals:
                telemetrySurface
            }
        }
    }

    @ViewBuilder
    private var contractEditorContent: some View {
        if let worldDraft {
            VStack(alignment: .leading, spacing: 10) {
                LabCompactKeyValueRow(label: "Basis", value: worldDraft.sourceSummary)
                LabCompactKeyValueRow(label: "Routing", value: worldDraft.connectivitySummary)

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 10)], alignment: .leading, spacing: 10) {
                    LabControlGroup(label: "Grid") {
                        Picker("Grid", selection: $gridPreset) {
                            ForEach(LabGridPreset.allCases) { preset in
                                Text("\(preset.rawValue)x\(preset.rawValue)").tag(preset)
                            }
                        }
                        .pickerStyle(.segmented)
                        .controlSize(.small)
                    }

                    LabControlGroup(label: "Speed") {
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

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 10)], alignment: .leading, spacing: 10) {
                    LabControlGroup(label: "Matter lanes") {
                        Picker("Matter lanes", selection: channelCountBinding) {
                            ForEach(1...4, id: \.self) { channelCount in
                                Text("\(channelCount)").tag(channelCount)
                            }
                        }
                        .pickerStyle(.segmented)
                        .controlSize(.small)
                    }

                    LabControlGroup(label: "Border") {
                        Picker("Border", selection: borderBinding) {
                            Text("Torus").tag("torus")
                            Text("Wall").tag("wall")
                        }
                        .pickerStyle(.segmented)
                        .controlSize(.small)
                    }
                }

                HStack(spacing: 8) {
                    Toggle("Parameter transport", isOn: parameterEmbeddingBinding)
                        .toggleStyle(.button)
                        .controlSize(.small)
                    Toggle("Food field", isOn: foodEnabledBinding)
                        .toggleStyle(.button)
                        .controlSize(.small)
                }

                if worldDraft.parameterEmbeddingEnabled {
                    LabControlGroup(label: "Parameter mix") {
                        Picker("Parameter mix", selection: parameterMixBinding) {
                            Text("Avg").tag("avg")
                            Text("Softmax").tag("softmax")
                        }
                        .pickerStyle(.segmented)
                        .controlSize(.small)
                    }
                }

                if worldDraft.foodEnabled {
                    LabControlGroup(label: "Food lane") {
                        Picker("Food lane", selection: foodChannelBinding) {
                            ForEach(0..<worldDraft.channelCount, id: \.self) { channel in
                                Text("c\(channel)").tag(channel)
                            }
                        }
                        .pickerStyle(.segmented)
                        .controlSize(.small)
                    }
                }

                LabControlGroup(label: "Init seed") {
                    Stepper(value: initSeedBinding, in: 0...999_999) {
                        Text("\(worldDraft.initSeed)")
                            .font(StudioType.data)
                            .foregroundStyle(StudioPalette.ink)
                    }
                    .controlSize(.small)
                }

                LabSliderRow(label: "Patch Size", value: "\(worldDraft.patchSize)") {
                    Slider(value: patchSizeBinding, in: 12...72, step: 2)
                        .controlSize(.small)
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text("Connectivity matrix")
                            .font(StudioType.title)
                            .foregroundStyle(StudioPalette.ink)
                        Spacer()
                        Text("\(worldDraft.kernelCount) kernels")
                            .font(StudioType.dataSmall)
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
                        .font(StudioType.body)
                        .foregroundStyle(.red)
                }
            }
        } else if let worldDraftError {
            Text(worldDraftError)
                .font(StudioType.body)
                .foregroundStyle(.red)
        } else {
            Text("No editable runtime contract is available for this world.")
                .font(StudioType.body)
                .foregroundStyle(StudioPalette.mutedInk)
        }
    }

    private var taxonomySurface: some View {
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    if track1Catalog.isLoading {
                        ProgressView()
                            .controlSize(.small)
                            .scaleEffect(0.72)
                    }
                    Text("\(track1Catalog.catalog.families.count) families · \(track1Catalog.catalog.labLoadableCount) loadable")
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer(minLength: 8)
                    Button {
                        track1Catalog.load(rootPath: track1ConfigRoot)
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Rescan Track 1 configs")

                    Button {
                        chooseTrack1Root()
                    } label: {
                        Image(systemName: "folder")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Choose Track 1 config root")
                }

                if let error = track1Catalog.error {
                    Text(error)
                        .font(StudioType.bodySmall)
                        .foregroundStyle(StudioPalette.ember)
                        .lineLimit(3)
                }

                if case .track1Config = worldSelection, let worldDraftError {
                    Text(worldDraftError)
                        .font(StudioType.bodySmall)
                        .foregroundStyle(StudioPalette.ember)
                        .lineLimit(3)
                }

                if !track1Catalog.catalog.families.isEmpty {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(track1Catalog.catalog.families) { family in
                                Track1FamilyChip(
                                    family: family,
                                    isSelected: selectedTrack1Family?.id == family.id,
                                    onSelect: {
                                        selectedTrack1FamilyID = family.id
                                    }
                                )
                            }
                        }
                        .padding(.vertical, 1)
                    }

                    if let selectedTrack1Family {
                        Track1TaxonomyFamilyPanel(
                            family: selectedTrack1Family,
                            selectedPath: selectedTrack1Config?.path,
                            onLoad: loadTrack1Config
                        )
                    }

                    if let selectedTrack1Config {
                        DisclosureGroup("Details") {
                            LabInfoSection(title: "Selected lineage") {
                                LabCompactKeyValueRow(label: "Family", value: selectedTrack1Config.family)
                                LabCompactKeyValueRow(label: "Genus", value: selectedTrack1Config.genus)
                                LabCompactKeyValueRow(label: "Species", value: selectedTrack1Config.displayName)
                                LabCompactKeyValueRow(label: "Pattern", value: selectedTrack1Config.patternID)
                                LabCompactKeyValueRow(label: "Runtime", value: selectedTrack1Config.runtimeSummary)
                                if !track1ConfigRoot.isEmpty {
                                    LabCompactKeyValueRow(label: "Root", value: track1RootDisplay(track1ConfigRoot))
                                }
                            }
                        }
                        .font(StudioType.body)
                    }
                } else if !track1Catalog.isLoading {
                    Text("No Track 1 taxonomy loaded.")
                        .font(StudioType.body)
                        .foregroundStyle(StudioPalette.mutedInk)
                }
            }
        }
    }

    private var universeSurface: some View {
        StudioSurface(
            title: "Runtime Contract",
            subtitle: "Physics, topology, and execution state",
            style: .console
        ) {
            if let contract = model.worldContract {
                VStack(alignment: .leading, spacing: 14) {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 72), spacing: 8)], alignment: .leading, spacing: 8) {
                        StudioMetricPill(label: "Matter", value: "\(contract.channels)", accent: StudioPalette.ocean, style: .console)
                        StudioMetricPill(label: "Params", value: contract.parameterFieldMode.displayName, accent: StudioPalette.ocean, style: .console)
                        StudioMetricPill(label: "Kernels", value: "\(contract.kernelCount)", accent: StudioPalette.ember, style: .console)
                        StudioMetricPill(label: "Radius", value: String(format: "%.1f", contract.radius), accent: StudioPalette.moss, style: .console)
                    }

                    LabInfoSection(title: "Runtime") {
                        LabCompactKeyValueRow(label: "Mode", value: model.runtimeModeLabel)
                        LabCompactKeyValueRow(
                            label: "Backend",
                            value: model.externalReplayTitle == nil ? labBackendLabel(contract.backend) : "Tenstorrent export"
                        )
                        LabCompactKeyValueRow(label: "Health", value: model.healthState.label)
                        LabCompactKeyValueRow(label: "Projection", value: model.activeProjection.label)
                    }

                    LabInfoSection(title: "Cadence") {
                        LabCompactKeyValueRow(
                            label: "View",
                            value: model.snapshotFps > 0 ? String(format: "%.0f fps", model.snapshotFps) : "--"
                        )
                        LabCompactKeyValueRow(
                            label: "Solver",
                            value: model.realizedStepRateHz > 0 ? String(format: "%.0f Hz · %.2f ms", model.realizedStepRateHz, model.stepDurationMs) : "--"
                        )
                        LabCompactKeyValueRow(label: "Speed cap", value: "\(speedCap) Hz")
                    }

                    LabInfoSection(title: "World source") {
                        LabCompactKeyValueRow(label: "Basis", value: activeWorldEntry?.name ?? "--")
                        if let worldDraft {
                            LabCompactKeyValueRow(label: "Draft", value: worldDraft.sourceSummary)
                        }
                        LabCompactKeyValueRow(label: "Stamp", value: selectedStampEntry.name)
                        if let worldDraft {
                            LabCompactKeyValueRow(label: "Init seed", value: "\(worldDraft.initSeed)")
                        }
                    }

                    Divider()

                    DisclosureGroup("Contract details") {
                        VStack(alignment: .leading, spacing: 8) {
                            LabCompactKeyValueRow(label: "Engine", value: contract.executionSummary)
                            LabCompactKeyValueRow(label: "Fields", value: contract.fieldSummary)
                            LabCompactKeyValueRow(label: "Capabilities", value: contract.featureSummary)
                            LabCompactKeyValueRow(label: "Grid", value: "\(contract.gridSize)x\(contract.gridSize)")
                            LabCompactKeyValueRow(label: "Profile", value: contract.kernelProfile)
                            LabCompactKeyValueRow(label: "Flow", value: "dt \(formatCompact(contract.dt)) · dd \(contract.dd) · sigma \(formatCompact(contract.sigma))")
                            LabCompactKeyValueRow(label: "Border", value: "\(contract.border) · n \(contract.n) · thetaA \(formatCompact(contract.thetaA))")
                            LabCompactKeyValueRow(label: "Kernel seed", value: "\(contract.seed)")
                            LabCompactKeyValueRow(label: "Connectivity", value: contract.connectivitySummary)
                            LabCompactKeyValueRow(label: "Stamp source", value: selectedStampSourceSummary)
                            if let replayReference = activeWorldEntry?.replayReference {
                                LabCompactKeyValueRow(label: "Replay base", value: replayReference.baseConfigPath)
                            }
                            if let worldDraft, worldDraft.usesRandomKernelBank {
                                LabCompactKeyValueRow(label: "Param seed", value: "\(worldDraft.paramsSeed)")
                            }
                            if let saved = selectedStampEntry.savedCreature {
                                LabCompactKeyValueRow(label: "Init family", value: saved.initialConditionFamily ?? "--")
                            }
                        }
                    }

                    DisclosureGroup("Kernel bank (\(contract.kernels.count))") {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(contract.kernels) { kernel in
                                LabKernelRow(kernel: kernel)
                            }
                        }
                    }
                    .font(StudioType.body)
                }
            } else if let runtimeStatusMessage = model.runtimeStatusMessage {
                Text(runtimeStatusMessage)
                    .font(StudioType.body)
                    .foregroundStyle(StudioPalette.mutedInk)
            } else {
                Text("Runtime contract is materializing.")
                    .font(StudioType.body)
                    .foregroundStyle(StudioPalette.mutedInk)
            }
        }
    }

    private var paletteSurface: some View {
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 12) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 14) {
                        ForEach(stampEntries) { entry in
                            LabPaletteStampCard(
                                entry: entry,
                                isSelected: selectedStampID == entry.id,
                                onSelect: { selectedStampID = entry.id },
                                onSetWorld: {
                                    selectedStampID = entry.id
                                    worldSelection = .stamp(entry.id)
                                }
                            )
                        }
                    }
                }
            }
        }
    }

    private var telemetrySurface: some View {
        StudioSurface(title: "Signal Telemetry", subtitle: "Health, cadence, and saturation", style: .console) {
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
                    .font(StudioType.body)
                    .foregroundStyle(StudioPalette.ink)

                if !model.healthWarnings.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(model.healthWarnings.enumerated()), id: \.offset) { _, warning in
                            Text(warning)
                                .font(StudioType.body)
                                .foregroundStyle(StudioPalette.mutedInk)
                        }
                    }
                }

                if let metrics = model.latestMetrics {
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
                        .font(StudioType.body)
                        .foregroundStyle(StudioPalette.mutedInk)
                }
            }
        }
    }

    private var stageStatusLine: String {
        if let externalReplayTitle = model.externalReplayTitle {
            return "\(externalReplayTitle) · \(model.isRunning ? "playing" : "loaded")"
        }
        if let activeWorldEntry {
            return "\(activeWorldEntry.name) · \(model.isRunning ? "running" : "ready")"
        }
        return "Building world"
    }

    private func syncWorldDraft(rebuild: Bool) {
        worldDraftError = nil
        do {
            let nextDraft: LabWorldDraft
            if case .track1Config(let path) = worldSelection {
                let basisName = track1Catalog.catalog.config(path: path)?.displayName
                    ?? URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
                nextDraft = try makeTrack1WorldDraft(path: path, basisName: basisName)
            } else if let preset = selectedWorldPreset, let defaultDraft = preset.defaultDraft {
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
            worldDraftError = "Failed to prepare world contract: \(labErrorDescription(error))"
        }
    }

    private func loadTrack1Config(_ config: Track1TaxonomyConfig) {
        guard config.isLabLoadable else {
            worldDraftError = "Track 1 config is cataloged but not loadable by the current Lab runtime: \(config.implementationMode)."
            return
        }
        selectedTrack1FamilyID = config.family
        worldSelection = .track1Config(config.path)
        stageZoom = 1.35
        stageOffset = .zero
        worldDraftError = nil
        do {
            let nextDraft = try makeTrack1WorldDraft(config: config)
            worldDraft = nextDraft
            if let matchingGrid = LabGridPreset.allCases.first(where: { $0.rawValue == nextDraft.gridSize }),
               matchingGrid != gridPreset {
                gridPreset = matchingGrid
            }
            model.rebuildWorld(
                sourceEntryID: config.studioEntry().id,
                runtimeConfig: nextDraft.runtimeConfig(overridingBackend: backend),
                backend: backend,
                speedCap: speedCap,
                shouldRun: false
            )
        } catch {
            worldDraft = nil
            worldDraftError = "Failed to load Track 1 config: \(labErrorDescription(error))"
        }
    }

    private func chooseTrack1Root() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Use Root"
        panel.message = "Select the directory containing Track 1 runtime configs."
        if !track1ConfigRoot.isEmpty {
            panel.directoryURL = URL(fileURLWithPath: track1ConfigRoot, isDirectory: true)
        }
        guard panel.runModal() == .OK, let url = panel.url else { return }
        track1ConfigRoot = url.path
    }

    private func track1RootDisplay(_ path: String) -> String {
        let components = URL(fileURLWithPath: path).pathComponents
        guard components.count > 3 else { return path }
        return ".../" + components.suffix(3).joined(separator: "/")
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
                shouldRun: false
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
                shouldRun: false
            )
        } catch {
            worldDraftError = "Failed to load replay base: \(labErrorDescription(error))"
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

    private func adjustBrushRadius(by delta: Int) {
        brushRadius = labBrushRadiusStepping(from: brushRadius, delta: delta)
    }
}

let labBrushRadiusRange: ClosedRange<Double> = 1...16

func labBrushRadiusStepping(from radius: Double, delta: Int) -> Double {
    min(labBrushRadiusRange.upperBound, max(labBrushRadiusRange.lowerBound, radius + Double(delta)))
}

private enum LabInspectorPanel: String, CaseIterable, Identifiable {
    case bay
    case catalog
    case runtime
    case signals

    var id: String { rawValue }

    var title: String {
        switch self {
        case .bay:
            "Bay"
        case .catalog:
            "Catalog"
        case .runtime:
            "Runtime"
        case .signals:
            "Signals"
        }
    }
}

private func labErrorDescription(_ error: Error) -> String {
    let description = String(describing: error)
    if !description.isEmpty, description != error.localizedDescription {
        return description
    }
    return error.localizedDescription
}

enum LabHealthState: Equatable {
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

struct LabHealthAssessment {
    let state: LabHealthState
    let summary: String
    let warnings: [String]
}

func labHealthAssessment(
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
    if metrics.massPeak > 1.0 {
        warnings.append("Local density is above display range; the renderer clips the brightest cells.")
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

    if metrics.nonFiniteFraction > 0 {
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

private struct LabTacticalReadout: View {
    let label: String
    let value: String
    let accent: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text(label.uppercased())
                .font(StudioType.label)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(StudioType.data)
                .foregroundStyle(accent)
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(
            Rectangle()
                .fill(StudioPalette.consoleControl.opacity(0.92))
        )
        .overlay(
            Rectangle()
                .stroke(accent.opacity(0.35), lineWidth: 1)
        )
    }
}

private struct LabTacticalStageOverlay: View {
    let gridSize: Int
    let zoom: CGFloat
    let projectionLabel: String
    let healthLabel: String
    let healthAccent: Color

    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                Path { path in
                    let columns = 8
                    for index in 1..<columns {
                        let x = size.width * CGFloat(index) / CGFloat(columns)
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: size.height))
                    }
                    for index in 1..<columns {
                        let y = size.height * CGFloat(index) / CGFloat(columns)
                        path.move(to: CGPoint(x: 0, y: y))
                        path.addLine(to: CGPoint(x: size.width, y: y))
                    }
                }
                .stroke(StudioPalette.ocean.opacity(0.07), lineWidth: 1)

                Path { path in
                    let length: CGFloat = 34
                    let inset: CGFloat = 12
                    path.move(to: CGPoint(x: inset, y: inset + length))
                    path.addLine(to: CGPoint(x: inset, y: inset))
                    path.addLine(to: CGPoint(x: inset + length, y: inset))

                    path.move(to: CGPoint(x: size.width - inset - length, y: inset))
                    path.addLine(to: CGPoint(x: size.width - inset, y: inset))
                    path.addLine(to: CGPoint(x: size.width - inset, y: inset + length))

                    path.move(to: CGPoint(x: inset, y: size.height - inset - length))
                    path.addLine(to: CGPoint(x: inset, y: size.height - inset))
                    path.addLine(to: CGPoint(x: inset + length, y: size.height - inset))

                    path.move(to: CGPoint(x: size.width - inset - length, y: size.height - inset))
                    path.addLine(to: CGPoint(x: size.width - inset, y: size.height - inset))
                    path.addLine(to: CGPoint(x: size.width - inset, y: size.height - inset - length))
                }
                .stroke(StudioPalette.ember.opacity(0.72), lineWidth: 1.25)

                Path { path in
                    let center = CGPoint(x: size.width / 2, y: size.height / 2)
                    path.move(to: CGPoint(x: center.x - 20, y: center.y))
                    path.addLine(to: CGPoint(x: center.x - 6, y: center.y))
                    path.move(to: CGPoint(x: center.x + 6, y: center.y))
                    path.addLine(to: CGPoint(x: center.x + 20, y: center.y))
                    path.move(to: CGPoint(x: center.x, y: center.y - 20))
                    path.addLine(to: CGPoint(x: center.x, y: center.y - 6))
                    path.move(to: CGPoint(x: center.x, y: center.y + 6))
                    path.addLine(to: CGPoint(x: center.x, y: center.y + 20))
                }
                .stroke(StudioPalette.ocean.opacity(0.34), lineWidth: 1)

                VStack {
                    HStack(alignment: .top) {
                        Spacer()
                        if healthLabel != "Armed" {
                            overlayTag(healthLabel, accent: healthAccent)
                        }
                    }
                    Spacer()
                }
                .padding(12)
            }
        }
    }

    private func overlayTag(_ text: String, accent: Color) -> some View {
        Text(text)
            .font(StudioType.labelStrong)
            .foregroundStyle(accent)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(Rectangle().fill(Color.black.opacity(0.54)))
            .overlay(Rectangle().stroke(accent.opacity(0.35), lineWidth: 1))
    }
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
                    .font(StudioType.body)
                    .foregroundStyle(StudioPalette.ink)
                    .frame(width: 110, alignment: .leading)

                control
                    .frame(maxWidth: 260)

                Text(value)
                    .font(StudioType.data)
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
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Circle()
                    .fill(isSelected ? StudioPalette.ocean : StudioPalette.hairline)
                    .frame(width: 6, height: 6)

                VStack(alignment: .leading, spacing: 2) {
                    Text(preset.name)
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)

                Text("\(preset.channels)m/\(preset.parameterFields)p")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.ocean)
            }
            .frame(width: 140, alignment: .leading)
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(isSelected ? StudioPalette.consoleSurfaceRaised : StudioPalette.consoleSurface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(isSelected ? StudioPalette.ocean.opacity(0.7) : StudioPalette.hairline.opacity(0.65), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .help(preset.detail)
    }
}

private struct LabPaletteStampCard: View {
    let entry: StudioCompareEntry
    let isSelected: Bool
    let onSelect: () -> Void
    let onSetWorld: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            CreatureThumbnailView(creature: entry.creature, size: 72)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(entry.name)
                        .font(StudioType.title)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(1)
                }

                HStack(spacing: 8) {
                    Button(isSelected ? "Selected" : "Stamp", action: onSelect)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    Button("World", action: onSetWorld)
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                }
            }
        }
        .frame(width: 320, alignment: .leading)
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .fill(isSelected ? StudioPalette.consoleSurfaceRaised : StudioPalette.consoleSurface)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 4, style: .continuous)
                .stroke(isSelected ? StudioPalette.ocean.opacity(0.7) : StudioPalette.hairline, lineWidth: 1)
        )
    }
}

private struct Track1FamilyChip: View {
    let family: Track1TaxonomyFamily
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 7) {
                Circle()
                    .fill(isSelected ? StudioPalette.ocean : StudioPalette.hairline)
                    .frame(width: 6, height: 6)
                Text(family.name)
                    .font(StudioType.labelStrong)
                    .foregroundStyle(isSelected ? StudioPalette.ink : StudioPalette.mutedInk)
                    .lineLimit(1)
            }
            .frame(width: 116, height: 30, alignment: .leading)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(isSelected ? StudioPalette.consoleSurfaceRaised : StudioPalette.consoleControl.opacity(0.82))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(isSelected ? StudioPalette.ocean.opacity(0.78) : StudioPalette.hairline, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct Track1TaxonomyFamilyPanel: View {
    let family: Track1TaxonomyFamily
    let selectedPath: String?
    let onLoad: (Track1TaxonomyConfig) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(family.name)
                    .font(StudioType.labelStrong)
                    .foregroundStyle(StudioPalette.ink)
                Spacer(minLength: 6)
                Text("\(family.speciesCount) species")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .lineLimit(1)
            }

            ForEach(family.genera) { genus in
                VStack(alignment: .leading, spacing: 5) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(genus.name)
                            .font(StudioType.labelStrong)
                            .foregroundStyle(StudioPalette.ocean)
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(track1SpeciesGroups(for: genus)) { group in
                            Track1TaxonomySpeciesRow(
                                group: group,
                                selectedPath: selectedPath,
                                onLoad: onLoad
                            )
                        }
                    }
                }
                .padding(.top, 2)
            }
        }
        .padding(8)
        .background(Rectangle().fill(StudioPalette.consoleSurface.opacity(0.72)))
        .overlay(Rectangle().stroke(StudioPalette.hairline.opacity(0.75), lineWidth: 1))
    }
}

private struct Track1TaxonomySpeciesRow: View {
    let group: Track1SpeciesGroup
    let selectedPath: String?
    let onLoad: (Track1TaxonomyConfig) -> Void

    private var activeConfig: Track1TaxonomyConfig {
        group.configs.first { $0.path == selectedPath }
            ?? group.configs.first(where: \.isLabLoadable)
            ?? group.configs[0]
    }

    private var isSelected: Bool {
        group.configs.contains { $0.path == selectedPath }
    }

    private var hasLoadableConfig: Bool {
        group.configs.contains(where: \.isLabLoadable)
    }

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(group.name)
                    .font(StudioType.dataSmall)
                    .foregroundStyle(isSelected ? StudioPalette.ink : StudioPalette.mutedInk)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 6)
            if group.configs.count > 1 {
                Text("\(group.configs.count)x")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(hasLoadableConfig ? (isSelected ? StudioPalette.moss : StudioPalette.ocean) : StudioPalette.ember)
                    .frame(width: 28, alignment: .trailing)
            }

            Button {
                onLoad(activeConfig)
            } label: {
                Image(systemName: isSelected ? "checkmark" : (hasLoadableConfig ? "tray.and.arrow.down" : "exclamationmark.triangle"))
            }
            .buttonStyle(.bordered)
            .controlSize(.mini)
            .disabled(!hasLoadableConfig)
            .help(hasLoadableConfig ? "Load \(group.name)" : "No Lab-loadable variant")

            if group.configs.count > 1 {
                Menu {
                    ForEach(group.configs) { config in
                        Button(config.variantLabel) {
                            onLoad(config)
                        }
                        .disabled(!config.isLabLoadable)
                    }
                } label: {
                    Image(systemName: "list.bullet")
                }
                .menuStyle(.borderlessButton)
                .controlSize(.mini)
                .frame(width: 24)
                .help("Choose variant")
            }
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 5)
        .background(
            Rectangle()
                .fill(isSelected ? StudioPalette.consoleSurfaceRaised : StudioPalette.consoleControl.opacity(0.44))
        )
        .overlay(
            Rectangle()
                .stroke(isSelected ? StudioPalette.moss.opacity(0.72) : StudioPalette.hairline.opacity(0.48), lineWidth: 1)
        )
    }
}

private struct Track1SpeciesGroup: Identifiable {
    let id: String
    let name: String
    let configs: [Track1TaxonomyConfig]
}

private func track1SpeciesGroups(for genus: Track1TaxonomyGenus) -> [Track1SpeciesGroup] {
    Dictionary(grouping: genus.configs, by: \.displayName)
        .map { species, configs in
            Track1SpeciesGroup(
                id: "\(genus.id)/\(species)",
                name: species,
                configs: configs.sorted { lhs, rhs in
                    if lhs.isLabLoadable != rhs.isLabLoadable {
                        return lhs.isLabLoadable && !rhs.isLabLoadable
                    }
                    return lhs.variantLabel.localizedStandardCompare(rhs.variantLabel) == .orderedAscending
                }
            )
        }
        .sorted { lhs, rhs in
            lhs.name.localizedStandardCompare(rhs.name) == .orderedAscending
        }
}

private struct LabInfoSection<Content: View>: View {
    let title: String
    let content: Content

    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(StudioType.labelStrong)
                .textCase(.uppercase)
                .foregroundStyle(StudioPalette.mutedInk)
            content
        }
    }
}

private struct LabControlGroup<Content: View>: View {
    let label: String
    let content: Content

    init(label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label)
                .font(StudioType.labelStrong)
                .foregroundStyle(StudioPalette.mutedInk)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct LabCompactKeyValueRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(label)
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.mutedInk)
                .frame(width: 78, alignment: .leading)
            Text(value)
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.ink)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
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
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .frame(width: 112)
                }
            }

            ForEach(0..<channelCount, id: \.self) { source in
                GridRow {
                    Text("c\(source)")
                        .font(StudioType.labelStrong)
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
                        .frame(width: 112)
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
                .font(StudioType.data)
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

private struct LabStageFrameSurface: View {
    let frameStore: LeniaLabFrameStore
    let renderMode: LeniaRenderMode
    let zoom: CGFloat
    let offset: CGSize
    let gridSize: Int
    let projectionLabel: String
    let healthLabel: String
    let healthAccent: Color
    let hoveredGridPoint: SIMD2<Int>?
    let primaryTool: SandboxTool
    let brushRadius: Int
    let selectedStampEntry: StudioCompareEntry
    let selectedStampPreview: CreatureStamp?
    let onTransformChange: (LeniaLabStageTransform) -> Void
    let onPrimaryPoint: (SIMD2<Int>) -> Void
    let onSecondaryPoint: (SIMD2<Int>) -> Void
    let onHoverPointChange: (SIMD2<Int>?) -> Void
    let onBrushRadiusDelta: ((Int) -> Void)?

    var body: some View {
        ZStack(alignment: .topLeading) {
            LeniaLabStageView(
                frameStore: frameStore,
                renderMode: renderMode,
                zoom: zoom,
                offset: offset,
                onTransformChange: onTransformChange,
                onPrimaryPoint: onPrimaryPoint,
                onSecondaryPoint: onSecondaryPoint,
                onHoverPointChange: onHoverPointChange,
                onBrushRadiusDelta: onBrushRadiusDelta
            )

            LabTacticalStageOverlay(
                gridSize: gridSize,
                zoom: zoom,
                projectionLabel: projectionLabel,
                healthLabel: healthLabel,
                healthAccent: healthAccent
            )
            .allowsHitTesting(false)

            GeometryReader { proxy in
                LabStageHoverOverlay(
                    point: hoveredGridPoint,
                    tool: primaryTool,
                    brushRadius: brushRadius,
                    selectedStamp: selectedStampEntry,
                    selectedStampPreview: selectedStampPreview,
                    transform: LeniaLabStageTransform(zoom: zoom, offset: offset),
                    viewSize: proxy.size,
                    gridSize: gridSize
                )
            }
            .allowsHitTesting(false)
        }
    }
}

struct LeniaLabStageView: NSViewRepresentable {
    let frame: LeniaFieldFrame?
    let frameStore: LeniaLabFrameStore?
    let renderMode: LeniaRenderMode
    let zoom: CGFloat
    let offset: CGSize
    let onTransformChange: (LeniaLabStageTransform) -> Void
    let onPrimaryPoint: (SIMD2<Int>) -> Void
    let onSecondaryPoint: (SIMD2<Int>) -> Void
    let onHoverPointChange: (SIMD2<Int>?) -> Void
    let onBrushRadiusDelta: ((Int) -> Void)?

    init(
        frame: LeniaFieldFrame?,
        renderMode: LeniaRenderMode,
        zoom: CGFloat,
        offset: CGSize,
        onTransformChange: @escaping (LeniaLabStageTransform) -> Void,
        onPrimaryPoint: @escaping (SIMD2<Int>) -> Void,
        onSecondaryPoint: @escaping (SIMD2<Int>) -> Void,
        onHoverPointChange: @escaping (SIMD2<Int>?) -> Void,
        onBrushRadiusDelta: ((Int) -> Void)?
    ) {
        self.frame = frame
        self.frameStore = nil
        self.renderMode = renderMode
        self.zoom = zoom
        self.offset = offset
        self.onTransformChange = onTransformChange
        self.onPrimaryPoint = onPrimaryPoint
        self.onSecondaryPoint = onSecondaryPoint
        self.onHoverPointChange = onHoverPointChange
        self.onBrushRadiusDelta = onBrushRadiusDelta
    }

    init(
        frameStore: LeniaLabFrameStore,
        renderMode: LeniaRenderMode,
        zoom: CGFloat,
        offset: CGSize,
        onTransformChange: @escaping (LeniaLabStageTransform) -> Void,
        onPrimaryPoint: @escaping (SIMD2<Int>) -> Void,
        onSecondaryPoint: @escaping (SIMD2<Int>) -> Void,
        onHoverPointChange: @escaping (SIMD2<Int>?) -> Void,
        onBrushRadiusDelta: ((Int) -> Void)?
    ) {
        self.frame = nil
        self.frameStore = frameStore
        self.renderMode = renderMode
        self.zoom = zoom
        self.offset = offset
        self.onTransformChange = onTransformChange
        self.onPrimaryPoint = onPrimaryPoint
        self.onSecondaryPoint = onSecondaryPoint
        self.onHoverPointChange = onHoverPointChange
        self.onBrushRadiusDelta = onBrushRadiusDelta
    }

    func makeNSView(context: Context) -> LeniaLabStageNSView {
        let view = LeniaLabStageNSView()
        if let frameStore {
            frameStore.attach(view)
        } else {
            view.updateFrame(frame)
        }
        view.onTransformChange = onTransformChange
        view.onPrimaryPoint = onPrimaryPoint
        view.onSecondaryPoint = onSecondaryPoint
        view.onHoverPointChange = onHoverPointChange
        view.onBrushRadiusDelta = onBrushRadiusDelta
        return view
    }

    func updateNSView(_ nsView: LeniaLabStageNSView, context: Context) {
        if let frameStore {
            frameStore.attach(nsView)
        } else {
            nsView.updateFrame(frame)
        }
        nsView.onTransformChange = onTransformChange
        nsView.onPrimaryPoint = onPrimaryPoint
        nsView.onSecondaryPoint = onSecondaryPoint
        nsView.onHoverPointChange = onHoverPointChange
        nsView.onBrushRadiusDelta = onBrushRadiusDelta
        nsView.update(
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
    var onBrushRadiusDelta: ((Int) -> Void)?

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

    func updateFrame(_ frame: LeniaFieldFrame?) {
        gridSize = frame?.width ?? 0
        renderer.update(frame: frame)
        if gridSize == 0 {
            onHoverPointChange?(nil)
        }
        needsDisplay = true
    }

    func update(renderMode: LeniaRenderMode, transform: LeniaLabStageTransform) {
        let viewSize = bounds.size
        let shouldRedraw = self.renderMode.rawValue != renderMode.rawValue
            || self.transform != transform
            || renderer.viewSize != viewSize
        self.renderMode = renderMode
        self.transform = transform
        renderer.viewSize = viewSize
        renderer.transform = transform
        renderer.renderMode = renderMode
        if shouldRedraw {
            needsDisplay = true
        }
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

        let verticalIntent = abs(event.scrollingDeltaY) >= abs(event.scrollingDeltaX)
        if verticalIntent && !event.modifierFlags.contains(.shift), let onBrushRadiusDelta {
            if event.scrollingDeltaY != 0 {
                onBrushRadiusDelta(event.scrollingDeltaY > 0 ? 1 : -1)
            }
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
                    .font(StudioType.data)
                    .foregroundStyle(StudioPalette.ink)
                Spacer()
                Text("r \(formatCompact(kernel.radius)) · m \(formatCompact(kernel.center)) · s \(formatCompact(kernel.sigma)) · h \(formatCompact(kernel.gain))")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            }

            Text("b \(formatKernelVector(kernel.beta))")
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)
            Text("w \(formatKernelVector(kernel.weights))")
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)
            Text("a \(formatKernelVector(kernel.anchors))")
                .font(StudioType.dataSmall)
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
                    .font(StudioType.labelStrong)
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
