import Foundation

public struct LeniaInteractiveEngineDescriptor: Sendable {
    public let backend: FlowSandboxBackend
    public let gridPreset: LabGridPreset
    public let kernelCount: Int
    public let parameterCount: Int

    public init(
        backend: FlowSandboxBackend,
        gridPreset: LabGridPreset,
        kernelCount: Int,
        parameterCount: Int
    ) {
        self.backend = backend
        self.gridPreset = gridPreset
        self.kernelCount = kernelCount
        self.parameterCount = parameterCount
    }

    public var executionLabel: String {
        switch backend {
        case .metalFull:
            return "Metal engine"
        case .mlx:
            return "MLX engine"
        }
    }
}

public actor LeniaInteractiveEngine {
    public nonisolated let descriptor: LeniaInteractiveEngineDescriptor

    private let runtime: FlowSandboxRuntime

    public init(
        params: ResolvedParams,
        gridPreset: LabGridPreset = .standard256,
        initialStamp: CreatureStamp? = nil,
        backend: FlowSandboxBackend = .metalFull,
        autoFoodSeed: Int = 17
    ) {
        self.descriptor = LeniaInteractiveEngineDescriptor(
            backend: backend,
            gridPreset: gridPreset,
            kernelCount: params.r.count,
            parameterCount: params.h.count
        )
        self.runtime = FlowSandboxRuntime(
            params: params,
            gridPreset: gridPreset,
            initialStamp: initialStamp,
            backend: backend,
            autoFoodSeed: autoFoodSeed
        )
    }

    public func start() async {
        await runtime.start()
    }

    public func pause() async {
        await runtime.pause()
    }

    public func resume() async {
        await runtime.resume()
    }

    public func stop() async {
        await runtime.stop()
    }

    public func reset() async {
        await runtime.reset()
    }

    public func setSpeedCap(hz: Int) async {
        await runtime.setSpeedCap(hz: hz)
    }

    public func setAutoFoodSpawn(
        enabled: Bool,
        probability: Float? = nil,
        patchSize: Int? = nil,
        value: Float? = nil
    ) async {
        await runtime.setAutoFoodSpawn(
            enabled: enabled,
            probability: probability,
            patchSize: patchSize,
            value: value
        )
    }

    public func worldContract() async -> FlowSandboxWorldContract {
        await runtime.worldContract()
    }

    public func step() async {
        await runtime.step()
    }

    public func applyStroke(_ stroke: SandboxStroke) async {
        await runtime.applyStroke(stroke)
    }

    public func applyFoodRect(_ rect: SandboxRect, value: Float) async {
        await runtime.applyFoodRect(rect, value: value)
    }

    public func applyCreatureStamp(_ stamp: CreatureStamp, center: SIMD2<Int>) async {
        await runtime.applyCreatureStamp(stamp, center: center)
    }

    public func displaySnapshot(
        includeBytes: Bool = false,
        refreshMetrics: Bool = false
    ) async -> FlowSandboxSnapshot {
        await runtime.snapshot(includeBytes: includeBytes, refreshMetrics: refreshMetrics)
    }

    public func materializeStateSnapshot() async -> FlowSandboxStateSnapshot {
        await runtime.materializeStateSnapshot()
    }

    public func restoreStateSnapshot(_ snapshot: FlowSandboxStateSnapshot) async throws {
        try await runtime.restoreStateSnapshot(snapshot)
    }

    public func telemetry() async -> FlowSandboxRuntimeTelemetry {
        await runtime.telemetry()
    }
}

public func makeLeniaInteractiveEngine(
    from runtimeConfig: LeniaRuntimeConfig,
    backend: FlowSandboxBackend
) -> LeniaInteractiveEngine? {
    guard backend == .metalFull else {
        return nil
    }
    guard leniaInteractiveEngineCanRun(runtimeConfig) else {
        return nil
    }
    guard let gridPreset = LabGridPreset(rawValue: runtimeConfig.sx) else {
        return nil
    }
    guard let initialStamp = leniaInteractiveEngineInitialStamp(from: runtimeConfig) else {
        return nil
    }
    return LeniaInteractiveEngine(
        params: runtimeConfig.params,
        gridPreset: gridPreset,
        initialStamp: initialStamp,
        backend: backend
    )
}

public func leniaInteractiveEngineCanRun(_ runtimeConfig: LeniaRuntimeConfig) -> Bool {
    guard runtimeConfig.sx == runtimeConfig.sy else { return false }
    guard LabGridPreset(rawValue: runtimeConfig.sx) != nil else { return false }
    guard runtimeConfig.channels == 1 else { return false }
    guard runtimeConfig.nbK == runtimeConfig.params.r.count,
          runtimeConfig.params.h.count == runtimeConfig.nbK else { return false }
    guard runtimeConfig.c0 == Array(repeating: 0, count: runtimeConfig.nbK),
          runtimeConfig.c1.count == 1,
          runtimeConfig.c1[0] == Array(0..<runtimeConfig.nbK) else { return false }
    guard !runtimeConfig.parameterEmbedding.enabled else { return false }
    guard runtimeConfig.chemotaxis == nil,
          runtimeConfig.obstacleField == nil,
          runtimeConfig.food?.enabled != true,
          runtimeConfig.walls?.enabled != true,
          runtimeConfig.environment == nil,
          runtimeConfig.beamMutation == nil,
          runtimeConfig.interventions.isEmpty else { return false }
    guard leniaInteractiveEngineApproximately(runtimeConfig.dt, 0.2),
          runtimeConfig.dd == 5,
          leniaInteractiveEngineApproximately(runtimeConfig.sigma, 0.65),
          runtimeConfig.n == 2,
          leniaInteractiveEngineApproximately(runtimeConfig.thetaA, 2.0),
          runtimeConfig.border == "torus" else { return false }
    guard runtimeConfig.implementation.mode == "flowlenia_2022_paper_equations",
          runtimeConfig.implementation.border == "torus",
          runtimeConfig.implementation.gradientBoundary == "periodic",
          runtimeConfig.implementation.alphaMode == "mass",
          runtimeConfig.implementation.kernelProfile == "flowlenia_2022_paper_equations",
          runtimeConfig.implementation.flowClip == "none" else { return false }
    return true
}

private func leniaInteractiveEngineInitialStamp(from runtimeConfig: LeniaRuntimeConfig) -> CreatureStamp? {
    if let statePatch = runtimeConfig.statePatch {
        guard statePatch.channels == 1,
              statePatch.center == [runtimeConfig.sx / 2, runtimeConfig.sy / 2] else {
            return nil
        }
        return leniaInteractiveEngineStamp(
            name: "Initial state",
            width: statePatch.width,
            height: statePatch.height,
            mass: statePatch.decodedValues(),
            params: runtimeConfig.params
        )
    }

    guard runtimeConfig.patches.count == 1,
          let patch = runtimeConfig.patches.first,
          patch.center == [runtimeConfig.sx / 2, runtimeConfig.sy / 2],
          patch.size > 0,
          patch.size <= runtimeConfig.sx,
          patch.size <= runtimeConfig.sy else {
        return nil
    }

    var rng = SeededRandomNumberGenerator(seed: UInt64(runtimeConfig.initSeed))
    let valueRange = runtimeConfig.aUniform.low...runtimeConfig.aUniform.high
    let mass = (0..<(patch.size * patch.size)).map { _ in
        Float.random(in: valueRange, using: &rng)
    }
    return leniaInteractiveEngineStamp(
        name: "Initial patch",
        width: patch.size,
        height: patch.size,
        mass: mass,
        params: runtimeConfig.params
    )
}

private func leniaInteractiveEngineStamp(
    name: String,
    width: Int,
    height: Int,
    mass: [Float],
    params: ResolvedParams
) -> CreatureStamp? {
    guard width > 0,
          height > 0,
          mass.count == width * height,
          !params.h.isEmpty else {
        return nil
    }
    var parameterValues = [Float](
        repeating: 0,
        count: mass.count * params.h.count
    )
    for index in mass.indices where mass[index] > 0.001 {
        let base = index * params.h.count
        for parameter in params.h.indices {
            parameterValues[base + parameter] = params.h[parameter]
        }
    }
    return CreatureStamp(
        name: name,
        width: width,
        height: height,
        mass: mass,
        params: parameterValues,
        parameterCount: params.h.count
    )
}

private func leniaInteractiveEngineApproximately(_ lhs: Float, _ rhs: Float, tolerance: Float = 0.0001) -> Bool {
    abs(lhs - rhs) <= tolerance
}
