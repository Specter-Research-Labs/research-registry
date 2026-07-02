import Foundation
import MLX

public struct IMGEPConfig: Codable, Sendable {
    public let iterations: Int
    public let warmupIterations: Int
    public let batchSize: Int
    public let seedsPerCandidate: Int
    public let goal: IMGEPGoalConfig
    public let mutation: IMGEPMutationConfig
    public let experiment: IMGEPExperimentConfig?

    public init(
        iterations: Int,
        warmupIterations: Int,
        batchSize: Int,
        seedsPerCandidate: Int,
        goal: IMGEPGoalConfig,
        mutation: IMGEPMutationConfig,
        experiment: IMGEPExperimentConfig? = nil
    ) {
        self.iterations = iterations
        self.warmupIterations = warmupIterations
        self.batchSize = batchSize
        self.seedsPerCandidate = seedsPerCandidate
        self.goal = goal
        self.mutation = mutation
        self.experiment = experiment
    }
}

public struct IMGEPGoalConfig: Codable, Sendable {
    public let features: [String]
    public let boundsMode: String
    public let bounds: [String: [Float]]?

    public init(features: [String], boundsMode: String, bounds: [String: [Float]]?) {
        self.features = features
        self.boundsMode = boundsMode
        self.bounds = bounds
    }
}

public struct IMGEPMutationConfig: Codable, Sendable {
    public let std: Float
    public let clip: Bool

    public init(std: Float, clip: Bool) {
        self.std = std
        self.clip = clip
    }
}

public struct IMGEPHistoryEntry: Codable, Sendable {
    public let id: UUID
    public let seed: Int
    public let params: KernelParams
    public let metrics: SimulationMetrics
    public let embedding: [Float]
    public let goal: [Float]?
    public let score: Float?

    public init(
        id: UUID = UUID(),
        seed: Int,
        params: KernelParams,
        metrics: SimulationMetrics,
        embedding: [Float],
        goal: [Float]?,
        score: Float?
    ) {
        self.id = id
        self.seed = seed
        self.params = params
        self.metrics = metrics
        self.embedding = embedding
        self.goal = goal
        self.score = score
    }
}

public func goalVector(from metrics: SimulationMetrics, features: [String]) -> [Float] {
    return features.map { feature in
        guard let value = featureValue(metrics: metrics, feature: feature) else {
            fatalError("Goal feature '\(feature)' is not available in metrics.")
        }
        return value
    }
}

public func goalVector(from result: SimulationResultData, features: [String]) -> [Float] {
    return features.map { feature in
        guard let value = featureValue(result: result, feature: feature) else {
            fatalError("Goal feature '\(feature)' is not available in result payload.")
        }
        return value
    }
}

public func sampleGoal(
    bounds: [(min: Float, max: Float)],
    rng: inout SeededRandomNumberGenerator
) -> [Float] {
    return bounds.map { range in
        Float.random(in: range.min...range.max, using: &rng)
    }
}

public func boundsFromHistory(history: [IMGEPHistoryEntry]) -> [(min: Float, max: Float)] {
    guard let first = history.first else {
        return []
    }
    let dims = first.embedding.count
    var mins = Array(repeating: Float.greatestFiniteMagnitude, count: dims)
    var maxs = Array(repeating: -Float.greatestFiniteMagnitude, count: dims)
    for entry in history {
        for i in 0..<dims {
            let value = entry.embedding[i]
            mins[i] = min(mins[i], value)
            maxs[i] = max(maxs[i], value)
        }
    }
    return zip(mins, maxs).map { (min: $0.0, max: $0.1) }
}

public func nearestNeighborIndex(goal: [Float], history: [IMGEPHistoryEntry]) -> Int {
    guard !history.isEmpty else { return 0 }
    let dims = goal.count
    let flat = history.flatMap { $0.embedding }
    let emb = MLXArray(flat).reshaped([history.count, dims])
    let goalArr = MLXArray(goal).reshaped([1, dims])
    let diff = emb - goalArr
    let dist = (diff * diff).sum(axis: 1)
    let distCPU: [Float] = dist.asArray(Float.self)
    var bestIdx = 0
    var bestVal = Float.greatestFiniteMagnitude
    for (idx, value) in distCPU.enumerated() {
        if value < bestVal {
            bestVal = value
            bestIdx = idx
        }
    }
    return bestIdx
}

public func mutateParams(
    base: KernelParams,
    ranges: KernelParamRanges,
    config: IMGEPMutationConfig,
    rng: inout SeededRandomNumberGenerator
) -> KernelParams {
    let r = mutateVector(base.r, range: ranges.r, config: config, rng: &rng)
    let b = mutateMatrix(base.b, range: ranges.b, config: config, rng: &rng)
    let w = mutateMatrix(base.w, range: ranges.w, config: config, rng: &rng)
    let a = mutateMatrix(base.a, range: ranges.a, config: config, rng: &rng)
    let m = mutateVector(base.m, range: ranges.m, config: config, rng: &rng)
    let s = mutateVector(base.s, range: ranges.s, config: config, rng: &rng)
    let h = mutateVector(base.h, range: ranges.h, config: config, rng: &rng)
    let R = mutateScalar(base.R, range: ranges.R, config: config, rng: &rng)
    return KernelParams(r: r, b: b, w: w, a: a, m: m, s: s, h: h, R: R)
}

private func featureValue(metrics: SimulationMetrics, feature: String) -> Float? {
    switch feature {
    case "mass_mean": return metrics.massMean
    case "mass_std": return metrics.massStd
    case "mass_min": return metrics.massMin
    case "mass_max": return metrics.massMax
    case "occupancy_mean": return metrics.occupancyMean
    case "variance_mean": return metrics.varianceMean
    case "energy_mean": return metrics.energyMean
    case "speed_mean": return metrics.speedMean
    case "path_length": return metrics.pathLength
    case "displacement": return metrics.displacement
    case "gyration": return metrics.gyration
    case "center_velocity": return metrics.centerVelocity
    case "complexity_mean": return metrics.complexityMean
    case "complexity_target_score": return metrics.complexityTargetScore
    case "hu1": return metrics.hu1
    case "hu2": return metrics.hu2
    case "hu3": return metrics.hu3
    case "hu4": return metrics.hu4
    case "hu5": return metrics.hu5
    case "hu6": return metrics.hu6
    case "hu7": return metrics.hu7
    case "flusser1": return metrics.flusser1
    case "flusser2": return metrics.flusser2
    case "flusser3": return metrics.flusser3
    case "flusser4": return metrics.flusser4
    case "moment_mass": return metrics.momentMass
    case "moment_volume": return metrics.momentVolume
    case "moment_density": return metrics.momentDensity
    case "moment_anisotropy": return metrics.momentAnisotropy
    case "largest_component_anisotropy": return metrics.largestComponentAnisotropy
    case "activity_eac_mean": return metrics.activityEacMean
    case "activity_ean_mean": return metrics.activityEanMean
    case "activity_diversity_mean": return metrics.activityDiversityMean
    case "activity_species_mean": return metrics.activitySpeciesMean
    default: return nil
    }
}

private func featureValue(result: SimulationResultData, feature: String) -> Float? {
    if let value = featureValue(metrics: result.metrics, feature: feature) {
        return value
    }

    guard let descriptorBundle = result.descriptorBundle else {
        return nil
    }

    let terminal = descriptorBundle.terminal
    let trajectory = descriptorBundle.trajectory
    let symmetry = terminal.angularSymmetry

    switch feature {
    case "symmetry_dominant_order":
        guard let order = symmetry.dominantOrder else { return nil }
        return Float(order)
    case "symmetry_dominant_amplitude":
        return symmetry.dominantAmplitude
    case "symmetry_entropy":
        return symmetry.normalizedEntropy
    case let harmonic where harmonic.hasPrefix("symmetry_harmonic_"):
        guard let order = Int(harmonic.dropFirst("symmetry_harmonic_".count)),
              order >= 1,
              order <= symmetry.harmonics.count else {
            return nil
        }
        return symmetry.harmonics[order - 1]
    case "terminal_final_mass":
        return terminal.finalMass
    case "terminal_final_occupancy":
        return terminal.finalOccupancy
    case "terminal_final_gyration":
        return terminal.finalGyration
    case "terminal_component_count":
        return terminal.componentCount
    case "terminal_largest_component_fraction":
        return terminal.largestComponentFraction
    case "terminal_largest_component_anisotropy":
        return terminal.largestComponentAnisotropy
    case "terminal_window_mass_std":
        return terminal.windowMassStd
    case "terminal_window_occupancy_std":
        return terminal.windowOccupancyStd
    case "terminal_window_gyration_std":
        return terminal.windowGyrationStd
    case "trajectory_path_tortuosity":
        return trajectory?.pathTortuosity
    case "trajectory_movement_efficiency":
        return trajectory?.movementEfficiency
    case "trajectory_heading_circular_variance":
        return trajectory?.headingCircularVariance
    case "trajectory_accumulated_turn_abs":
        return trajectory?.accumulatedTurnAbs
    case "trajectory_component_series_mean":
        return trajectory?.componentSeriesMean
    case "trajectory_component_series_std":
        return trajectory?.componentSeriesStd
    case "trajectory_component_series_max":
        guard let value = trajectory?.componentSeriesMax else { return nil }
        return Float(value)
    default:
        return nil
    }
}

private func mutateScalar(
    _ value: Float,
    range: [Float],
    config: IMGEPMutationConfig,
    rng: inout SeededRandomNumberGenerator
) -> Float {
    let noise = gaussianSample(std: config.std, rng: &rng)
    var out = value + noise
    if config.clip, range.count == 2 {
        out = max(range[0], min(range[1], out))
    }
    return out
}

private func mutateVector(
    _ values: [Float],
    range: [Float],
    config: IMGEPMutationConfig,
    rng: inout SeededRandomNumberGenerator
) -> [Float] {
    return values.map { value in
        mutateScalar(value, range: range, config: config, rng: &rng)
    }
}

private func mutateMatrix(
    _ values: [[Float]],
    range: [Float],
    config: IMGEPMutationConfig,
    rng: inout SeededRandomNumberGenerator
) -> [[Float]] {
    return values.map { row in
        row.map { value in
            mutateScalar(value, range: range, config: config, rng: &rng)
        }
    }
}

