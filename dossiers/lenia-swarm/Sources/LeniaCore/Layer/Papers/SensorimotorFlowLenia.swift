import Foundation
import Logging
import MLX
import MLXFFT

// Sensorimotor-agency discovery on Flow-Lenia: the same IMGEP diversity search +
// gradient descent + curriculum as the Hamon 2024 sensorimotor protocol, but the
// inner physics is the mass-conserving Flow-Lenia integrator (flow field +
// reintegration transport) instead of asymptotic Lenia. Because mass is
// conserved, "death" is dispersal (the body spreads thin or fragments), not the
// mass decay used by the asymptotic runner, so viability and the behavior
// embedding are built from gyration and fragmentation rather than mass collapse.
// Obstacles are positive wall potentials: mass flows down the growth potential
// (a negative well attracts), so a positive hill repels mass and acts as a wall.
// CLI: discover sensorimotor-flowlenia.

// MARK: - Physics core

// Resolved, physics-only knobs for one Flow-Lenia rollout. Rule parameters
// (a/w/b/r/m/s/h) and the initial state are passed separately because the
// gradient inner loop differentiates through them.
struct FlowSensorimotorStepConfig {
    let sx: Int
    let sy: Int
    let nbK: Int
    let channels: Int
    let learnableChannels: Int
    let dd: Int
    let sigma: Float
    let dt: Float
    let n: Int
    let thetaA: Float
    let R: Float
    let kernelProfile: String
    let gradientBoundary: String
    let alphaMode: String
    let flowClip: String
    let growthProfile: String
    let useTorus: Bool
}

// Differentiable kernel stack fK [1, sx, sy, nbK] built from MLXArray rule
// parameters so gradients reach the kernel-shape parameters. Mirrors the
// flowlenia_2022_colab branch of normalizedSpatialKernelStack, but kept as a
// pure-MLXArray path (the forward builder consumes plain-Float ResolvedParams and
// is not differentiable). a/w/b are [nbK, bumps]; r is [nbK].
func flowSensorimotorKernelStack(
    a: MLXArray,
    w: MLXArray,
    b: MLXArray,
    r: MLXArray,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    guard config.kernelProfile == "flowlenia_2022_colab" else {
        fatalError("flow-lenia sensorimotor kernel stack requires the flowlenia_2022_colab profile, got \(config.kernelProfile)")
    }
    let midX = config.sx / 2
    let midY = config.sy / 2
    let coordsX = MLXArray(Array(0..<config.sx).map { Float($0 - midX) })
    let coordsY = MLXArray(Array(0..<config.sy).map { Float($0 - midY) })
    let (X, Y) = meshgrid(coordsX, coordsY)
    let DBase = MLX.sqrt(X * X + Y * Y)

    let radiusBase = config.R + 15.0
    var kernels: [MLXArray] = []
    kernels.reserveCapacity(config.nbK)
    for k in 0..<config.nbK {
        let divisor = r[k] * MLXArray(radiusBase)
        let D = DBase / divisor
        let profiled = kernelProfile(D, a: a[k], w: w[k], b: b[k], kernelProfile: "flowlenia_2022_colab")
        let gate = sigmoid(-(D - MLXArray(Float(1.0))) * MLXArray(Float(10.0)))
        kernels.append(gate * profiled)
    }
    let stacked = MLX.stacked(kernels, axis: 2)
    let sumK = stacked.sum(axes: [0, 1], keepDims: true)
    let normalized = stacked / (sumK + MLXArray(Float(1e-10)))
    let shifted = fftshift2(normalized)
    let fK = MLXFFT.fft2(shifted, axes: [0, 1])
    return fK.expandedDimensions(axis: 0)
}

// Reintegration position grid [1, sx, sy, 2, 1] in (row, col) order, cell-centered.
func flowSensorimotorPosGrid(sx: Int, sy: Int) -> MLXArray {
    let coordsX = MLXArray((0..<sx).map { Float($0) })
    let coordsY = MLXArray((0..<sy).map { Float($0) })
    let (X, Y) = meshgrid(coordsX, coordsY)
    var pos = MLX.stacked([Y, X], axis: -1) + MLXArray(Float(0.5))
    pos = pos.expandedDimensions(axis: 0)
    return pos.expandedDimensions(axis: -1)
}

// One differentiable, mass-conserving Flow-Lenia rollout. `initial` is
// [1, sx, sy, channels]; `wallPotential` (positive inside obstacles) is added to
// the growth potential so advection steers mass away from it. Returns the final
// state [1, sx, sy, channels].
func flowSensorimotorRollout(
    initial: MLXArray,
    a: MLXArray,
    w: MLXArray,
    b: MLXArray,
    r: MLXArray,
    m: MLXArray,
    s: MLXArray,
    h: MLXArray,
    c0Idxs: MLXArray,
    c1Mask: MLXArray,
    posGrid: MLXArray,
    wallPotential: MLXArray?,
    steps: Int,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    let fK = flowSensorimotorKernelStack(a: a, w: w, b: b, r: r, config: config)
    var state = initial
    for _ in 0..<steps {
        state = leniaStepBatched(
            state,
            fK: fK, m: m, s: s, h: h,
            c0Idxs: c0Idxs, c1Mask: c1Mask,
            posGrid: posGrid,
            dt: config.dt, dd: config.dd, sigma: config.sigma,
            n: config.n, thetaA: config.thetaA,
            gradientBoundary: config.gradientBoundary,
            alphaMode: config.alphaMode,
            flowClip: config.flowClip,
            growthProfile: config.growthProfile,
            useTorus: config.useTorus,
            chemChannel: nil,
            chemIncludeInMass: true,
            sx: config.sx, sy: config.sy,
            wallPotential: wallPotential,
            gatherBeforeFFT: true
        )
    }
    return state
}

// MARK: - Differentiable behavior metrics

// Per-cell mass of the learnable body (obstacle channels excluded), [1, sx, sy].
func flowSensorimotorMassMap(_ state: MLXArray, config: FlowSensorimotorStepConfig) -> MLXArray {
    let body = state[0..., 0..., 0..., 0..<config.learnableChannels]
    return body.sum(axis: -1)
}

// Total conserved body mass (scalar MLXArray).
func flowSensorimotorMass(_ state: MLXArray, config: FlowSensorimotorStepConfig) -> MLXArray {
    return flowSensorimotorMassMap(state, config: config).sum()
}

// Mass-weighted centroid in (row, col), scalar MLXArrays. Floored mass avoids a
// divide-by-zero only when the body is numerically empty; callers gate on
// viability before trusting the value.
func flowSensorimotorCentroid(
    _ state: MLXArray,
    config: FlowSensorimotorStepConfig
) -> (row: MLXArray, col: MLXArray) {
    let massMap = flowSensorimotorMassMap(state, config: config)[0]
    let total = massMap.sum() + MLXArray(Float(1e-8))
    let rows = MLXArray((0..<config.sx).map { Float($0) }).reshaped([config.sx, 1])
    let cols = MLXArray((0..<config.sy).map { Float($0) }).reshaped([1, config.sy])
    let row = (massMap * rows).sum() / total
    let col = (massMap * cols).sum() / total
    return (row, col)
}

// Radius of gyration: sqrt of the mass-weighted mean squared distance from the
// centroid. Low gyration is a compact body; runaway gyration is dispersal, the
// mass-conserving analogue of the asymptotic runner's mass collapse.
func flowSensorimotorGyration(
    _ state: MLXArray,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    let massMap = flowSensorimotorMassMap(state, config: config)[0]
    let total = massMap.sum() + MLXArray(Float(1e-8))
    let rows = MLXArray((0..<config.sx).map { Float($0) }).reshaped([config.sx, 1])
    let cols = MLXArray((0..<config.sy).map { Float($0) }).reshaped([1, config.sy])
    let cr = (massMap * rows).sum() / total
    let cc = (massMap * cols).sum() / total
    let dr = rows - cr
    let dc = cols - cc
    let sq = dr * dr + dc * dc
    return MLX.sqrt((massMap * sq).sum() / total)
}

// MARK: - Behavior embedding, viability, goal loss

// 3D behavior descriptor, the Flow-Lenia analogue of the paper's
// [collapse, centroidX, centroidY]. Compactness (normalized gyration) replaces
// the asymptotic collapse proxy; x/y are the centroid displacement from grid
// center, normalized by grid size. The search keeps compactness small (a
// coherent body) and explores x/y (where the body travels).
struct FlowSensorimotorEmbedding {
    let compactness: Float
    let x: Float
    let y: Float

    var vector: [Float] { [compactness, x, y] }
}

func flowSensorimotorEmbedding(
    _ state: MLXArray,
    config: FlowSensorimotorStepConfig
) -> FlowSensorimotorEmbedding {
    let gyration = flowSensorimotorGyration(state, config: config).item(Float.self)
    let centroid = flowSensorimotorCentroid(state, config: config)
    let row = centroid.row.item(Float.self)
    let col = centroid.col.item(Float.self)
    let scale = Float(min(config.sx, config.sy))
    return FlowSensorimotorEmbedding(
        compactness: gyration / scale,
        x: (col - Float(config.sy) / 2) / Float(config.sy),
        y: (row - Float(config.sx) / 2) / Float(config.sx)
    )
}

// Mass-conserving viability. Because Flow-Lenia conserves mass, a body cannot
// die by mass decay; it fails by dispersing (gyration blows up) or fragmenting
// (the largest connected component stops dominating). These replace the
// asymptotic runner's mass-floor death test.
struct FlowSensorimotorViabilityThresholds {
    let componentMassThreshold: Float
    let maxGyration: Float
    let minLargestComponentFraction: Float
    let maxComponentCount: Int
}

struct FlowSensorimotorViability {
    let mass: Float
    let gyration: Float
    let componentCount: Float
    let largestComponentFraction: Float
    let alive: Bool
}

func flowSensorimotorViability(
    _ state: MLXArray,
    config: FlowSensorimotorStepConfig,
    thresholds: FlowSensorimotorViabilityThresholds
) -> FlowSensorimotorViability {
    let massMap = flowSensorimotorMassMap(state, config: config)
    let mass = massMap.sum().item(Float.self)
    let gyration = flowSensorimotorGyration(state, config: config).item(Float.self)
    let materialized = materializeMassBatch(massMap)
    let components = computeComponentMetricsBatch(
        materialized: materialized,
        threshold: thresholds.componentMassThreshold,
        useTorus: config.useTorus
    )
    let count = components.count[0]
    let largestFraction = components.largestFraction[0]
    let alive = mass > 0
        && gyration <= thresholds.maxGyration
        && largestFraction >= thresholds.minLargestComponentFraction
        && count <= Float(thresholds.maxComponentCount)
    return FlowSensorimotorViability(
        mass: mass,
        gyration: gyration,
        componentCount: count,
        largestComponentFraction: largestFraction,
        alive: alive
    )
}

// Differentiable goal loss for the gradient inner loop. The target is a Gaussian
// body of the same conserved mass, placed at the goal centroid with a width set
// by the goal compactness; the loss is the squared error between the final body
// mass map and that target. A dense spatial target conditions the gradient
// better than an embedding-space distance and pulls mass toward both the goal
// location and the goal size.
struct FlowSensorimotorGoal {
    let compactness: Float
    let x: Float
    let y: Float

    var vector: [Float] { [compactness, x, y] }
}

func flowSensorimotorGoalLoss(
    finalState: MLXArray,
    goal: FlowSensorimotorGoal,
    config: FlowSensorimotorStepConfig
) -> MLXArray {
    let massMap = flowSensorimotorMassMap(finalState, config: config)[0]
    let totalMass = massMap.sum()

    let scale = Float(min(config.sx, config.sy))
    let targetRow = Float(config.sx) / 2 + goal.y * Float(config.sx)
    let targetCol = Float(config.sy) / 2 + goal.x * Float(config.sy)
    // gyration of an isotropic 2D Gaussian is sqrt(2)*sigma, so invert that to set
    // the target width from the goal compactness (compactness = gyration/scale).
    let sigma = max(goal.compactness * scale / Float(2.0).squareRoot(), 1.0)

    let rows = MLXArray((0..<config.sx).map { Float($0) }).reshaped([config.sx, 1])
    let cols = MLXArray((0..<config.sy).map { Float($0) }).reshaped([1, config.sy])
    let dr = rows - MLXArray(targetRow)
    let dc = cols - MLXArray(targetCol)
    let bell = MLX.exp(-(dr * dr + dc * dc) / MLXArray(2.0 * sigma * sigma))
    let target = bell / (bell.sum() + MLXArray(Float(1e-8))) * totalMass

    let diff = massMap - target
    return (diff * diff).sum()
}

// MARK: - Configuration

// Single nested config for the whole protocol, decoded from one JSON file with
// convertFromSnakeCase. The asymptotic runner splits this across three files and
// ~90 flat fields; here the obstacle is a wall potential rather than a channel
// (so channels == learnable channels == 1) and viability is dispersal-based,
// which keeps the surface small.
struct FlowSensorimotorConfig: Codable, Sendable {
    struct Grid: Codable, Sendable {
        let sx: Int
        let sy: Int
    }

    struct Physics: Codable, Sendable {
        let nbK: Int
        let bumpsPerKernel: Int
        let dd: Int
        let sigma: Float
        let dt: Float
        let n: Int
        let thetaA: Float
        let R: Float
        let kernelProfile: String
        let gradientBoundary: String
        let alphaMode: String
        let flowClip: String
        let growthProfile: String
        let useTorus: Bool
    }

    struct Range: Codable, Sendable {
        let low: Float
        let high: Float
    }

    struct RuleSpace: Codable, Sendable {
        let a: Range
        let w: Range
        let b: Range
        let r: Range
        let m: Range
        let s: Range
        let h: Range
    }

    struct Initialization: Codable, Sendable {
        let size: Int
        let origin: [Int]
        let valueRange: [Float]
    }

    struct Obstacles: Codable, Sendable {
        let count: Int
        let radius: Int
        let potentialHeight: Float
        let leftHalfClear: Bool
        let clearInitializationRadius: Int
    }

    struct Viability: Codable, Sendable {
        let componentMassThreshold: Float
        let maxGyration: Float
        let minLargestComponentFraction: Float
        let maxComponentCount: Int
    }

    struct GoalSampling: Codable, Sendable {
        let warmupSteps: Int
        let warmupStart: [Float]
        let warmupDelta: [Float]
        let compactnessGoalMean: Float
        let compactnessJitterStd: Float
        let bestGoalProbability: Float
        let randomFarProbability: Float
        let bestGoalXOffset: [Float]
        let bestGoalYOffset: [Float]
        let farXRange: [Float]
        let farYRange: [Float]
        let broadXRange: [Float]
        let broadYRange: [Float]
        let closeDistance: Float
        let veryCloseDistance: Float
        let minCloseNeighbors: Int
        let maxVeryCloseNeighbors: Int
    }

    struct Optimization: Codable, Sendable {
        let stepsUnmutated: Int
        let stepsMutated: Int
        let ruleLr: Float
        let initializationLr: Float
        let betas: [Float]
        let eps: Float
    }

    struct Mutation: Codable, Sendable {
        let mutateEveryNSteps: Int
        let ruleStd: Float
        let initStd: Float
        let viabilityTrials: Int
    }

    struct Restart: Codable, Sendable {
        let maxAttempts: Int
        let minAliveRandomInitializations: Int
        let maxLoss: Float
    }

    let paper: String
    let grid: Grid
    let physics: Physics
    let ruleSpace: RuleSpace
    let initialization: Initialization
    let obstacles: Obstacles
    let viability: Viability
    let outerSteps: Int
    let historyInitializationTrials: Int
    let rolloutSteps: Int
    let evaluationRollouts: Int
    let goalSampling: GoalSampling
    let optimization: Optimization
    let mutation: Mutation
    let restart: Restart
}

func loadFlowSensorimotorConfig(configFile: URL) throws -> FlowSensorimotorConfig {
    let data = try Data(contentsOf: configFile)
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(FlowSensorimotorConfig.self, from: data)
}

extension FlowSensorimotorConfig {
    var stepConfig: FlowSensorimotorStepConfig {
        FlowSensorimotorStepConfig(
            sx: grid.sx, sy: grid.sy, nbK: physics.nbK, channels: 1, learnableChannels: 1,
            dd: physics.dd, sigma: physics.sigma, dt: physics.dt, n: physics.n,
            thetaA: physics.thetaA, R: physics.R,
            kernelProfile: physics.kernelProfile, gradientBoundary: physics.gradientBoundary,
            alphaMode: physics.alphaMode, flowClip: physics.flowClip,
            growthProfile: physics.growthProfile, useTorus: physics.useTorus
        )
    }

    var viabilityThresholds: FlowSensorimotorViabilityThresholds {
        FlowSensorimotorViabilityThresholds(
            componentMassThreshold: viability.componentMassThreshold,
            maxGyration: viability.maxGyration,
            minLargestComponentFraction: viability.minLargestComponentFraction,
            maxComponentCount: viability.maxComponentCount
        )
    }
}

// MARK: - Learnable state

// The genotype: per-kernel rule parameters plus the seed patch. R and dt are
// fixed in config (not learned) so the array layout matches the physics-core
// rollout signature exactly. Array order is the argument order the gradient
// inner loop differentiates.
struct FlowSensorimotorState {
    let a: MLXArray
    let w: MLXArray
    let b: MLXArray
    let r: MLXArray
    let m: MLXArray
    let s: MLXArray
    let h: MLXArray
    let initialization: MLXArray

    var arrays: [MLXArray] { [a, w, b, r, m, s, h, initialization] }

    init(a: MLXArray, w: MLXArray, b: MLXArray, r: MLXArray, m: MLXArray, s: MLXArray, h: MLXArray, initialization: MLXArray) {
        self.a = a
        self.w = w
        self.b = b
        self.r = r
        self.m = m
        self.s = s
        self.h = h
        self.initialization = initialization
    }

    init(arrays: [MLXArray]) {
        precondition(arrays.count == 8, "flow sensorimotor state expects 8 arrays, got \(arrays.count)")
        self.init(a: arrays[0], w: arrays[1], b: arrays[2], r: arrays[3], m: arrays[4], s: arrays[5], h: arrays[6], initialization: arrays[7])
    }
}

func flowSensorimotorUniformArray(shape: [Int], range: FlowSensorimotorConfig.Range, rng: inout SeededRandomNumberGenerator) -> MLXArray {
    let count = shape.reduce(1, *)
    let values = (0..<count).map { _ in Float.random(in: range.low...range.high, using: &rng) }
    return MLXArray(values).reshaped(shape)
}

func flowSensorimotorSampleState(config: FlowSensorimotorConfig, rng: inout SeededRandomNumberGenerator) -> FlowSensorimotorState {
    let nbK = config.physics.nbK
    let bumps = config.physics.bumpsPerKernel
    let size = config.initialization.size
    let initRange = FlowSensorimotorConfig.Range(low: config.initialization.valueRange[0], high: config.initialization.valueRange[1])
    return FlowSensorimotorState(
        a: flowSensorimotorUniformArray(shape: [nbK, bumps], range: config.ruleSpace.a, rng: &rng),
        w: flowSensorimotorUniformArray(shape: [nbK, bumps], range: config.ruleSpace.w, rng: &rng),
        b: flowSensorimotorUniformArray(shape: [nbK, bumps], range: config.ruleSpace.b, rng: &rng),
        r: flowSensorimotorUniformArray(shape: [nbK], range: config.ruleSpace.r, rng: &rng),
        m: flowSensorimotorUniformArray(shape: [nbK], range: config.ruleSpace.m, rng: &rng),
        s: flowSensorimotorUniformArray(shape: [nbK], range: config.ruleSpace.s, rng: &rng),
        h: flowSensorimotorUniformArray(shape: [nbK], range: config.ruleSpace.h, rng: &rng),
        initialization: flowSensorimotorUniformArray(shape: [size, size], range: initRange, rng: &rng)
    )
}

func flowSensorimotorClamp(_ state: FlowSensorimotorState, config: FlowSensorimotorConfig) -> FlowSensorimotorState {
    func clip(_ x: MLXArray, _ range: FlowSensorimotorConfig.Range) -> MLXArray {
        MLX.clip(x, min: MLXArray(range.low), max: MLXArray(range.high))
    }
    let initRange = FlowSensorimotorConfig.Range(low: config.initialization.valueRange[0], high: config.initialization.valueRange[1])
    return FlowSensorimotorState(
        a: clip(state.a, config.ruleSpace.a),
        w: clip(state.w, config.ruleSpace.w),
        b: clip(state.b, config.ruleSpace.b),
        r: clip(state.r, config.ruleSpace.r),
        m: clip(state.m, config.ruleSpace.m),
        s: clip(state.s, config.ruleSpace.s),
        h: clip(state.h, config.ruleSpace.h),
        initialization: clip(state.initialization, initRange)
    )
}

// Place the seed patch into a full [1, sx, sy, 1] grid by concatenating zero
// blocks around it. Concatenation passes gradients to the patch, so the gradient
// inner loop reaches the initialization parameter.
func flowSensorimotorInitialState(initialization: MLXArray, config: FlowSensorimotorConfig) -> MLXArray {
    let sx = config.grid.sx
    let sy = config.grid.sy
    let size = config.initialization.size
    let top = config.initialization.origin[0]
    let left = config.initialization.origin[1]
    let bottom = sx - size - top
    let right = sy - size - left
    precondition(top >= 0 && bottom >= 0 && left >= 0 && right >= 0,
                 "init patch of size \(size) at origin \(config.initialization.origin) does not fit in \(sx)x\(sy)")

    var rowBlocks: [MLXArray] = []
    if top > 0 { rowBlocks.append(MLX.zeros([top, size])) }
    rowBlocks.append(initialization)
    if bottom > 0 { rowBlocks.append(MLX.zeros([bottom, size])) }
    let rowsStacked = MLX.concatenated(rowBlocks, axis: 0)

    var colBlocks: [MLXArray] = []
    if left > 0 { colBlocks.append(MLX.zeros([sx, left])) }
    colBlocks.append(rowsStacked)
    if right > 0 { colBlocks.append(MLX.zeros([sx, right])) }
    let full = MLX.concatenated(colBlocks, axis: 1)
    return full.reshaped([1, sx, sy, 1])
}

// Positive wall potential [1, sx, sy, 1] from random obstacle disks. Mass flows
// down the growth potential, so positive disks repel. Disks avoid a clear radius
// around the seed origin so the body is not born inside a wall, and optionally
// keep the left half clear (a corridor for directed locomotion).
func flowSensorimotorObstaclePotential(config: FlowSensorimotorConfig, rng: inout SeededRandomNumberGenerator) -> MLXArray {
    let sx = config.grid.sx
    let sy = config.grid.sy
    var field = [Float](repeating: 0.0, count: sx * sy)
    let radius = config.obstacles.radius
    let height = config.obstacles.potentialHeight
    let clearRadius = config.obstacles.clearInitializationRadius
    let initCenterRow = config.initialization.origin[0] + config.initialization.size / 2
    let initCenterCol = config.initialization.origin[1] + config.initialization.size / 2

    var placed = 0
    var attempts = 0
    let maxAttempts = config.obstacles.count * 64
    while placed < config.obstacles.count && attempts < maxAttempts {
        attempts += 1
        let cr = Int.random(in: radius..<(sx - radius), using: &rng)
        let lowCol = config.obstacles.leftHalfClear ? sy / 2 : radius
        guard lowCol < sy - radius else { break }
        let cc = Int.random(in: lowCol..<(sy - radius), using: &rng)
        let dRow = Float(cr - initCenterRow)
        let dCol = Float(cc - initCenterCol)
        if (dRow * dRow + dCol * dCol).squareRoot() < Float(clearRadius + radius) {
            continue
        }
        for row in (cr - radius)...(cr + radius) {
            for col in (cc - radius)...(cc + radius) {
                let dr = row - cr
                let dc = col - cc
                if dr * dr + dc * dc <= radius * radius {
                    field[row * sy + col] = height
                }
            }
        }
        placed += 1
    }
    return MLXArray(field).reshaped([1, sx, sy, 1])
}

// MARK: - IMGEP search

struct FlowSensorimotorRecord {
    let step: Int
    let goal: FlowSensorimotorGoal?
    let reached: FlowSensorimotorEmbedding
    let alive: Bool
    let mutated: Bool
    let trainingLoss: Float?
    let state: FlowSensorimotorState
}

func flowSensorimotorGoalDistance(_ a: [Float], _ b: [Float]) -> Float {
    var sum: Float = 0
    for i in 0..<a.count {
        let d = a[i] - b[i]
        sum += d * d
    }
    return sum.squareRoot()
}

// IMGEP diversity search on Flow-Lenia. Holds the rollout constants (position
// grid, channel maps, derived step config) so the goal-sampling, mutation, and
// gradient methods share them. Artifact writing lives in the run() extension.
final class FlowSensorimotorRunner {
    let config: FlowSensorimotorConfig
    let logger: Logger
    let stepConfig: FlowSensorimotorStepConfig
    let posGrid: MLXArray
    let c0Idxs: MLXArray
    let c1Mask: MLXArray

    init(config: FlowSensorimotorConfig, logger: Logger) {
        self.config = config
        self.logger = logger
        self.stepConfig = config.stepConfig
        self.posGrid = flowSensorimotorPosGrid(sx: config.grid.sx, sy: config.grid.sy)
        let nbK = config.physics.nbK
        self.c0Idxs = MLXArray((0..<nbK).map { _ in Int32(0) })
        self.c1Mask = MLXArray([Float](repeating: 1.0, count: nbK)).reshaped([1, nbK])
    }

    func rollout(state: FlowSensorimotorState, wallPotential: MLXArray?) -> MLXArray {
        let initial = flowSensorimotorInitialState(initialization: state.initialization, config: config)
        return flowSensorimotorRollout(
            initial: initial, a: state.a, w: state.w, b: state.b, r: state.r,
            m: state.m, s: state.s, h: state.h,
            c0Idxs: c0Idxs, c1Mask: c1Mask, posGrid: posGrid,
            wallPotential: wallPotential, steps: config.rolloutSteps, config: stepConfig
        )
    }

    // Behavior reached over evaluationRollouts random obstacle fields. The mean
    // embedding is the archived descriptor; the candidate is alive only if every
    // rollout stayed viable (coherent and non-dispersed).
    func archiveEvaluation(state: FlowSensorimotorState, rng: inout SeededRandomNumberGenerator) -> (reached: FlowSensorimotorEmbedding, alive: Bool) {
        var sum: [Float] = [0, 0, 0]
        var alive = true
        for _ in 0..<config.evaluationRollouts {
            let obstacle = flowSensorimotorObstaclePotential(config: config, rng: &rng)
            let final = rollout(state: state, wallPotential: obstacle)
            let viability = flowSensorimotorViability(final, config: stepConfig, thresholds: config.viabilityThresholds)
            if !viability.alive { alive = false }
            let embedding = flowSensorimotorEmbedding(final, config: stepConfig)
            sum[0] += embedding.compactness
            sum[1] += embedding.x
            sum[2] += embedding.y
        }
        let inv = 1 / Float(max(config.evaluationRollouts, 1))
        let reached = FlowSensorimotorEmbedding(compactness: sum[0] * inv, x: sum[1] * inv, y: sum[2] * inv)
        return (reached, alive)
    }

    func sampleGoal(explorationIndex: Int, records: [FlowSensorimotorRecord], rng: inout SeededRandomNumberGenerator) -> FlowSensorimotorGoal {
        let g = config.goalSampling
        if explorationIndex < g.warmupSteps {
            return FlowSensorimotorGoal(
                compactness: g.compactnessGoalMean,
                x: g.warmupStart[0] + Float(explorationIndex) * g.warmupDelta[0],
                y: g.warmupStart[1] + Float(explorationIndex) * g.warmupDelta[1]
            )
        }

        let aliveReached = records.filter(\.alive).map(\.reached)
        // "best" is the most mobile alive body (largest displacement from origin),
        // the Flow-Lenia analogue of the paper's furthest-traveled creature.
        let best = aliveReached.max(by: { ($0.x * $0.x + $0.y * $0.y) < ($1.x * $1.x + $1.y * $1.y) })

        var target = FlowSensorimotorGoal(compactness: g.compactnessGoalMean, x: 0, y: 0)
        var closeCount = 0
        var veryCloseCount = Int.max
        while closeCount < g.minCloseNeighbors || veryCloseCount > g.maxVeryCloseNeighbors {
            let compactness = g.compactnessGoalMean + gaussianSample(std: g.compactnessJitterStd, rng: &rng)
            if Float.random(in: 0...1, using: &rng) < g.bestGoalProbability, let best {
                target = FlowSensorimotorGoal(
                    compactness: compactness,
                    x: best.x + Float.random(in: g.bestGoalXOffset[0]...g.bestGoalXOffset[1], using: &rng),
                    y: best.y + Float.random(in: g.bestGoalYOffset[0]...g.bestGoalYOffset[1], using: &rng)
                )
            } else if Float.random(in: 0...1, using: &rng) < g.randomFarProbability {
                target = FlowSensorimotorGoal(
                    compactness: compactness,
                    x: Float.random(in: g.farXRange[0]...g.farXRange[1], using: &rng),
                    y: Float.random(in: g.farYRange[0]...g.farYRange[1], using: &rng)
                )
            } else {
                target = FlowSensorimotorGoal(
                    compactness: compactness,
                    x: Float.random(in: g.broadXRange[0]...g.broadXRange[1], using: &rng),
                    y: Float.random(in: g.broadYRange[0]...g.broadYRange[1], using: &rng)
                )
            }
            let distances = aliveReached.map { flowSensorimotorGoalDistance(target.vector, $0.vector) }
            closeCount = distances.filter { $0 < g.closeDistance }.count
            veryCloseCount = distances.filter { $0 < g.veryCloseDistance }.count
            if aliveReached.isEmpty { break }
        }
        return target
    }

    func sourceIndex(for goal: FlowSensorimotorGoal, records: [FlowSensorimotorRecord]) -> Int {
        var bestIndex = 0
        var bestDistance = Float.greatestFiniteMagnitude
        for (index, record) in records.enumerated() where record.alive {
            let distance = flowSensorimotorGoalDistance(goal.vector, record.reached.vector)
            if distance < bestDistance {
                bestDistance = distance
                bestIndex = index
            }
        }
        return bestIndex
    }

    func mutate(source: FlowSensorimotorState, rng: inout SeededRandomNumberGenerator) -> (state: FlowSensorimotorState, mutated: Bool) {
        func perturb(_ x: MLXArray, std: Float) -> MLXArray {
            let count = x.shape.reduce(1, *)
            let noise = MLXArray((0..<count).map { _ in gaussianSample(std: std, rng: &rng) }).reshaped(x.shape)
            return x + noise
        }
        for _ in 0..<config.mutation.viabilityTrials {
            let ruleStd = config.mutation.ruleStd
            let candidate = flowSensorimotorClamp(FlowSensorimotorState(
                a: perturb(source.a, std: ruleStd),
                w: perturb(source.w, std: ruleStd),
                b: perturb(source.b, std: ruleStd),
                r: perturb(source.r, std: ruleStd),
                m: perturb(source.m, std: ruleStd),
                s: perturb(source.s, std: ruleStd),
                h: perturb(source.h, std: ruleStd),
                initialization: perturb(source.initialization, std: config.mutation.initStd)
            ), config: config)
            let obstacle = flowSensorimotorObstaclePotential(config: config, rng: &rng)
            let final = rollout(state: candidate, wallPotential: obstacle)
            if flowSensorimotorViability(final, config: stepConfig, thresholds: config.viabilityThresholds).alive {
                return (candidate, true)
            }
        }
        return (source, false)
    }

    func optimizeTowardGoal(
        initialState: FlowSensorimotorState,
        goal: FlowSensorimotorGoal,
        mutated: Bool,
        rng: inout SeededRandomNumberGenerator
    ) -> (state: FlowSensorimotorState, loss: Float, reached: FlowSensorimotorEmbedding, steps: Int) {
        var state = flowSensorimotorClamp(initialState, config: config)
        var optimizer = MLXAdam(
            paramShapes: state.arrays.map(\.shape),
            learningRates: Array(repeating: config.optimization.ruleLr, count: state.arrays.count - 1)
                + [config.optimization.initializationLr],
            beta1: config.optimization.betas[0],
            beta2: config.optimization.betas[1],
            eps: config.optimization.eps
        )
        let gradientSteps = mutated ? config.optimization.stepsMutated : config.optimization.stepsUnmutated
        var lastLoss: Float = .infinity
        var lastDead = false

        for _ in 0..<gradientSteps {
            let obstacle = flowSensorimotorObstaclePotential(config: config, rng: &rng)
            let objective = valueAndGrad { [self] (arrays: [MLXArray]) -> [MLXArray] in
                let candidate = FlowSensorimotorState(arrays: arrays)
                let final = rollout(state: candidate, wallPotential: obstacle)
                return [flowSensorimotorGoalLoss(finalState: final, goal: goal, config: stepConfig)]
            }
            let (value, gradients) = objective(state.arrays)
            state = flowSensorimotorClamp(FlowSensorimotorState(arrays: optimizer.step(params: state.arrays, gradients: gradients)), config: config)
            MLX.eval(state.arrays + value)
            lastLoss = value[0].item(Float.self)

            let aliveFinal = rollout(state: state, wallPotential: obstacle)
            let dead = !flowSensorimotorViability(aliveFinal, config: stepConfig, thresholds: config.viabilityThresholds).alive
            if dead && lastDead { break }
            lastDead = dead
        }

        let evalFinal = rollout(state: state, wallPotential: nil)
        let reached = flowSensorimotorEmbedding(evalFinal, config: stepConfig)
        return (state, lastLoss, reached, gradientSteps)
    }

    // One restart attempt: random-initialization phase to seed the archive, then
    // the goal-directed exploration phase. Returns an empty history to request a
    // restart when too few random seeds survive or an early optimized loss is
    // hopeless.
    func runAttempt(rng: inout SeededRandomNumberGenerator) -> [FlowSensorimotorRecord] {
        var records: [FlowSensorimotorRecord] = []
        records.reserveCapacity(config.outerSteps)
        var aliveRandom = 0
        var restartAllowed = true

        while records.count < config.outerSteps {
            if records.count < config.historyInitializationTrials {
                let state = flowSensorimotorSampleState(config: config, rng: &rng)
                let (reached, alive) = archiveEvaluation(state: state, rng: &rng)
                if alive { aliveRandom += 1 }
                records.append(FlowSensorimotorRecord(
                    step: records.count, goal: nil, reached: reached, alive: alive,
                    mutated: false, trainingLoss: nil, state: state
                ))
                if records.count == config.historyInitializationTrials,
                   aliveRandom < config.restart.minAliveRandomInitializations {
                    logger.warning("Restarting flow sensorimotor attempt: alive random count \(aliveRandom) < \(config.restart.minAliveRandomInitializations)")
                    return []
                }
                continue
            }

            let explorationIndex = records.count - config.historyInitializationTrials
            let goal = sampleGoal(explorationIndex: explorationIndex, records: records, rng: &rng)
            let source = records[sourceIndex(for: goal, records: records)].state
            let useSourceDirectly = explorationIndex < config.goalSampling.warmupSteps
                || records.count % config.mutation.mutateEveryNSteps == 0
            let mutation = useSourceDirectly ? (state: source, mutated: false) : mutate(source: source, rng: &rng)
            let optimized = optimizeTowardGoal(initialState: mutation.state, goal: goal, mutated: mutation.mutated, rng: &rng)

            if restartAllowed, explorationIndex < 2, optimized.loss > config.restart.maxLoss {
                logger.warning("Restarting flow sensorimotor attempt: early post-random loss \(optimized.loss) > \(config.restart.maxLoss)")
                return []
            }
            if restartAllowed, explorationIndex == 1 { restartAllowed = false }

            let (reached, alive) = archiveEvaluation(state: optimized.state, rng: &rng)
            records.append(FlowSensorimotorRecord(
                step: records.count, goal: goal, reached: reached, alive: alive,
                mutated: mutation.mutated, trainingLoss: optimized.loss, state: optimized.state
            ))
        }
        return records
    }

    func search(seed: UInt64) -> (records: [FlowSensorimotorRecord], restartCount: Int) {
        var rng = SeededRandomNumberGenerator(seed: seed)
        var restartCount = 0
        while restartCount < config.restart.maxAttempts {
            logger.info("Flow sensorimotor attempt \(restartCount + 1)/\(config.restart.maxAttempts)")
            let attempt = runAttempt(rng: &rng)
            if !attempt.isEmpty { return (attempt, restartCount) }
            restartCount += 1
        }
        return ([], restartCount)
    }
}
