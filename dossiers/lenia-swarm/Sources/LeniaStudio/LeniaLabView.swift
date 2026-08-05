import AppKit
import MetalKit
import SwiftUI
import UniformTypeIdentifiers
import LeniaCore
import LeniaVisuals

struct LeniaLabFrameUpdate: Sendable {
    let snapshot: FlowSandboxSnapshot
    let snapshotFps: Double
    let runtimeTelemetry: FlowSandboxRuntimeTelemetry
    let activity: Double
    let refreshMetrics: Bool
    let replayPosition: LabReplayPosition?
}

@MainActor
final class LeniaLabFrameStore {
    private weak var stageView: LeniaLabStageNSView?
    private var latestFrame: LeniaFieldFrame?
    private var runtime: LabRuntimeHandle?
    private var frameTask: Task<Void, Never>?
    private var activeProjection: LabFieldProjection = .matter
    private var targetSpeedCap = 0
    private var isRunning = false
    private var refreshPending = false
    private var generation = 0
    private var onUpdate: (@MainActor (LeniaLabFrameUpdate) -> Void)?
    private let beforeSnapshot: (@Sendable () async -> Void)?

    init(beforeSnapshot: (@Sendable () async -> Void)? = nil) {
        self.beforeSnapshot = beforeSnapshot
    }

    func attach(_ stageView: LeniaLabStageNSView) {
        guard self.stageView !== stageView else { return }
        self.stageView = stageView
        stageView.setFramePacing(active: isRunning)
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

    func run(
        runtime: LabRuntimeHandle,
        speedCap: Int,
        projection: LabFieldProjection,
        isRunning: Bool,
        onUpdate: @escaping @MainActor (LeniaLabFrameUpdate) -> Void
    ) {
        stop()
        self.runtime = runtime
        self.targetSpeedCap = speedCap
        self.activeProjection = projection
        self.isRunning = isRunning
        refreshPending = false
        self.onUpdate = onUpdate
        stageView?.setFramePacing(active: isRunning)
        generation += 1
        startFrameTaskIfNeeded()
    }

    func stop() {
        generation += 1
        frameTask?.cancel()
        frameTask = nil
        runtime = nil
        onUpdate = nil
        isRunning = false
        refreshPending = false
        stageView?.setFramePacing(active: false)
    }

    func setRunning(_ running: Bool) {
        isRunning = running
        stageView?.setFramePacing(active: running)
        startFrameTaskIfNeeded()
    }

    func setSpeedCap(_ hz: Int) {
        targetSpeedCap = hz
    }

    func setProjection(_ projection: LabFieldProjection) {
        activeProjection = projection
        requestRefresh()
    }

    func requestRefresh() {
        if frameTask != nil {
            refreshPending = true
            return
        }
        startFrameTaskIfNeeded()
    }

    private func startFrameTaskIfNeeded() {
        guard frameTask == nil, runtime != nil else { return }
        let runGeneration = generation
        frameTask = Task { [weak self] in
            await self?.frameLoop(generation: runGeneration)
        }
    }

    private func frameLoop(generation runGeneration: Int) async {
        let telemetryInterval: Duration = .milliseconds(500)
        var lastMetricsRefresh = ContinuousClock.now - telemetryInterval
        var fpsTimestamps = [Date]()
        var previousMetrics: FlowSandboxMetrics?
        var latestActivity = 0.0
        var latestRuntimeTelemetry = FlowSandboxRuntimeTelemetry(lastStepDurationMs: 0, realizedStepRateHz: 0)
        fpsTimestamps.reserveCapacity(24)

        while !Task.isCancelled {
            let frameStartedAt = ContinuousClock.now
            guard let loopState = await MainActor.run(body: { self.frameLoopState(generation: runGeneration) }) else {
                return
            }
            await beforeSnapshot?()
            guard generation == runGeneration, !Task.isCancelled else { return }
            let refreshMetrics = ContinuousClock.now - lastMetricsRefresh >= telemetryInterval
            let runtimeFrame = await loopState.runtime.frameSnapshot(
                refreshMetrics: refreshMetrics,
                projection: loopState.projection
            )
            let snapshot = runtimeFrame.snapshot
            let replayPosition = runtimeFrame.replayPosition
            if refreshMetrics {
                latestRuntimeTelemetry = await loopState.runtime.telemetry()
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
            let update = LeniaLabFrameUpdate(
                snapshot: snapshot,
                snapshotFps: snapshotFps,
                runtimeTelemetry: latestRuntimeTelemetry,
                activity: latestActivity,
                refreshMetrics: refreshMetrics,
                replayPosition: replayPosition
            )

            await MainActor.run {
                guard self.generation == runGeneration else { return }
                if replayPosition?.isRunning == false, self.isRunning {
                    self.isRunning = false
                    self.stageView?.setFramePacing(active: false)
                }
                self.present(snapshot)
                self.onUpdate?(update)
            }

            if isRunning {
                refreshPending = false
            } else if refreshPending {
                refreshPending = false
                continue
            } else {
                break
            }

            let elapsed = ContinuousClock.now - frameStartedAt
            let remaining = loopState.targetDelay - elapsed
            if remaining > .zero {
                try? await Task.sleep(for: remaining)
            }
        }
        if generation == runGeneration {
            frameTask = nil
        }
    }

    private func frameLoopState(
        generation runGeneration: Int
    ) -> (
        runtime: LabRuntimeHandle,
        projection: LabFieldProjection,
        targetDelay: Duration
    )? {
        guard generation == runGeneration, let runtime else { return nil }
        let frameCap = targetSpeedCap > 0 ? max(1, min(60, targetSpeedCap)) : 60
        let delay = Duration.milliseconds(max(1, Int((1_000.0 / Double(frameCap)).rounded())))
        return (runtime, activeProjection, delay)
    }
}

private struct LabPendingStrokeBatch {
    let runtime: LabRuntimeHandle
    let generation: Int
    let tool: SandboxTool
    let radius: Int
    let strength: Float
    var points: [SIMD2<Int>]

    func canCoalesce(
        generation: Int,
        tool: SandboxTool,
        radius: Int,
        strength: Float
    ) -> Bool {
        self.generation == generation
            && self.tool == tool
            && self.radius == radius
            && self.strength == strength
    }
}

func labInterpolatedStrokePoints(
    from start: SIMD2<Int>,
    to end: SIMD2<Int>
) -> [SIMD2<Int>] {
    let deltaX = end.x - start.x
    let deltaY = end.y - start.y
    let stepCount = max(abs(deltaX), abs(deltaY))
    guard stepCount > 0 else { return [start] }
    return (0...stepCount).map { step in
        let progress = Double(step) / Double(stepCount)
        return SIMD2<Int>(
            Int((Double(start.x) + Double(deltaX) * progress).rounded()),
            Int((Double(start.y) + Double(deltaY) * progress).rounded())
        )
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
    @Published var activityHistory: [Double] = []
    @Published var externalReplayTitle: String?
    @Published var hasSnapshot = false
    @Published var fieldWidth: Int?
    @Published var latestStep = 0
    @Published var latestMetrics: FlowSandboxMetrics?
    @Published var checkpointCount = 0
    @Published var canUndo = false
    @Published var canRedo = false
    @Published var experimentStatusMessage: String?
    @Published var replayFrameIndex = 0
    @Published var replayFrameCount = 0
    @Published var replayIsLooping = true
    @Published private(set) var autoFoodEnabled = false

    let frames: LeniaLabFrameStore
    let history: StudioExperimentHistory
    private var runtime: LabRuntimeHandle?
    private var targetSpeedCap = 0
    private var sessionGeneration = 0
    private var runtimeLoadTask: Task<Void, Never>?
    private var runStateTask: Task<Void, Never>?
    private var runStateRequest = 0
    private var runtimeMutationTail: Task<Void, Never>?
    private var runtimeMutationEpoch = 0
    private var runtimeMutationRequest = 0
    private var strokeFlushTask: Task<Void, Never>?
    private var pendingStrokeBatches: [LabPendingStrokeBatch] = []
    private let beforeExperimentSnapshot: (@Sendable () async -> Void)?
    private let beforeRuntimeMutation: (@Sendable (String) async -> Void)?
    private let beforeRunStateTransition: (@Sendable (Bool) async -> Void)?

    init(
        frameStore: LeniaLabFrameStore = LeniaLabFrameStore(),
        history: StudioExperimentHistory = StudioExperimentHistory(),
        beforeExperimentSnapshot: (@Sendable () async -> Void)? = nil,
        beforeRuntimeMutation: (@Sendable (String) async -> Void)? = nil,
        beforeRunStateTransition: (@Sendable (Bool) async -> Void)? = nil
    ) {
        self.frames = frameStore
        self.history = history
        self.beforeExperimentSnapshot = beforeExperimentSnapshot
        self.beforeRuntimeMutation = beforeRuntimeMutation
        self.beforeRunStateTransition = beforeRunStateTransition
    }

    func rebuildWorld(
        sourceEntryID: String,
        baseConfigData: Data,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool = false
    ) {
        startWorldLoad(
            sourceEntryID: sourceEntryID,
            backend: backend,
            speedCap: speedCap,
            shouldRun: shouldRun
        ) {
            try Task.checkCancellation()
            let runtimeConfig = try loadRuntimeConfig(
                from: baseConfigData,
                overrides: ["backend": backend.rawValue]
            )
            if !labConfigRequiresCanonicalRuntime(runtimeConfig),
               let engine = makeLeniaInteractiveEngine(from: runtimeConfig, backend: backend) {
                return .engine(engine)
            }
            return .replay(CanonicalLabRuntime(runtimeConfig: runtimeConfig))
        }
    }

    func rebuildWorld(
        sourceEntryID: String,
        runtimeConfig: LeniaRuntimeConfig,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool = false
    ) {
        startWorldLoad(
            sourceEntryID: sourceEntryID,
            backend: backend,
            speedCap: speedCap,
            shouldRun: shouldRun
        ) {
            try Task.checkCancellation()
            if !labConfigRequiresCanonicalRuntime(runtimeConfig),
               let engine = makeLeniaInteractiveEngine(from: runtimeConfig, backend: backend) {
                return .engine(engine)
            }
            return .replay(CanonicalLabRuntime(runtimeConfig: runtimeConfig))
        }
    }

    private func startWorldLoad(
        sourceEntryID: String,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool,
        build: @escaping @Sendable () throws -> LabRuntimeHandle
    ) {
        let transition = beginRuntimeTransition(
            sourceEntryID: sourceEntryID,
            backend: backend,
            speedCap: speedCap,
            shouldRun: shouldRun,
            modeLabel: "Loading world"
        )
        let generation = transition.generation
        let previousRuntime = transition.previousRuntime

        runtimeLoadTask = Task { [weak self] in
            if let previousRuntime {
                await previousRuntime.stop()
            }
            do {
                try await Task.sleep(for: .milliseconds(75))
            } catch {
                return
            }
            guard let self,
                  !Task.isCancelled,
                  self.sessionGeneration == generation else {
                return
            }

            let buildTask = Task.detached(priority: .userInitiated) {
                try Task.checkCancellation()
                let runtime = try build()
                try Task.checkCancellation()
                return runtime
            }
            let result = await withTaskCancellationHandler {
                await buildTask.result
            } onCancel: {
                buildTask.cancel()
            }

            switch result {
            case .success(let loadedRuntime):
                await self.installLoadedRuntime(
                    loadedRuntime,
                    generation: generation,
                    speedCap: speedCap
                )
            case .failure(let error):
                guard !Task.isCancelled,
                      self.sessionGeneration == generation else {
                    return
                }
                self.applyRuntimeLoadFailure(
                    modeLabel: "Replay failed",
                    message: "Failed to load canonical replay world: \(error.localizedDescription)"
                )
                self.runtimeLoadTask = nil
            }
        }
    }

    private func installLoadedRuntime(
        _ loadedRuntime: LabRuntimeHandle,
        generation: Int,
        speedCap: Int
    ) async {
        guard !Task.isCancelled, sessionGeneration == generation else {
            await loadedRuntime.stop()
            return
        }

        await loadedRuntime.setSpeedCap(hz: speedCap)
        await loadedRuntime.setAutoFoodSpawn(
            enabled: autoFoodEnabled,
            probability: 0.03,
            patchSize: 12,
            value: 0.35
        )
        let contract = await loadedRuntime.worldContract()
        let projections = await loadedRuntime.availableProjections()

        guard !Task.isCancelled, sessionGeneration == generation else {
            await loadedRuntime.stop()
            return
        }

        runtime = loadedRuntime
        worldContract = contract
        availableProjections = projections
        activeProjection = projections.contains(activeProjection) ? activeProjection : .matter
        runtimeModeLabel = loadedRuntime.modeLabel
        activityEstimate = 0

        await loadedRuntime.pause()
        guard !Task.isCancelled,
              ownsRuntime(loadedRuntime, generation: generation) else {
            await loadedRuntime.stop()
            return
        }
        await publishInitialFrame(runtime: loadedRuntime, generation: generation)
        guard !Task.isCancelled,
              ownsRuntime(loadedRuntime, generation: generation) else {
            await loadedRuntime.stop()
            return
        }
        await initializeExperiment(runtime: loadedRuntime, generation: generation)
        guard !Task.isCancelled,
              ownsRuntime(loadedRuntime, generation: generation) else {
            await loadedRuntime.stop()
            return
        }
        if isRunning {
            await loadedRuntime.start()
        } else {
            await loadedRuntime.pause()
        }
        guard !Task.isCancelled,
              ownsRuntime(loadedRuntime, generation: generation) else {
            await loadedRuntime.stop()
            return
        }
        startFrameLoop()
        runtimeLoadTask = nil
    }

    private func beginRuntimeTransition(
        sourceEntryID: String?,
        backend: FlowSandboxBackend,
        speedCap: Int,
        shouldRun: Bool,
        modeLabel: String
    ) -> (generation: Int, previousRuntime: LabRuntimeHandle?) {
        sessionGeneration &+= 1
        runtimeLoadTask?.cancel()
        runtimeLoadTask = nil
        runStateTask?.cancel()
        runStateTask = nil
        cancelRuntimeMutations()
        strokeFlushTask?.cancel()
        strokeFlushTask = nil
        pendingStrokeBatches.removeAll(keepingCapacity: true)

        let previousRuntime = runtime
        runtime = nil
        frames.stop()

        activeWorldEntryID = sourceEntryID
        activeBackend = backend
        targetSpeedCap = speedCap
        isRunning = shouldRun
        clearFrameState()
        externalReplayTitle = nil
        worldContract = nil
        snapshotFps = 0
        activityEstimate = 0
        runtimeStatusMessage = nil
        stepDurationMs = 0
        realizedStepRateHz = 0
        availableProjections = [.matter]
        activeProjection = .matter
        runtimeModeLabel = modeLabel
        activityHistory = []
        experimentStatusMessage = nil
        replayFrameIndex = 0
        replayFrameCount = 0
        replayIsLooping = true
        history.clear()
        syncHistoryState()
        return (sessionGeneration, previousRuntime)
    }

    private func applyRuntimeLoadFailure(modeLabel: String, message: String) {
        runtime = nil
        clearFrameState()
        isRunning = false
        worldContract = nil
        activityEstimate = 0
        stepDurationMs = 0
        realizedStepRateHz = 0
        availableProjections = [.matter]
        activeProjection = .matter
        runtimeModeLabel = modeLabel
        runtimeStatusMessage = message
        history.clear()
        syncHistoryState()
    }

    func loadFrameSequence(manifestURL: URL) {
        autoFoodEnabled = false
        let transition = beginRuntimeTransition(
            sourceEntryID: nil,
            backend: .metalFull,
            speedCap: targetSpeedCap,
            shouldRun: false,
            modeLabel: "Loading TT export"
        )
        let generation = transition.generation
        let previousRuntime = transition.previousRuntime

        runtimeLoadTask = Task { [weak self] in
            if let previousRuntime {
                await previousRuntime.stop()
            }
            guard let self,
                  !Task.isCancelled,
                  self.sessionGeneration == generation else {
                return
            }

            let loadTask = Task.detached(priority: .userInitiated) {
                try Task.checkCancellation()
                let sequence = try TTFrameSequence.load(manifestURL: manifestURL)
                try Task.checkCancellation()
                return sequence
            }
            let result = await withTaskCancellationHandler {
                await loadTask.result
            } onCancel: {
                loadTask.cancel()
            }

            switch result {
            case .success(let sequence):
                let frameRuntime = TTFrameSequenceRuntime(sequence: sequence)
                let loadedRuntime = LabRuntimeHandle.frameSequence(frameRuntime)
                await frameRuntime.setSpeedCap(hz: self.targetSpeedCap)
                let contract = await frameRuntime.worldContract()

                guard !Task.isCancelled,
                      self.sessionGeneration == generation else {
                    await loadedRuntime.stop()
                    return
                }

                self.runtime = loadedRuntime
                self.worldContract = contract
                self.externalReplayTitle = sequence.title
                self.runtimeModeLabel = loadedRuntime.modeLabel
                self.runtimeStatusMessage = nil
                self.history.clear()
                self.syncHistoryState()
                self.startFrameLoop()
                self.runtimeLoadTask = nil
            case .failure(let error):
                guard !Task.isCancelled,
                      self.sessionGeneration == generation else {
                    return
                }
                self.applyRuntimeLoadFailure(
                    modeLabel: "TT export replay failed",
                    message: "Failed to load TT export: \(error.localizedDescription)"
                )
                self.externalReplayTitle = manifestURL.lastPathComponent
                self.runtimeLoadTask = nil
            }
        }
    }

    func setRunning(_ running: Bool) {
        isRunning = running
        if !running {
            frames.setRunning(false)
        }
        guard let runtime else { return }
        let generation = sessionGeneration
        runStateRequest &+= 1
        let request = runStateRequest
        runStateTask?.cancel()
        runStateTask = Task { [weak self] in
            guard let self,
                  !Task.isCancelled,
                  self.sessionGeneration == generation,
                  self.runStateRequest == request,
                  self.ownsRuntime(runtime, generation: generation) else {
                return
            }
            await self.beforeRunStateTransition?(running)
            guard !Task.isCancelled,
                  self.sessionGeneration == generation,
                  self.runStateRequest == request,
                  self.ownsRuntime(runtime, generation: generation) else {
                return
            }
            if self.isRunning {
                await runtime.resume()
            } else {
                await runtime.pause()
            }
            if self.ownsRuntime(runtime, generation: generation),
               self.runStateRequest == request {
                if self.isRunning {
                    self.frames.setRunning(true)
                } else {
                    self.frames.requestRefresh()
                }
                self.runStateTask = nil
            }
        }
    }

    func waitForRunStateTransition() async {
        await runStateTask?.value
    }

    func waitForRuntimeMutations() async {
        await runtimeMutationTail?.value
    }

    func runtimeStepSnapshot() async -> Int? {
        guard let runtime else { return nil }
        return await runtime.snapshot(
            refreshMetrics: false,
            projection: activeProjection
        ).step
    }

    func reset() {
        guard let runtime else { return }
        let generation = sessionGeneration
        enqueueRuntimeMutation(named: "reset", runtime: runtime, generation: generation) { [weak self] in
            await runtime.pause()
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            await runtime.reset()
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            let snapshot = await runtime.materializeStateSnapshot()
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            if let snapshot {
                self.history.reset(initial: snapshot)
                self.syncHistoryState()
            }
            if self.isRunning {
                await runtime.resume()
            } else {
                await runtime.pause()
            }
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            self.activityHistory = []
            self.frames.requestRefresh()
        }
    }

    func step(_ count: Int = 1) {
        guard let runtime, !isRunning else { return }
        let generation = sessionGeneration
        let resolvedCount = max(1, count)
        enqueueRuntimeMutation(named: "step", runtime: runtime, generation: generation) { [weak self] in
            await runtime.pause()
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            for _ in 0..<resolvedCount {
                guard !Task.isCancelled else { return }
                await runtime.step()
                guard self.ownsRuntime(runtime, generation: generation) else { return }
            }
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            let snapshot = await runtime.materializeStateSnapshot()
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            if let snapshot {
                self.history.checkpoint(
                    snapshot,
                    label: resolvedCount == 1 ? "Step" : "Step ×\(resolvedCount)"
                )
                self.syncHistoryState()
            }
            self.frames.requestRefresh()
        }
    }

    func stepReplayBackward() {
        guard let runtime, externalReplayTitle != nil, !isRunning else { return }
        let generation = sessionGeneration
        enqueueRuntimeMutation(named: "replay-backward", runtime: runtime, generation: generation) { [weak self] in
            await runtime.stepBackward()
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            self.frames.requestRefresh()
        }
    }

    func seekReplay(toProgress progress: Double) {
        guard let runtime, replayFrameCount > 0 else { return }
        let clamped = min(1, max(0, progress.isFinite ? progress : 0))
        let index = Int((clamped * Double(max(0, replayFrameCount - 1))).rounded())
        setRunning(false)
        let generation = sessionGeneration
        enqueueRuntimeMutation(named: "replay-seek", runtime: runtime, generation: generation) { [weak self] in
            await runtime.pause()
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            await runtime.seekReplay(to: index)
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            self.frames.requestRefresh()
        }
    }

    func setReplayLooping(_ looping: Bool) {
        guard let runtime, replayFrameCount > 0 else { return }
        replayIsLooping = looping
        let generation = sessionGeneration
        enqueueRuntimeMutation(named: "replay-looping", runtime: runtime, generation: generation) { [weak self] in
            await runtime.setReplayLooping(looping)
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            self.frames.requestRefresh()
        }
    }

    func createCheckpoint(label: String? = nil) {
        guard let runtime else { return }
        let generation = sessionGeneration
        Task { [weak self] in
            let snapshot = await runtime.materializeStateSnapshot()
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            guard let snapshot else { return }
            self.history.checkpoint(
                snapshot,
                label: label ?? "Checkpoint t\(snapshot.step)"
            )
            self.syncHistoryState()
            self.experimentStatusMessage = "Checkpoint saved at t\(snapshot.step)"
        }
    }

    func undo() {
        guard let snapshot = history.undo() else { return }
        syncHistoryState()
        restoreExperimentState(snapshot)
    }

    func redo() {
        guard let snapshot = history.redo() else { return }
        syncHistoryState()
        restoreExperimentState(snapshot)
    }

    func captureSpecimen(
        name: String,
        near point: SIMD2<Int>,
        existingCreatures: [SavedCreature]
    ) async throws -> StudioSpecimenCaptureResult? {
        guard let runtime, let worldContract else {
            throw LeniaLabExperimentError.runtimeUnavailable
        }
        let generation = sessionGeneration
        let snapshot = await runtime.materializeStateSnapshot()
        guard ownsRuntime(runtime, generation: generation) else { return nil }
        guard let snapshot else {
            throw LeniaLabExperimentError.stateUnavailable
        }
        let result = try await Task.detached(priority: .userInitiated) {
            try StudioSpecimenCaptureStore.capture(
                name: name,
                ownerID: "studio",
                snapshot: snapshot,
                contract: worldContract,
                near: point,
                existingCreatures: existingCreatures
            )
        }.value
        guard ownsRuntime(runtime, generation: generation) else { return nil }
        history.record(
            kind: .capture,
            summary: "Captured context-free specimen \(result.creature.name)",
            step: snapshot.step,
            details: ["fingerprint": result.component.fingerprint]
        )
        experimentStatusMessage = "Saved context-free specimen \(result.creature.name)"
        return result
    }

    func exportExperiment(title: String, sourceName: String, to destination: URL) throws {
        guard let worldContract else {
            throw LeniaLabExperimentError.runtimeUnavailable
        }
        try StudioExperimentBundleWriter.write(
            title: title,
            sourceName: sourceName,
            contract: worldContract,
            history: history,
            to: destination
        )
        experimentStatusMessage = "Exported \(destination.lastPathComponent)"
    }

    func setSpeedCap(_ hz: Int) {
        targetSpeedCap = hz
        frames.setSpeedCap(hz)
        guard let runtime else { return }
        Task {
            await runtime.setSpeedCap(hz: hz)
        }
    }

    func setAutoFood(enabled: Bool, probability: Float = 0.03, patchSize: Int = 12, value: Float = 0.35) {
        autoFoodEnabled = enabled
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
        frames.setProjection(projection)
    }

    func applyStroke(tool: SandboxTool, points: [SIMD2<Int>], radius: Int, strength: Float) {
        guard let runtime, !points.isEmpty else { return }
        let generation = sessionGeneration
        if let lastIndex = pendingStrokeBatches.indices.last,
           pendingStrokeBatches[lastIndex].canCoalesce(
               generation: generation,
               tool: tool,
               radius: radius,
               strength: strength
           ) {
            let previousPoint = pendingStrokeBatches[lastIndex].points.last
            pendingStrokeBatches[lastIndex].points.append(
                contentsOf: continuousStrokePoints(after: previousPoint, points: points)
            )
        } else {
            pendingStrokeBatches.append(
                LabPendingStrokeBatch(
                    runtime: runtime,
                    generation: generation,
                    tool: tool,
                    radius: radius,
                    strength: strength,
                    points: continuousStrokePoints(after: nil, points: points)
                )
            )
        }
        startStrokeFlushIfNeeded(generation: generation)
    }

    func applyStamp(entry: StudioCompareEntry, at point: SIMD2<Int>, stampCache: LeniaLabStampCache) {
        guard let runtime else { return }
        let generation = sessionGeneration
        Task { [weak self] in
            let stamp = await stampCache.stamp(for: entry)
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            await runtime.applyCreatureStamp(stamp, center: point)
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            let snapshot = await runtime.materializeStateSnapshot()
            guard self.ownsRuntime(runtime, generation: generation) else { return }
            if let snapshot {
                self.history.record(
                    kind: .stamp,
                    summary: "Stamped \(entry.name)",
                    step: snapshot.step
                )
                self.history.checkpoint(snapshot, label: "Stamp \(entry.name)")
                self.syncHistoryState()
            }
            self.frames.requestRefresh()
        }
    }

    func shutdown() {
        sessionGeneration &+= 1
        runtimeLoadTask?.cancel()
        runtimeLoadTask = nil
        runStateTask?.cancel()
        runStateTask = nil
        cancelRuntimeMutations()
        strokeFlushTask?.cancel()
        strokeFlushTask = nil
        pendingStrokeBatches.removeAll()
        let currentRuntime = runtime
        runtime = nil
        frames.stop()
        if let currentRuntime {
            Task {
                await currentRuntime.stop()
            }
        }
    }

    private func initializeExperiment(
        runtime: LabRuntimeHandle,
        generation: Int
    ) async {
        await beforeExperimentSnapshot?()
        guard ownsRuntime(runtime, generation: generation) else { return }
        let snapshot = await runtime.materializeStateSnapshot()
        guard ownsRuntime(runtime, generation: generation) else { return }
        guard let snapshot else {
            history.clear()
            syncHistoryState()
            return
        }
        history.reset(initial: snapshot)
        syncHistoryState()
    }

    private func publishInitialFrame(
        runtime: LabRuntimeHandle,
        generation: Int
    ) async {
        let runtimeFrame = await runtime.frameSnapshot(
            refreshMetrics: true,
            projection: activeProjection
        )
        guard ownsRuntime(runtime, generation: generation) else { return }
        frames.present(runtimeFrame.snapshot)
        consumeFrameUpdate(
            LeniaLabFrameUpdate(
                snapshot: runtimeFrame.snapshot,
                snapshotFps: 0,
                runtimeTelemetry: FlowSandboxRuntimeTelemetry(
                    lastStepDurationMs: 0,
                    realizedStepRateHz: 0
                ),
                activity: 0,
                refreshMetrics: false,
                replayPosition: runtimeFrame.replayPosition
            )
        )
        latestMetrics = runtimeFrame.snapshot.metrics
    }

    private func restoreExperimentState(_ snapshot: FlowSandboxStateSnapshot) {
        guard let runtime else { return }
        let generation = sessionGeneration
        isRunning = false
        frames.setRunning(false)
        runStateRequest &+= 1
        runStateTask?.cancel()
        runStateTask = nil
        enqueueRuntimeMutation(named: "restore", runtime: runtime, generation: generation) { [weak self] in
            await runtime.pause()
            guard let self, self.ownsRuntime(runtime, generation: generation) else { return }
            do {
                let restored = try await runtime.restoreStateSnapshot(snapshot)
                guard self.ownsRuntime(runtime, generation: generation) else { return }
                guard restored else {
                    self.experimentStatusMessage = "This replay cannot restore checkpoints"
                    return
                }
                self.experimentStatusMessage = "Restored t\(snapshot.step)"
                self.frames.requestRefresh()
            } catch {
                guard self.ownsRuntime(runtime, generation: generation) else { return }
                self.experimentStatusMessage = error.localizedDescription
            }
        }
    }

    private func syncHistoryState() {
        checkpointCount = history.checkpoints.count
        canUndo = history.canUndo
        canRedo = history.canRedo
    }

    private func startStrokeFlushIfNeeded(generation: Int) {
        guard strokeFlushTask == nil else { return }
        strokeFlushTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(8))
            guard let self, !Task.isCancelled else { return }

            var lastAppliedBatch: LabPendingStrokeBatch?

            while !Task.isCancelled,
                  self.sessionGeneration == generation,
                  !self.pendingStrokeBatches.isEmpty {
                let batch = self.pendingStrokeBatches.removeFirst()
                let stroke = SandboxStroke(
                    tool: batch.tool,
                    points: batch.points,
                    radius: batch.radius,
                    strength: batch.strength
                )
                await batch.runtime.applyStroke(stroke)
                guard self.ownsRuntime(batch.runtime, generation: generation) else { return }
                lastAppliedBatch = batch
                self.frames.requestRefresh()
                await Task.yield()
            }

            if let batch = lastAppliedBatch {
                let snapshot = await batch.runtime.materializeStateSnapshot()
                guard self.ownsRuntime(batch.runtime, generation: generation) else { return }
                if let snapshot {
                    self.history.record(
                        kind: .brush,
                        summary: "\(batch.tool.rawValue.capitalized) stroke",
                        step: snapshot.step
                    )
                    self.history.checkpoint(
                        snapshot,
                        label: "\(batch.tool.rawValue.capitalized) stroke"
                    )
                    self.syncHistoryState()
                }
            }

            guard self.sessionGeneration == generation else { return }
            self.strokeFlushTask = nil
            if !self.pendingStrokeBatches.isEmpty {
                self.startStrokeFlushIfNeeded(generation: generation)
            }
        }
    }

    private func continuousStrokePoints(
        after previousPoint: SIMD2<Int>?,
        points: [SIMD2<Int>]
    ) -> [SIMD2<Int>] {
        var result: [SIMD2<Int>] = []
        var previous = previousPoint
        for point in points {
            if let previous {
                result.append(contentsOf: labInterpolatedStrokePoints(from: previous, to: point).dropFirst())
            } else {
                result.append(point)
            }
            previous = point
        }
        return result
    }

    private func enqueueRuntimeMutation(
        named name: String,
        runtime candidate: LabRuntimeHandle,
        generation: Int,
        operation: @escaping @MainActor @Sendable () async -> Void
    ) {
        let predecessor = runtimeMutationTail
        let epoch = runtimeMutationEpoch
        runtimeMutationRequest &+= 1
        let request = runtimeMutationRequest
        let task = Task { [weak self] in
            await predecessor?.value
            guard let self,
                  !Task.isCancelled,
                  self.runtimeMutationEpoch == epoch,
                  self.ownsRuntime(candidate, generation: generation) else {
                return
            }
            defer {
                self.completeRuntimeMutation(request: request, epoch: epoch)
            }
            await self.beforeRuntimeMutation?(name)
            guard !Task.isCancelled,
                  self.runtimeMutationEpoch == epoch,
                  self.ownsRuntime(candidate, generation: generation) else {
                return
            }
            await operation()
        }
        runtimeMutationTail = task
    }

    private func completeRuntimeMutation(request: Int, epoch: Int) {
        guard runtimeMutationEpoch == epoch,
              runtimeMutationRequest == request else {
            return
        }
        runtimeMutationTail = nil
    }

    private func cancelRuntimeMutations() {
        runtimeMutationEpoch &+= 1
        runtimeMutationRequest &+= 1
        runtimeMutationTail?.cancel()
        runtimeMutationTail = nil
    }

    private func ownsRuntime(_ candidate: LabRuntimeHandle, generation: Int) -> Bool {
        sessionGeneration == generation && runtime?.isIdentical(to: candidate) == true
    }

    private func clearFrameState() {
        frames.clear()
        hasSnapshot = false
        fieldWidth = nil
        latestStep = 0
        latestMetrics = nil
    }

    private func startFrameLoop() {
        guard let runtime else { return }
        frames.run(
            runtime: runtime,
            speedCap: targetSpeedCap,
            projection: activeProjection,
            isRunning: isRunning
        ) { [weak self] update in
            self?.consumeFrameUpdate(update)
        }
    }

    private func consumeFrameUpdate(_ update: LeniaLabFrameUpdate) {
        hasSnapshot = true
        if fieldWidth != update.snapshot.width {
            fieldWidth = update.snapshot.width
        }
        latestStep = update.snapshot.step
        if let replayPosition = update.replayPosition {
            replayFrameIndex = replayPosition.frameIndex
            replayFrameCount = replayPosition.frameCount
            replayIsLooping = replayPosition.isLooping
            if isRunning, !replayPosition.isRunning {
                isRunning = false
                runStateRequest &+= 1
                runStateTask?.cancel()
                runStateTask = nil
                frames.setRunning(false)
            }
        }
        guard update.refreshMetrics else { return }

        snapshotFps = update.snapshotFps
        latestMetrics = update.snapshot.metrics
        activityEstimate = update.activity
        stepDurationMs = update.runtimeTelemetry.lastStepDurationMs
        realizedStepRateHz = update.runtimeTelemetry.realizedStepRateHz
        activityHistory.append(update.activity)
        if activityHistory.count > 48 {
            activityHistory.removeFirst(activityHistory.count - 48)
        }
    }
}

func labConfigRequiresCanonicalRuntime(_ runtimeConfig: LeniaRuntimeConfig) -> Bool {
    runtimeConfig.statePatch != nil
}

private enum LeniaLabExperimentError: LocalizedError {
    case runtimeUnavailable
    case stateUnavailable

    var errorDescription: String? {
        switch self {
        case .runtimeUnavailable:
            return "No editable runtime is loaded."
        case .stateUnavailable:
            return "This replay does not expose an editable state."
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
    @State private var speedCap = 30
    @State private var diagnosticsEnabled = false
    @State private var worldSelection: LabWorldSelection = .preset("flow-sail-0aa5d7b6")
    @State private var selectedStampID: String?
    @State private var selectedStampPreview: CreatureStamp?
    @State private var worldDraft: LabWorldDraft?
    @State private var worldDraftError: String?
    @State private var stageZoom: CGFloat = 1.35
    @State private var stageOffset: CGSize = .zero
    @State private var hoveredGridPoint: SIMD2<Int>?
    @State private var showTTExportImporter = false
    @State private var showContractEditor = false
    @State private var showPhysicsEditor = true
    @State private var selectedPhysicsKernel = 0
    @State private var selectedTrack1FamilyID: String?
    @State private var catalogScope: LabCatalogScope = .flowLife
    @State private var catalogSearch = ""
    @State private var inspectorPanel: LabInspectorPanel = .catalog

    private let stampCache = LeniaLabStampCache()
    private static let backendOrder: [FlowSandboxBackend] = [.metalFull, .mlx]
    private static let organismPresets = buildLabMissionPresets()
    private static let missionPresets = organismPresets.filter {
        $0.organismConfig?.catalogTier == .primary
    }
    private static let blankWorldPresets = buildBlankLabMissionPresets()
    private static let allWorldPresets = buildAllLabWorldPresets()

    init() {
        let frameStore = LeniaLabFrameStore()
        _frameStore = State(initialValue: frameStore)
        _model = StateObject(wrappedValue: LeniaLabModel(frameStore: frameStore))
    }

    private var stampEntries: [StudioCompareEntry] {
        let starter = orbiumStarterEntry()
        let comparison = appState.compareTray
        let saved = appState.library.prefix(10).map(appState.studioEntry)
        let live = appState.recentCreatures.prefix(10).map(appState.studioEntry)
        var seen: Set<String> = []
        return ([starter] + comparison + saved + live).filter { entry in
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
            return Self.allWorldPresets.first(where: { $0.id == presetID })?.entry ?? Self.missionPresets[0].entry
        case .stamp(let entryID):
            return stampEntries.first(where: { $0.id == entryID }) ?? selectedStampEntry
        case .track1Config(let path):
            return track1Catalog.catalog.config(path: path)?.studioEntry() ?? fallbackTrack1Entry(path: path)
        }
    }

    private var selectedWorldPreset: LabMissionPreset? {
        guard case .preset(let presetID) = worldSelection else { return nil }
        return Self.allWorldPresets.first(where: { $0.id == presetID })
    }

    private var activeWorldEntry: StudioCompareEntry? {
        guard let activeWorldEntryID = model.activeWorldEntryID else { return nil }
        if let preset = Self.allWorldPresets.first(where: { $0.entry.id == activeWorldEntryID }) {
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

    private var selectedTrack1Config: Track1TaxonomyConfig? {
        guard case .track1Config(let path) = worldSelection else { return nil }
        return track1Catalog.catalog.config(path: path)
    }

    private var requiredWorldBackend: FlowSandboxBackend? {
        selectedTrack1Config?.requiredLabBackend
            ?? selectedWorldPreset?.organismConfig?.requiredLabBackend
    }

    private var flowOrganisms: [Track1TaxonomyConfig] {
        track1Catalog.catalog.featuredFlowConfigs
    }

    private var matchingFlowOrganisms: [Track1TaxonomyConfig] {
        flowOrganisms.filter { track1Config($0, matches: catalogSearch) }
    }

    private var matchingFlowFamilies: [FlowOrganismFamily] {
        flowOrganismFamilies(from: matchingFlowOrganisms)
    }

    private var matchingClassicalReferences: [Track1TaxonomyConfig] {
        track1Catalog.catalog.classicalReferenceConfigs.filter {
            track1Config($0, matches: catalogSearch)
        }
    }

    private var filteredTaxonomyFamilies: [Track1TaxonomyFamily] {
        filteredTrack1Families(
            track1Catalog.catalog.families,
            search: catalogSearch
        )
    }

    private var displayedTrack1Family: Track1TaxonomyFamily? {
        if let selectedTrack1FamilyID,
           let selected = filteredTaxonomyFamilies.first(where: { $0.id == selectedTrack1FamilyID }) {
            return selected
        }
        return filteredTaxonomyFamilies.first
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

    private var isReadOnlyReplay: Bool {
        !labStageAllowsEditing(externalReplayTitle: model.externalReplayTitle)
    }

    private var stageAccessibilityValue: String {
        let grid = model.worldContract?.gridSize ?? model.fieldWidth ?? gridPreset.rawValue
        let state = model.isRunning ? "playing" : "paused"
        let mode = isReadOnlyReplay ? "read-only replay" : primaryGhostSummary
        return "Step \(model.latestStep), \(grid) by \(grid) field, \(state), \(mode)"
    }

    var body: some View {
        GeometryReader { proxy in
            Group {
                if labWorkspaceLayout(for: proxy.size.width) == .stacked {
                    ScrollView {
                        VStack(spacing: 14) {
                            stageSurface
                            controlSurface
                            inspectorSurface
                        }
                        .padding(10)
                    }
                } else {
                    let inspectorWidth = min(420, max(360, proxy.size.width * 0.26))
                    ScrollView {
                        HStack(alignment: .top, spacing: 14) {
                            VStack(spacing: 14) {
                                stageSurface
                                controlSurface
                            }
                            .frame(minWidth: 620, maxWidth: .infinity)
                            .layoutPriority(1)

                            inspectorSurface
                                .frame(width: inspectorWidth)
                        }
                        .padding(10)
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
        .task {
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
        .onChange(of: model.activeProjection) { _, newValue in
            model.setProjection(newValue)
        }
        .onChange(of: gridPreset) { _, newValue in
            applyDraftChange { draft in
                draft.setGridSize(newValue.rawValue)
            }
        }
        .onChange(of: worldDraft?.kernelCount) { _, count in
            selectedPhysicsKernel = min(selectedPhysicsKernel, max(0, (count ?? 1) - 1))
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
        VStack(spacing: 0) {
            stageToolbar
            stageCanvas
            stageDatumStrip
        }
        .background(StudioPalette.consoleSurface)
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .stroke(StudioPalette.hairline.opacity(0.65), lineWidth: 1)
        }
    }

    private var stageToolbar: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) {
                stagePlaybackControls
                stageObservationStatus
                    .layoutPriority(1)
                Spacer(minLength: 8)
                stageDisplayControls
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    stagePlaybackControls
                    stageObservationStatus
                        .layoutPriority(1)
                }

                ScrollView(.horizontal, showsIndicators: false) {
                    stageDisplayControls
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(StudioPalette.consoleSurfaceRaised.opacity(0.72))
    }

    private var stagePlaybackControls: some View {
        HStack(spacing: 6) {
            if model.replayFrameCount > 0 {
                Button {
                    model.stepReplayBackward()
                } label: {
                    Image(systemName: "backward.frame.fill")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(model.isRunning || model.replayFrameIndex == 0)
                .help("Previous replay frame")
            }

            Button {
                model.setRunning(!model.isRunning)
            } label: {
                Label(
                    model.isRunning ? "Hold" : "Run",
                    systemImage: model.isRunning ? "pause.fill" : "play.fill"
                )
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(!model.hasSnapshot)

            Button {
                model.reset()
            } label: {
                Image(systemName: "arrow.counterclockwise")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(!model.hasSnapshot)
            .help("Reset runtime")

            Button {
                model.step()
            } label: {
                Image(systemName: "forward.frame")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(model.isRunning || !model.hasSnapshot)
            .help("Advance one exact step")

            if model.replayFrameCount == 0 {
                Menu {
                    Button("Step 10") { model.step(10) }
                    Button("Step 100") { model.step(100) }
                } label: {
                    Image(systemName: "forward.end")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(model.isRunning || !model.hasSnapshot)
                .help("Advance multiple exact steps")
            }

            Menu {
                ForEach([15, 30, 60, 120, 0], id: \.self) { rate in
                    Button {
                        speedCap = rate
                    } label: {
                        let title = rate == 0 ? "Maximum" : "\(rate) steps/s"
                        if speedCap == rate {
                            Label(title, systemImage: "checkmark")
                        } else {
                            Text(title)
                        }
                    }
                }
            } label: {
                Label(speedCap == 0 ? "Max" : "\(speedCap)/s", systemImage: "speedometer")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Observation rate")

            if model.replayFrameCount > 0 {
                Slider(
                    value: Binding(
                        get: {
                            guard model.replayFrameCount > 1 else { return 0 }
                            return Double(model.replayFrameIndex) / Double(model.replayFrameCount - 1)
                        },
                        set: { model.seekReplay(toProgress: $0) }
                    ),
                    in: 0...1
                )
                .frame(width: 130)
                .accessibilityLabel("Replay timeline")

                Text("\(model.replayFrameIndex + 1)/\(model.replayFrameCount)")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .monospacedDigit()
                    .frame(minWidth: 48, alignment: .trailing)

                Toggle(isOn: Binding(
                    get: { model.replayIsLooping },
                    set: { model.setReplayLooping($0) }
                )) {
                    Image(systemName: "repeat")
                }
                .toggleStyle(.button)
                .controlSize(.small)
                .help("Loop replay")
            }
        }
    }

    private var stageObservationStatus: some View {
        HStack(spacing: 7) {
            if !model.hasSnapshot, model.runtimeStatusMessage == nil {
                ProgressView()
                    .controlSize(.small)
                    .scaleEffect(0.72)
            } else {
                Circle()
                    .fill(
                        model.runtimeStatusMessage != nil
                            ? StudioPalette.ember
                            : (model.isRunning ? StudioPalette.moss : StudioPalette.ocean)
                    )
                    .frame(width: 6, height: 6)
            }

            Text(stageStatusLine)
                .font(StudioType.dataSmall)
                .foregroundStyle(model.runtimeStatusMessage == nil ? StudioPalette.mutedInk : StudioPalette.ember)
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }

    private var stageDisplayControls: some View {
        HStack(spacing: 6) {
            if model.availableProjections.count > 1 {
                Picker("Field", selection: $model.activeProjection) {
                    ForEach(model.availableProjections) { projection in
                        Text(projection.label).tag(projection)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .controlSize(.small)
                .frame(width: min(210, CGFloat(model.availableProjections.count) * 86))
            }

            Toggle(isOn: $diagnosticsEnabled) {
                Image(systemName: "waveform.path.ecg")
            }
            .toggleStyle(.button)
            .controlSize(.small)
            .help("Show observation telemetry")

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

            Divider()
                .frame(height: 18)

            Button {
                adjustStageZoom(by: 0.85)
            } label: {
                Image(systemName: "minus.magnifyingglass")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Zoom out")

            Text("\(Int((stageZoom * 100).rounded()))%")
                .font(StudioType.dataSmall)
                .foregroundStyle(StudioPalette.mutedInk)
                .frame(width: 42)

            Button {
                adjustStageZoom(by: 1.15)
            } label: {
                Image(systemName: "plus.magnifyingglass")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Zoom in")

            Button {
                updateStageTransform(LeniaLabStageTransform(zoom: 1.85, offset: .zero))
            } label: {
                Image(systemName: "scope")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Focus specimen")

            Button {
                updateStageTransform(.init())
            } label: {
                Image(systemName: "arrow.down.right.and.arrow.up.left")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Fit field")
        }
    }

    @ViewBuilder
    private var stageCanvas: some View {
        if let runtimeStatusMessage = model.runtimeStatusMessage, !model.hasSnapshot {
            VStack(spacing: 10) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.title2)
                    .foregroundStyle(StudioPalette.ember)
                Text("World unavailable")
                    .font(StudioType.title)
                    .foregroundStyle(.white.opacity(0.94))
                Text(runtimeStatusMessage)
                    .font(StudioType.bodySmall)
                    .foregroundStyle(.white.opacity(0.68))
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 520)
            }
            .padding(24)
            .frame(maxWidth: .infinity, minHeight: 480)
            .background(StudioPalette.stageBottom)
        } else {
            ZStack {
                LabStageFrameSurface(
                    frameStore: frameStore,
                    renderMode: renderMode,
                    zoom: stageZoom,
                    offset: stageOffset,
                    gridSize: model.fieldWidth ?? gridPreset.rawValue,
                    hoveredGridPoint: hoveredGridPoint,
                    primaryTool: primaryTool,
                    secondaryTool: secondaryTool,
                    brushRadius: Int(brushRadius.rounded()),
                    selectedStampEntry: selectedStampEntry,
                    selectedStampPreview: selectedStampPreview,
                    isEditable: !isReadOnlyReplay,
                    accessibilityValue: stageAccessibilityValue,
                    onTransformChange: updateStageTransform,
                    onPrimaryPoint: { handleStagePoint($0, tool: primaryTool) },
                    onSecondaryPoint: { handleStagePoint($0, tool: secondaryTool) },
                    onHoverPointChange: { hoveredGridPoint = $0 },
                    onBrushRadiusDelta: adjustBrushRadius
                )

                if !model.hasSnapshot {
                    VStack(spacing: 10) {
                        ProgressView()
                            .controlSize(.small)
                        Text("Preparing observation")
                            .font(StudioType.dataSmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .fill(StudioPalette.consoleSurface.opacity(0.9))
                    )
                }
            }
            .frame(maxWidth: .infinity, minHeight: 480)
            .background(StudioPalette.stageBottom)
        }
    }

    private var stageDatumStrip: some View {
        let resolvedGrid = model.worldContract?.gridSize ?? model.fieldWidth ?? gridPreset.rawValue
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 18) {
                LabObservationDatum(
                    label: "Step",
                    value: model.hasSnapshot ? "\(model.latestStep)" : "--",
                    accent: StudioPalette.ember
                )
                LabObservationDatum(
                    label: "Field",
                    value: "\(resolvedGrid)x\(resolvedGrid)",
                    accent: StudioPalette.ocean
                )
                LabObservationDatum(
                    label: "Tool",
                    value: isReadOnlyReplay ? "Read-only" : primaryGhostCompactLabel,
                    accent: isReadOnlyReplay ? StudioPalette.mutedInk : hoverAccent(for: primaryTool)
                )
                if let hoveredGridPoint {
                    LabObservationDatum(
                        label: "Cell",
                        value: "\(hoveredGridPoint.x),\(hoveredGridPoint.y)",
                        accent: StudioPalette.ink
                    )
                }
                if diagnosticsEnabled {
                    LabObservationDatum(
                        label: "Activity",
                        value: String(format: "%.4f", model.activityEstimate),
                        accent: activityAccent(for: model.activityEstimate)
                    )
                    if let metrics = model.latestMetrics {
                        LabObservationDatum(
                            label: "Mass",
                            value: formatCompact(metrics.massMean),
                            accent: StudioPalette.moss
                        )
                        LabObservationDatum(
                            label: "Occupancy",
                            value: formatCompact(metrics.occupancy),
                            accent: StudioPalette.ember
                        )
                    }
                    LabObservationDatum(
                        label: "View",
                        value: model.snapshotFps > 0 ? String(format: "%.0f fps", model.snapshotFps) : "--",
                        accent: StudioPalette.ink
                    )
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
        }
        .background(StudioPalette.consoleSurfaceRaised.opacity(0.52))
    }

    private var controlSurface: some View {
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 12) {
                LabWorkbenchSection(title: "Organism", systemImage: "leaf") {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) {
                            Text(worldDraft?.sourceSummary ?? stageStatusLine)
                                .font(StudioType.dataSmall)
                                .foregroundStyle(StudioPalette.mutedInk)
                                .lineLimit(1)
                                .truncationMode(.middle)

                            Spacer(minLength: 8)
                            worldActionControls
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text(worldDraft?.sourceSummary ?? stageStatusLine)
                                .font(StudioType.dataSmall)
                                .foregroundStyle(StudioPalette.mutedInk)
                                .lineLimit(1)
                                .truncationMode(.middle)

                            ScrollView(.horizontal, showsIndicators: false) {
                                worldActionControls
                            }
                        }
                    }

                    HStack(spacing: 8) {
                        Text("Flow life")
                            .font(StudioType.labelStrong)
                            .foregroundStyle(StudioPalette.ink)
                        Spacer(minLength: 8)
                        Button {
                            catalogScope = .allConfigs
                            inspectorPanel = .catalog
                        } label: {
                            Label("Browse catalog", systemImage: "list.bullet.indent")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)

                        Menu {
                            ForEach(Self.blankWorldPresets) { preset in
                                Button(preset.name) {
                                    selectWorldPreset(preset)
                                }
                            }
                        } label: {
                            Label("Blank world", systemImage: "square.dashed")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(Self.missionPresets) { preset in
                                LabMissionPresetCard(
                                    preset: preset,
                                    isSelected: worldSelection == .preset(preset.id),
                                    onSelect: {
                                        selectWorldPreset(preset)
                                    }
                                )
                            }
                        }
                        .padding(.vertical, 1)
                    }
                }

                Divider()

                LabWorkbenchSection(title: "Tools", systemImage: "paintbrush") {
                    if isReadOnlyReplay {
                        Label("Read-only replay", systemImage: "lock.fill")
                            .font(StudioType.dataSmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                    } else {
                        LazyVGrid(
                            columns: [GridItem(.adaptive(minimum: 210), spacing: 12)],
                            alignment: .leading,
                            spacing: 10
                        ) {
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

                            LabSliderRow(label: "Brush radius", value: "\(Int(brushRadius))") {
                                Slider(value: $brushRadius, in: labBrushRadiusRange, step: 1)
                                    .controlSize(.small)
                            }

                            LabSliderRow(label: "Brush strength", value: String(format: "%.2f", brushStrength)) {
                                Slider(value: $brushStrength, in: 0.05...1.0, step: 0.05)
                                    .controlSize(.small)
                            }
                        }

                        Text(primaryGhostSummary)
                            .font(StudioType.dataSmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }

                Divider()

                LabWorkbenchSection(title: "Experiment", systemImage: "point.3.connected.trianglepath.dotted") {
                    experimentControls
                }

                Divider()

                DisclosureGroup(isExpanded: $showPhysicsEditor) {
                    physicsEditorContent
                } label: {
                    HStack(spacing: 8) {
                        Label("Physics", systemImage: "waveform.path.ecg")
                            .font(StudioType.body)
                            .foregroundStyle(StudioPalette.ink)
                        Spacer()
                        if let draft = worldDraft {
                            Text("dt \(formatCompact(draft.timeStep))  R \(formatCompact(draft.globalRadius))")
                                .font(StudioType.dataSmall)
                                .foregroundStyle(StudioPalette.mutedInk)
                        }
                    }
                }

                DisclosureGroup(isExpanded: $showContractEditor) {
                    contractEditorContent
                } label: {
                    HStack(spacing: 8) {
                        Label("World contract", systemImage: "slider.horizontal.3")
                            .font(StudioType.body)
                            .foregroundStyle(StudioPalette.ink)
                        Spacer()
                        Text(worldDraft?.connectivitySummary ?? "--")
                            .font(StudioType.dataSmall)
                            .foregroundStyle(StudioPalette.mutedInk)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
            }
        }
    }

    private var worldActionControls: some View {
        HStack(spacing: 6) {
            Toggle(
                "Auto food",
                isOn: Binding(
                    get: { model.autoFoodEnabled },
                    set: { model.setAutoFood(enabled: $0) }
                )
            )
                .toggleStyle(.button)
                .controlSize(.small)
                .disabled(model.externalReplayTitle != nil || !model.hasSnapshot)

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
                    .disabled(
                        requiredWorldBackend.map { $0 != option } ?? false
                    )
                }
            } label: {
                Label(labBackendLabel(backend), systemImage: "cpu")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Compute backend")

            Button {
                selectedStampID = selectedStampEntry.id
                worldSelection = .stamp(selectedStampEntry.id)
            } label: {
                Image(systemName: "scope")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Build world from selected specimen")

            Button {
                rebuildActiveWorld()
            } label: {
                Label("Apply", systemImage: "checkmark")
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(worldDraft == nil)
        }
    }

    private var experimentControls: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Button {
                    model.undo()
                } label: {
                    Image(systemName: "arrow.uturn.backward")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(model.isRunning || !model.canUndo)
                .help("Restore previous checkpoint")

                Button {
                    model.redo()
                } label: {
                    Image(systemName: "arrow.uturn.forward")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(model.isRunning || !model.canRedo)
                .help("Restore next checkpoint")

                Button {
                    model.createCheckpoint()
                } label: {
                    Label("Checkpoint", systemImage: "bookmark")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(!model.hasSnapshot || model.externalReplayTitle != nil)

                Text("\(model.checkpointCount)")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                    .frame(minWidth: 20)

                Button {
                    captureHoveredSpecimen()
                } label: {
                    Label("Capture", systemImage: "viewfinder.circle")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(
                    hoveredGridPoint == nil
                        || !model.hasSnapshot
                        || model.externalReplayTitle != nil
                )
                .help("Capture mass and local parameter context without food or walls")

                Button {
                    exportExperiment()
                } label: {
                    Label("Export", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(model.checkpointCount == 0)

                if let status = model.experimentStatusMessage {
                    Text(status)
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                }
            }
        }
    }

    private var inspectorSurface: some View {
        VStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 7) {
                Picker("Inspector", selection: $inspectorPanel) {
                    ForEach(LabInspectorPanel.allCases) { panel in
                        Text(panel.title).tag(panel)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .controlSize(.small)

                HStack(spacing: 7) {
                    Image(systemName: inspectorPanel.systemImage)
                        .foregroundStyle(StudioPalette.ocean)
                    Text(inspectorContextSummary)
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer(minLength: 8)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 7)
            .background(StudioPalette.consoleSurface)

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

    private var inspectorContextSummary: String {
        switch inspectorPanel {
        case .bay:
            return selectedStampEntry.name
        case .catalog:
            return "\(track1Catalog.catalog.families.count) families"
        case .runtime:
            return model.runtimeModeLabel
        case .signals:
            return model.latestMetrics == nil ? "Awaiting signal" : "t\(model.latestStep)"
        }
    }

    @ViewBuilder
    private var physicsEditorContent: some View {
        if let draft = worldDraft {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text("Kernel")
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.mutedInk)
                    Picker("Kernel", selection: $selectedPhysicsKernel) {
                        ForEach(0..<draft.kernelCount, id: \.self) { index in
                            Text("k\(index)").tag(index)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .controlSize(.small)
                    .frame(maxWidth: min(300, max(84, CGFloat(max(1, draft.kernelCount)) * 58)))

                    Spacer()

                    Button {
                        rebuildActiveWorld()
                    } label: {
                        Label("Apply", systemImage: "checkmark")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }

                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 230), spacing: 12)],
                    alignment: .leading,
                    spacing: 10
                ) {
                    LabSliderRow(label: "Time step", value: formatCompact(draft.timeStep)) {
                        Slider(value: timeStepPhysicsBinding, in: doubleRange(LabWorldDraft.timeStepRange))
                            .controlSize(.small)
                    }
                    LabSliderRow(label: "World radius", value: formatCompact(draft.globalRadius)) {
                        Slider(value: globalRadiusPhysicsBinding, in: doubleRange(LabWorldDraft.globalRadiusRange))
                            .controlSize(.small)
                    }
                    LabSliderRow(label: "Kernel radius", value: formatCompact(draft.kernelRelativeRadius(at: selectedPhysicsKernel) ?? 0)) {
                        Slider(value: kernelRadiusPhysicsBinding, in: doubleRange(LabWorldDraft.kernelRelativeRadiusRange))
                            .controlSize(.small)
                    }
                    LabSliderRow(label: "Growth center", value: formatCompact(draft.kernelCenter(at: selectedPhysicsKernel) ?? 0)) {
                        Slider(value: kernelCenterPhysicsBinding, in: doubleRange(LabWorldDraft.kernelCenterRange))
                            .controlSize(.small)
                    }
                    LabSliderRow(label: "Growth width", value: formatCompact(draft.kernelSigma(at: selectedPhysicsKernel) ?? 0)) {
                        Slider(value: kernelSigmaPhysicsBinding, in: doubleRange(LabWorldDraft.kernelSigmaRange))
                            .controlSize(.small)
                    }
                    LabSliderRow(label: "Growth gain", value: formatCompact(draft.kernelGain(at: selectedPhysicsKernel) ?? 0)) {
                        Slider(value: kernelGainPhysicsBinding, in: doubleRange(LabWorldDraft.kernelGainRange))
                            .controlSize(.small)
                    }
                }
            }
            .padding(.top, 8)
        } else if let worldDraftError {
            Label(worldDraftError, systemImage: "exclamationmark.triangle")
                .font(StudioType.bodySmall)
                .foregroundStyle(StudioPalette.ember)
                .padding(.top, 8)
        } else {
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                Text("Preparing physics")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            }
            .padding(.top, 8)
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

                    LabControlGroup(label: "Compute cap") {
                        Picker("Compute cap", selection: $speedCap) {
                            Text("15").tag(15)
                            Text("30").tag(30)
                            Text("60").tag(60)
                            Text("120").tag(120)
                            Text("Max").tag(0)
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
                        .foregroundStyle(StudioPalette.ember)
                }
            }
        } else if let worldDraftError {
            Text(worldDraftError)
                .font(StudioType.body)
                .foregroundStyle(StudioPalette.ember)
        } else {
            Text("No editable runtime contract is available for this world.")
                .font(StudioType.body)
                .foregroundStyle(StudioPalette.mutedInk)
        }
    }

    private var taxonomySurface: some View {
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    if track1Catalog.isLoading {
                        ProgressView()
                            .controlSize(.small)
                            .scaleEffect(0.72)
                    }
                    Text("\(flowOrganisms.count) Flow · \(track1Catalog.catalog.classicalReferenceConfigs.count) classical")
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

                Picker("Organisms", selection: $catalogScope) {
                    ForEach(LabCatalogScope.allCases) { scope in
                        Text(scope.title).tag(scope)
                    }
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .controlSize(.small)

                TextField(
                    catalogScope == .flowLife
                        ? "Search family, body plan, lineage, or specimen"
                        : "Search family, genus, species, or code",
                    text: $catalogSearch
                )
                    .textFieldStyle(.roundedBorder)
                    .controlSize(.small)

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

                if catalogScope == .flowLife, !flowOrganisms.isEmpty {
                    if matchingFlowOrganisms.isEmpty {
                        ContentUnavailableView.search(text: catalogSearch)
                            .frame(maxWidth: .infinity, minHeight: 150)
                    } else {
                        ForEach(matchingFlowFamilies) { family in
                            FlowOrganismFamilyPanel(
                                family: family,
                                selectedPath: selectedTrack1Config?.path,
                                onObserve: loadTrack1Config
                            )
                        }
                    }
                } else if catalogScope == .classicalReference,
                          !track1Catalog.catalog.classicalReferenceConfigs.isEmpty {
                    if matchingClassicalReferences.isEmpty {
                        ContentUnavailableView.search(text: catalogSearch)
                            .frame(maxWidth: .infinity, minHeight: 150)
                    } else {
                        LazyVGrid(
                            columns: [GridItem(.flexible())],
                            alignment: .leading,
                            spacing: 8
                        ) {
                            ForEach(matchingClassicalReferences) { config in
                                Track1FeaturedOrganismCard(
                                    config: config,
                                    isSelected: selectedTrack1Config?.path == config.path,
                                    onObserve: { loadTrack1Config(config) }
                                )
                            }
                        }
                    }
                } else if catalogScope == .allConfigs, !track1Catalog.catalog.families.isEmpty {
                    if filteredTaxonomyFamilies.isEmpty {
                        ContentUnavailableView.search(text: catalogSearch)
                            .frame(maxWidth: .infinity, minHeight: 150)
                    } else {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(filteredTaxonomyFamilies) { family in
                                    Track1FamilyChip(
                                        family: family,
                                        isSelected: displayedTrack1Family?.id == family.id,
                                        onSelect: {
                                            selectedTrack1FamilyID = family.id
                                        }
                                    )
                                }
                            }
                            .padding(.vertical, 1)
                        }

                        if let displayedTrack1Family {
                            Track1TaxonomyFamilyPanel(
                                family: displayedTrack1Family,
                                selectedPath: selectedTrack1Config?.path,
                                onLoad: loadTrack1Config
                            )
                        }
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
                    Text("No named organism catalog is available.")
                        .font(StudioType.body)
                        .foregroundStyle(StudioPalette.mutedInk)
                }
            }
        }
    }

    private var universeSurface: some View {
        StudioSurface(style: .console) {
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
                        LabCompactKeyValueRow(
                            label: "Speed cap",
                            value: speedCap == 0 ? "Max" : "\(speedCap) Hz"
                        )
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
                                onSelect: {
                                    selectedStampID = entry.id
                                    primaryTool = .creatureStamp
                                },
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
        StudioSurface(style: .console) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
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
            if !model.hasSnapshot {
                return "\(activeWorldEntry.name) · loading"
            }
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
            stageZoom = labRecommendedStageZoom(for: nextDraft.runtimeConfigValue)
            stageOffset = .zero
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
        let loadBackend = config.requiredLabBackend ?? backend
        if backend != loadBackend {
            backend = loadBackend
        }
        worldDraftError = nil
        do {
            let shouldRun = model.isRunning
            let nextDraft = try makeTrack1WorldDraft(config: config)
            worldDraft = nextDraft
            stageZoom = labRecommendedStageZoom(for: nextDraft.runtimeConfigValue)
            stageOffset = .zero
            if let matchingGrid = LabGridPreset.allCases.first(where: { $0.rawValue == nextDraft.gridSize }),
               matchingGrid != gridPreset {
                gridPreset = matchingGrid
            }
            model.rebuildWorld(
                sourceEntryID: config.studioEntry().id,
                runtimeConfig: nextDraft.runtimeConfig(overridingBackend: loadBackend),
                backend: loadBackend,
                speedCap: speedCap,
                shouldRun: shouldRun
            )
        } catch {
            worldDraft = nil
            worldDraftError = "Failed to load Track 1 config: \(labErrorDescription(error))"
        }
    }

    private func selectWorldPreset(_ preset: LabMissionPreset) {
        worldSelection = .preset(preset.id)
        if let requiredBackend = preset.organismConfig?.requiredLabBackend,
           backend != requiredBackend {
            backend = requiredBackend
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

    private func captureHoveredSpecimen() {
        guard let point = hoveredGridPoint else { return }
        let name = "Capture t\(model.latestStep)"
        Task {
            do {
                guard let result = try await model.captureSpecimen(
                    name: name,
                    near: point,
                    existingCreatures: appState.library
                ) else { return }
                appState.addToLocalLibrary(result.creature)
                selectedStampID = appState.studioEntry(for: result.creature).id
            } catch {
                model.experimentStatusMessage = error.localizedDescription
            }
        }
    }

    private func exportExperiment() {
        let panel = NSSavePanel()
        panel.canCreateDirectories = true
        panel.isExtensionHidden = false
        panel.nameFieldStringValue = "Lenia-t\(model.latestStep).leniaexperiment"
        panel.prompt = "Export Experiment"
        guard panel.runModal() == .OK, let selectedURL = panel.url else { return }
        let destination = selectedURL.pathExtension.isEmpty
            ? selectedURL.appendingPathExtension("leniaexperiment")
            : selectedURL
        do {
            try model.exportExperiment(
                title: "Lenia t\(model.latestStep)",
                sourceName: selectedWorldEntry.name,
                to: destination
            )
        } catch {
            model.experimentStatusMessage = error.localizedDescription
        }
    }

    private func track1RootDisplay(_ path: String) -> String {
        let components = URL(fileURLWithPath: path).pathComponents
        guard components.count > 3 else { return path }
        return ".../" + components.suffix(3).joined(separator: "/")
    }

    private func rebuildActiveWorld(backend overrideBackend: FlowSandboxBackend? = nil) {
        worldDraftError = nil
        let targetBackend = requiredWorldBackend ?? overrideBackend ?? backend
        let shouldRun = model.isRunning
        if let worldDraft {
            model.rebuildWorld(
                sourceEntryID: selectedWorldEntry.id,
                runtimeConfig: worldDraft.runtimeConfig(overridingBackend: targetBackend),
                backend: targetBackend,
                speedCap: speedCap,
                shouldRun: shouldRun
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
                shouldRun: shouldRun
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

    private func doubleRange(_ range: ClosedRange<Float>) -> ClosedRange<Double> {
        Double(range.lowerBound)...Double(range.upperBound)
    }

    private var timeStepPhysicsBinding: Binding<Double> {
        Binding(
            get: { Double(worldDraft?.timeStep ?? LabWorldDraft.timeStepRange.lowerBound) },
            set: { value in
                applyDraftChange { $0.setTimeStep(Float(value)) }
            }
        )
    }

    private var globalRadiusPhysicsBinding: Binding<Double> {
        Binding(
            get: { Double(worldDraft?.globalRadius ?? LabWorldDraft.globalRadiusRange.lowerBound) },
            set: { value in
                applyDraftChange { $0.setGlobalRadius(Float(value)) }
            }
        )
    }

    private var kernelRadiusPhysicsBinding: Binding<Double> {
        Binding(
            get: {
                Double(worldDraft?.kernelRelativeRadius(at: selectedPhysicsKernel)
                    ?? LabWorldDraft.kernelRelativeRadiusRange.lowerBound)
            },
            set: { value in
                applyDraftChange {
                    $0.setKernelRelativeRadius(Float(value), at: selectedPhysicsKernel)
                }
            }
        )
    }

    private var kernelCenterPhysicsBinding: Binding<Double> {
        Binding(
            get: {
                Double(worldDraft?.kernelCenter(at: selectedPhysicsKernel)
                    ?? LabWorldDraft.kernelCenterRange.lowerBound)
            },
            set: { value in
                applyDraftChange { $0.setKernelCenter(Float(value), at: selectedPhysicsKernel) }
            }
        )
    }

    private var kernelSigmaPhysicsBinding: Binding<Double> {
        Binding(
            get: {
                Double(worldDraft?.kernelSigma(at: selectedPhysicsKernel)
                    ?? LabWorldDraft.kernelSigmaRange.lowerBound)
            },
            set: { value in
                applyDraftChange { $0.setKernelSigma(Float(value), at: selectedPhysicsKernel) }
            }
        )
    }

    private var kernelGainPhysicsBinding: Binding<Double> {
        Binding(
            get: {
                Double(worldDraft?.kernelGain(at: selectedPhysicsKernel)
                    ?? LabWorldDraft.kernelGainRange.lowerBound)
            },
            set: { value in
                applyDraftChange { $0.setKernelGain(Float(value), at: selectedPhysicsKernel) }
            }
        )
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
        guard !isReadOnlyReplay else { return }
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

enum LabWorkspaceLayout: Equatable {
    case stacked
    case split
}

func labWorkspaceLayout(for width: CGFloat) -> LabWorkspaceLayout {
    width < 1_180 ? .stacked : .split
}

let labBrushRadiusRange: ClosedRange<Double> = 1...16

func labStageAllowsEditing(externalReplayTitle: String?) -> Bool {
    externalReplayTitle == nil
}

func labBrushRadiusStepping(from radius: Double, delta: Int) -> Double {
    min(labBrushRadiusRange.upperBound, max(labBrushRadiusRange.lowerBound, radius + Double(delta)))
}

private enum LabCatalogScope: String, CaseIterable, Identifiable {
    case flowLife
    case classicalReference
    case allConfigs

    var id: Self { self }

    var title: String {
        switch self {
        case .flowLife: "Flow"
        case .classicalReference: "Classical"
        case .allConfigs: "All configs"
        }
    }
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
            "Organisms"
        case .runtime:
            "Runtime"
        case .signals:
            "Signals"
        }
    }

    var systemImage: String {
        switch self {
        case .bay:
            "shippingbox"
        case .catalog:
            "leaf"
        case .runtime:
            "cpu"
        case .signals:
            "waveform.path.ecg"
        }
    }
}

func track1Config(_ config: Track1TaxonomyConfig, matches search: String) -> Bool {
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !query.isEmpty else { return true }
    let normalizedQuery = track1SearchKey(query)
    return [
        config.family,
        config.genus,
        config.displayName,
        config.patternID,
        config.catalogCollection.title,
        config.catalogTier.title,
        config.catalogHierarchy,
    ]
        .contains {
            $0.localizedCaseInsensitiveContains(query)
                || (!normalizedQuery.isEmpty && track1SearchKey($0).contains(normalizedQuery))
        }
}

private func track1SearchKey(_ value: String) -> String {
    value.lowercased()
        .components(separatedBy: CharacterSet.alphanumerics.inverted)
        .joined()
}

func filteredTrack1Families(
    _ families: [Track1TaxonomyFamily],
    search: String
) -> [Track1TaxonomyFamily] {
    let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !query.isEmpty else { return families }
    return families.compactMap { family in
        if family.name.localizedCaseInsensitiveContains(query) {
            return family
        }
        let genera = family.genera.compactMap { genus -> Track1TaxonomyGenus? in
            if genus.name.localizedCaseInsensitiveContains(query) {
                return genus
            }
            let configs = genus.configs.filter { track1Config($0, matches: query) }
            guard !configs.isEmpty else { return nil }
            return Track1TaxonomyGenus(id: genus.id, name: genus.name, configs: configs)
        }
        guard !genera.isEmpty else { return nil }
        return Track1TaxonomyFamily(id: family.id, name: family.name, genera: genera)
    }
}

private struct FlowOrganismFamilyPanel: View {
    let family: FlowOrganismFamily
    let selectedPath: String?
    let onObserve: (Track1TaxonomyConfig) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(family.name)
                    .font(StudioType.labelStrong)
                    .foregroundStyle(StudioPalette.ink)
                Spacer(minLength: 6)
                Text("\(family.configs.count) specimens")
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
                if family.configs.allSatisfy({ $0.catalogTier == .experimental }) {
                    Text("Experimental")
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.ember)
                }
            }

            ForEach(family.configs) { config in
                Track1FeaturedOrganismCard(
                    config: config,
                    isSelected: selectedPath == config.path,
                    onObserve: { onObserve(config) }
                )
            }
        }
    }
}

private struct Track1FeaturedOrganismCard: View {
    let config: Track1TaxonomyConfig
    let isSelected: Bool
    let onObserve: () -> Void

    private var runtimeLabel: String {
        switch config.catalogTier {
        case .primary: "Metal Flow"
        case .experimental: "Experimental"
        case .reference: "Additive reference"
        }
    }

    var body: some View {
        Button(action: onObserve) {
            HStack(spacing: 9) {
                Track1OrganismThumbnailView(config: config, size: 62)
                    .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))

                VStack(alignment: .leading, spacing: 4) {
                    Text(config.genus)
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(2)
                    Text("\(config.family) / \(config.patternID)")
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                    HStack(spacing: 5) {
                        Text(config.displayName)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text(runtimeLabel)
                            .foregroundStyle(
                                config.catalogTier == .primary
                                    ? StudioPalette.moss
                                    : StudioPalette.ember
                            )
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .font(StudioType.dataSmall)
                }
                Spacer(minLength: 2)
                Image(systemName: isSelected ? "checkmark.circle.fill" : "play.circle")
                    .foregroundStyle(isSelected ? StudioPalette.moss : StudioPalette.ocean)
            }
            .frame(maxWidth: .infinity, minHeight: 70, alignment: .leading)
            .padding(7)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(isSelected ? StudioPalette.consoleSurfaceRaised : StudioPalette.consoleControl.opacity(0.46))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .stroke(isSelected ? StudioPalette.moss.opacity(0.72) : StudioPalette.hairline.opacity(0.62), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .help("Observe \(config.catalogHierarchy) on \(runtimeLabel)")
    }
}

private func labErrorDescription(_ error: Error) -> String {
    let description = String(describing: error)
    if !description.isEmpty, description != error.localizedDescription {
        return description
    }
    return error.localizedDescription
}

private struct LabObservationDatum: View {
    let label: String
    let value: String
    let accent: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Text(label.uppercased())
                .font(StudioType.label)
                .foregroundStyle(StudioPalette.mutedInk)
            Text(value)
                .font(StudioType.dataSmall)
                .foregroundStyle(accent)
                .lineLimit(1)
        }
        .fixedSize(horizontal: true, vertical: false)
    }
}

private struct LabTacticalStageOverlay: View {
    var body: some View {
        GeometryReader { proxy in
            let size = proxy.size
            ZStack {
                Path { path in
                    let columns = 4
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
                .stroke(StudioPalette.ocean.opacity(0.035), lineWidth: 1)

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
                .stroke(StudioPalette.ink.opacity(0.18), lineWidth: 1)

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
                .stroke(StudioPalette.ocean.opacity(0.16), lineWidth: 1)
            }
        }
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
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(label)
                    .font(StudioType.bodySmall)
                    .foregroundStyle(StudioPalette.ink)
                Spacer(minLength: 8)
                Text(value)
                    .font(StudioType.dataSmall)
                    .foregroundStyle(StudioPalette.mutedInk)
            }

            control
                .frame(maxWidth: .infinity)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct LabMissionPresetCard: View {
    let preset: LabMissionPreset
    let isSelected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            HStack(alignment: .center, spacing: 9) {
                if let config = preset.organismConfig {
                    Track1OrganismThumbnailView(config: config, size: 52)
                        .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(preset.name)
                        .font(StudioType.labelStrong)
                        .foregroundStyle(StudioPalette.ink)
                        .lineLimit(2)
                    Text(preset.subtitle)
                        .font(StudioType.dataSmall)
                        .foregroundStyle(StudioPalette.mutedInk)
                        .lineLimit(1)
                }

                Spacer(minLength: 0)
                Circle()
                    .fill(isSelected ? StudioPalette.moss : StudioPalette.hairline)
                    .frame(width: 6, height: 6)
            }
            .frame(width: 224, height: 62, alignment: .leading)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(isSelected ? StudioPalette.consoleSurfaceRaised : StudioPalette.consoleControl.opacity(0.34))
            )
            .overlay {
                if isSelected {
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .stroke(StudioPalette.ocean.opacity(0.68), lineWidth: 1)
                }
            }
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

private struct LabWorkbenchSection<Content: View>: View {
    let title: String
    let systemImage: String
    let content: Content

    init(title: String, systemImage: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.systemImage = systemImage
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: systemImage)
                .font(StudioType.panelTitle)
                .foregroundStyle(StudioPalette.ink)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
    let hoveredGridPoint: SIMD2<Int>?
    let primaryTool: SandboxTool
    let secondaryTool: SandboxTool
    let brushRadius: Int
    let selectedStampEntry: StudioCompareEntry
    let selectedStampPreview: CreatureStamp?
    let isEditable: Bool
    let accessibilityValue: String
    let onTransformChange: (LeniaLabStageTransform) -> Void
    let onPrimaryPoint: (SIMD2<Int>) -> Void
    let onSecondaryPoint: (SIMD2<Int>) -> Void
    let onHoverPointChange: (SIMD2<Int>?) -> Void
    let onBrushRadiusDelta: ((Int) -> Void)?

    var body: some View {
        stageWithEditActions(
            ZStack(alignment: .topLeading) {
                LeniaLabStageView(
                    frameStore: frameStore,
                    renderMode: renderMode,
                    zoom: zoom,
                    offset: offset,
                    scrollPolicy: .transformCanvas,
                    onTransformChange: onTransformChange,
                    onPrimaryPoint: isEditable ? onPrimaryPoint : { _ in },
                    onSecondaryPoint: isEditable ? onSecondaryPoint : { _ in },
                    onHoverPointChange: onHoverPointChange,
                    onBrushRadiusDelta: isEditable ? onBrushRadiusDelta : nil
                )

                LabTacticalStageOverlay()
                    .allowsHitTesting(false)

                if isEditable {
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
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Lenia simulation field")
        .accessibilityValue(accessibilityValue)
        .accessibilityAddTraits(.isImage)
        .accessibilityAction(named: "Fit field") {
            onTransformChange(.init())
        }
    }

    @ViewBuilder
    private func stageWithEditActions<Content: View>(_ content: Content) -> some View {
        if isEditable {
            content
                .accessibilityAction(named: "Apply \(primaryTool.rawValue) at field center") {
                    onPrimaryPoint(accessibilityTargetPoint)
                }
                .accessibilityAction(named: "Apply \(secondaryTool.rawValue) at field center") {
                    onSecondaryPoint(accessibilityTargetPoint)
                }
        } else {
            content
        }
    }

    private var accessibilityTargetPoint: SIMD2<Int> {
        hoveredGridPoint ?? SIMD2<Int>(max(0, gridSize / 2), max(0, gridSize / 2))
    }

}

enum LeniaLabStageScrollPolicy: Equatable, Sendable {
    case passThrough
    case transformCanvas
}

struct LeniaLabStageView: NSViewRepresentable {
    let frame: LeniaFieldFrame?
    let frameStore: LeniaLabFrameStore?
    let renderMode: LeniaRenderMode
    let zoom: CGFloat
    let offset: CGSize
    let scrollPolicy: LeniaLabStageScrollPolicy
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
        scrollPolicy: LeniaLabStageScrollPolicy = .passThrough,
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
        self.scrollPolicy = scrollPolicy
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
        scrollPolicy: LeniaLabStageScrollPolicy = .passThrough,
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
        self.scrollPolicy = scrollPolicy
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
        view.scrollPolicy = scrollPolicy
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
            transform: LeniaLabStageTransform(zoom: zoom, offset: offset),
            scrollPolicy: scrollPolicy
        )
    }
}

final class LeniaLabStageNSView: MTKView {
    private let renderer: LeniaMetalFieldRenderer
    private var trackingAreaHandle: NSTrackingArea?
    private var renderMode: LeniaRenderMode = .smoothMagma
    private var continuousDrawing = false
    var transform = LeniaLabStageTransform()
    var gridSize = 0
    var onTransformChange: ((LeniaLabStageTransform) -> Void)?
    var onPrimaryPoint: ((SIMD2<Int>) -> Void)?
    var onSecondaryPoint: ((SIMD2<Int>) -> Void)?
    var onHoverPointChange: ((SIMD2<Int>?) -> Void)?
    var onBrushRadiusDelta: ((Int) -> Void)?
    var scrollPolicy: LeniaLabStageScrollPolicy = .passThrough

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
        requestDraw()
    }

    func updateFrame(_ frame: LeniaFieldFrame?) {
        gridSize = frame?.width ?? 0
        renderer.update(frame: frame)
        if gridSize == 0 {
            onHoverPointChange?(nil)
        }
        requestDraw()
    }

    func update(
        renderMode: LeniaRenderMode,
        transform: LeniaLabStageTransform,
        scrollPolicy: LeniaLabStageScrollPolicy
    ) {
        let viewSize = bounds.size
        let shouldRedraw = self.renderMode.rawValue != renderMode.rawValue
            || self.transform != transform
            || renderer.viewSize != viewSize
        self.renderMode = renderMode
        self.transform = transform
        self.scrollPolicy = scrollPolicy
        renderer.viewSize = viewSize
        renderer.transform = transform
        renderer.renderMode = renderMode
        if shouldRedraw {
            requestDraw()
        }
    }

    func setFramePacing(active: Bool) {
        guard continuousDrawing != active else { return }
        continuousDrawing = active
        enableSetNeedsDisplay = !active
        isPaused = !active
        requestDraw()
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
        guard scrollPolicy == .transformCanvas else {
            super.magnify(with: event)
            return
        }
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
        guard scrollPolicy == .transformCanvas else {
            super.scrollWheel(with: event)
            return
        }

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
        requestDraw()
    }

    private func requestDraw() {
        if !continuousDrawing {
            needsDisplay = true
        }
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
        .white.opacity(0.92)
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
        return "MLX GPU"
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
