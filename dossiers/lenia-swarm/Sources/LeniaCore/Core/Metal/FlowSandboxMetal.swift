import Foundation
import MLX

public struct FlowSandboxMetalStageTimings: Codable, Sendable {
    public let prepareMs: Double
    public let fftMs: Double
    public let growthReduceMs: Double
    public let flowMs: Double
    public let reintegrateMs: Double
    public let totalMs: Double

    public init(
        prepareMs: Double,
        fftMs: Double,
        growthReduceMs: Double,
        flowMs: Double,
        reintegrateMs: Double,
        totalMs: Double
    ) {
        self.prepareMs = prepareMs
        self.fftMs = fftMs
        self.growthReduceMs = growthReduceMs
        self.flowMs = flowMs
        self.reintegrateMs = reintegrateMs
        self.totalMs = totalMs
    }
}

public enum FlowSandboxBackend: String, CaseIterable, Identifiable, Sendable, Equatable, Hashable {
    case mlx = "mlx"
    case metalFull = "metal-full"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .mlx:
            "Sandbox MLX"
        case .metalFull:
            "Sandbox Metal full (exp)"
        }
    }
}

public struct FlowSandboxBenchmarkResult: Sendable {
    public let backend: FlowSandboxBackend
    public let gridSize: Int
    public let steps: Int
    public let duration: TimeInterval
    public let stepsPerSecond: Double
    public let stageTimings: FlowSandboxMetalStageTimings?

    public init(
        backend: FlowSandboxBackend,
        gridSize: Int,
        steps: Int,
        duration: TimeInterval,
        stepsPerSecond: Double,
        stageTimings: FlowSandboxMetalStageTimings? = nil
    ) {
        self.backend = backend
        self.gridSize = gridSize
        self.steps = steps
        self.duration = duration
        self.stepsPerSecond = stepsPerSecond
        self.stageTimings = stageTimings
    }
}

struct FlowSandboxMetalStageOutputs {
    let preparedMass: MLXArray
    let uk: MLXArray
    let scalarField: MLXArray
    let flow: MLXArray
}

struct FlowSandboxMetalStagedStepResult {
    let nextMass: MLXArray
    let nextParams: MLXArray
    let stages: FlowSandboxMetalStageOutputs?
    let timings: FlowSandboxMetalStageTimings?
}

func flowSandboxDurationMs(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1_000.0 +
        Double(duration.components.attoseconds) / 1_000_000_000_000_000.0
}

enum FlowSandboxStepper {
    case mlx(FlowLeniaParamsBatched)
    case metalFull(FlowLeniaSandboxMetalEngine)

    func step(_ mass: MLXArray, _ params: MLXArray) -> (MLXArray, MLXArray) {
        switch self {
        case .mlx(let engine):
            engine.step(mass, params)
        case .metalFull(let engine):
            engine.step(mass, params)
        }
    }

    init(
        backend: FlowSandboxBackend,
        config: BatchedConfig,
        kernels: CompiledKernels,
        wallPotential: MLXArray? = nil
    ) {
        switch backend {
        case .mlx:
            self = .mlx(
                FlowLeniaParamsBatched(
                    config: config,
                    kernels: kernels,
                    mixMode: "avg",
                    mixSeed: nil,
                    wallPotential: wallPotential
                )
            )
        case .metalFull:
            self = .metalFull(
                FlowLeniaSandboxMetalEngine(
                    config: config,
                    kernels: kernels,
                    wallPotential: wallPotential
                )
            )
        }
    }
}

final class FlowLeniaSandboxMetalEngine: @unchecked Sendable {
    let config: BatchedConfig
    let kernels: CompiledKernels
    let wallPotential: MLXArray?
    let reintegrateParams: Bool

    private let fullMetalBridge: FlowLeniaMetalFullBridge
    private let parameterCount: Int
    private let kernelBatchCount: Int

    init(config: BatchedConfig, kernels: CompiledKernels, wallPotential: MLXArray? = nil, reintegrateParams: Bool = true) {
        self.config = config
        self.kernels = kernels
        self.wallPotential = wallPotential
        self.reintegrateParams = reintegrateParams
        self.parameterCount = FlowLeniaMetalFullPipeline.parameterCount(for: kernels)
        self.kernelBatchCount = FlowLeniaMetalFullPipeline.kernelBatchCount(for: kernels)
        self.fullMetalBridge = FlowLeniaMetalFullBridge(config: config, kernels: kernels, wallPotential: wallPotential)
    }

    func step(_ mass: MLXArray, _ params: MLXArray) -> (MLXArray, MLXArray) {
        guard mass.shape.count == 4 else {
            preconditionFailure("FlowLeniaSandboxMetalEngine expects rank-4 mass fields.")
        }
        guard mass.shape[3] == config.channels else {
            preconditionFailure("FlowLeniaSandboxMetalEngine expects mass with shape [batch, sx, sy, channels].")
        }
        guard params.shape.count == 4, params.shape[3] == parameterCount else {
            preconditionFailure("FlowLeniaSandboxMetalEngine expects params with shape [batch, sx, sy, parameterCount].")
        }
        guard mass.shape[0] == params.shape[0], mass.shape[1] == params.shape[1], mass.shape[2] == params.shape[2] else {
            preconditionFailure("FlowLeniaSandboxMetalEngine mass and parameter batches must share batch and spatial dimensions.")
        }
        guard kernelBatchCount == 1 || kernelBatchCount == mass.shape[0] else {
            preconditionFailure("FlowLeniaSandboxMetalEngine requires either shared kernels or one kernel set per batch element.")
        }
        let result = stagedStep(mass, params)
        return (result.nextMass, reintegrateParams ? result.nextParams : params)
    }

    func stagedStep(
        _ mass: MLXArray,
        _ params: MLXArray,
        captureStages: Bool = false,
        profileStages: Bool = false
    ) -> FlowSandboxMetalStagedStepResult {
        return fullMetalBridge.stagedStep(
            mass: mass,
            params: params,
            captureStages: captureStages,
            profileStages: profileStages
        )
    }
}

private func averageStageTimings(_ timings: [FlowSandboxMetalStageTimings]) -> FlowSandboxMetalStageTimings? {
    guard !timings.isEmpty else { return nil }
    let count = Double(timings.count)
    return FlowSandboxMetalStageTimings(
        prepareMs: timings.reduce(0.0) { $0 + $1.prepareMs } / count,
        fftMs: timings.reduce(0.0) { $0 + $1.fftMs } / count,
        growthReduceMs: timings.reduce(0.0) { $0 + $1.growthReduceMs } / count,
        flowMs: timings.reduce(0.0) { $0 + $1.flowMs } / count,
        reintegrateMs: timings.reduce(0.0) { $0 + $1.reintegrateMs } / count,
        totalMs: timings.reduce(0.0) { $0 + $1.totalMs } / count
    )
}

func profileFlowSandboxMetalStages(
    config: BatchedConfig,
    kernels: CompiledKernels,
    initialMass: MLXArray,
    initialParams: MLXArray,
    steps: Int = 3
) -> FlowSandboxMetalStageTimings {
    let engine = FlowLeniaSandboxMetalEngine(config: config, kernels: kernels)
    var mass = initialMass
    var params = initialParams
    _ = engine.stagedStep(mass, params)
    var timings: [FlowSandboxMetalStageTimings] = []
    timings.reserveCapacity(max(steps, 1))

    for _ in 0..<max(steps, 1) {
        let result = engine.stagedStep(mass, params, profileStages: true)
        if let stageTimings = result.timings {
            timings.append(stageTimings)
        }
        mass = result.nextMass
        params = result.nextParams
    }

    guard let averaged = averageStageTimings(timings) else {
        preconditionFailure("Expected staged Metal profiling timings.")
    }
    return averaged
}

public func benchmarkFlowSandboxBackend(
    gridPreset: LabGridPreset,
    steps: Int,
    params: ResolvedParams,
    backend: FlowSandboxBackend
) async -> FlowSandboxBenchmarkResult {
    let initialStamp = buildWarmCreatureStamp(
        name: "benchmark-seed",
        params: params,
        seed: 17,
        warmupGridSize: min(gridPreset.size, 128)
    )
    let runtime = FlowSandboxRuntime(
        params: params,
        gridPreset: gridPreset,
        initialStamp: initialStamp,
        backend: backend
    )
    await runtime.setAutoFoodSpawn(enabled: false)
    await runtime.step()
    await runtime.benchmarkSynchronize()
    let start = Date()
    for _ in 0..<steps {
        await runtime.step()
        await runtime.benchmarkSynchronize()
    }
    let duration = Date().timeIntervalSince(start)
    let stageTimings: FlowSandboxMetalStageTimings?
    if backend == .metalFull {
        let c0 = Array(repeating: 0, count: params.r.count)
        let c1 = [Array(0..<params.r.count)]
        let config = flowSandboxConfig(gridSize: gridPreset.size, nbK: params.r.count)
        let kernels = compileKernels(params: params, config: config, c0: c0, c1: c1)
        let initialMass = flowSandboxSeedState(seed: 17, gridSize: gridPreset.size)
        let initialParams = flowSandboxParameterField(
            mass: initialMass,
            parameterValues: params.h,
            threshold: 0.05
        )
        stageTimings = profileFlowSandboxMetalStages(
            config: config,
            kernels: kernels,
            initialMass: initialMass,
            initialParams: initialParams
        )
    } else {
        stageTimings = nil
    }

    return FlowSandboxBenchmarkResult(
        backend: backend,
        gridSize: gridPreset.size,
        steps: steps,
        duration: duration,
        stepsPerSecond: Double(steps) / duration,
        stageTimings: stageTimings
    )
}

func flowSandboxParameterField(
    mass: MLXArray,
    parameterValues: [Float],
    threshold: Float = 0.05
) -> MLXArray {
    let parameterCount = parameterValues.count
    let batch = mass.shape[0]
    let sx = mass.shape[1]
    let sy = mass.shape[2]
    let mask = MLX.greater(mass[0..., 0..., 0..., 0], MLXArray(threshold)).asType(.float32)
        .expandedDimensions(axis: -1)
    let parameterTemplate = MLXArray(parameterValues).reshaped([1, 1, 1, parameterCount])
    let broadcastMask = MLX.broadcast(mask, to: [batch, sx, sy, parameterCount])
    return broadcastMask * parameterTemplate
}
