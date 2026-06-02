import Foundation
import MLX

public struct FlowLeniaMetalSweepCase: Sendable {
    public let gridSize: Int
    public let channels: Int
    public let kernels: Int

    public init(gridSize: Int, channels: Int, kernels: Int) {
        self.gridSize = gridSize
        self.channels = channels
        self.kernels = kernels
    }
}

public struct FlowLeniaMetalSweepResult: Sendable {
    public let gridSize: Int
    public let channels: Int
    public let kernels: Int
    public let reintegrateParams: Bool
    public let batchSize: Int
    public let steps: Int
    public let duration: TimeInterval
    public let stepsPerSecond: Double
    public let cellChannelStepsPerSecond: Double
    public let visibleWorkingSetBytes: Int
    public let stageTimings: FlowSandboxMetalStageTimings?

    public init(
        gridSize: Int,
        channels: Int,
        kernels: Int,
        reintegrateParams: Bool,
        batchSize: Int,
        steps: Int,
        duration: TimeInterval,
        stepsPerSecond: Double,
        cellChannelStepsPerSecond: Double,
        visibleWorkingSetBytes: Int,
        stageTimings: FlowSandboxMetalStageTimings?
    ) {
        self.gridSize = gridSize
        self.channels = channels
        self.kernels = kernels
        self.reintegrateParams = reintegrateParams
        self.batchSize = batchSize
        self.steps = steps
        self.duration = duration
        self.stepsPerSecond = stepsPerSecond
        self.cellChannelStepsPerSecond = cellChannelStepsPerSecond
        self.visibleWorkingSetBytes = visibleWorkingSetBytes
        self.stageTimings = stageTimings
    }
}

func flowLeniaBenchmarkRanges() -> KernelParamRanges {
    KernelParamRanges(
        r: [0.2, 1.0],
        b: [0.0, 1.0],
        w: [0.01, 0.5],
        a: [0.0, 1.0],
        m: [0.05, 0.5],
        s: [0.001, 0.2],
        h: [0.0, 1.0],
        R: [2.0, 25.0]
    )
}

func flowLeniaBenchmarkEvolutionRanges() -> [String: (Float, Float)] {
    let ranges = flowLeniaBenchmarkRanges()
    return [
        "r": (ranges.r[0], ranges.r[1]),
        "b": (ranges.b[0], ranges.b[1]),
        "w": (ranges.w[0], ranges.w[1]),
        "a": (ranges.a[0], ranges.a[1]),
        "m": (ranges.m[0], ranges.m[1]),
        "s": (ranges.s[0], ranges.s[1]),
        "h": (ranges.h[0], ranges.h[1]),
        "R": (ranges.R[0], ranges.R[1]),
    ]
}

func flowLeniaBenchmarkRuntimeConfig(
    gridSize: Int,
    steps: Int,
    params: ResolvedParams,
    backend: FlowLeniaComputeBackend
) -> LeniaRuntimeConfig {
    precondition(gridSize >= 40, "Flow Lenia paper benchmarks require gridSize >= 40.")
    let c0 = Array(repeating: 0, count: params.r.count)
    let c1 = [Array(0..<params.r.count)]
    return LeniaRuntimeConfig(
        backend: backend,
        sx: gridSize,
        sy: gridSize,
        channels: 1,
        nbK: params.r.count,
        profile: .paper,
        c0: c0,
        c1: c1,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2.0,
        border: "torus",
        implementation: ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        ),
        params: params,
        initSeed: 17,
        patches: [PatchConfig(center: [gridSize / 2, gridSize / 2], size: 40)],
        aUniform: UniformRange(low: 0.0, high: 1.0),
        pUniform: UniformRange(low: 0.0, high: 1.0),
        steps: steps,
        parameterEmbedding: ParameterEmbeddingConfig(enabled: true, mix: "avg", mix_seed: nil),
        chemotaxis: nil,
        food: nil,
        walls: nil,
        environment: nil,
        beamMutation: nil,
        interventions: []
    )
}

public func benchmarkFlowLeniaMetalSweepCase(
    _ benchmarkCase: FlowLeniaMetalSweepCase,
    batchSize: Int,
    steps: Int,
    warmupSteps: Int,
    reintegrateParams: Bool = true,
    profileStages: Bool = false
) -> FlowLeniaMetalSweepResult {
    precondition(benchmarkCase.gridSize > 0, "Metal sweep grid size must be > 0.")
    precondition(benchmarkCase.channels > 0, "Metal sweep channel count must be > 0.")
    precondition(benchmarkCase.kernels > 0, "Metal sweep kernel count must be > 0.")
    precondition(batchSize > 0, "Metal sweep batch size must be > 0.")
    precondition(steps > 0, "Metal sweep steps must be > 0.")
    precondition(warmupSteps >= 0, "Metal sweep warmup steps must be >= 0.")

    let config = BatchedConfig(
        sx: benchmarkCase.gridSize,
        sy: benchmarkCase.gridSize,
        channels: benchmarkCase.channels,
        nbK: benchmarkCase.kernels,
        dt: 0.2,
        dd: 5,
        sigma: 0.65,
        n: 2,
        thetaA: 2.0,
        border: "torus",
        implementation: ImplementationSettings(
            mode: "flowlenia_2022_paper_equations",
            border: "torus",
            gradientBoundary: "periodic",
            alphaMode: "mass",
            kernelProfile: "flowlenia_2022_paper_equations",
            flowClip: "none"
        ),
        chemChannel: nil,
        chemIncludeInMass: true
    )
    let params = generateRandomParams(
        seed: 9 + benchmarkCase.gridSize + benchmarkCase.channels * 101 + benchmarkCase.kernels * 1009,
        nbK: benchmarkCase.kernels,
        ranges: flowLeniaBenchmarkRanges()
    )
    let connectivity = roundRobinConnectivity(channels: benchmarkCase.channels, kernels: benchmarkCase.kernels)
    let kernels = compileKernels(params: params, config: config, c0: connectivity.c0, c1: connectivity.c1)
    let runner = FlowLeniaMetalFullStateRunner(
        config: config,
        kernels: kernels,
        batchCount: batchSize,
        reintegrateParams: reintegrateParams
    )
    runner.setState(
        mass: deterministicMetalSweepMass(
            seed: 17,
            batchSize: batchSize,
            gridSize: benchmarkCase.gridSize,
            channels: benchmarkCase.channels
        ),
        params: deterministicMetalSweepParams(
            params: params,
            batchSize: batchSize,
            gridSize: benchmarkCase.gridSize
        )
    )
    runner.step(count: warmupSteps)
    let stageTimings = profileStages ? runner.profileCurrentStep() : nil

    let start = Date()
    runner.step(count: steps)
    let duration = Date().timeIntervalSince(start)
    _ = runner.materializeMass()
    let simulatedSteps = Double(batchSize * steps)
    let cellChannelSteps = simulatedSteps
        * Double(benchmarkCase.gridSize * benchmarkCase.gridSize * benchmarkCase.channels)
    return FlowLeniaMetalSweepResult(
        gridSize: benchmarkCase.gridSize,
        channels: benchmarkCase.channels,
        kernels: benchmarkCase.kernels,
        reintegrateParams: reintegrateParams,
        batchSize: batchSize,
        steps: steps,
        duration: duration,
        stepsPerSecond: simulatedSteps / duration,
        cellChannelStepsPerSecond: cellChannelSteps / duration,
        visibleWorkingSetBytes: estimatedFlowLeniaMetalVisibleWorkingSetBytes(
            gridSize: benchmarkCase.gridSize,
            channels: benchmarkCase.channels,
            kernels: benchmarkCase.kernels,
            batchSize: batchSize
        ),
        stageTimings: stageTimings
    )
}

private func estimatedFlowLeniaMetalVisibleWorkingSetBytes(
    gridSize: Int,
    channels: Int,
    kernels: Int,
    batchSize: Int
) -> Int {
    let sx = gridSize
    let sy = gridSize
    let cellCount = batchSize * sx * sy
    let reducedY = (sy / 2) + 1
    let floatBytes = MemoryLayout<Float>.stride
    let complexFloatBytes = MemoryLayout<SIMD2<Float>>.stride
    let intBytes = MemoryLayout<Int32>.stride
    let parameterCount = kernels

    let stateBytes = 2 * cellCount * (channels + parameterCount) * floatBytes
    let kernelBytes = sx * reducedY * kernels * complexFloatBytes
    let channelSpectrumBytes = batchSize * sx * reducedY * channels * complexFloatBytes
    let gatheredSpectrumBytes = batchSize * sx * reducedY * kernels * complexFloatBytes
    let ukBytes = cellCount * kernels * floatBytes
    let matterBytes = cellCount * floatBytes
    let uBytes = cellCount * channels * floatBytes
    let flowBytes = cellCount * channels * 2 * floatBytes
    let wallPotentialBytes = cellCount * floatBytes
    let kernelScalarBytes = batchSize * kernels * floatBytes
    let transferBytes =
        kernels * intBytes
        + 2 * kernelScalarBytes
        + channels * floatBytes
        + channels * kernels * floatBytes
        + wallPotentialBytes

    return stateBytes
        + kernelBytes
        + channelSpectrumBytes
        + gatheredSpectrumBytes
        + ukBytes
        + matterBytes
        + uBytes
        + flowBytes
        + wallPotentialBytes
        + transferBytes
}

private func roundRobinConnectivity(channels: Int, kernels: Int) -> (c0: [Int], c1: [[Int]]) {
    var c0: [Int] = []
    c0.reserveCapacity(kernels)
    var c1 = Array(repeating: [Int](), count: channels)
    for kernel in 0..<kernels {
        let channel = kernel % channels
        c0.append(channel)
        c1[channel].append(kernel)
    }
    return (c0, c1)
}

private func deterministicMetalSweepMass(
    seed: UInt64,
    batchSize: Int,
    gridSize: Int,
    channels: Int
) -> MLXArray {
    var rng = MetalSweepRNG(seed: seed)
    var values: [Float] = []
    values.reserveCapacity(batchSize * gridSize * gridSize * channels)
    for _ in 0..<(batchSize * gridSize * gridSize * channels) {
        values.append(rng.nextFloat())
    }
    return MLXArray(values).reshaped([batchSize, gridSize, gridSize, channels])
}

private func deterministicMetalSweepParams(
    params: ResolvedParams,
    batchSize: Int,
    gridSize: Int
) -> MLXArray {
    let cellCount = batchSize * gridSize * gridSize
    var values: [Float] = []
    values.reserveCapacity(cellCount * params.h.count)
    for _ in 0..<cellCount {
        values.append(contentsOf: params.h)
    }
    return MLXArray(values).reshaped([batchSize, gridSize, gridSize, params.h.count])
}

private struct MetalSweepRNG {
    private var state: UInt64

    init(seed: UInt64) {
        state = seed
    }

    mutating func nextFloat() -> Float {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        let value = UInt32(truncatingIfNeeded: state >> 32)
        return Float(value) / Float(UInt32.max)
    }
}
