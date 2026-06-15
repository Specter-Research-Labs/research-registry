import Foundation
import LeniaCore
import MLX

enum LabFieldProjection: Hashable, Identifiable, Sendable {
    case matter
    case channel(Int)

    var id: String {
        switch self {
        case .matter:
            return "matter"
        case .channel(let channel):
            return "channel-\(channel)"
        }
    }

    var label: String {
        switch self {
        case .matter:
            return "Matter"
        case .channel(let channel):
            return "Channel \(channel)"
        }
    }
}

enum LabRuntimeHandle: Sendable {
    case engine(LeniaInteractiveEngine)
    case replay(CanonicalLabRuntime)
    case frameSequence(TTFrameSequenceRuntime)

    var modeLabel: String {
        switch self {
        case .engine(let engine):
            return engine.descriptor.executionLabel
        case .replay:
            return "Canonical replay"
        case .frameSequence:
            return "TT export replay"
        }
    }

    func start() async {
        switch self {
        case .engine(let engine):
            await engine.start()
        case .replay(let runtime):
            await runtime.start()
        case .frameSequence(let runtime):
            await runtime.start()
        }
    }

    func pause() async {
        switch self {
        case .engine(let engine):
            await engine.pause()
        case .replay(let runtime):
            await runtime.pause()
        case .frameSequence(let runtime):
            await runtime.pause()
        }
    }

    func resume() async {
        switch self {
        case .engine(let engine):
            await engine.resume()
        case .replay(let runtime):
            await runtime.resume()
        case .frameSequence(let runtime):
            await runtime.resume()
        }
    }

    func stop() async {
        switch self {
        case .engine(let engine):
            await engine.stop()
        case .replay(let runtime):
            await runtime.stop()
        case .frameSequence(let runtime):
            await runtime.stop()
        }
    }

    func reset() async {
        switch self {
        case .engine(let engine):
            await engine.reset()
        case .replay(let runtime):
            await runtime.reset()
        case .frameSequence(let runtime):
            await runtime.reset()
        }
    }

    func setSpeedCap(hz: Int) async {
        switch self {
        case .engine(let engine):
            await engine.setSpeedCap(hz: hz)
        case .replay(let runtime):
            await runtime.setSpeedCap(hz: hz)
        case .frameSequence(let runtime):
            await runtime.setSpeedCap(hz: hz)
        }
    }

    func setAutoFoodSpawn(
        enabled: Bool,
        probability: Float,
        patchSize: Int,
        value: Float
    ) async {
        switch self {
        case .engine(let engine):
            await engine.setAutoFoodSpawn(
                enabled: enabled,
                probability: probability,
                patchSize: patchSize,
                value: value
            )
        case .replay(let runtime):
            await runtime.setAutoFoodSpawn(
                enabled: enabled,
                probability: probability,
                patchSize: patchSize,
                value: value
            )
        case .frameSequence(let runtime):
            await runtime.setAutoFoodSpawn(
                enabled: enabled,
                probability: probability,
                patchSize: patchSize,
                value: value
            )
        }
    }

    func worldContract() async -> FlowSandboxWorldContract {
        switch self {
        case .engine(let engine):
            await engine.worldContract()
        case .replay(let runtime):
            await runtime.worldContract()
        case .frameSequence(let runtime):
            await runtime.worldContract()
        }
    }

    func snapshot(
        refreshMetrics: Bool,
        projection: LabFieldProjection
    ) async -> FlowSandboxSnapshot {
        switch self {
        case .engine(let engine):
            await engine.displaySnapshot(refreshMetrics: refreshMetrics)
        case .replay(let runtime):
            await runtime.snapshot(refreshMetrics: refreshMetrics, projection: projection)
        case .frameSequence(let runtime):
            await runtime.snapshot(refreshMetrics: refreshMetrics, projection: projection)
        }
    }

    func availableProjections() async -> [LabFieldProjection] {
        switch self {
        case .engine:
            return [.matter]
        case .replay(let runtime):
            return await runtime.availableProjections()
        case .frameSequence(let runtime):
            return await runtime.availableProjections()
        }
    }

    func applyStroke(_ stroke: SandboxStroke) async {
        switch self {
        case .engine(let engine):
            await engine.applyStroke(stroke)
        case .replay(let runtime):
            await runtime.applyStroke(stroke)
        case .frameSequence(let runtime):
            await runtime.applyStroke(stroke)
        }
    }

    func applyCreatureStamp(_ stamp: CreatureStamp, center: SIMD2<Int>) async {
        switch self {
        case .engine(let engine):
            await engine.applyCreatureStamp(stamp, center: center)
        case .replay(let runtime):
            await runtime.applyCreatureStamp(stamp, center: center)
        case .frameSequence(let runtime):
            await runtime.applyCreatureStamp(stamp, center: center)
        }
    }

    func telemetry() async -> FlowSandboxRuntimeTelemetry {
        switch self {
        case .engine(let engine):
            await engine.telemetry()
        case .replay(let runtime):
            await runtime.telemetry()
        case .frameSequence(let runtime):
            await runtime.telemetry()
        }
    }
}

actor CanonicalLabRuntime {
    private let runtime: FlowLeniaInteractiveSimulator
    private let baseWallMask: [Float]
    private let hasBaseWallMask: Bool
    private let runtimeConfig: LeniaRuntimeConfig

    private var state: FlowLeniaInteractiveState
    private var initialState: FlowLeniaInteractiveState
    private var wallOverlay: [Float]
    private var hasWallOverlay = false
    private var simulationTask: Task<Void, Never>?
    private var isPaused = true
    private var targetFrameDuration: Duration = .milliseconds(16)
    private var autoFoodEnabled = false
    private var autoFoodProbability: Float = 0.03
    private var autoFoodPatchSize = 12
    private var autoFoodValue: Float = 0.35
    private var lastStepDurationMs = 0.0
    private var cachedMetrics = FlowSandboxMetrics(
        massMean: 0,
        occupancy: 0,
        foodMean: 0,
        wallFraction: 0,
        massPeak: 0,
        foodPeak: 0,
        nonFiniteFraction: 0
    )

    init(replayReference: StudioReplayReference, backend: FlowSandboxBackend) throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: replayReference.baseConfigPath))
        let runtimeState = try Self.buildRuntimeState(baseConfigData: data, backend: backend)

        self.runtime = runtimeState.runtime
        self.runtimeConfig = runtimeState.runtimeConfig
        self.initialState = runtimeState.initialState
        self.state = runtimeState.initialState
        self.baseWallMask = runtimeState.wallMask
        self.hasBaseWallMask = canonicalHasClosedCells(runtimeState.wallMask)
        self.wallOverlay = Array(repeating: 1, count: runtimeState.wallMask.count)
        self.cachedMetrics = canonicalLabMetrics(
            mass: canonicalMatterData(runtime: runtimeState.runtime, state: runtimeState.initialState),
            food: canonicalFoodData(state: runtimeState.initialState, size: runtimeState.runtimeConfig.sx * runtimeState.runtimeConfig.sy),
            walls: runtimeState.wallMask
        )
    }

    init(baseConfigData: Data, backend: FlowSandboxBackend) throws {
        let runtimeState = try Self.buildRuntimeState(baseConfigData: baseConfigData, backend: backend)

        self.runtime = runtimeState.runtime
        self.runtimeConfig = runtimeState.runtimeConfig
        self.initialState = runtimeState.initialState
        self.state = runtimeState.initialState
        self.baseWallMask = runtimeState.wallMask
        self.hasBaseWallMask = canonicalHasClosedCells(runtimeState.wallMask)
        self.wallOverlay = Array(repeating: 1, count: runtimeState.wallMask.count)
        self.cachedMetrics = canonicalLabMetrics(
            mass: canonicalMatterData(runtime: runtimeState.runtime, state: runtimeState.initialState),
            food: canonicalFoodData(state: runtimeState.initialState, size: runtimeState.runtimeConfig.sx * runtimeState.runtimeConfig.sy),
            walls: runtimeState.wallMask
        )
    }

    init(runtimeConfig: LeniaRuntimeConfig) throws {
        let runtimeState = Self.buildRuntimeState(runtimeConfig: runtimeConfig)

        self.runtime = runtimeState.runtime
        self.runtimeConfig = runtimeState.runtimeConfig
        self.initialState = runtimeState.initialState
        self.state = runtimeState.initialState
        self.baseWallMask = runtimeState.wallMask
        self.hasBaseWallMask = canonicalHasClosedCells(runtimeState.wallMask)
        self.wallOverlay = Array(repeating: 1, count: runtimeState.wallMask.count)
        self.cachedMetrics = canonicalLabMetrics(
            mass: canonicalMatterData(runtime: runtimeState.runtime, state: runtimeState.initialState),
            food: canonicalFoodData(state: runtimeState.initialState, size: runtimeState.runtimeConfig.sx * runtimeState.runtimeConfig.sy),
            walls: runtimeState.wallMask
        )
    }

    private static func buildRuntimeState(
        baseConfigData: Data,
        backend: FlowSandboxBackend
    ) throws -> (
        runtime: FlowLeniaInteractiveSimulator,
        runtimeConfig: LeniaRuntimeConfig,
        initialState: FlowLeniaInteractiveState,
        wallMask: [Float]
    ) {
        let runtimeConfig = try loadRuntimeConfig(from: baseConfigData, overrides: ["backend": backend.rawValue])
        let runtime = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
        let initialState = runtime.makeInitialState()
        let wallMask = runtime.wallMaskMap()?.asArray(Float.self)
            ?? Array(repeating: 1, count: runtimeConfig.sx * runtimeConfig.sy)
        return (runtime, runtimeConfig, initialState, wallMask)
    }

    private static func buildRuntimeState(
        runtimeConfig: LeniaRuntimeConfig
    ) -> (
        runtime: FlowLeniaInteractiveSimulator,
        runtimeConfig: LeniaRuntimeConfig,
        initialState: FlowLeniaInteractiveState,
        wallMask: [Float]
    ) {
        let runtime = FlowLeniaInteractiveSimulator(runtimeConfig: runtimeConfig)
        let initialState = runtime.makeInitialState()
        let wallMask = runtime.wallMaskMap()?.asArray(Float.self)
            ?? Array(repeating: 1, count: runtimeConfig.sx * runtimeConfig.sy)
        return (runtime, runtimeConfig, initialState, wallMask)
    }

    deinit {
        simulationTask?.cancel()
    }

    func start() {
        isPaused = false
    }

    func pause() {
        isPaused = true
    }

    func resume() {
        isPaused = false
    }

    func stop() {
        simulationTask?.cancel()
        simulationTask = nil
        isPaused = true
    }

    func reset() {
        state = initialState
        wallOverlay = Array(repeating: 1, count: wallOverlay.count)
        hasWallOverlay = false
        lastStepDurationMs = 0
        cachedMetrics = canonicalLabMetrics(
            mass: canonicalMatterData(runtime: runtime, state: state),
            food: canonicalFoodData(state: state, size: runtimeConfig.sx * runtimeConfig.sy),
            walls: effectiveWalls()
        )
    }

    func setSpeedCap(hz: Int) {
        let clamped = max(1, min(240, hz))
        targetFrameDuration = .milliseconds(max(1, Int((1000.0 / Double(clamped)).rounded())))
    }

    func setAutoFoodSpawn(
        enabled: Bool,
        probability: Float? = nil,
        patchSize: Int? = nil,
        value: Float? = nil
    ) {
        autoFoodEnabled = enabled
        if let probability {
            autoFoodProbability = max(0, min(1, probability))
        }
        if let patchSize {
            autoFoodPatchSize = max(1, min(runtimeConfig.sx, patchSize))
        }
        if let value {
            autoFoodValue = max(0, value)
        }
    }

    func worldContract() -> FlowSandboxWorldContract {
        FlowSandboxWorldContract(
            backend: sandboxBackend(for: runtimeConfig.backend),
            gridSize: runtimeConfig.sx,
            channels: runtimeConfig.channels,
            parameterFieldMode: FlowLeniaParameterFieldMode.fromEmbeddingEnabled(runtimeConfig.parameterEmbedding.enabled),
            parameterFieldCount: runtimeConfig.parameterEmbedding.enabled ? runtimeConfig.nbK : 0,
            kernelCount: runtimeConfig.nbK,
            dt: runtimeConfig.dt,
            dd: runtimeConfig.dd,
            sigma: runtimeConfig.sigma,
            n: runtimeConfig.n,
            thetaA: runtimeConfig.thetaA,
            border: runtimeConfig.border,
            kernelProfile: runtimeConfig.implementation.kernelProfile,
            seed: runtimeConfig.initSeed,
            radius: runtimeConfig.params.R,
            executionSummary: "Canonical replay on \(runtimeConfig.backend.displayName)",
            fieldSummary: canonicalFieldSummary(runtimeConfig: runtimeConfig),
            featureSummary: canonicalFeatureSummary(runtimeConfig: runtimeConfig),
            connectivitySummary: canonicalConnectivitySummary(runtimeConfig: runtimeConfig),
            kernels: runtimeConfig.params.r.indices.map { index in
                FlowSandboxKernelContract(
                    id: index,
                    radius: runtimeConfig.params.r[index],
                    center: runtimeConfig.params.m[index],
                    sigma: runtimeConfig.params.s[index],
                    gain: runtimeConfig.params.h[index],
                    beta: runtimeConfig.params.b[index],
                    weights: runtimeConfig.params.w[index],
                    anchors: runtimeConfig.params.a[index]
                )
            }
        )
    }

    func availableProjections() -> [LabFieldProjection] {
        guard runtimeConfig.channels > 1 else {
            return [.matter]
        }
        return [.matter] + (0..<runtimeConfig.channels).map(LabFieldProjection.channel)
    }

    func step() {
        state = runtime.step(state)
        if autoFoodEnabled {
            injectAutoFoodPatchIfNeeded()
        }
        if hasWallOverlay {
            applyWallOverlay()
        }
    }

    func applyStroke(_ stroke: SandboxStroke) {
        guard !stroke.points.isEmpty else { return }
        let size = runtimeConfig.sx
        let parameterCount = runtimeConfig.parameterEmbedding.enabled ? runtimeConfig.nbK : 0
        eval(state.mass)
        if let params = state.params {
            eval(params)
        }
        if let food = state.food {
            eval(food)
        }

        var mass = state.mass.asArray(Float.self)
        var params = state.params?.asArray(Float.self)
        var food = state.food?.asArray(Float.self)
        var walls = wallOverlay
        let wallSupport = effectiveWalls(overlay: walls)

        switch stroke.tool {
        case .creatureStamp:
            return
        case .food:
            guard food != nil else { return }
            forEachStrokeCell(stroke: stroke, size: size) { x, y in
                let index = x * size + y
                guard wallSupport[index] > 0.5 else { return }
                let currentFood = food?[index] ?? 0
                food?[index] = min(1, max(0, currentFood + stroke.strength))
            }
        case .wall:
            forEachStrokeCell(stroke: stroke, size: size) { x, y in
                let index = x * size + y
                walls[index] = 0
                zeroMass(at: index, channels: runtimeConfig.channels, mass: &mass)
                zeroParams(at: index, parameterCount: parameterCount, params: &params)
                food?[index] = 0
            }
        case .erase:
            forEachStrokeCell(stroke: stroke, size: size) { x, y in
                let index = x * size + y
                walls[index] = 1
                zeroMass(at: index, channels: runtimeConfig.channels, mass: &mass)
                zeroParams(at: index, parameterCount: parameterCount, params: &params)
                food?[index] = 0
            }
        case .mutation:
            guard params != nil, parameterCount > 0 else { return }
            var rng = SeededRandomNumberGenerator(seed: UInt64(state.step + stroke.radius + 17))
            forEachStrokeCell(stroke: stroke, size: size) { x, y in
                let index = x * size + y
                guard wallSupport[index] > 0.5 else { return }
                for parameter in 0..<parameterCount {
                    let paramIndex = index * parameterCount + parameter
                    let delta = Float.random(in: -stroke.strength...stroke.strength, using: &rng)
                    let currentValue = params?[paramIndex] ?? 0
                    params?[paramIndex] = min(2, max(-2, currentValue + delta))
                }
            }
        }

        wallOverlay = walls
        hasWallOverlay = canonicalHasClosedCells(wallOverlay)
        materializeState(mass: mass, params: params, food: food)
        if hasWallOverlay {
            applyWallOverlay()
        }
        cachedMetrics = canonicalLabMetrics(
            mass: canonicalMatterData(runtime: runtime, state: state),
            food: canonicalFoodData(state: state, size: runtimeConfig.sx * runtimeConfig.sy),
            walls: effectiveWalls()
        )
    }

    func applyCreatureStamp(_ stamp: CreatureStamp, center: SIMD2<Int>) {
        eval(state.mass)
        if let params = state.params {
            eval(params)
        }
        if let food = state.food {
            eval(food)
        }

        let size = runtimeConfig.sx
        let parameterCount = runtimeConfig.parameterEmbedding.enabled ? runtimeConfig.nbK : 0
        let wallSupport = effectiveWalls()
        var mass = state.mass.asArray(Float.self)
        var params = state.params?.asArray(Float.self)
        let food = state.food?.asArray(Float.self)
        let originX = center.x - stamp.width / 2
        let originY = center.y - stamp.height / 2

        for localX in 0..<stamp.width {
            for localY in 0..<stamp.height {
                let worldX = originX + localX
                let worldY = originY + localY
                guard canonicalContains(x: worldX, y: worldY, size: size) else { continue }
                let worldIndex = worldX * size + worldY
                guard wallSupport[worldIndex] > 0.5 else { continue }
                let stampIndex = localX * stamp.height + localY
                let massValue = stamp.mass[stampIndex]
                guard massValue > 0.001 else { continue }

                let massBase = worldIndex * runtimeConfig.channels
                mass[massBase] = max(mass[massBase], massValue)

                if parameterCount > 0,
                   stamp.parameterCount == parameterCount,
                   params != nil {
                    let stampParamBase = stampIndex * parameterCount
                    let paramBase = worldIndex * parameterCount
                    for parameter in 0..<parameterCount {
                        params?[paramBase + parameter] = stamp.params[stampParamBase + parameter]
                    }
                }
            }
        }

        materializeState(mass: mass, params: params, food: food)
        if hasWallOverlay {
            applyWallOverlay()
        }
        cachedMetrics = canonicalLabMetrics(
            mass: canonicalMatterData(runtime: runtime, state: state),
            food: canonicalFoodData(state: state, size: runtimeConfig.sx * runtimeConfig.sy),
            walls: effectiveWalls()
        )
    }

    func snapshot(
        refreshMetrics: Bool,
        projection: LabFieldProjection
    ) -> FlowSandboxSnapshot {
        advanceIfRunning()
        let displayField = displayField(for: projection)
        if refreshMetrics {
            cachedMetrics = canonicalLabMetrics(
                mass: canonicalMatterData(runtime: runtime, state: state),
                food: canonicalFoodData(state: state, size: runtimeConfig.sx * runtimeConfig.sy),
                walls: effectiveWalls()
            )
        }

        return FlowSandboxSnapshot(
            step: state.step,
            width: runtimeConfig.sx,
            height: runtimeConfig.sy,
            sharedField: LeniaMetalFieldSurface(
                field: displayField,
                width: runtimeConfig.sx,
                height: runtimeConfig.sy
            ),
            metrics: cachedMetrics
        )
    }

    func telemetry() -> FlowSandboxRuntimeTelemetry {
        FlowSandboxRuntimeTelemetry(
            lastStepDurationMs: lastStepDurationMs,
            realizedStepRateHz: lastStepDurationMs > 0 ? 1_000.0 / lastStepDurationMs : 0
        )
    }

    private func advanceIfRunning() {
        guard !isPaused else { return }
        let startedAt = ContinuousClock.now
        step()
        let elapsed = ContinuousClock.now - startedAt
        lastStepDurationMs = canonicalDurationMs(elapsed)
    }

    private func runLoop() async {
        while !Task.isCancelled {
            if isPaused {
                try? await Task.sleep(for: .milliseconds(25))
                continue
            }

            let startedAt = ContinuousClock.now
            step()
            let elapsed = ContinuousClock.now - startedAt
            lastStepDurationMs = canonicalDurationMs(elapsed)
            let remaining = targetFrameDuration - elapsed
            if remaining > .zero {
                try? await Task.sleep(for: remaining)
            }
        }
    }

    private func materializeState(
        mass: [Float],
        params: [Float]?,
        food: [Float]?
    ) {
        state = FlowLeniaInteractiveState(
            step: state.step,
            mass: MLXArray(mass).reshaped([runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.channels]),
            params: params.map { MLXArray($0).reshaped([runtimeConfig.sx, runtimeConfig.sy, runtimeConfig.nbK]) },
            food: food.map { MLXArray($0).reshaped([runtimeConfig.sx, runtimeConfig.sy]) }
        )
        eval(state.mass)
        if let params = state.params {
            eval(params)
        }
        if let food = state.food {
            eval(food)
        }
    }

    private func applyWallOverlay() {
        let wallSupport = effectiveWalls()
        eval(state.mass)
        if let params = state.params {
            eval(params)
        }
        if let food = state.food {
            eval(food)
        }

        var mass = state.mass.asArray(Float.self)
        var params = state.params?.asArray(Float.self)
        var food = state.food?.asArray(Float.self)

        for index in wallSupport.indices where wallSupport[index] < 0.5 {
            zeroMass(at: index, channels: runtimeConfig.channels, mass: &mass)
            zeroParams(at: index, parameterCount: runtimeConfig.parameterEmbedding.enabled ? runtimeConfig.nbK : 0, params: &params)
            food?[index] = 0
        }

        materializeState(mass: mass, params: params, food: food)
    }

    private func injectAutoFoodPatchIfNeeded() {
        guard var food = state.food?.asArray(Float.self) else { return }
        var rng = SeededRandomNumberGenerator(seed: UInt64(state.step + 1_337))
        guard Float.random(in: 0..<1, using: &rng) < autoFoodProbability else { return }
        let size = runtimeConfig.sx
        let patchSize = min(autoFoodPatchSize, size)
        let maxX = max(0, size - patchSize)
        let maxY = max(0, size - patchSize)
        let startX = Int.random(in: 0...maxX, using: &rng)
        let startY = Int.random(in: 0...maxY, using: &rng)
        let wallSupport = effectiveWalls()

        for x in startX..<(startX + patchSize) {
            for y in startY..<(startY + patchSize) {
                let index = x * size + y
                guard wallSupport[index] > 0.5 else { continue }
                food[index] = max(food[index], autoFoodValue)
            }
        }

        materializeState(
            mass: state.mass.asArray(Float.self),
            params: state.params?.asArray(Float.self),
            food: food
        )
    }

    private func displayField(for projection: LabFieldProjection) -> MLXArray {
        switch projection {
        case .matter:
            let matter = runtime.matterMap(for: state)
            let display: MLXArray
            if let food = state.food {
                display = MLX.clip(
                    matter + food * MLXArray(0.55),
                    min: MLXArray(0),
                    max: MLXArray(1)
                )
            } else {
                display = MLX.clip(matter, min: MLXArray(0), max: MLXArray(1))
            }
            let field = displayFieldByApplyingWallMaskIfNeeded(display)
            eval(field)
            return field
        case .channel(let channel):
            let field = displayFieldByApplyingWallMaskIfNeeded(
                runtime.channelMap(for: state, channel: channel)
            )
            eval(field)
            return field
        }
    }

    private func displayFieldByApplyingWallMaskIfNeeded(_ field: MLXArray) -> MLXArray {
        guard hasBaseWallMask || hasWallOverlay else {
            return field.contiguous()
        }
        let wallField = MLXArray(effectiveWalls()).reshaped([runtimeConfig.sx, runtimeConfig.sy])
        return (field * wallField).contiguous()
    }

    private func effectiveWalls() -> [Float] {
        effectiveWalls(overlay: wallOverlay)
    }

    private func effectiveWalls(overlay: [Float]) -> [Float] {
        zip(baseWallMask, overlay).map { $0 * $1 }
    }
}

private func sandboxBackend(for backend: FlowLeniaComputeBackend) -> FlowSandboxBackend {
    switch backend {
    case .mlx:
        return .mlx
    case .metalFull:
        return .metalFull
    }
}

private func canonicalFieldSummary(runtimeConfig: LeniaRuntimeConfig) -> String {
    var parts = ["\(runtimeConfig.channels) matter lanes"]
    if runtimeConfig.parameterEmbedding.enabled {
        parts.append("\(runtimeConfig.nbK) parameter lanes")
    }
    if runtimeConfig.food?.enabled == true {
        parts.append("food scalar")
    }
    if runtimeConfig.walls?.enabled == true || runtimeConfig.environment != nil {
        parts.append("wall mask")
    }
    return parts.joined(separator: " + ")
}

private func canonicalFeatureSummary(runtimeConfig: LeniaRuntimeConfig) -> String {
    var features: [String] = []
    if runtimeConfig.parameterEmbedding.enabled {
        features.append("parameter embedding")
    }
    if let chemotaxis = runtimeConfig.chemotaxis, chemotaxis.enabled {
        features.append("chemotaxis c\(chemotaxis.channel_index)")
    }
    if let obstacle = runtimeConfig.obstacleField, obstacle.enabled {
        features.append("obstacle c\(obstacle.channel_index)")
    }
    if let food = runtimeConfig.food, food.enabled {
        features.append("food c\(food.channel_index)")
    }
    if runtimeConfig.walls?.enabled == true {
        features.append("walls")
    }
    if runtimeConfig.environment != nil {
        features.append("environment")
    }
    if runtimeConfig.beamMutation?.enabled == true {
        features.append("beam mutation")
    }
    return features.isEmpty ? "pure field" : features.joined(separator: ", ")
}

private func canonicalConnectivitySummary(runtimeConfig: LeniaRuntimeConfig) -> String {
    var counts: [String: Int] = [:]
    for target in runtimeConfig.c1.indices {
        for kernel in runtimeConfig.c1[target] {
            guard kernel >= 0, kernel < runtimeConfig.c0.count else { continue }
            let source = runtimeConfig.c0[kernel]
            counts["c\(source) -> c\(target)", default: 0] += 1
        }
    }
    if counts.isEmpty {
        return "No active edges"
    }
    return counts
        .sorted { $0.key < $1.key }
        .map { "\($0.key) × \($0.value)" }
        .joined(separator: ", ")
}

private func canonicalMatterData(
    runtime: FlowLeniaInteractiveSimulator,
    state: FlowLeniaInteractiveState
) -> [Float] {
    let matter = runtime.matterMap(for: state).contiguous()
    eval(matter)
    return matter.asArray(Float.self)
}

private func canonicalFoodData(
    state: FlowLeniaInteractiveState,
    size: Int
) -> [Float] {
    guard let food = state.food else {
        return Array(repeating: 0, count: size)
    }
    let field = food.contiguous()
    eval(field)
    return field.asArray(Float.self)
}

private func canonicalHasClosedCells(_ walls: [Float]) -> Bool {
    walls.contains { $0 < 0.5 }
}

private func canonicalLabMetrics(
    mass: [Float],
    food: [Float],
    walls: [Float]
) -> FlowSandboxMetrics {
    let count = Float(max(1, mass.count))
    let finiteMass = mass.filter(\.isFinite)
    let finiteFood = food.filter(\.isFinite)
    let nonFiniteCount = mass.count - finiteMass.count + food.count - finiteFood.count
    let occupied = Float(finiteMass.filter { $0 > 0.05 }.count)
    let wallCount = Float(walls.filter { $0 < 0.5 }.count)
    return FlowSandboxMetrics(
        massMean: finiteMass.reduce(0, +) / count,
        occupancy: occupied / count,
        foodMean: finiteFood.reduce(0, +) / count,
        wallFraction: wallCount / count,
        massPeak: finiteMass.max() ?? 0,
        foodPeak: finiteFood.max() ?? 0,
        nonFiniteFraction: Float(nonFiniteCount) / max(1.0, Float(mass.count + food.count))
    )
}

private func canonicalDurationMs(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1_000.0 +
        Double(duration.components.attoseconds) / 1_000_000_000_000_000.0
}

private func canonicalContains(x: Int, y: Int, size: Int) -> Bool {
    x >= 0 && y >= 0 && x < size && y < size
}

private func forEachStrokeCell(
    stroke: SandboxStroke,
    size: Int,
    _ body: (Int, Int) -> Void
) {
    var visited = Set<Int>()
    for point in stroke.points {
        let x0 = max(0, point.x - stroke.radius)
        let x1 = min(size - 1, point.x + stroke.radius)
        let y0 = max(0, point.y - stroke.radius)
        let y1 = min(size - 1, point.y + stroke.radius)
        let radiusSquared = stroke.radius * stroke.radius

        for x in x0...x1 {
            for y in y0...y1 {
                let dx = x - point.x
                let dy = y - point.y
                guard dx * dx + dy * dy <= radiusSquared else { continue }
                let index = x * size + y
                guard visited.insert(index).inserted else { continue }
                body(x, y)
            }
        }
    }
}

private func zeroMass(at index: Int, channels: Int, mass: inout [Float]) {
    let base = index * channels
    for channel in 0..<channels {
        mass[base + channel] = 0
    }
}

private func zeroParams(
    at index: Int,
    parameterCount: Int,
    params: inout [Float]?
) {
    guard parameterCount > 0, params != nil else { return }
    let base = index * parameterCount
    for parameter in 0..<parameterCount {
        params?[base + parameter] = 0
    }
}
