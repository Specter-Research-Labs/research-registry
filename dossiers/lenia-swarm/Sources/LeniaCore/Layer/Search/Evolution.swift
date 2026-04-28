import Foundation
import MLX
import MLXRandom

// ES Configuration structures matching es.py

public struct FitnessConfig: Codable {
    public let objective: String  // "directed_motion", "angular_motion", "obstacle_navigation", "chemotaxis"
    public let targetStep: Int
    public let angleThreshold: Float
    public let gyrationPenalty: Float?
    public let componentCountPenalty: Float?
    public let largestComponentFractionReward: Float?
    public let largestComponentAnisotropyPenalty: Float?
    public let momentDensityReward: Float?
    public let momentAnisotropyPenalty: Float?
    public let morphologyThreshold: Float?

    enum CodingKeys: String, CodingKey {
        case objective
        case targetStep = "target_step"
        case angleThreshold = "angle_threshold"
        case gyrationPenalty = "gyration_penalty"
        case componentCountPenalty = "component_count_penalty"
        case largestComponentFractionReward = "largest_component_fraction_reward"
        case largestComponentAnisotropyPenalty = "largest_component_anisotropy_penalty"
        case momentDensityReward = "moment_density_reward"
        case momentAnisotropyPenalty = "moment_anisotropy_penalty"
        case morphologyThreshold = "morphology_threshold"
    }

    public init(
        objective: String,
        targetStep: Int,
        angleThreshold: Float,
        gyrationPenalty: Float? = nil,
        componentCountPenalty: Float? = nil,
        largestComponentFractionReward: Float? = nil,
        largestComponentAnisotropyPenalty: Float? = nil,
        momentDensityReward: Float? = nil,
        momentAnisotropyPenalty: Float? = nil,
        morphologyThreshold: Float? = nil
    ) {
        self.objective = objective
        self.targetStep = targetStep
        self.angleThreshold = angleThreshold
        self.gyrationPenalty = gyrationPenalty
        self.componentCountPenalty = componentCountPenalty
        self.largestComponentFractionReward = largestComponentFractionReward
        self.largestComponentAnisotropyPenalty = largestComponentAnisotropyPenalty
        self.momentDensityReward = momentDensityReward
        self.momentAnisotropyPenalty = momentAnisotropyPenalty
        self.morphologyThreshold = morphologyThreshold
    }

    var usesMorphologyMetrics: Bool {
        componentCountPenalty != nil ||
            largestComponentFractionReward != nil ||
            largestComponentAnisotropyPenalty != nil ||
            momentDensityReward != nil ||
            momentAnisotropyPenalty != nil
    }
}

public struct ESObstacleFieldConfig: Codable {
    public let enabled: Bool
    public let channelIndex: Int
    public let mode: String
    public let count: Int
    public let circleRadius: Float
    public let sigma: Float
    public let amplitude: Float
    public let center: [Float]?
    public let seed: Int

    enum CodingKeys: String, CodingKey {
        case enabled
        case channelIndex = "channel_index"
        case mode
        case count
        case circleRadius = "circle_radius"
        case sigma
        case amplitude
        case center
        case seed
    }

    public init(
        enabled: Bool,
        channelIndex: Int,
        mode: String,
        count: Int,
        circleRadius: Float,
        sigma: Float,
        amplitude: Float,
        center: [Float]?,
        seed: Int
    ) {
        self.enabled = enabled
        self.channelIndex = channelIndex
        self.mode = mode
        self.count = count
        self.circleRadius = circleRadius
        self.sigma = sigma
        self.amplitude = amplitude
        self.center = center
        self.seed = seed
    }
}

public struct InitPatchConfig: Codable {
    public let enabled: Bool
    public let size: Int
    public let center: [Int]
    public let valueLow: Float
    public let valueHigh: Float

    enum CodingKeys: String, CodingKey {
        case enabled
        case size
        case center
        case valueLow = "value_low"
        case valueHigh = "value_high"
    }

    public init(enabled: Bool, size: Int, center: [Int], valueLow: Float, valueHigh: Float) {
        self.enabled = enabled
        self.size = size
        self.center = center
        self.valueLow = valueLow
        self.valueHigh = valueHigh
    }
}

public struct ESConfig: Codable {
    public let outputDir: String
    public let generations: Int
    public let population: Int
    public let sigma: Float
    public let learningRate: Float
    public let seed: Int
    public let steps: Int
    public let fitness: FitnessConfig
    public let fitnessShaping: String  // "centered_rank", "standardize", "raw"
    public let initPatch: InitPatchConfig?
    public let initialInitPatchValues: [Float]?
    public let initialKernelParams: KernelParams?
    public let paramRanges: [String: [Float]]?
    public let obstacleField: ESObstacleFieldConfig?

    enum CodingKeys: String, CodingKey {
        case outputDir = "output_dir"
        case generations
        case population
        case sigma
        case learningRate = "learning_rate"
        case seed
        case steps
        case fitness
        case fitnessShaping = "fitness_shaping"
        case initPatch = "init_patch"
        case initialInitPatchValues = "initial_init_patch_values"
        case initialKernelParams = "initial_kernel_params"
        case paramRanges = "param_ranges"
        case obstacleField = "obstacle_field"
    }

    public init(
        outputDir: String,
        generations: Int,
        population: Int,
        sigma: Float,
        learningRate: Float,
        seed: Int,
        steps: Int,
        fitness: FitnessConfig,
        fitnessShaping: String,
        initPatch: InitPatchConfig?,
        initialInitPatchValues: [Float]?,
        initialKernelParams: KernelParams? = nil,
        paramRanges: [String: [Float]]?,
        obstacleField: ESObstacleFieldConfig?
    ) {
        self.outputDir = outputDir
        self.generations = generations
        self.population = population
        self.sigma = sigma
        self.learningRate = learningRate
        self.seed = seed
        self.steps = steps
        self.fitness = fitness
        self.fitnessShaping = fitnessShaping
        self.initPatch = initPatch
        self.initialInitPatchValues = initialInitPatchValues
        self.initialKernelParams = initialKernelParams
        self.paramRanges = paramRanges
        self.obstacleField = obstacleField
    }
}

// Parameter space with sigmoid/logit normalization (matches es.py)

public struct ParamSlice {
    public let start: Int
    public let end: Int
    public let shape: [Int]

    public init(start: Int, end: Int, shape: [Int]) {
        self.start = start
        self.end = end
        self.shape = shape
    }
}

public struct ParamSpace {
    public let slices: [String: ParamSlice]
    public let low: [Float]
    public let high: [Float]
    public let totalDim: Int

    public init(nbK: Int, ranges: [String: (Float, Float)]) {
        var slices: [String: ParamSlice] = [:]
        var low: [Float] = []
        var high: [Float] = []
        var offset = 0

        func add(_ name: String, _ shape: [Int]) {
            let (lo, hi) = ranges[name]!
            let size = shape.reduce(1, *)
            slices[name] = ParamSlice(start: offset, end: offset + size, shape: shape)
            low.append(contentsOf: [Float](repeating: lo, count: size))
            high.append(contentsOf: [Float](repeating: hi, count: size))
            offset += size
        }

        add("r", [nbK])
        add("b", [nbK, 3])
        add("w", [nbK, 3])
        add("a", [nbK, 3])
        add("m", [nbK])
        add("s", [nbK])
        add("h", [nbK])
        add("R", [1])

        self.slices = slices
        self.low = low
        self.high = high
        self.totalDim = offset
    }
}

private func sigmoid(_ x: Float) -> Float {
    1.0 / (1.0 + exp(-x))
}

private func logit(_ x: Float) -> Float {
    log(x / (1.0 - x))
}

private func sigmoidArray(_ x: [Float]) -> [Float] {
    x.map { sigmoid($0) }
}

public func paramsToVector(_ params: ResolvedParams, space: ParamSpace) -> [Float] {
    var vec = [Float](repeating: 0.0, count: space.totalDim)

    func encode(_ name: String, _ values: [Float]) {
        let slice = space.slices[name]!
        for (i, val) in values.enumerated() {
            let lo = space.low[slice.start + i]
            let hi = space.high[slice.start + i]
            let span = hi - lo
            let normalized = (val - lo) / (span == 0 ? 1.0 : span)
            let clipped = max(1e-6, min(1.0 - 1e-6, normalized))
            vec[slice.start + i] = logit(clipped)
        }
    }

    encode("r", params.r)
    encode("b", params.b.flatMap { $0 })
    encode("w", params.w.flatMap { $0 })
    encode("a", params.a.flatMap { $0 })
    encode("m", params.m)
    encode("s", params.s)
    encode("h", params.h)
    encode("R", [params.R])

    return vec
}

public func vectorToParams(_ vec: [Float], space: ParamSpace, seed: Int = 0) -> ResolvedParams {
    let scaled = zip(zip(space.low, space.high), vec).map { (bounds, v) in
        let (lo, hi) = bounds
        return lo + sigmoid(v) * (hi - lo)
    }

    func decode1D(_ name: String) -> [Float] {
        let slice = space.slices[name]!
        return Array(scaled[slice.start..<slice.end])
    }

    func decode2D(_ name: String, cols: Int) -> [[Float]] {
        let slice = space.slices[name]!
        let flat = Array(scaled[slice.start..<slice.end])
        let rows = flat.count / cols
        return (0..<rows).map { r in
            Array(flat[r * cols..<(r + 1) * cols])
        }
    }

    return ResolvedParams(
        r: decode1D("r"),
        b: decode2D("b", cols: 3),
        w: decode2D("w", cols: 3),
        a: decode2D("a", cols: 3),
        m: decode1D("m"),
        s: decode1D("s"),
        h: decode1D("h"),
        R: decode1D("R")[0],
        seed: seed
    )
}

private func resolvedParams(from kernelParams: KernelParams, space: ParamSpace, seed: Int = 0) -> ResolvedParams {
    let kernelCount = space.slices["r"]?.shape.first ?? 0
    guard kernelParams.r.count == kernelCount,
          kernelParams.b.count == kernelCount,
          kernelParams.w.count == kernelCount,
          kernelParams.a.count == kernelCount,
          kernelParams.m.count == kernelCount,
          kernelParams.s.count == kernelCount,
          kernelParams.h.count == kernelCount else {
        fatalError("initial_kernel_params shape does not match ES topology nbK=\(kernelCount).")
    }

    func rows3(_ name: String, _ rows: [[Float]], fill: Float) -> [[Float]] {
        rows.enumerated().map { index, row in
            guard row.count <= 3 else {
                fatalError("initial_kernel_params.\(name)[\(index)] has \(row.count) entries; expected at most 3.")
            }
            return Array((row + Array(repeating: fill, count: 3)).prefix(3))
        }
    }

    return ResolvedParams(
        r: kernelParams.r,
        b: rows3("b", kernelParams.b, fill: 0.0),
        w: rows3("w", kernelParams.w, fill: 0.0),
        a: rows3("a", kernelParams.a, fill: 0.0),
        m: kernelParams.m,
        s: kernelParams.s,
        h: kernelParams.h,
        R: kernelParams.R,
        seed: seed
    )
}

// Adam Optimizer (matches es.py)

public class Adam {
    public let lr: Float
    public let beta1: Float
    public let beta2: Float
    public let eps: Float

    public var m: [Float]?
    public var v: [Float]?
    public var t: Int = 0

    public init(lr: Float, beta1: Float = 0.9, beta2: Float = 0.999, eps: Float = 1e-8) {
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
    }

    public func step(params: [Float], grad: [Float]) -> [Float] {
        if m == nil {
            m = [Float](repeating: 0.0, count: params.count)
            v = [Float](repeating: 0.0, count: params.count)
        }

        t += 1
        var newParams = params

        for i in 0..<params.count {
            m![i] = beta1 * m![i] + (1.0 - beta1) * grad[i]
            v![i] = beta2 * v![i] + (1.0 - beta2) * grad[i] * grad[i]

            let mHat = m![i] / (1.0 - pow(beta1, Float(t)))
            let vHat = v![i] / (1.0 - pow(beta2, Float(t)))

            let stepVal = lr * mHat / (sqrt(vHat) + eps)
            newParams[i] = params[i] + stepVal
        }

        return newParams
    }
}

// Fitness shaping (matches es.py)

public func fitnessShaping(_ fitness: [Float], mode: String) -> [Float] {
    switch mode {
    case "raw":
        return fitness

    case "standardize":
        let mean = fitness.reduce(0, +) / Float(fitness.count)
        let variance = fitness.map { ($0 - mean) * ($0 - mean) }.reduce(0, +) / Float(fitness.count)
        let std = sqrt(variance)
        if std == 0 {
            return fitness.map { $0 - mean }
        }
        return fitness.map { ($0 - mean) / std }

    case "centered_rank":
        let indexed = fitness.enumerated().map { ($0.offset, $0.element) }
        let sorted = indexed.sorted { $0.1 < $1.1 }
        var ranks = [Float](repeating: 0.0, count: fitness.count)
        for (rank, (idx, _)) in sorted.enumerated() {
            ranks[idx] = Float(rank)
        }
        let n = Float(fitness.count)
        if n > 1 {
            return ranks.map { $0 / (n - 1) - 0.5 }
        }
        return ranks.map { _ in 0.0 }

    default:
        return fitness
    }
}

private func sampleStandardNormal(rng: inout SeededRandomNumberGenerator) -> Float {
    let u1 = max(Float.random(in: 0..<1, using: &rng), 1e-7)
    let u2 = Float.random(in: 0..<1, using: &rng)
    let radius = sqrt(-2.0 * log(u1))
    let angle = 2.0 * Float.pi * u2
    return radius * cos(angle)
}

func sampleOpenESNoise(
    population: Int,
    dimensions: Int,
    rng: inout SeededRandomNumberGenerator
) -> [[Float]] {
    guard population > 0 else { return [] }
    guard population % 2 == 0 else {
        fatalError("OpenES population must be even for antithetic sampling.")
    }

    let half = population / 2
    var plus = Array(
        repeating: Array(repeating: Float(0.0), count: dimensions),
        count: half
    )
    for i in 0..<half {
        for j in 0..<dimensions {
            plus[i][j] = sampleStandardNormal(rng: &rng)
        }
    }

    var noise = plus
    noise.reserveCapacity(population)
    for row in plus {
        noise.append(row.map(-))
    }
    return noise
}

// Center of mass computation (matches es.py)

func excludedMassChannelsForEvolution(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    obstacleField: ESObstacleFieldConfig?
) -> Set<Int> {
    flowExcludedMassChannels(
        channels: channels,
        chemotaxis: chemotaxis,
        food: food,
        additionalExcludedChannels: obstacleField.map { $0.enabled ? [$0.channelIndex] : [] } ?? []
    )
}

func creatureChannelsForEvolution(
    channels: Int,
    chemotaxis: ChemotaxisConfig?,
    food: FoodConfig?,
    obstacleField: ESObstacleFieldConfig?
) -> [Int] {
    flowCreatureChannels(
        channels: channels,
        chemotaxis: chemotaxis,
        food: food,
        additionalExcludedChannels: obstacleField.map { $0.enabled ? [$0.channelIndex] : [] } ?? []
    )
}

func evolutionMassMap(_ A: MLXArray, excludedChannels: Set<Int>) -> MLXArray {
    flowMatterMap(A, excludedChannels: excludedChannels)
}

private func evolutionMassMapBatch(_ A: MLXArray, excludedChannels: Set<Int>) -> MLXArray {
    flowMatterMap(A, excludedChannels: excludedChannels)
}

public func centerOfMass(_ A: MLXArray, excludedChannels: Set<Int> = []) -> (Float, Float)? {
    let massMap = evolutionMassMap(A, excludedChannels: excludedChannels)
    let sx = A.shape[0]
    let sy = A.shape[1]
    let coordsX = MLXArray(Array(0..<sx).map { Float($0) }).reshaped([sx, 1])
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) }).reshaped([1, sy])
    let totalArr = massMap.sum()
    let sumXArr = (massMap * coordsX).sum()
    let sumYArr = (massMap * coordsY).sum()
    eval(totalArr, sumXArr, sumYArr)
    let total = totalArr.item(Float.self)
    if total <= 0 {
        return nil
    }
    let cx = sumXArr.item(Float.self) / total
    let cy = sumYArr.item(Float.self) / total

    // Normalize to [-0.5, 0.5]
    return (cx / Float(sx) - 0.5, cy / Float(sy) - 0.5)
}

private func computeGyrationScalar(_ A: MLXArray, excludedChannels: Set<Int>) -> Float {
    let massMap = evolutionMassMap(A, excludedChannels: excludedChannels)
    let sx = A.shape[0]
    let sy = A.shape[1]
    let coordsX = MLXArray(Array(0..<sx).map { Float($0) }).reshaped([sx, 1])
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) }).reshaped([1, sy])
    let totalMassArr = massMap.sum()
    let sumXArr = (massMap * coordsX).sum()
    let sumYArr = (massMap * coordsY).sum()
    eval(totalMassArr, sumXArr, sumYArr)
    let totalMass = totalMassArr.item(Float.self)
    if totalMass <= 0 { return 1.0 }
    let cxArr = sumXArr / totalMassArr
    let cyArr = sumYArr / totalMassArr
    let distSq = (coordsX - cxArr) * (coordsX - cxArr) + (coordsY - cyArr) * (coordsY - cyArr)
    let gyrationArr = (massMap * distSq).sum() / totalMassArr
    eval(gyrationArr)
    return gyrationArr.item(Float.self) / Float(sx * sy)
}

private func applyExternalField(
    _ A: MLXArray,
    field: MLXArray,
    channelIndex: Int
) -> MLXArray {
    overwriteFieldChannel(A, field: field, channelIndex: channelIndex)
}

private func applyExternalFieldBatch(
    _ A: MLXArray,
    field: MLXArray,
    channelIndex: Int
) -> MLXArray {
    let signpost = LeniaSignposts.beginStep("applyExternalFieldBatch")
    defer { LeniaSignposts.end(signpost) }
    return overwriteFieldChannel(A, field: field, channelIndex: channelIndex)
}

private func buildChemotaxisField(
    sx: Int,
    sy: Int,
    config: ChemotaxisConfig,
    evalSeed: Int
) -> MLXArray {
    let coordsX = MLXArray(Array(0..<sx).map { Float($0) })
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) })
    let (X, Y) = meshgrid(coordsX, coordsY)

    var cx = config.center[0]
    var cy = config.center[1]
    if config.mode == "random_on_circle", let radius = config.circle_radius {
        var rng = SeededRandomNumberGenerator(seed: UInt64(evalSeed))
        let angle = Float.random(in: 0...(2 * Float.pi), using: &rng)
        cx += radius * cos(angle)
        cy += radius * sin(angle)
    }

    let distSq = (X - MLXArray(cx)) * (X - MLXArray(cx)) + (Y - MLXArray(cy)) * (Y - MLXArray(cy))
    let sigma = config.sigma
    let exponent = -distSq / MLXArray(2.0 * sigma * sigma)
    return MLXArray(config.amplitude) * MLX.exp(exponent)
}

private func buildObstacleField(
    sx: Int,
    sy: Int,
    config: ESObstacleFieldConfig,
    evalSeed: Int
) -> MLXArray {
    let center = config.center ?? [Float(sx) / 2.0, Float(sy) / 2.0]
    let sigmaSq = max(config.sigma * config.sigma, 1e-6)
    var rng = SeededRandomNumberGenerator(seed: UInt64(evalSeed))
    var obstacleCenters: [(Float, Float)] = []
    obstacleCenters.reserveCapacity(config.count)

    switch config.mode {
    case "random_on_circle":
        for _ in 0..<config.count {
            let angle = Float.random(in: 0...(2 * Float.pi), using: &rng)
            obstacleCenters.append((
                center[0] + config.circleRadius * cos(angle),
                center[1] + config.circleRadius * sin(angle)
            ))
        }
    default:
        fatalError("Unsupported obstacle_field.mode: \(config.mode)")
    }

    let coordsX = MLXArray(Array(0..<sx).map { Float($0) })
    let coordsY = MLXArray(Array(0..<sy).map { Float($0) })
    let (X, Y) = meshgrid(coordsX, coordsY)
    let xGrid = X.expandedDimensions(axis: -1)
    let yGrid = Y.expandedDimensions(axis: -1)
    let centersX = MLXArray(obstacleCenters.map(\.0)).reshaped([1, 1, obstacleCenters.count])
    let centersY = MLXArray(obstacleCenters.map(\.1)).reshaped([1, 1, obstacleCenters.count])
    let dx = xGrid - centersX
    let dy = yGrid - centersY
    let distSq = dx * dx + dy * dy
    let exponent = -distSq / MLXArray(2.0 * sigmaSq)
    let gaussian = MLXArray(config.amplitude) * MLX.exp(exponent)
    return gaussian.max(axis: -1)
}

private func buildObstaclePotential(from field: MLXArray) -> MLXArray {
    switch field.shape.count {
    case 2:
        return (field * MLXArray(-1.0)).expandedDimensions(axes: [0, 3])
    case 3:
        return (field * MLXArray(-1.0)).expandedDimensions(axis: 3)
    default:
        fatalError("obstacle potential expects rank-2 or rank-3 field")
    }
}

private func durationMs(_ duration: Duration) -> Double {
    Double(duration.components.seconds) * 1_000.0 +
        Double(duration.components.attoseconds) / 1_000_000_000_000_000.0
}

// Evolution Engine (matches es.py)

public final class EvolutionEngine {
    private enum PopulationEvaluator {
        case mlx
        case metalFull
    }

    private struct CenterSnapshot {
        let alive: Bool
        let x: Float
        let y: Float
    }

    private struct CandidateMeasurement {
        let initial: CenterSnapshot
        let mid: CenterSnapshot?
        let target: CenterSnapshot?
        let gyration: Float?
        let componentCount: Float?
        let largestComponentFraction: Float?
        let largestComponentAnisotropy: Float?
        let momentDensity: Float?
        let momentAnisotropy: Float?
        let chemotaxisScore: Float?
    }

    private struct MorphologyMeasurementBatch {
        let componentCount: [Float]?
        let largestComponentFraction: [Float]?
        let largestComponentAnisotropy: [Float]?
        let momentDensity: [Float]?
        let momentAnisotropy: [Float]?
    }

    private struct PopulationEvaluation {
        let measurements: [CandidateMeasurement]
        let kernelCompileMs: Double
        let stateBuildMs: Double
        let fieldBuildMs: Double
        let rolloutMs: Double
        let measurementMs: Double
    }

    public let config: BatchedConfig
    public let runtimeConfig: LeniaRuntimeConfig
    public let populationSim: FlowLeniaBatched
    public let esConfig: ESConfig
    public let paramSpace: ParamSpace
    public let optimizer: Adam
    public let excludedMassChannels: Set<Int>
    public let creatureChannels: [Int]
    public let metricGridX: MLXArray
    public let metricGridY: MLXArray
    private let populationEvaluator: PopulationEvaluator
    private var metalFullPopulationRunner: FlowLeniaMetalFullStateRunner?

    public var theta: [Float]
    public var rng: SeededRandomNumberGenerator
    public var evaluationCounter: Int = 0

    // For init patch evolution
    public let initPatchDim: Int
    public let thetaParamsDim: Int

    public init(
        runtimeConfig: LeniaRuntimeConfig,
        esConfig: ESConfig,
        ranges: [String: (Float, Float)]
    ) {
        self.esConfig = esConfig
        self.runtimeConfig = runtimeConfig
        self.config = batchedConfigFromRuntime(runtimeConfig)
        self.excludedMassChannels = excludedMassChannelsForEvolution(
            channels: runtimeConfig.channels,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food,
            obstacleField: esConfig.obstacleField
        )
        self.creatureChannels = creatureChannelsForEvolution(
            channels: runtimeConfig.channels,
            chemotaxis: runtimeConfig.chemotaxis,
            food: runtimeConfig.food,
            obstacleField: esConfig.obstacleField
        )

        let builtParamSpace = ParamSpace(nbK: config.nbK, ranges: ranges)
        self.paramSpace = builtParamSpace
        self.thetaParamsDim = builtParamSpace.totalDim
        self.optimizer = Adam(lr: esConfig.learningRate)
        self.rng = SeededRandomNumberGenerator(seed: UInt64(esConfig.seed))

        let supportedObjectives: Set<String> = [
            "directed_motion",
            "angular_motion",
            "obstacle_navigation",
            "chemotaxis",
        ]
        if !supportedObjectives.contains(esConfig.fitness.objective) {
            fatalError("Unsupported evolution objective: \(esConfig.fitness.objective)")
        }
        if esConfig.population % 2 != 0 {
            fatalError("OpenES population must be even for antithetic sampling.")
        }
        if esConfig.fitness.objective == "chemotaxis",
           runtimeConfig.chemotaxis?.enabled != true {
            fatalError("chemotaxis objective requires chemotaxis.enabled in the base config.")
        }
        if esConfig.fitness.objective == "obstacle_navigation",
           esConfig.obstacleField?.enabled != true {
            fatalError("obstacle_navigation objective requires obstacle_field.enabled in the ES config.")
        }
        if let obstacleField = esConfig.obstacleField, obstacleField.enabled {
            if obstacleField.channelIndex < 0 || obstacleField.channelIndex >= runtimeConfig.channels {
                fatalError("obstacle_field.channel_index is out of range for configured channels.")
            }
            if obstacleField.count <= 0 {
                fatalError("obstacle_field.count must be > 0.")
            }
            if obstacleField.circleRadius <= 0 {
                fatalError("obstacle_field.circle_radius must be > 0.")
            }
            if obstacleField.sigma <= 0 {
                fatalError("obstacle_field.sigma must be > 0.")
            }
            if obstacleField.center != nil && obstacleField.center?.count != 2 {
                fatalError("obstacle_field.center must have exactly two coordinates when provided.")
            }
        }

        let initialParams = esConfig.initialKernelParams.map {
            resolvedParams(from: $0, space: builtParamSpace, seed: runtimeConfig.params.seed)
        } ?? runtimeConfig.params
        var thetaParams = paramsToVector(initialParams, space: builtParamSpace)

        // Handle init patch if enabled
        if let initPatch = esConfig.initPatch, initPatch.enabled {
            let patchSize = initPatch.size * initPatch.size * creatureChannels.count
            self.initPatchDim = patchSize

            var patchTheta: [Float] = []
            let initialValues = esConfig.initialInitPatchValues
            if let initialValues, initialValues.count != patchSize {
                fatalError("initial_init_patch_values count \(initialValues.count) does not match expected patch size \(patchSize).")
            }
            for index in 0..<patchSize {
                let val = initialValues?[index] ?? Float.random(in: initPatch.valueLow...initPatch.valueHigh, using: &rng)
                let normalized = (val - initPatch.valueLow) / (initPatch.valueHigh - initPatch.valueLow)
                let clipped = max(1e-6, min(1.0 - 1e-6, normalized))
                patchTheta.append(logit(clipped))
            }
            thetaParams.append(contentsOf: patchTheta)
        } else {
            self.initPatchDim = 0
        }

        self.theta = thetaParams

        let coordsX = MLXArray(Array(0..<config.sx).map { Float($0) }).reshaped([1, config.sx, 1])
        let coordsY = MLXArray(Array(0..<config.sy).map { Float($0) }).reshaped([1, 1, config.sy])
        self.metricGridX = coordsX
        self.metricGridY = coordsY

        let seedParams = Array(repeating: initialParams, count: esConfig.population)
        self.populationSim = FlowLeniaBatched(
            config: config,
            kernels: compilePopulationKernels(
                paramsBatch: seedParams,
                config: config,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        )

        switch runtimeConfig.backend {
        case .mlx:
            self.populationEvaluator = .mlx
        case .metalFull:
            Self.validateMetalBackendCompatibility(runtimeConfig: runtimeConfig, esConfig: esConfig)
            self.populationEvaluator = .metalFull
        }
    }

    private func reusableMetalFullPopulationRunner(kernels: CompiledKernels) -> FlowLeniaMetalFullStateRunner {
        if let runner = metalFullPopulationRunner {
            runner.updateKernels(kernels)
            runner.setMatterWeights(metalMatterWeights())
            return runner
        }
        let runner = FlowLeniaMetalFullStateRunner(
            config: config,
            kernels: kernels,
            batchCount: esConfig.population,
            matterWeights: metalMatterWeights()
        )
        metalFullPopulationRunner = runner
        return runner
    }

    private func metalMatterWeights() -> [Float]? {
        flowMatterWeights(channels: config.channels, excludedChannels: excludedMassChannels)
    }

    private func metalStaticChannelFields(
        chemFieldBatch: MLXArray?,
        obstacleFieldBatch: MLXArray?
    ) -> [FlowLeniaMetalChannelField] {
        var fields: [FlowLeniaMetalChannelField] = []
        if let field = chemFieldBatch,
           let chemotaxis = runtimeConfig.chemotaxis,
           chemotaxis.enabled {
            fields.append(FlowLeniaMetalChannelField(
                channelIndex: chemotaxis.channel_index,
                field: field.expandedDimensions(axis: 3)
            ))
        }
        if let field = obstacleFieldBatch,
           let obstacleField = esConfig.obstacleField,
           obstacleField.enabled {
            fields.append(FlowLeniaMetalChannelField(
                channelIndex: obstacleField.channelIndex,
                field: field.expandedDimensions(axis: 3)
            ))
        }
        return fields
    }

    public func buildInitialState(seed: Int) -> MLXArray {
        var localRng = SeededRandomNumberGenerator(seed: UInt64(seed))
        var data = [Float](repeating: 0.0, count: config.sx * config.sy * config.channels)

        let patches = runtimeConfig.patches.isEmpty
            ? [PatchConfig(center: [config.sx / 2, config.sy / 2], size: 40)]
            : runtimeConfig.patches
        let low = runtimeConfig.aUniform.low
        let high = runtimeConfig.aUniform.high

        for patch in patches {
            let cx = patch.center[0]
            let cy = patch.center[1]
            let half = patch.size / 2
            for x in (cx - half)..<(cx + patch.size - half) {
                for y in (cy - half)..<(cy + patch.size - half) {
                    for c in creatureChannels {
                        let idx = (x * config.sy + y) * config.channels + c
                        if idx >= 0 && idx < data.count {
                            data[idx] = Float.random(in: low...high, using: &localRng)
                        }
                    }
                }
            }
        }

        return MLXArray(data).reshaped([config.sx, config.sy, config.channels])
    }

    public func buildStateFromPatch(_ patchValues: [Float]) -> MLXArray {
        guard let initPatch = esConfig.initPatch else {
            return buildInitialState(seed: esConfig.seed)
        }

        var data = [Float](repeating: 0.0, count: config.sx * config.sy * config.channels)
        let size = initPatch.size
        let cx = initPatch.center[0]
        let cy = initPatch.center[1]
        let half = size / 2

        var patchIdx = 0
        for x in (cx - half)..<(cx + size - half) {
            for y in (cy - half)..<(cy + size - half) {
                for c in creatureChannels {
                    let idx = (x * config.sy + y) * config.channels + c
                    if idx >= 0 && idx < data.count && patchIdx < patchValues.count {
                        data[idx] = patchValues[patchIdx]
                    }
                    patchIdx += 1
                }
            }
        }

        return MLXArray(data).reshaped([config.sx, config.sy, config.channels])
    }

    private func buildStateForCandidate(_ candidate: [Float]) -> MLXArray {
        if initPatchDim == 0 {
            return buildInitialState(seed: esConfig.seed)
        }
        let patchVec = Array(candidate[thetaParamsDim...])
        let patchValues = patchVec.map { val -> Float in
            guard let initPatch = esConfig.initPatch else { return 0 }
            let sig = sigmoid(val)
            return initPatch.valueLow + sig * (initPatch.valueHigh - initPatch.valueLow)
        }
        return buildStateFromPatch(patchValues)
    }

    private func buildStateBatch(_ candidates: [[Float]]) -> MLXArray {
        MLX.stacked(candidates.map(buildStateForCandidate))
    }

    private func buildChemotaxisFieldBatch(startIndex: Int, count: Int) -> MLXArray? {
        guard let chemotaxis = runtimeConfig.chemotaxis, chemotaxis.enabled else {
            return nil
        }
        var fields: [MLXArray] = []
        fields.reserveCapacity(count)
        for offset in 0..<count {
            let dynamicSeed = (chemotaxis.seed ?? 0) + startIndex + offset
            fields.append(buildChemotaxisField(
                sx: config.sx,
                sy: config.sy,
                config: chemotaxis,
                evalSeed: dynamicSeed
            ))
        }
        return MLX.stacked(fields)
    }

    private func buildObstacleFieldBatch(startIndex: Int, count: Int) -> MLXArray? {
        guard let obstacleField = esConfig.obstacleField, obstacleField.enabled else {
            return nil
        }
        var fields: [MLXArray] = []
        fields.reserveCapacity(count)
        for offset in 0..<count {
            fields.append(buildObstacleField(
                sx: config.sx,
                sy: config.sy,
                config: obstacleField,
                evalSeed: obstacleField.seed + startIndex + offset
            ))
        }
        return MLX.stacked(fields)
    }

    private func buildConstantParameterFieldBatch(_ parameterValuesBatch: [[Float]]) -> MLXArray {
        guard let parameterCount = parameterValuesBatch.first?.count else {
            preconditionFailure("EvolutionEngine requires at least one parameter vector to build a batched field.")
        }
        guard parameterValuesBatch.allSatisfy({ $0.count == parameterCount }) else {
            preconditionFailure("EvolutionEngine batched parameter fields require a consistent kernel count per candidate.")
        }
        let flatValues = parameterValuesBatch.flatMap { $0 }
        let template = MLXArray(flatValues).reshaped([parameterValuesBatch.count, 1, 1, parameterCount])
        return MLX.broadcast(template, to: [parameterValuesBatch.count, config.sx, config.sy, parameterCount])
    }

    private struct BatchCenterOfMassDevice {
        let total: MLXArray
        let x: MLXArray
        let y: MLXArray
    }

    private struct BatchCenterOfMassCPU {
        let alive: [Float]
        let x: [Float]
        let y: [Float]
    }

    private func centerOfMassBatchDevice(_ ABatch: MLXArray) -> BatchCenterOfMassDevice {
        let signpost = LeniaSignposts.beginPhase("centerOfMassBatch")
        defer { LeniaSignposts.end(signpost) }
        let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
        return centerOfMassBatchDeviceFromMassMap(massMap)
    }

    private func centerOfMassBatchDeviceFromMassMap(_ massMap: MLXArray) -> BatchCenterOfMassDevice {
        let totalArr = massMap.sum(axes: [1, 2])
        let totalSafe = MLX.maximum(totalArr, MLXArray(Float(1e-6)))
        let comXArr = (massMap * metricGridX).sum(axes: [1, 2]) / totalSafe
        let comYArr = (massMap * metricGridY).sum(axes: [1, 2]) / totalSafe
        return BatchCenterOfMassDevice(total: totalArr, x: comXArr, y: comYArr)
    }

    private func materializeCenterOfMassBatch(_ metrics: [BatchCenterOfMassDevice]) -> [BatchCenterOfMassCPU] {
        guard !metrics.isEmpty else { return [] }
        let evalSignpost = LeniaSignposts.beginPhase("centerOfMassBatchEval")
        var arrays: [MLXArray] = []
        arrays.reserveCapacity(metrics.count * 3)
        for metric in metrics {
            arrays.append(metric.total)
            arrays.append(metric.x)
            arrays.append(metric.y)
        }
        eval(arrays)
        LeniaSignposts.end(evalSignpost)
        return metrics.map { metric in
            let totalCPU: [Float] = metric.total.asArray(Float.self)
            let rawXCPU: [Float] = metric.x.asArray(Float.self)
            let rawYCPU: [Float] = metric.y.asArray(Float.self)
            let aliveCPU = totalCPU.map { $0 > 0 ? Float(1.0) : Float(0.0) }
            let xCPU = rawXCPU.map { $0 / Float(config.sx) - 0.5 }
            let yCPU = rawYCPU.map { $0 / Float(config.sy) - 0.5 }
            return BatchCenterOfMassCPU(alive: aliveCPU, x: xCPU, y: yCPU)
        }
    }

    private func objectiveRequirements() -> (
        objective: String,
        usesCenterOfMass: Bool,
        usesMidCenter: Bool,
        targetStep: Int,
        midStep: Int
    ) {
        let objective = esConfig.fitness.objective
        let usesCenterOfMass = objective == "directed_motion" ||
            objective == "obstacle_navigation" ||
            objective == "angular_motion"
        let targetStep = esConfig.fitness.targetStep
        return (
            objective,
            usesCenterOfMass,
            objective == "angular_motion",
            targetStep,
            targetStep / 2
        )
    }

    private func deadSnapshot() -> CenterSnapshot {
        CenterSnapshot(alive: false, x: 0.0, y: 0.0)
    }

    private func centerSnapshot(from metrics: BatchCenterOfMassCPU?, index: Int) -> CenterSnapshot? {
        guard let metrics else { return nil }
        return CenterSnapshot(
            alive: metrics.alive[index] > 0.0,
            x: metrics.x[index],
            y: metrics.y[index]
        )
    }

    private func centerSnapshotForSingleBatch(_ ABatch: MLXArray) -> CenterSnapshot {
        let metrics = materializeCenterOfMassBatch([centerOfMassBatchDevice(ABatch)])[0]
        return CenterSnapshot(
            alive: metrics.alive[0] > 0.0,
            x: metrics.x[0],
            y: metrics.y[0]
        )
    }

    private func centerSnapshot(
        centerXHistory: [Float],
        centerYHistory: [Float],
        aliveHistory: [Bool],
        index: Int
    ) -> CenterSnapshot {
        let clampedIndex = min(max(index, 0), centerXHistory.count - 1)
        return CenterSnapshot(
            alive: aliveHistory[clampedIndex],
            x: centerXHistory[clampedIndex],
            y: centerYHistory[clampedIndex]
        )
    }

    private func centerSnapshot(from summary: FlowLeniaMetalMassSummary, index: Int) -> CenterSnapshot {
        let total = summary.totalMass[index]
        guard total > 0 else {
            return deadSnapshot()
        }
        return CenterSnapshot(
            alive: true,
            x: summary.centerXIndex[index] / Float(config.sx) - 0.5,
            y: summary.centerYIndex[index] / Float(config.sy) - 0.5
        )
    }

    private func evaluatePopulation(
        candidates: [[Float]],
        paramsBatch: [ResolvedParams],
        evaluationStart: Int
    ) -> PopulationEvaluation {
        switch populationEvaluator {
        case .mlx:
            return evaluatePopulationMLX(
                candidates: candidates,
                paramsBatch: paramsBatch,
                evaluationStart: evaluationStart
            )
        case .metalFull:
            return evaluatePopulationMetal(
                candidates: candidates,
                paramsBatch: paramsBatch,
                evaluationStart: evaluationStart
            )
        }
    }

    private func evaluatePopulationMLX(
        candidates: [[Float]],
        paramsBatch: [ResolvedParams],
        evaluationStart: Int
    ) -> PopulationEvaluation {
        let pop = candidates.count
        let requirements = objectiveRequirements()

        let kernelCompileStart = ContinuousClock.now
        let kernelCompileSignpost = LeniaSignposts.beginPhase("kernelCompile")
        populationSim.kernels = compilePopulationKernels(
            paramsBatch: paramsBatch,
            config: config,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        LeniaSignposts.end(kernelCompileSignpost)
        let kernelCompileMs = durationMs(kernelCompileStart.duration(to: ContinuousClock.now))

        let stateBuildStart = ContinuousClock.now
        let stateBuildSignpost = LeniaSignposts.beginPhase("stateBuild")
        var ABatch = buildStateBatch(candidates)
        LeniaSignposts.end(stateBuildSignpost)
        let stateBuildMs = durationMs(stateBuildStart.duration(to: ContinuousClock.now))

        let fieldBuildStart = ContinuousClock.now
        let fieldBuildSignpost = LeniaSignposts.beginPhase("fieldBuild")
        let chemFieldBatch = buildChemotaxisFieldBatch(startIndex: evaluationStart, count: pop)
        let obstacleFieldBatch = buildObstacleFieldBatch(startIndex: evaluationStart, count: pop)
        populationSim.wallPotential = obstacleFieldBatch.map(buildObstaclePotential)

        if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
        }
        if let field = obstacleFieldBatch, let obstacleConfig = esConfig.obstacleField {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleConfig.channelIndex)
        }
        LeniaSignposts.end(fieldBuildSignpost)
        let fieldBuildMs = durationMs(fieldBuildStart.duration(to: ContinuousClock.now))

        let rolloutStart = ContinuousClock.now
        let rolloutSignpost = LeniaSignposts.beginPhase("rollout")
        let com0Device = requirements.usesCenterOfMass ? centerOfMassBatchDevice(ABatch) : nil
        var comMidDevice: BatchCenterOfMassDevice? = nil
        var comTargetDevice: BatchCenterOfMassDevice? = nil

        for step in 1...esConfig.steps {
            if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
            }
            if let field = obstacleFieldBatch, let obstacleConfig = esConfig.obstacleField {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleConfig.channelIndex)
            }
            ABatch = populationSim.step(ABatch)

            if requirements.usesMidCenter && step == requirements.midStep {
                comMidDevice = centerOfMassBatchDevice(ABatch)
            }
            if requirements.usesCenterOfMass && step == requirements.targetStep {
                comTargetDevice = centerOfMassBatchDevice(ABatch)
            }
        }

        LeniaSignposts.end(rolloutSignpost)
        let rolloutMs = durationMs(rolloutStart.duration(to: ContinuousClock.now))

        let measurementStart = ContinuousClock.now
        let measurementSignpost = LeniaSignposts.beginPhase("measurement")
        let centerMetrics: [BatchCenterOfMassCPU]
        if requirements.usesMidCenter, let com0Device, let comMidDevice, let comTargetDevice {
            centerMetrics = materializeCenterOfMassBatch([com0Device, comMidDevice, comTargetDevice])
        } else if requirements.usesCenterOfMass, let com0Device, let comTargetDevice {
            centerMetrics = materializeCenterOfMassBatch([com0Device, comTargetDevice])
        } else {
            centerMetrics = []
        }

        let initialCenters = requirements.usesCenterOfMass ? centerMetrics[0] : nil
        let midCenters = requirements.usesMidCenter ? centerMetrics[1] : nil
        let targetCenters = requirements.usesMidCenter ? centerMetrics[2] : (requirements.usesCenterOfMass ? centerMetrics[1] : nil)

        let gyrationValues = esConfig.fitness.gyrationPenalty == nil ? nil : computeGyrationBatch(ABatch)
        let morphologyValues = morphologyMeasurements(from: ABatch)
        let chemotaxisScores: [Float]?
        if requirements.objective == "chemotaxis" {
            guard let field = chemFieldBatch else {
                chemotaxisScores = Array(repeating: 0.0, count: pop)
                LeniaSignposts.end(measurementSignpost)
                let measurementMs = durationMs(measurementStart.duration(to: ContinuousClock.now))
                let measurements = (0..<pop).map { index in
                    CandidateMeasurement(
                        initial: deadSnapshot(),
                        mid: nil,
                        target: nil,
                        gyration: nil,
                        componentCount: morphologyValues?.componentCount?[index],
                        largestComponentFraction: morphologyValues?.largestComponentFraction?[index],
                        largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?[index],
                        momentDensity: morphologyValues?.momentDensity?[index],
                        momentAnisotropy: morphologyValues?.momentAnisotropy?[index],
                        chemotaxisScore: 0.0
                    )
                }
                return PopulationEvaluation(
                    measurements: measurements,
                    kernelCompileMs: kernelCompileMs,
                    stateBuildMs: stateBuildMs,
                    fieldBuildMs: fieldBuildMs,
                    rolloutMs: rolloutMs,
                    measurementMs: measurementMs
                )
            }
            let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
            let numerator = (massMap * field).sum(axes: [1, 2])
            let denominator = massMap.sum(axes: [1, 2])
            eval(numerator, denominator)
            let numeratorCPU: [Float] = numerator.asArray(Float.self)
            let denominatorCPU: [Float] = denominator.asArray(Float.self)
            chemotaxisScores = zip(numeratorCPU, denominatorCPU).map { numerator, denominator in
                numerator / max(denominator, 1e-6)
            }
        } else {
            chemotaxisScores = nil
        }

        let measurements = (0..<pop).map { index in
            CandidateMeasurement(
                initial: centerSnapshot(from: initialCenters, index: index) ?? deadSnapshot(),
                mid: centerSnapshot(from: midCenters, index: index),
                target: centerSnapshot(from: targetCenters, index: index),
                gyration: gyrationValues?[index],
                componentCount: morphologyValues?.componentCount?[index],
                largestComponentFraction: morphologyValues?.largestComponentFraction?[index],
                largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?[index],
                momentDensity: morphologyValues?.momentDensity?[index],
                momentAnisotropy: morphologyValues?.momentAnisotropy?[index],
                chemotaxisScore: chemotaxisScores?[index]
            )
        }
        LeniaSignposts.end(measurementSignpost)
        let measurementMs = durationMs(measurementStart.duration(to: ContinuousClock.now))

        return PopulationEvaluation(
            measurements: measurements,
            kernelCompileMs: kernelCompileMs,
            stateBuildMs: stateBuildMs,
            fieldBuildMs: fieldBuildMs,
            rolloutMs: rolloutMs,
            measurementMs: measurementMs
        )
    }

    private func evaluatePopulationMetal(
        candidates: [[Float]],
        paramsBatch: [ResolvedParams],
        evaluationStart: Int
    ) -> PopulationEvaluation {
        let pop = candidates.count
        let requirements = objectiveRequirements()
        var measurements: [CandidateMeasurement] = []
        measurements.reserveCapacity(pop)
        let deadSnapshots = Array(repeating: deadSnapshot(), count: pop)
        var initialSnapshots = deadSnapshots
        var midSnapshots = [CenterSnapshot?](repeating: nil, count: pop)
        var targetSnapshots = [CenterSnapshot?](repeating: nil, count: pop)
        var kernelCompileMs = 0.0
        var stateBuildMs = 0.0
        var fieldBuildMs = 0.0
        var rolloutMs = 0.0
        var measurementMs = 0.0
        _ = evaluationStart
        let kernelCompileStart = ContinuousClock.now
        let kernels = compilePopulationKernels(
            paramsBatch: paramsBatch,
            config: config,
            c0: runtimeConfig.c0,
            c1: runtimeConfig.c1
        )
        let runner = reusableMetalFullPopulationRunner(kernels: kernels)
        kernelCompileMs = durationMs(kernelCompileStart.duration(to: ContinuousClock.now))

        let stateBuildStart = ContinuousClock.now
        var ABatch = buildStateBatch(candidates)
        let PBatch = buildConstantParameterFieldBatch(paramsBatch.map(\.h))
        stateBuildMs = durationMs(stateBuildStart.duration(to: ContinuousClock.now))

        let fieldBuildStart = ContinuousClock.now
        let chemFieldBatch = buildChemotaxisFieldBatch(startIndex: evaluationStart, count: pop)
        let obstacleFieldBatch = buildObstacleFieldBatch(startIndex: evaluationStart, count: pop)
        if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
        }
        if let field = obstacleFieldBatch, let obstacleField = esConfig.obstacleField {
            ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleField.channelIndex)
        }
        runner.setMatterWeights(metalMatterWeights())
        runner.setWallPotential(obstacleFieldBatch.map(buildObstaclePotential))
        runner.setStaticChannelFields(
            metalStaticChannelFields(
                chemFieldBatch: chemFieldBatch,
                obstacleFieldBatch: obstacleFieldBatch
            )
        )
        runner.setState(mass: ABatch, params: PBatch)
        fieldBuildMs = durationMs(fieldBuildStart.duration(to: ContinuousClock.now))

        let initialMeasurementStart = ContinuousClock.now
        if requirements.usesCenterOfMass {
            if runner.supportsMassSummary {
                let summary = runner.summarizeMass(
                    occupancyThreshold: 0.0,
                    includeGyration: false,
                    channelWeights: metalMatterWeights()
                )
                initialSnapshots = (0..<pop).map { centerSnapshot(from: summary, index: $0) }
            } else {
                let massMap = runner.materializeMassMap(channelWeights: metalMatterWeights())
                let centers = materializeCenterOfMassBatch([centerOfMassBatchDeviceFromMassMap(massMap)])[0]
                initialSnapshots = (0..<pop).map { centerSnapshot(from: centers, index: $0) ?? deadSnapshot() }
            }
        }
        measurementMs += durationMs(initialMeasurementStart.duration(to: ContinuousClock.now))

        let rolloutStart = ContinuousClock.now
        var completedSteps = 0

        func advanceRunner(to targetStep: Int) {
            let delta = targetStep - completedSteps
            if delta > 0 {
                runner.step(count: delta)
                completedSteps = targetStep
            }
        }

        if requirements.usesMidCenter {
            let midMeasurementStart = ContinuousClock.now
            advanceRunner(to: requirements.midStep)
            if runner.supportsMassSummary {
                let summary = runner.summarizeMass(
                    occupancyThreshold: 0.0,
                    includeGyration: false,
                    channelWeights: metalMatterWeights()
                )
                midSnapshots = (0..<pop).map { centerSnapshot(from: summary, index: $0) }
            } else {
                let massMap = runner.materializeMassMap(channelWeights: metalMatterWeights())
                let centers = materializeCenterOfMassBatch([centerOfMassBatchDeviceFromMassMap(massMap)])[0]
                midSnapshots = (0..<pop).map { centerSnapshot(from: centers, index: $0) ?? deadSnapshot() }
            }
            measurementMs += durationMs(midMeasurementStart.duration(to: ContinuousClock.now))
        }

        if requirements.usesCenterOfMass {
            let targetMeasurementStart = ContinuousClock.now
            advanceRunner(to: requirements.targetStep)
            if runner.supportsMassSummary {
                let summary = runner.summarizeMass(
                    occupancyThreshold: 0.0,
                    includeGyration: false,
                    channelWeights: metalMatterWeights()
                )
                targetSnapshots = (0..<pop).map { centerSnapshot(from: summary, index: $0) }
            } else {
                let massMap = runner.materializeMassMap(channelWeights: metalMatterWeights())
                let centers = materializeCenterOfMassBatch([centerOfMassBatchDeviceFromMassMap(massMap)])[0]
                targetSnapshots = (0..<pop).map { centerSnapshot(from: centers, index: $0) ?? deadSnapshot() }
            }
            measurementMs += durationMs(targetMeasurementStart.duration(to: ContinuousClock.now))
        }

        advanceRunner(to: esConfig.steps)
        rolloutMs = durationMs(rolloutStart.duration(to: ContinuousClock.now))

        let finalMeasurementStart = ContinuousClock.now
        var finalMassMapBatch: MLXArray? = nil
        let gyrationValues: [Float]?
        if runner.supportsMassSummary {
            let summary = runner.summarizeMass(
                occupancyThreshold: 0.0,
                includeGyration: esConfig.fitness.gyrationPenalty != nil,
                channelWeights: metalMatterWeights()
            )
            if let rawGyration = summary.rawGyration {
                gyrationValues = zip(summary.totalMass, rawGyration).map { totalMass, gyration in
                    totalMass > 0 ? gyration / Float(config.sx * config.sy) : 1.0
                }
            } else {
                gyrationValues = nil
            }
        } else {
            finalMassMapBatch = runner.materializeMassMap(channelWeights: metalMatterWeights())
            gyrationValues = esConfig.fitness.gyrationPenalty == nil ? nil : computeGyrationBatchFromMassMap(finalMassMapBatch!)
        }
        let morphologyValues: MorphologyMeasurementBatch?
        if esConfig.fitness.usesMorphologyMetrics {
            if finalMassMapBatch == nil {
                finalMassMapBatch = runner.materializeMassMap(channelWeights: metalMatterWeights())
            }
            morphologyValues = morphologyMeasurements(fromMassMap: finalMassMapBatch!)
        } else {
            morphologyValues = nil
        }
        let chemotaxisScores: [Float]?
        if requirements.objective == "chemotaxis" {
            if let field = chemFieldBatch {
                if finalMassMapBatch == nil {
                    finalMassMapBatch = runner.materializeMassMap(channelWeights: metalMatterWeights())
                }
                let numerator = (finalMassMapBatch! * field).sum(axes: [1, 2])
                let denominator = finalMassMapBatch!.sum(axes: [1, 2])
                eval(numerator, denominator)
                let numeratorCPU: [Float] = numerator.asArray(Float.self)
                let denominatorCPU: [Float] = denominator.asArray(Float.self)
                chemotaxisScores = zip(numeratorCPU, denominatorCPU).map { numerator, denominator in
                    numerator / max(denominator, 1e-6)
                }
            } else {
                chemotaxisScores = Array(repeating: 0.0, count: pop)
            }
        } else {
            chemotaxisScores = nil
        }
        measurementMs += durationMs(finalMeasurementStart.duration(to: ContinuousClock.now))

        for index in 0..<pop {
            measurements.append(
                CandidateMeasurement(
                    initial: initialSnapshots[index],
                    mid: midSnapshots[index],
                    target: targetSnapshots[index],
                    gyration: gyrationValues?[index],
                    componentCount: morphologyValues?.componentCount?[index],
                    largestComponentFraction: morphologyValues?.largestComponentFraction?[index],
                    largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?[index],
                    momentDensity: morphologyValues?.momentDensity?[index],
                    momentAnisotropy: morphologyValues?.momentAnisotropy?[index],
                    chemotaxisScore: chemotaxisScores?[index]
                )
            )
        }

        return PopulationEvaluation(
            measurements: measurements,
            kernelCompileMs: kernelCompileMs,
            stateBuildMs: stateBuildMs,
            fieldBuildMs: fieldBuildMs,
            rolloutMs: rolloutMs,
            measurementMs: measurementMs
        )
    }

    private func fitnessValue(from measurement: CandidateMeasurement) -> Float {
        switch esConfig.fitness.objective {
        case "directed_motion", "obstacle_navigation":
            guard measurement.initial.alive, let target = measurement.target, target.alive else {
                return 0.0
            }
            let dx = target.x - measurement.initial.x
            let dy = target.y - measurement.initial.y
            let displacement = sqrt(dx * dx + dy * dy)
            return adjustedFitness(base: displacement, measurement: measurement)
        case "angular_motion":
            guard measurement.initial.alive,
                  let mid = measurement.mid, mid.alive,
                  let target = measurement.target, target.alive else {
                return 0.0
            }
            let v1 = (mid.x - measurement.initial.x, mid.y - measurement.initial.y)
            let v2 = (target.x - mid.x, target.y - mid.y)
            let d1 = sqrt(v1.0 * v1.0 + v1.1 * v1.1)
            let d2 = sqrt(v2.0 * v2.0 + v2.1 * v2.1)
            guard d1 >= esConfig.fitness.angleThreshold, d2 >= esConfig.fitness.angleThreshold else {
                return adjustedFitness(base: d1 + d2, measurement: measurement)
            }
            let dot = v1.0 * v2.0 + v1.1 * v2.1
            var cosAngle = dot / (d1 * d2)
            cosAngle = max(-1.0, min(1.0, cosAngle))
            return adjustedFitness(base: d1 + d2 + acos(cosAngle), measurement: measurement)
        case "chemotaxis":
            return adjustedFitness(base: measurement.chemotaxisScore ?? 0.0, measurement: measurement)
        default:
            return 0.0
        }
    }

    private func adjustedFitness(base: Float, measurement: CandidateMeasurement) -> Float {
        var value = base
        if let penalty = esConfig.fitness.gyrationPenalty {
            guard let gyration = measurement.gyration else {
                fatalError("gyration_penalty requested but gyration was not computed.")
            }
            value -= penalty * gyration
        }
        if let penalty = esConfig.fitness.componentCountPenalty {
            guard let componentCount = measurement.componentCount else {
                fatalError("component_count_penalty requested but component metrics were not computed.")
            }
            value -= penalty * max(componentCount - 1.0, 0.0)
        }
        if let reward = esConfig.fitness.largestComponentFractionReward {
            guard let largestComponentFraction = measurement.largestComponentFraction else {
                fatalError("largest_component_fraction_reward requested but component metrics were not computed.")
            }
            value += reward * largestComponentFraction
        }
        if let penalty = esConfig.fitness.largestComponentAnisotropyPenalty {
            guard let largestComponentAnisotropy = measurement.largestComponentAnisotropy else {
                fatalError("largest_component_anisotropy_penalty requested but component metrics were not computed.")
            }
            value -= penalty * largestComponentAnisotropy
        }
        if let reward = esConfig.fitness.momentDensityReward {
            guard let momentDensity = measurement.momentDensity else {
                fatalError("moment_density_reward requested but moment metrics were not computed.")
            }
            value += reward * momentDensity
        }
        if let penalty = esConfig.fitness.momentAnisotropyPenalty {
            guard let momentAnisotropy = measurement.momentAnisotropy else {
                fatalError("moment_anisotropy_penalty requested but moment metrics were not computed.")
            }
            value -= penalty * momentAnisotropy
        }
        return value
    }

    private func fitnessValues(from measurements: [CandidateMeasurement]) -> [Float] {
        measurements.map(fitnessValue(from:))
    }

    private func morphologyMeasurements(from stateBatch: MLXArray) -> MorphologyMeasurementBatch? {
        guard esConfig.fitness.usesMorphologyMetrics else {
            return nil
        }
        let massMap = evolutionMassMapBatch(stateBatch, excludedChannels: excludedMassChannels)
        return morphologyMeasurements(fromMassMap: massMap)
    }

    private func morphologyMeasurements(fromMassMap massMap: MLXArray) -> MorphologyMeasurementBatch? {
        guard esConfig.fitness.usesMorphologyMetrics else {
            return nil
        }
        let materialized = materializeMassBatch(massMap)
        let threshold = esConfig.fitness.morphologyThreshold ?? 0.03
        let componentMetricsNeeded = esConfig.fitness.componentCountPenalty != nil ||
            esConfig.fitness.largestComponentFractionReward != nil ||
            esConfig.fitness.largestComponentAnisotropyPenalty != nil
        let componentMetrics = componentMetricsNeeded
            ? computeComponentMetricsBatch(
                materialized: materialized,
                threshold: threshold,
                useTorus: runtimeConfig.border == "torus"
            )
            : nil
        let momentMetricsNeeded = esConfig.fitness.momentDensityReward != nil ||
            esConfig.fitness.momentAnisotropyPenalty != nil
        let momentMetrics = !momentMetricsNeeded
            ? nil
            : computeMomentsBatch(
                materialized: materialized,
                config: MomentsConfig(enabled: true, threshold: threshold)
            )
        return MorphologyMeasurementBatch(
            componentCount: componentMetrics?.count,
            largestComponentFraction: componentMetrics?.largestFraction,
            largestComponentAnisotropy: componentMetrics?.largestAnisotropy,
            momentDensity: momentMetrics?.density,
            momentAnisotropy: momentMetrics?.anisotropy
        )
    }

    private func computeGyrationBatchFromMassMap(_ massMap: MLXArray) -> [Float] {
        let signpost = LeniaSignposts.beginPhase("computeGyrationBatch")
        defer { LeniaSignposts.end(signpost) }
        let totalArr = massMap.sum(axes: [1, 2])
        let totalSafe = MLX.maximum(totalArr, MLXArray(Float(1e-6)))
        let comXArr = (massMap * metricGridX).sum(axes: [1, 2]) / totalSafe
        let comYArr = (massMap * metricGridY).sum(axes: [1, 2]) / totalSafe
        let comXGrid = comXArr.expandedDimensions(axes: [1, 2])
        let comYGrid = comYArr.expandedDimensions(axes: [1, 2])
        let distSq = (metricGridX - comXGrid) * (metricGridX - comXGrid) +
            (metricGridY - comYGrid) * (metricGridY - comYGrid)
        let scale = MLXArray(Float(config.sx * config.sy))
        let gyrationArr = (massMap * distSq).sum(axes: [1, 2]) / totalSafe / scale
        let evalSignpost = LeniaSignposts.beginPhase("computeGyrationBatchEval")
        eval(totalArr, gyrationArr)
        LeniaSignposts.end(evalSignpost)
        let totalCPU: [Float] = totalArr.asArray(Float.self)
        let gyrationCPU: [Float] = gyrationArr.asArray(Float.self)
        return zip(totalCPU, gyrationCPU).map { total, gyration in
            total > 0 ? gyration : 1.0
        }
    }

    private func computeGyrationBatch(_ ABatch: MLXArray) -> [Float] {
        let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
        return computeGyrationBatchFromMassMap(massMap)
    }

    private static func validateMetalBackendCompatibility(
        runtimeConfig: LeniaRuntimeConfig,
        esConfig: ESConfig
    ) {
        let validBoundaryPair = (runtimeConfig.border == "torus" && runtimeConfig.implementation.gradientBoundary == "periodic") ||
            (runtimeConfig.border == "wall" && runtimeConfig.implementation.gradientBoundary == "zero_pad")
        guard validBoundaryPair else {
            fatalError("EvolutionEngine Metal backends require torus/periodic or wall/zero_pad boundaries.")
        }
        if let food = runtimeConfig.food, food.enabled {
            fatalError("EvolutionEngine Metal backends do not support food fields yet.")
        }
        let supportedObjectives: Set<String> = ["directed_motion", "angular_motion", "obstacle_navigation", "chemotaxis"]
        if !supportedObjectives.contains(esConfig.fitness.objective) {
            fatalError("EvolutionEngine Metal backends do not support objective \(esConfig.fitness.objective).")
        }
    }

    public func runGeneration(gen: Int) -> ESGenerationResult {
        let generationStart = ContinuousClock.now
        let generationSignpost = LeniaSignposts.beginPhase("runGeneration", generation: gen)
        defer { LeniaSignposts.end(generationSignpost) }
        let totalDim = theta.count
        let pop = esConfig.population

        let candidateSetupStart = generationStart
        let candidateSetupSignpost = LeniaSignposts.beginPhase("candidateSetup")
        let noise = sampleOpenESNoise(
            population: pop,
            dimensions: totalDim,
            rng: &rng
        )

        let evalStart = evaluationCounter
        evaluationCounter += pop

        var candidates: [[Float]] = []
        candidates.reserveCapacity(pop)
        var paramsBatch: [ResolvedParams] = []
        paramsBatch.reserveCapacity(pop)
        for i in 0..<pop {
            var candidate: [Float] = []
            for j in 0..<totalDim {
                candidate.append(theta[j] + esConfig.sigma * noise[i][j])
            }
            candidates.append(candidate)
            let paramsVec = Array(candidate[0..<thetaParamsDim])
            paramsBatch.append(vectorToParams(paramsVec, space: paramSpace))
        }
        LeniaSignposts.end(candidateSetupSignpost)
        let candidateSetupMs = durationMs(candidateSetupStart.duration(to: ContinuousClock.now))

        let evaluation = evaluatePopulation(
            candidates: candidates,
            paramsBatch: paramsBatch,
            evaluationStart: evalStart
        )

        let fitnessStart = ContinuousClock.now
        let fitnessSignpost = LeniaSignposts.beginPhase("fitness")
        let fitnessValues = fitnessValues(from: evaluation.measurements)

        let safeFitnessValues = fitnessValues.map { fitness in
            fitness.isFinite ? fitness : -1e9
        }
        LeniaSignposts.end(fitnessSignpost)
        let fitnessMs = evaluation.measurementMs + durationMs(fitnessStart.duration(to: ContinuousClock.now))

        let optimizerStart = ContinuousClock.now
        let optimizerSignpost = LeniaSignposts.beginPhase("optimizer")
        let shaped = fitnessShaping(safeFitnessValues, mode: esConfig.fitnessShaping)

        // Compute gradient estimate: grad = (noise.T @ shaped) / (pop * sigma)
        var grad = [Float](repeating: 0.0, count: totalDim)
        for j in 0..<totalDim {
            var sum: Float = 0.0
            for i in 0..<pop {
                sum += noise[i][j] * shaped[i]
            }
            grad[j] = sum / (Float(pop) * esConfig.sigma)
        }

        // Update theta
        theta = optimizer.step(params: theta, grad: grad)

        let bestIndex = safeFitnessValues.enumerated().max(by: { $0.element < $1.element })?.offset ?? 0
        let bestFitness = safeFitnessValues[bestIndex]
        let meanFitness = safeFitnessValues.reduce(0, +) / Float(pop)
        let variance = safeFitnessValues.reduce(Float(0.0)) { partial, value in
            let diff = value - meanFitness
            return partial + diff * diff
        } / Float(pop)
        let fitnessStd = sqrt(max(variance, 0.0))
        LeniaSignposts.end(optimizerSignpost)
        let optimizerMs = durationMs(optimizerStart.duration(to: ContinuousClock.now))
        let totalMs = durationMs(generationStart.duration(to: ContinuousClock.now))

        return ESGenerationResult(
            bestFitness: bestFitness,
            meanFitness: meanFitness,
            fitnessStd: fitnessStd,
            bestCandidate: candidates[bestIndex],
            profile: ESGenerationProfile(
                candidateSetupMs: candidateSetupMs,
                kernelCompileMs: evaluation.kernelCompileMs,
                stateBuildMs: evaluation.stateBuildMs,
                fieldBuildMs: evaluation.fieldBuildMs,
                rolloutMs: evaluation.rolloutMs,
                fitnessMs: fitnessMs,
                optimizerMs: optimizerMs,
                totalMs: totalMs
            )
        )
    }

    public func getBestParams() -> ResolvedParams {
        let paramsVec = Array(theta[0..<thetaParamsDim])
        return vectorToParams(paramsVec, space: paramSpace)
    }

    public func evaluateCandidateForResearchExport(
        _ candidate: [Float],
        evaluationIndex: Int = 0
    ) -> ESEvaluatedCreatureExport {
        let paramsVec = Array(candidate[0..<thetaParamsDim])
        let params = vectorToParams(paramsVec, space: paramSpace)
        let patchValues = resolvedInitPatchValues(candidate)
        let initConfig = resolvedResearchInitConfig(patchValues: patchValues)

        let sim = FlowLeniaBatched(
            config: config,
            kernels: compilePopulationKernels(
                paramsBatch: [params],
                config: config,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        )

        var ABatch = MLX.stacked([
            patchValues.map(buildStateFromPatch) ?? buildInitialState(seed: esConfig.seed)
        ])
        let chemFieldBatch = buildChemotaxisFieldBatch(startIndex: evaluationIndex, count: 1)
        let obstacleFieldBatch = buildObstacleFieldBatch(startIndex: evaluationIndex, count: 1)
        sim.wallPotential = obstacleFieldBatch.map(buildObstaclePotential)

        var massHistory: [Float] = []
        var occupancyHistory: [Float] = []
        var varianceHistory: [Float] = []
        var energyHistory: [Float] = []
        var centerXHistory: [Float] = []
        var centerYHistory: [Float] = []
        var aliveHistory: [Bool] = []

        func applyFields() {
            if let field = chemFieldBatch, let chemotaxis = runtimeConfig.chemotaxis {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: chemotaxis.channel_index)
            }
            if let field = obstacleFieldBatch, let obstacleConfig = esConfig.obstacleField {
                ABatch = applyExternalFieldBatch(ABatch, field: field, channelIndex: obstacleConfig.channelIndex)
            }
        }

        func record() {
            let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
            let total = massMap.sum(axes: [1, 2])
            let occupancy = MLX.greater(massMap, MLXArray(Float(1e-3))).asType(.float32).mean(axes: [1, 2])
            let meanMass = massMap.mean(axes: [1, 2])
            let centered = massMap - meanMass.expandedDimensions(axes: [1, 2])
            let variance = (centered * centered).mean(axes: [1, 2])
            let energy = (massMap * massMap).mean(axes: [1, 2])
            let com = centerOfMassBatchDevice(ABatch)
            eval(total, occupancy, variance, energy, com.total, com.x, com.y)

            let totalCPU = total.asArray(Float.self)[0]
            let occupancyCPU = occupancy.asArray(Float.self)[0]
            let varianceCPU = variance.asArray(Float.self)[0]
            let energyCPU = energy.asArray(Float.self)[0]
            let alive = com.total.asArray(Float.self)[0] > 0
            let centerX = com.x.asArray(Float.self)[0] / Float(config.sx) - 0.5
            let centerY = com.y.asArray(Float.self)[0] / Float(config.sy) - 0.5

            massHistory.append(totalCPU)
            occupancyHistory.append(occupancyCPU)
            varianceHistory.append(varianceCPU)
            energyHistory.append(energyCPU)
            centerXHistory.append(centerX)
            centerYHistory.append(centerY)
            aliveHistory.append(alive)
        }

        applyFields()
        record()
        for _ in 1...esConfig.steps {
            applyFields()
            ABatch = sim.step(ABatch)
            record()
        }

        let speeds = evolutionSpeeds(
            centerXHistory: centerXHistory,
            centerYHistory: centerYHistory,
            aliveHistory: aliveHistory
        )
        let velocityX = speeds.last?.dx ?? 0
        let velocityY = speeds.last?.dy ?? 0
        let lastSpeed = speeds.last?.speed ?? 0
        let heading = lastSpeed > 0 ? atan2(velocityY, velocityX) : 0
        let pathLength = speeds.reduce(Float(0)) { $0 + $1.speed }
        let displacement = evolutionDisplacement(
            centerXHistory: centerXHistory,
            centerYHistory: centerYHistory,
            aliveHistory: aliveHistory
        )
        let speedValues = speeds.map(\.speed)
        let massMean = evolutionMean(massHistory)
        let massStd = evolutionStd(massHistory, mean: massMean)
        let metrics = SimulationMetrics(
            massMean: massMean,
            massStd: massStd,
            massMin: massHistory.min() ?? 0,
            massMax: massHistory.max() ?? 0,
            occupancyMean: evolutionMean(occupancyHistory),
            varianceMean: evolutionMean(varianceHistory),
            energyMean: evolutionMean(energyHistory),
            speedMean: evolutionMean(speedValues),
            pathLength: pathLength,
            displacement: displacement,
            sampleCount: massHistory.count,
            speedCount: speedValues.count,
            gyration: computeGyrationBatch(ABatch)[0],
            centerVelocity: lastSpeed,
            velocityX: velocityX,
            velocityY: velocityY,
            headingRad: heading,
            isStable: evolutionIsStable(
                massMean: massMean,
                massStd: massStd,
                finalMass: massHistory.last ?? 0
            )
        )

        let requirements = objectiveRequirements()
        let chemotaxisScore: Float?
        if esConfig.fitness.objective == "chemotaxis", let field = chemFieldBatch {
            let massMap = evolutionMassMapBatch(ABatch, excludedChannels: excludedMassChannels)
            let numerator = (massMap * field).sum(axes: [1, 2])
            let denominator = massMap.sum(axes: [1, 2])
            eval(numerator, denominator)
            chemotaxisScore = numerator.asArray(Float.self)[0] / max(denominator.asArray(Float.self)[0], 1e-6)
        } else {
            chemotaxisScore = nil
        }
        let morphologyValues = morphologyMeasurements(from: ABatch)
        let fitness = fitnessValue(
            from: CandidateMeasurement(
                initial: centerSnapshot(
                    centerXHistory: centerXHistory,
                    centerYHistory: centerYHistory,
                    aliveHistory: aliveHistory,
                    index: 0
                ),
                mid: requirements.usesMidCenter
                    ? centerSnapshot(
                        centerXHistory: centerXHistory,
                        centerYHistory: centerYHistory,
                        aliveHistory: aliveHistory,
                        index: requirements.midStep
                    )
                    : nil,
                target: requirements.usesCenterOfMass
                    ? centerSnapshot(
                        centerXHistory: centerXHistory,
                        centerYHistory: centerYHistory,
                        aliveHistory: aliveHistory,
                        index: requirements.targetStep
                    )
                    : nil,
                gyration: metrics.gyration,
                componentCount: morphologyValues?.componentCount?.first,
                largestComponentFraction: morphologyValues?.largestComponentFraction?.first,
                largestComponentAnisotropy: morphologyValues?.largestComponentAnisotropy?.first,
                momentDensity: morphologyValues?.momentDensity?.first,
                momentAnisotropy: morphologyValues?.momentAnisotropy?.first,
                chemotaxisScore: chemotaxisScore
            )
        )
        let resultData = materializeReplayResultData(
            seed: evaluationIndex,
            initSeed: initConfig.seed,
            backend: runtimeConfig.backend.rawValue,
            implementation: runtimeConfig.implementation,
            initialConditionFamily: morphospaceInitialConditionFamily(initConfig),
            descriptorBundle: nil,
            score: fitness,
            scoreWeights: ["fitness": 1.0],
            filtersPassed: fitness.isFinite,
            filters: [:],
            metrics: metrics,
            params: params.toKernelParams()
        )

        return ESEvaluatedCreatureExport(
            initConfig: initConfig,
            initPatchValues: patchValues,
            fitness: fitness,
            resultData: resultData
        )
    }

    private func resolvedInitPatchValues(_ candidate: [Float]) -> [Float]? {
        guard initPatchDim > 0 else { return nil }
        let patchVec = Array(candidate[thetaParamsDim...])
        return patchVec.map { val -> Float in
            guard let initPatch = esConfig.initPatch else { return 0 }
            let sig = sigmoid(val)
            return initPatch.valueLow + sig * (initPatch.valueHigh - initPatch.valueLow)
        }
    }

    private func resolvedResearchInitConfig(patchValues: [Float]?) -> InitConfig {
        if let initPatch = esConfig.initPatch, initPatch.enabled {
            return InitConfig(
                seed: esConfig.seed,
                patches: [PatchConfig(center: initPatch.center, size: initPatch.size)],
                a_uniform: UniformRange(low: initPatch.valueLow, high: initPatch.valueHigh),
                p_uniform: nil
            )
        }
        let patches = runtimeConfig.patches.isEmpty
            ? [PatchConfig(center: [config.sx / 2, config.sy / 2], size: 40)]
            : runtimeConfig.patches
        return InitConfig(
            seed: esConfig.seed,
            patches: patches,
            a_uniform: runtimeConfig.aUniform,
            p_uniform: runtimeConfig.pUniform
        )
    }

}

public struct ESEvaluatedCreatureExport: Sendable {
    public let initConfig: InitConfig
    public let initPatchValues: [Float]?
    public let fitness: Float
    public let resultData: SimulationResultData
}

private func evolutionMean(_ values: [Float]) -> Float {
    guard !values.isEmpty else { return 0 }
    return values.reduce(0, +) / Float(values.count)
}

private func evolutionStd(_ values: [Float], mean: Float) -> Float {
    guard !values.isEmpty else { return 0 }
    let variance = values.reduce(Float(0)) { partial, value in
        let diff = value - mean
        return partial + diff * diff
    } / Float(values.count)
    return sqrt(max(variance, 0))
}

private func evolutionDisplacement(
    centerXHistory: [Float],
    centerYHistory: [Float],
    aliveHistory: [Bool]
) -> Float {
    guard let firstIndex = aliveHistory.firstIndex(of: true),
          let lastIndex = aliveHistory.lastIndex(of: true) else {
        return 0
    }
    let dx = centerXHistory[lastIndex] - centerXHistory[firstIndex]
    let dy = centerYHistory[lastIndex] - centerYHistory[firstIndex]
    return sqrt(dx * dx + dy * dy)
}

private func evolutionSpeeds(
    centerXHistory: [Float],
    centerYHistory: [Float],
    aliveHistory: [Bool]
) -> [(dx: Float, dy: Float, speed: Float)] {
    guard centerXHistory.count == centerYHistory.count, centerXHistory.count == aliveHistory.count else {
        return []
    }
    guard centerXHistory.count > 1 else { return [] }
    return (1..<centerXHistory.count).compactMap { index in
        guard aliveHistory[index - 1], aliveHistory[index] else { return nil }
        let dx = centerXHistory[index] - centerXHistory[index - 1]
        let dy = centerYHistory[index] - centerYHistory[index - 1]
        return (dx, dy, sqrt(dx * dx + dy * dy))
    }
}

private func evolutionIsStable(massMean: Float, massStd: Float, finalMass: Float) -> Bool {
    finalMass > 0 && massMean > 0 && massStd <= max(0.1 * massMean, 1e-6)
}

// Load ES config from file

public func loadESConfig(path: String) throws -> ESConfig {
    let url = URL(fileURLWithPath: path)
    let data = try Data(contentsOf: url)
    return try JSONDecoder().decode(ESConfig.self, from: data)
}

// Extract param ranges from base config

public func extractRangesFromConfig(_ config: LeniaBaseConfig) throws -> [String: (Float, Float)] {
    guard config.params.mode == "random",
          let ranges = config.params.ranges else {
        throw NSError(domain: "Evolution", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "params.mode must be 'random' with ranges"])
    }

    return [
        "r": (ranges.r[0], ranges.r[1]),
        "b": (ranges.b[0], ranges.b[1]),
        "w": (ranges.w[0], ranges.w[1]),
        "a": (ranges.a[0], ranges.a[1]),
        "m": (ranges.m[0], ranges.m[1]),
        "s": (ranges.s[0], ranges.s[1]),
        "h": (ranges.h[0], ranges.h[1]),
        "R": (ranges.R[0], ranges.R[1])
    ]
}

// History entry for logging

public struct ESGenerationResult {
    public let bestFitness: Float
    public let meanFitness: Float
    public let fitnessStd: Float
    public let bestCandidate: [Float]
    public let profile: ESGenerationProfile

    public init(
        bestFitness: Float,
        meanFitness: Float,
        fitnessStd: Float,
        bestCandidate: [Float],
        profile: ESGenerationProfile
    ) {
        self.bestFitness = bestFitness
        self.meanFitness = meanFitness
        self.fitnessStd = fitnessStd
        self.bestCandidate = bestCandidate
        self.profile = profile
    }
}

public struct ESGenerationProfile: Sendable {
    public let candidateSetupMs: Double
    public let kernelCompileMs: Double
    public let stateBuildMs: Double
    public let fieldBuildMs: Double
    public let rolloutMs: Double
    public let fitnessMs: Double
    public let optimizerMs: Double
    public let totalMs: Double

    public init(
        candidateSetupMs: Double,
        kernelCompileMs: Double,
        stateBuildMs: Double,
        fieldBuildMs: Double,
        rolloutMs: Double,
        fitnessMs: Double,
        optimizerMs: Double,
        totalMs: Double
    ) {
        self.candidateSetupMs = candidateSetupMs
        self.kernelCompileMs = kernelCompileMs
        self.stateBuildMs = stateBuildMs
        self.fieldBuildMs = fieldBuildMs
        self.rolloutMs = rolloutMs
        self.fitnessMs = fitnessMs
        self.optimizerMs = optimizerMs
        self.totalMs = totalMs
    }
}

public struct ESHistoryEntry: Codable {
    public let generation: Int
    public let fitnessMean: Float
    public let fitnessStd: Float
    public let fitnessBest: Float
    public let fitnessShaping: String
    public let generationWallMs: Double?
    public let candidateEvalPerSecond: Double?
    public let simStepsPerSecond: Double?
    public let candidateSetupMs: Double?
    public let kernelCompileMs: Double?
    public let stateBuildMs: Double?
    public let fieldBuildMs: Double?
    public let rolloutMs: Double?
    public let fitnessMs: Double?
    public let optimizerMs: Double?

    enum CodingKeys: String, CodingKey {
        case generation
        case fitnessMean = "fitness_mean"
        case fitnessStd = "fitness_std"
        case fitnessBest = "fitness_best"
        case fitnessShaping = "fitness_shaping"
        case generationWallMs = "generation_wall_ms"
        case candidateEvalPerSecond = "candidate_eval_per_second"
        case simStepsPerSecond = "sim_steps_per_second"
        case candidateSetupMs = "candidate_setup_ms"
        case kernelCompileMs = "kernel_compile_ms"
        case stateBuildMs = "state_build_ms"
        case fieldBuildMs = "field_build_ms"
        case rolloutMs = "rollout_ms"
        case fitnessMs = "fitness_ms"
        case optimizerMs = "optimizer_ms"
    }

    public init(
        generation: Int,
        fitnessMean: Float,
        fitnessStd: Float,
        fitnessBest: Float,
        fitnessShaping: String,
        generationWallMs: Double? = nil,
        candidateEvalPerSecond: Double? = nil,
        simStepsPerSecond: Double? = nil,
        candidateSetupMs: Double? = nil,
        kernelCompileMs: Double? = nil,
        stateBuildMs: Double? = nil,
        fieldBuildMs: Double? = nil,
        rolloutMs: Double? = nil,
        fitnessMs: Double? = nil,
        optimizerMs: Double? = nil
    ) {
        self.generation = generation
        self.fitnessMean = fitnessMean
        self.fitnessStd = fitnessStd
        self.fitnessBest = fitnessBest
        self.fitnessShaping = fitnessShaping
        self.generationWallMs = generationWallMs
        self.candidateEvalPerSecond = candidateEvalPerSecond
        self.simStepsPerSecond = simStepsPerSecond
        self.candidateSetupMs = candidateSetupMs
        self.kernelCompileMs = kernelCompileMs
        self.stateBuildMs = stateBuildMs
        self.fieldBuildMs = fieldBuildMs
        self.rolloutMs = rolloutMs
        self.fitnessMs = fitnessMs
        self.optimizerMs = optimizerMs
    }
}

public struct ESBestResult: Codable {
    public let generation: Int
    public let fitness: Float
    public let params: KernelParams

    public init(generation: Int, fitness: Float, params: KernelParams) {
        self.generation = generation
        self.fitness = fitness
        self.params = params
    }
}

extension EvolutionEngine {
    func benchmarkRolloutStageTimings() -> FlowSandboxMetalStageTimings? {
        guard runtimeConfig.backend == .metalFull else {
            return nil
        }

        let totalDim = theta.count
        let pop = esConfig.population
        var localRng = rng
        let noise = sampleOpenESNoise(
            population: pop,
            dimensions: totalDim,
            rng: &localRng
        )

        var candidates: [[Float]] = []
        candidates.reserveCapacity(pop)
        var paramsBatch: [ResolvedParams] = []
        paramsBatch.reserveCapacity(pop)
        for i in 0..<pop {
            var candidate: [Float] = []
            for j in 0..<totalDim {
                candidate.append(theta[j] + esConfig.sigma * noise[i][j])
            }
            candidates.append(candidate)
            let paramsVec = Array(candidate[0..<thetaParamsDim])
            paramsBatch.append(vectorToParams(paramsVec, space: paramSpace))
        }

        let runner = reusableMetalFullPopulationRunner(
            kernels: compilePopulationKernels(
                paramsBatch: paramsBatch,
                config: config,
                c0: runtimeConfig.c0,
                c1: runtimeConfig.c1
            )
        )
        runner.setState(
            mass: buildStateBatch(candidates),
            params: buildConstantParameterFieldBatch(paramsBatch.map(\.h))
        )

        let preProfileSteps = min(max(esConfig.steps / 4, 0), max(esConfig.steps - 1, 0))
        if preProfileSteps > 0 {
            runner.step(count: preProfileSteps)
        }
        return runner.profileCurrentStep()
    }
}

public struct EvolutionBenchmarkResult: Sendable {
    public let backend: FlowLeniaComputeBackend
    public let gridSize: Int
    public let steps: Int
    public let population: Int
    public let duration: TimeInterval
    public let candidatesPerSecond: Double
    public let simStepsPerSecond: Double
    public let profile: ESGenerationProfile
    public let stageTimings: FlowSandboxMetalStageTimings?

    public init(
        backend: FlowLeniaComputeBackend,
        gridSize: Int,
        steps: Int,
        population: Int,
        duration: TimeInterval,
        candidatesPerSecond: Double,
        simStepsPerSecond: Double,
        profile: ESGenerationProfile,
        stageTimings: FlowSandboxMetalStageTimings? = nil
    ) {
        self.backend = backend
        self.gridSize = gridSize
        self.steps = steps
        self.population = population
        self.duration = duration
        self.candidatesPerSecond = candidatesPerSecond
        self.simStepsPerSecond = simStepsPerSecond
        self.profile = profile
        self.stageTimings = stageTimings
    }
}

public func benchmarkEvolutionEngineBackend(
    gridSize: Int,
    population: Int,
    steps: Int,
    params: ResolvedParams,
    backend: FlowLeniaComputeBackend,
    warmupRuns: Int = 1
) -> EvolutionBenchmarkResult {
    guard population > 0, population % 2 == 0 else {
        preconditionFailure("Evolution benchmark requires an even, positive population.")
    }

    let runtimeConfig = flowLeniaBenchmarkRuntimeConfig(
        gridSize: gridSize,
        steps: steps,
        params: params,
        backend: backend
    )
    let esConfig = ESConfig(
        outputDir: "/tmp/lenia-evolution-benchmark",
        generations: 1,
        population: population,
        sigma: 0.05,
        learningRate: 0.03,
        seed: 17,
        steps: steps,
        fitness: FitnessConfig(
            objective: "directed_motion",
            targetStep: max(1, steps),
            angleThreshold: 1.0,
            gyrationPenalty: 0.01
        ),
        fitnessShaping: "centered_rank",
        initPatch: nil,
        initialInitPatchValues: nil,
        paramRanges: nil,
        obstacleField: nil
    )
    let engine = EvolutionEngine(
        runtimeConfig: runtimeConfig,
        esConfig: esConfig,
        ranges: flowLeniaBenchmarkEvolutionRanges()
    )
    for generation in 0..<max(warmupRuns, 0) {
        _ = engine.runGeneration(gen: generation)
    }

    let measuredGeneration = max(warmupRuns, 0)
    let stageTimings = backend == .metalFull ? engine.benchmarkRolloutStageTimings() : nil
    let start = Date()
    let result = engine.runGeneration(gen: measuredGeneration)
    let duration = Date().timeIntervalSince(start)
    return EvolutionBenchmarkResult(
        backend: backend,
        gridSize: gridSize,
        steps: steps,
        population: population,
        duration: duration,
        candidatesPerSecond: Double(population) / duration,
        simStepsPerSecond: Double(population * steps) / duration,
        profile: result.profile,
        stageTimings: stageTimings
    )
}
